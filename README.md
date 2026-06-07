# AI Key Checker

多平台 AI API Key 余额检测工具，支持 **Streamlit 网页仪表盘** 与 **命令行批量检测**。

## 功能

- **网页仪表盘** — 基于 Streamlit 的可视化界面，输入各平台 Key 即可自动检测余额与有效性
- **多平台支持** — DeepSeek / SiliconFlow / OpenRouter / 智谱AI / Kimi / OpenAI / 阿里通义千问 / Gemini
- **批量检测** — 同时检测多个平台的 API Key，结果分类展示
- **本地存储** — Key 保存在本地 `api-keys.json`，不会上传至任何第三方

## 项目结构

```
ai-key-checker/
├── dashboard.py                 # Streamlit 网页仪表盘
├── deepseek-checker.py          # DeepSeek 检测脚本
├── siliconflow-checker.py       # SiliconFlow 检测脚本
├── openrouter-checker.py        # OpenRouter 检测脚本
├── zhipu-checker.py             # 智谱AI 检测脚本
├── kimi-checker.py              # Kimi (Moonshot) 检测脚本
├── openai-checker.py            # OpenAI 检测脚本
├── qwen-checker.py              # 阿里通义千问检测脚本
├── gemini/                      # Gemini 检测工具集
│   ├── check-gemini.py          # 基础检测（List Models）
│   ├── deep-check.py            # 深度检测（generateContent）
│   └── model-check.py           # 模型方法可用性检测
├── api-key-checker-app.py       # 命令行聚合入口
├── Start Dashboard.command      # macOS 一键启动
└── start-ui.sh                  # Linux/Mac 启动脚本
```

## 快速开始

### 依赖

```bash
pip install requests streamlit
```

### 启动仪表盘

```bash
streamlit run dashboard.py
```

浏览器访问 `http://localhost:8501`，在侧边栏输入各平台 Key 即可。

### 命令行检测

```bash
# 命令行交互模式
python3 api-key-checker-app.py

# 或直接使用单个检测脚本
python3 deepseek-checker.py <key或文件>
python3 openrouter-checker.py <key或文件> --report
```

## 平台支持

| 平台 | 检测内容 | 方式 |
|------|---------|------|
| DeepSeek | 余额查询 | GET /user/balance |
| SiliconFlow | 余额查询 | GET /v1/user/info |
| OpenRouter | 信用额度 | GET /api/v1/credits |
| 智谱AI | 余额验证 | GET /api/llm/balance |
| Kimi Moonshot | 余额查询 | GET /v1/users/me/balance |
| OpenAI | Key 有效性 | GET /dashboard/billing/credit_grants |
| 阿里通义千问 | 有效性验证 | POST /chat/completions |
| Gemini | 模型列表 + 实际调用 | List Models / generateContent |

> OpenAI 余额查询需要浏览器 session key，普通 API Key 仅能验证有效性。

## 安全

- API Key 仅本地存储，不上传任何第三方服务
- 仅用于调用各平台官方 API 进行余额/有效性检测
- 请勿将 `api-keys.json` 提交到公开仓库

## 外部链接

- [Linux DO 论坛](https://linux.do/)
- [博客文章](https://jibukeshi.dpdns.org/posts/project/ai-api-key-checker.html)
