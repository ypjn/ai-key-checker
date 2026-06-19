# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI API Key Checker — 多平台 AI API Key 余额批量检测工具。支持 Streamlit 网页仪表盘和命令行两种模式。

## Commands

```bash
# 启动 Streamlit 仪表盘（dashboard.py — 侧边栏配置版）
python3 -m streamlit run api-key-checker/dashboard.py --server.port 8501

# 启动 Streamlit 仪表盘（api-key-checker-app.py — 批量输入版）
python3 -m streamlit run api-key-checker/api-key-checker-app.py --server.port 8501

# 命令行检测（各平台独立的 checker 脚本）
python3 api-key-checker/deepseek-checker.py sk-your-key-here
python3 api-key-checker/deepseek-checker.py keys.txt --report

# 通用参数
python3 api-key-checker/xxx-checker.py <key或文件> [--report [文件]] [--sep 分隔符]
```

项目依赖仅 `requests` 和 `streamlit`，无构建步骤。没有测试框架。

## macOS 启动脚本

项目附带两个 `Start Dashboard.command` 文件（macOS 双击启动），以及 `start-ui.sh`（终端启动）：

- **根目录** `Start Dashboard.command` — 定位到 `api-key-checker/` 目录后启动 `dashboard.py`
- **`api-key-checker/Start Dashboard.command`** — 在当前目录启动 `dashboard.py`

**重要**：新增 Streamlit 入口文件或修改 Streamlit 启动参数时，必须同步更新这三个启动脚本（端口号、文件名、Python 命令等）。

## Architecture

### 两种 UI 入口对比

| 文件 | 模式 | 特点 |
|------|------|------|
| `dashboard.py` | 侧边栏配置 | 每个平台一个输入框，Key 持久化到 `api-keys.json`，自动检测 |
| `api-key-checker-app.py` | 批量输入 | 文本框粘贴多个 Key + 文件上传，多平台并行批量检测，导出报告 |

### 脚本架构

每个平台对应一个独立 checker 脚本（如 `deepseek-checker.py`），遵循相同模式：

1. `split_keys()` — 将输入按分隔符拆分为 Key 列表（支持 `, ; / | &` 和空白）
2. `collect_keys()` — 支持文件路径和直接 Key 混合输入
3. `fetch_with_retry()` — requests.Session + 指数退避重试
4. `check_key()` — 调用 API → 解析 JSON → 返回 `(status, detail)` 元组
5. `main()` — argparse CLI → 遍历检测 → 分类统计 → 可导出报告

### 状态分类

所有脚本使用同一套四分类状态：
- `positive` — ✅ 余额大于 0
- `zero` — ⭕ 余额为 0（或 Key 有效但无法查余额）
- `invalid` — ❌ 认证失败 / Key 无效
- `fail` — ⚠️ 网络错误

### Gemini 子目录

`gemini/` 下三个脚本有特殊处理：
- `check-gemini.py` — List Models 基础检测，支持多线程、本地缓存、原子写入
- `deep-check.py` — 调用 `generateContent` 做深度检测
- `model-check.py` — 逐方法测试模型可用性

### 余额查询 vs 有效性验证

部分平台无公开余额接口，需回落方案：
- 智谱AI：余额接口权限受限 → 调用 chat completions 验证 Key 可用性
- 阿里通义千问：无余额接口 → POST chat/completions 验证
- OpenAI：`credit_grants` 需 session key → 回落 `GET /v1/models` 验证
