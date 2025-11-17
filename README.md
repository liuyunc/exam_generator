# JSON 分片考试题生成器（DeepSeek + GA 对）

## 项目概览（Wiki 速览）
- **用途**：上传/传入 JSON 文本分片，调用 DeepSeek（经 GPUStack）批量生成包含来源引用的考试题（GA 对），并支持在线编辑与 DOCX 导出。
- **主体流程**：
  1. 前端 `static/index.html` 上传分片并配置参数。
  2. FastAPI 读取分片 → 按索引切片 → 逐分片调用 DeepSeek → 汇总 GA 对。
  3. 前端表格可修改题目、答案、难度与引用信息。
  4. `/export-docx` 将编辑后的 GA 对导出为 Word 文档。
- **主要模块**：
  - `main.py`：FastAPI API、分片处理、DeepSeek 调用与 JSON 解析。
  - `prompts.py`：默认的 GA 系统提示词与用户提示构造。
  - `docx_utils.py`：将 GA 对渲染为含题目/答案/引用的 DOCX。
  - `static/index.html`：上传、进度条、在线编辑与导出前端页面。
- **输入格式**：顶层为 `[{"name"|"fileName"|"title"?, "content"|"text"|"chunk"}]`，或包装在 `{ "chunks": [...] }` 中；索引用逗号分隔（如 `0,1,2`）。
- **输出格式**：模型需返回 `{ "ga_pairs": [{ id, question, ga_answer, difficulty, source_excerpt, source_locator, comment }] }`。

## 环境与运行
1. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```
2. 环境变量
   - `GPUSTACK_API_KEY`：GPUStack/DeepSeek API Key（必填）。
   - `GPUSTACK_BASE_URL`：API Base，默认为 `http://10.20.40.101/v1`，可直接填 DeepSeek 官方或代理地址（支持带 `/api/deepseek/v1` 路径）。会自动去掉首尾空格和末尾 `/`，避免因隐形空格导致连接失败。
   - `DEEPSEEK_MODEL_NAME`：模型名，默认 `deepseek-r1`，会自动 trim 首尾空格。
   - `GPUSTACK_TIMEOUT`：单次模型调用超时（秒），默认 `120`。
   - `GPUSTACK_MAX_RETRIES`：连接/超时重试次数，默认 `2`。
3. 启动服务
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
4. 使用
   - 浏览器访问 `http://localhost:8000/static` 进入页面。
   - 上传 JSON 分片、填写分片索引与题量（默认 20），可选自定义 System Prompt。
   - 生成后的 GA 对可在表格中直接编辑，再点击“导出 DOCX”。

## API 说明
- `GET /`：返回首页 HTML。
- `GET /api/deepseek-health`：检测 DeepSeek/GPUStack 连接与鉴权是否可用，返回 `ok` 和原因提示。
- `POST /api/generate-ga-from-file`：表单上传 JSON 分片并生成 GA 对。
  - 字段：`file`（上传文件）、`chunk_indices`（如 `0,1,2`）、`num_questions`、`system_prompt`。
- `POST /api/generate-ga`：纯 JSON 请求版。
  - Body：`{ "chunks": [...], "chunk_indices": [int], "num_questions": 20, "system_prompt": "..." }`。
- `POST /export-docx`：将前端编辑后的 GA 对导出为 DOCX，Body 见 `ExportDocxRequest`。
- 所有生成接口均会返回 `errors` 数组（若存在），便于前端直观提示 DeepSeek 调用失败的分片或异常原因。

## DeepSeek/GPUStack 调用与超时处理
- 单次调用默认 **120s** 超时，可通过 `GPUSTACK_TIMEOUT` 调整。
- 连接或超时错误会按 `GPUSTACK_MAX_RETRIES` 自动重试，并记录后台日志，避免前端“无声”失败。
- 仍失败时返回空列表，前端不会 500，可在日志中查看具体异常。

## 开发提示
- JSON 解析使用 `extract_json_block_from_content` 做括号匹配，能从模型的非纯 JSON 输出中提取合法块。
- 对每个分片生成的 GA 对，会自动补充 `source_locator`，格式如 `（自动定位：分片2，xxx）`，避免引用缺失。
- DOCX 导出：第一页仅题目，翻页后附答案/难度/引用/说明，默认标题可在前端输入框覆盖。

## 资源
- `text-chunks-export-2025-11-16.json`：示例分片数据，可直接在前端上传体验流程。
- 若需调整默认提示词，请编辑 `prompts.py` 中的 `GA_SYSTEM_PROMPT` 与 `build_ga_user_prompt`。
