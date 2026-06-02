## 代码安全修复指南

本文档说明最近对项目进行的安全性改进。

### 🔐 安全修复汇总

#### 1. **敏感信息保护** ✅
- **问题**: 硬编码的 API 密钥和内网 IP 地址
- **修复**:
  - 移除所有默认值，强制通过环境变量设置
  - 初始化失败时抛出异常，防止使用占位符
  - 添加 `.env.example` 模板作为配置参考

**使用方法**:
```bash
# 1. 复制配置模板
cp .env.example .env

# 2. 编辑 .env，填入真实的 API 密钥和 URL
GPUSTACK_API_KEY=sk-xxx...
GPUSTACK_BASE_URL=https://your-api-url/v1

# 3. 启动应用（自动加载 .env）
python -m uvicorn main:app --reload
```

#### 2. **输入验证加强** ✅
- **问题**: 文件上传、JSON 解析、API 参数无充分验证
- **修复**:
  - 文件大小限制：**10MB**
  - JSON 大小限制：**5MB**
  - 题目数量限制：**1-100**
  - MIME 类型检查：仅允许 `application/json`
  - Pydantic 字段验证：长度、范围、类型

**示例**:
```python
class GARequest(BaseModel):
    num_questions: conint(ge=1, le=100) = 20  # 范围限制
    system_prompt: Optional[constr(max_length=5000)] = None  # 长度限制
```

#### 3. **JSON 解析安全** ✅
- **问题**: 从模型返回内容中提取 JSON，可能被注入
- **修复**:
  - 内容大小检查（10倍 MAX_JSON_SIZE）
  - JSON 块大小限制（5MB）
  - 结构验证：检查 `ga_pairs` 字段存在和类型
  - 异常处理：所有 JSON 错误都被捕获

**代码示例**:
```python
def extract_json_block_from_content(content: str) -> dict:
    # 大小检查
    if len(content) > 10 * MAX_JSON_SIZE:
        raise ValueError("内容过大")
    
    # ... 括号匹配 ...
    
    # 结构验证
    if not isinstance(data, dict) or "ga_pairs" not in data:
        raise ValueError("JSON 结构无效")
    if not isinstance(data["ga_pairs"], list):
        raise ValueError("ga_pairs 必须是列表")
    
    return data
```

#### 4. **HTTP 安全头** ✅
- **问题**: 缺少安全头，易受 XSS、点击劫持攻击
- **修复**: 添加安全头中间件
  - `X-Content-Type-Options: nosniff` - 防止 MIME 嗅探
  - `X-Frame-Options: DENY` - 防止点击劫持
  - `X-XSS-Protection: 1; mode=block` - 浏览器 XSS 过滤
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` - 强制 HTTPS

#### 5. **CORS 配置** ✅
- **问题**: 默认允许所有 CORS 请求
- **修复**:
  - 通过环境变量配置允许的来源
  - 默认只允许 `localhost:3000` 和 `localhost:8000`
  - 生产环境应配置真实的域名

**配置方法**:
```bash
# .env 文件
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

#### 6. **API 限制** ✅
- **问题**: 超时和重试次数无限制
- **修复**: 添加安全范围
  - 超时：**10-600 秒**（默认 120s）
  - 重试：**1-5 次**（默认 2 次）
  - 超出范围会自动调整并记录警告

#### 7. **错误处理** ✅
- **问题**: 向用户暴露详细的异常信息
- **修复**:
  - 用户收到通用错误信息（如 "处理失败，请稍后重试"）
  - 详细错误信息仅记录在服务器日志
  - 日志使用 Python `logging` 模块

**示例**:
```python
except Exception as e:
    logger.exception("处理异常")  # 服务器日志记录完整信息
    raise HTTPException(status_code=500, detail="处理失败，请稍后重试")  # 用户看到通用消息
```

#### 8. **文件操作安全** ✅
- **问题**: 静态文件路径无验证，可能路径遍历
- **修复**: 使用 `Path.resolve()` 验证路径

```python
ALLOWED_INDEX_FILE = (Path("static") / "index.html").resolve()

# 检查文件是否存在
if not ALLOWED_INDEX_FILE.exists():
    return HTMLResponse("<h1>页面加载失败</h1>", status_code=500)
```

---

### 📋 部署检查清单

部署前请确认以下事项：

- [ ] 复制 `.env.example` 为 `.env`
- [ ] 设置真实的 `GPUSTACK_API_KEY`
- [ ] 设置正确的 `GPUSTACK_BASE_URL`
- [ ] 配置生产环境的 `CORS_ORIGINS`
- [ ] 使用 HTTPS 部署（推荐）
- [ ] 配置防火墙规则，限制 API 访问
- [ ] 定期查看日志，监控异常请求
- [ ] 更新依赖包到最新安全版本

### 🔧 安全常量一览

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_FILE_SIZE` | 10 MB | 上传文件最大大小 |
| `MAX_JSON_SIZE` | 5 MB | JSON 块最大大小 |
| `MAX_QUESTIONS` | 100 | 单次生成最多题目数 |
| `MIN_TIMEOUT` | 10 s | 最小 API 超时 |
| `MAX_TIMEOUT` | 600 s | 最大 API 超时 |
| `MIN_RETRIES` | 1 | 最小重试次数 |
| `MAX_RETRIES` | 5 | 最大重试次数 |

### 🚀 启动应用

```bash
# 安装依赖
pip install -r requirements.txt

# 加载环境变量并启动
# 方案 1: 使用 uvicorn（自动加载 .env）
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 方案 2: 使用 Docker
docker build -t exam-generator .
docker run --env-file .env -p 8000:8000 exam-generator
```

### 📝 日志示例

```
[config] base_url=https://api.deepseek.com/v1, model=deepseek-r1, timeout=120s, retries=2
[INFO] 环境变量加载成功
[WARNING] GPUSTACK_TIMEOUT 已调整到 [10, 600] 范围
[ERROR] 必须设置环境变量 GPUSTACK_API_KEY
```

---

### 📚 更新依赖

本次安全修复新增了以下依赖：

```
python-dotenv          # 环境变量管理
```

更新 `requirements.txt`:
```bash
pip install -r requirements.txt
```

---

### ❓ 常见问题

**Q: 为什么启动时报错"必须设置环境变量 GPUSTACK_API_KEY"？**

A: 应用强制要求环境变量设置。请：
1. 复制 `.env.example` 为 `.env`
2. 编辑 `.env` 填入真实值
3. 重新启动应用

**Q: 上传文件时提示"文件超过限制"？**

A: 文件大小限制为 10MB。如需调整，修改 `main.py` 中的 `MAX_FILE_SIZE` 常量。

**Q: 如何在生产环境配置 CORS？**

A: 设置环境变量 `CORS_ORIGINS`：
```bash
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

**Q: 为什么看不到具体的错误信息？**

A: 这是安全设计。详细错误只在服务器日志中。检查应用日志：
```bash
# 查看最近的日志
tail -f app.log
```

---

### 📞 安全问题报告

如发现新的安全问题，请立即提交 Issue 或私下联系维护者。

---

**最后更新**: 2026-06-02  
**修复版本**: 安全加固版 v1.0
