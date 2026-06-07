# AI Key Checker

多平台 AI API Key 余额检测工具，支持 **Streamlit 网页仪表盘** 与 **命令行批量检测**。

## 功能

- **网页仪表盘** — 基于 Streamlit 的可视化界面，在侧边栏输入各平台 Key 即可自动检测
- **多平台支持** — DeepSeek / SiliconFlow / OpenRouter / 智谱AI / Kimi / OpenAI / 阿里通义千问 / Gemini
- **批量检测** — 支持同时检测多个 Key，自动去重，结果分类展示
- **结果输出** — 终端彩色输出 + 可选报告文件
- **错误重试** — 网络错误自动重试
- **本地存储** — Key 仅存在本地 `api-keys.json`，不上传第三方

## 快速开始

### 依赖

```bash
pip install requests streamlit
```

### 启动仪表盘

```bash
streamlit run dashboard.py
```

浏览器访问 `http://localhost:8501`，在左侧边栏输入各平台的 API Key，点击「保存并检测」即可。

### 命令行交互模式

```bash
python3 api-key-checker-app.py
```

按提示粘贴各平台的 API Key 即可检测。

## 项目结构

```
ai-key-checker/
├── dashboard.py                 # Streamlit 网页仪表盘
├── api-key-checker-app.py       # 命令行聚合入口
├── deepseek-checker.py          # DeepSeek 检测脚本
├── siliconflow-checker.py       # SiliconFlow 检测脚本
├── openrouter-checker.py        # OpenRouter 检测脚本
├── zhipu-checker.py             # 智谱AI 检测脚本
├── kimi-checker.py              # Kimi (Moonshot) 检测脚本
├── openai-checker.py            # OpenAI 检测脚本
├── qwen-checker.py              # 阿里通义千问检测脚本
├── gemini/
│   ├── check-gemini.py          # 基础检测（List Models）
│   ├── deep-check.py            # 深度检测（generateContent）
│   └── model-check.py           # 模型方法可用性检测
├── Start Dashboard.command      # macOS 一键启动仪表盘
└── start-ui.sh                  # Linux/macOS 启动脚本
```

## 命令行检测

每个平台的检测脚本用法一致，支持直接传入 Key 或从文件读取。

### 基本用法

```bash
# 检测单个 Key
python3 deepseek-checker.py sk-xxxx

# 检测多个 Key
python3 siliconflow-checker.py key1 key2,key3;key4

# 从文件读取 Key 检测
python3 openrouter-checker.py keys.txt

# 混合文件与直接输入
python3 deepseek-checker.py keys.txt key1

# 输出报告到文件
python3 openrouter-checker.py key1 --report
python3 openrouter-checker.py keys.txt --report report.txt
```

### 通用参数

| 参数 | 说明 |
|------|------|
| `<key或文件>` | API Key 或包含 Key 的文件路径，可混合输入多个 |
| `--report [文件]` | 输出报告到文件，不指定文件名则自动生成 |
| `--sep 分隔符` | 报告文件中 Key 的分隔符，默认英文逗号 |
| `--threads 线程数` | Gemini 并发线程数，默认 10 |
| `--retry 次数` | 网络错误重试次数，默认 3 |
| `--timeout 秒数` | 请求超时秒数 |
| `--force` | Gemini 忽略缓存强制重测 |
| `--cache` | Gemini 乐观模式，命中缓存直接跳过 |

### 各平台检测脚本

| 脚本 | 检测方式 | 说明 |
|------|---------|------|
| `deepseek-checker.py` | GET /user/balance | 查询余额 |
| `siliconflow-checker.py` | GET /v1/user/info | 查询总余额 |
| `openrouter-checker.py` | GET /api/v1/credits | 查询信用额度 |
| `zhipu-checker.py` | GET /api/llm/balance | 查询余额（备用 POST 验证） |
| `kimi-checker.py` | GET /v1/users/me/balance | 查询可用余额 |
| `openai-checker.py` | GET /dashboard/billing/credit_grants | 验证 Key 有效性 |
| `qwen-checker.py` | POST /chat/completions | 验证 Key 有效性 |
| `check-gemini.py` | List Models | 基础检测 |
| `deep-check.py` | generateContent | 深度检测 |
| `model-check.py` | 逐方法测试 | 模型方法可用性 |

> OpenAI 余额查询需要浏览器 session key，普通 API Key 仅能验证有效性。

### Gemini 检测

Gemini 脚本额外支持多线程并发、本地缓存、深度检测等功能。

```bash
# 基础检测
python3 gemini/check-gemini.py keys.txt

# 深度检测（实际调用 generateContent）
python3 gemini/deep-check.py keys.txt

# 模型方法可用性检测
python3 gemini/model-check.py <key>
```

### 状态分类

| 状态 | 说明 |
|------|------|
| ✅ 可用 / 余额 > 0 | API Key 有效且有余额 |
| ⭕ 余额为 0 | API Key 有效但余额为 0 |
| ❌ 不可用 | API Key 无效 |
| ⚠️ 检测失败 | 网络错误 |

## 安全

- API Key 仅存储在本地 `api-keys.json`，请勿提交到公开仓库
- 仅用于调用各平台官方 API 进行检测
- 不会将 Key 上传至任何第三方服务

## 外部链接

- [Linux DO 论坛](https://linux.do/)
- [博客文章](https://jibukeshi.dpdns.org/posts/project/ai-api-key-checker.html)
