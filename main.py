# main.py

import json
import os
from io import BytesIO
from typing import List, Optional

from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
)

from prompts import GA_SYSTEM_PROMPT, build_ga_user_prompt
from docx_utils import build_docx_from_ga

# ========= 配置：gpustuck DeepSeek =========

GPUSTACK_API_KEY = os.getenv("GPUSTACK_API_KEY", "YOUR_API_KEY")
GPUSTACK_BASE_URL = os.getenv("GPUSTACK_BASE_URL", "http://10.20.40.101/v1")
MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-r1")
GPUSTACK_TIMEOUT = float(os.getenv("GPUSTACK_TIMEOUT", "120"))
GPUSTACK_MAX_RETRIES = max(int(os.getenv("GPUSTACK_MAX_RETRIES", "2")), 1)

client = OpenAI(
    api_key=GPUSTACK_API_KEY,
    base_url=GPUSTACK_BASE_URL,
)

# ========= FastAPI 应用 =========

app = FastAPI(title="JSON分片考试题生成器（DeepSeek + GA对）")

# 静态文件目录：static/index.html
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面"""
    index_path = os.path.join("static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)


# ========= 数据模型 =========

class GAPair(BaseModel):
    id: Optional[str] = None
    question: str
    ga_answer: str
    difficulty: Optional[str] = ""
    source_excerpt: Optional[str] = ""
    source_locator: Optional[str] = ""
    comment: Optional[str] = ""


class ExportDocxRequest(BaseModel):
    title: str
    ga_pairs: List[GAPair]


class GARequest(BaseModel):
    """纯 API 调用版本（非网页上传）"""
    chunks: List[dict]
    chunk_indices: List[int]
    num_questions: int = 20
    system_prompt: Optional[str] = None


# ========= 工具函数 =========

def extract_chunk_items(chunks: list, indices: list):
    """
    根据索引只抽取需要的分片，返回：
    [
      {
        "index": i,
        "title": "xxx",
        "text": "这一分片的正文"
      },
      ...
    ]
    """
    items = []
    for i in indices:
        if i < 0 or i >= len(chunks):
            continue
        item = chunks[i]
        text = (
            item.get("content")
            or item.get("text")
            or item.get("chunk")
            or ""
        )
        title = item.get("name") or item.get("fileName") or f"chunk-{i}"
        items.append({
            "index": i,
            "title": title,
            "text": text.strip()
        })
    return items


def extract_json_block_from_content(content: str) -> dict:
    """
    从大模型返回的 content 文本中，尽量稳健地抽取出一个 JSON 对象。
    优先寻找以 {"ga_pairs" 开头的 JSON；如果没有，就从第一个 { 开始做括号匹配。
    """
    if not content:
        raise ValueError("模型返回内容为空，无法解析 JSON")

    # 1) 优先找 {"ga_pairs"
    start = content.find('{"ga_pairs"')
    if start == -1:
        # 退而求其次：找第一个 {
        start = content.find("{")
    if start == -1:
        raise ValueError("未在模型返回中找到 '{'，可能没有输出 JSON：\n" + content[:200])

    in_str = False
    escape = False
    depth = 0
    end = None

    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                # 遇到第一个 { 时 depth 从 0 -> 1
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    if end is None:
        # 没闭合，尽量取到结尾
        end = len(content)

    json_str = content[start:end].strip()
    if not json_str:
        raise ValueError("提取到的 JSON 字符串为空。原始内容前 200 字符：\n" + content[:200])

    return json.loads(json_str)


def call_deepseek_ga_single_chunk(
    text_for_model: str,
    num_questions: int,
    system_prompt: Optional[str] = None,
):
    """针对单个分片调用 DeepSeek 生成 GA 对（带更稳健的 JSON 解析）"""
    sys_prompt = system_prompt.strip() if system_prompt else GA_SYSTEM_PROMPT
    user_prompt = build_ga_user_prompt(text_for_model, num_questions)

    resp = None
    last_error = None
    for attempt in range(1, GPUSTACK_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                timeout=GPUSTACK_TIMEOUT,
            )
            break
        except (APITimeoutError, APIConnectionError) as e:
            last_error = f"调用超时/连接异常：{repr(e)}"
            print(
                f"[DeepSeek] 第 {attempt}/{GPUSTACK_MAX_RETRIES} 次调用超时/连接异常：{repr(e)}；",
                f" 超时设置 {GPUSTACK_TIMEOUT}s"
            )
            if attempt == GPUSTACK_MAX_RETRIES:
                return [], last_error
            time.sleep(min(2 * attempt, 6))
        except APIError as e:
            last_error = f"服务器返回错误：{repr(e)}"
            print(f"[DeepSeek] 服务器返回错误：{repr(e)}")
            return [], last_error
        except Exception as e:
            last_error = f"API调用失败：{repr(e)}"
            print(f"API调用失败：{repr(e)}")
            return [], last_error

    if resp is None:
        return [], last_error or "调用失败，未返回响应"

    content = resp.choices[0].message.content or ""

    try:
        # 先尝试直接当 JSON 解析
        data = json.loads(content)
    except json.JSONDecodeError:
        # 如果失败，则用括号匹配从 content 中提取 JSON 块
        try:
            data = extract_json_block_from_content(content)
        except Exception as e:
            # 为了调试方便，把 content 打到后端日志里
            print("==== 模型原始返回（前 500 字符）====")
            print(content[:500])
            print("==== JSON 解析失败原因 ====")
            print(repr(e))
            # 不中断整个流程，返回空列表，让前端至少不 500
            return [], f"模型返回内容无法解析为 JSON：{repr(e)}"

    ga_pairs = data.get("ga_pairs", [])
    # 确保是列表
    if not isinstance(ga_pairs, list):
        print("模型返回中 ga_pairs 不是列表，完整 data：", data)
        return [], "模型返回中 ga_pairs 不是列表"
    return ga_pairs, None


def call_deepseek_ga_for_chunks(
    chunk_items: list,
    total_questions: int,
    system_prompt: Optional[str] = None,
):
    """
    按分片分别调用 DeepSeek，再汇总 GA 对：
    - total_questions：总题量
    - 各分片按数量平均分配
    """
    if not chunk_items or total_questions <= 0:
        return [], ["未提供分片或题目数量小于等于 0"]

    n_chunks = len(chunk_items)
    base = total_questions // n_chunks
    rem = total_questions % n_chunks

    all_pairs = []
    errors: List[str] = []
    for idx, item in enumerate(chunk_items):
        n_q = base + (1 if idx < rem else 0)
        if n_q <= 0:
            continue

        print(f"正在处理分片{item['index']}（{item['title']}），预计生成{n_q}道题目...")
        
        header = f"[分片{item['index']}：{item['title']}]\n"
        text_for_model = header + item["text"]

        ga_pairs, error_msg = call_deepseek_ga_single_chunk(
            text_for_model=text_for_model,
            num_questions=n_q,
            system_prompt=system_prompt,
        )

        if error_msg:
            errors.append(
                f"分片{item['index']}（{item['title']}）调用 DeepSeek 失败：{error_msg}"
            )
            print(errors[-1])
            continue

        print(f"分片{item['index']}处理完成，实际生成{len(ga_pairs)}道题目")

        # 给每个 GA 对附加分片定位（兜底）
        for p in ga_pairs:
            locator = (p.get("source_locator") or "").strip()
            extra = f"（自动定位：分片{item['index']}，{item['title']}）"
            if locator:
                locator = locator + "；" + extra
            else:
                locator = extra
            p["source_locator"] = locator
        all_pairs.extend(ga_pairs)
    
    print(f"所有分片处理完成，共生成{len(all_pairs)}道题目")

    return all_pairs, errors


# ========= API：网页调用 =========

@app.post("/api/generate-ga-from-file")
async def generate_ga_from_file(
    file: UploadFile,
    chunk_indices: str = Form(
        "",
        description="分片索引，如：0,1,2；留空则自动使用全部分片",
    ),
    num_questions: int = Form(20),
    system_prompt: str = Form("", description="自定义 system prompt，可留空使用默认"),
):
    """
    网页表单接口：
    - 上传 JSON 分片文件
    - 指定要使用的分片索引（逗号分隔）
    - 指定题目总数量
    - 可选：自定义提示词
    """
    print("开始处理文件上传...")
    raw = await file.read()
    chunks = json.loads(raw)
    print("文件解析完成")

    # 支持：顶层是 {'chunks': [...]} 或直接是 list
    if isinstance(chunks, dict) and "chunks" in chunks:
        chunks_list = chunks["chunks"]
    else:
        chunks_list = chunks

    # 解析索引
    indices = []
    for part in chunk_indices.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            indices.append(idx)
        except ValueError:
            continue

    if not indices:
        indices = list(range(len(chunks_list)))
        print(
            f"未显式指定分片索引，自动使用全部 {len(chunks_list)} 个分片: {indices}"
        )
    else:
        print(f"解析到 {len(indices)} 个分片索引: {indices}")
    chunk_items = extract_chunk_items(chunks_list, indices)
    print(f"提取到 {len(chunk_items)} 个有效分片")
    
    ga_pairs, errors = call_deepseek_ga_for_chunks(
        chunk_items,
        total_questions=num_questions,
        system_prompt=system_prompt if system_prompt.strip() else None,
    )

    print(f"生成完成，共生成 {len(ga_pairs)} 道题目；错误 {len(errors)} 条")
    return {"ga_pairs": ga_pairs, "errors": errors}


@app.post("/export-docx")
async def export_docx(req: ExportDocxRequest):
    """接收前端编辑好的 GA 对，生成 DOCX 下载"""
    ga_pairs_dicts = [p.dict() for p in req.ga_pairs]
    doc = build_docx_from_ga(ga_pairs_dicts, title=req.title)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    filename = "exam_ga_pairs.docx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


# ========= API：纯后端调用版（可选） =========

@app.post("/api/generate-ga")
async def api_generate_ga(req: GARequest):
    """
    纯 JSON API（不走上传文件），方便后续和 EasyDataset pipeline 联动
    """
    chunk_items = extract_chunk_items(req.chunks, req.chunk_indices)
    ga_pairs, errors = call_deepseek_ga_for_chunks(
        chunk_items,
        total_questions=req.num_questions,
        system_prompt=req.system_prompt,
    )
    return {"ga_pairs": ga_pairs, "errors": errors}
