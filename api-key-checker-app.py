#!/usr/bin/env python3
"""
API Key Checker - 多平台 API Key 批量检测工具 (Streamlit GUI)
"""
import json
import os
import re
import sys
import time
import tempfile
from datetime import datetime
from io import StringIO

import requests
import streamlit as st

# ──────────────────────────────────────────────
# 平台配置
# ──────────────────────────────────────────────
PLATFORMS = {
    "DeepSeek": {
        "api_url": "https://api.deepseek.com/user/balance",
        "prefix": "deepseek",
        "color": "#4F46E5",
        "parse": lambda d: _parse_deepseek(d),
    },
    "SiliconFlow": {
        "api_url": "https://api.siliconflow.cn/v1/user/info",
        "prefix": "siliconflow",
        "color": "#0EA5E9",
        "parse": lambda d: _parse_siliconflow(d),
    },
    "OpenRouter": {
        "api_url": "https://openrouter.ai/api/v1/credits",
        "prefix": "openrouter",
        "color": "#F59E0B",
        "parse": lambda d: _parse_openrouter(d),
    },
    "ZhipuAI (智谱)": {
        "api_url": "https://open.bigmodel.cn/api/llm/balance",
        "prefix": "zhipu",
        "color": "#10B981",
        "parse": lambda d: _parse_zhipu(d),
        "note": "未提供公开余额查询接口，将通过对话调用验证 Key 可用性",
        "chat_fallback": True,
    },
    "Kimi (Moonshot)": {
        "api_url": "https://api.moonshot.cn/v1/users/me/balance",
        "prefix": "kimi",
        "color": "#EC4899",
        "parse": lambda d: _parse_kimi(d),
    },
    "OpenAI": {
        "api_url": "https://api.openai.com/v1/dashboard/billing/credit_grants",
        "prefix": "openai",
        "color": "#111827",
        "parse": lambda d: _parse_openai(d),
        "note": "普通 API Key 无法查询余额，将验证 Key 有效性",
    },
}


# ──────────────────────────────────────────────
# 各平台 JSON 解析
# ──────────────────────────────────────────────
def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_deepseek(data):
    infos = data.get("balance_infos") or []
    if isinstance(infos, list) and infos:
        info = infos[0] if isinstance(infos[0], dict) else {}
        total = _to_float(info.get("total_balance"))
        granted = _to_float(info.get("granted_balance"))
        topped = _to_float(info.get("topped_up_balance"))
        currency = info.get("currency", "CNY")
        return total, total > 0, f"总余额: {total} | 赠金: {granted} | 充值: {topped} | 币种: {currency}"
    return 0, False, "无法解析余额数据"


def _parse_siliconflow(data):
    user_data = data.get("data") or {}
    if isinstance(user_data, dict):
        total = _to_float(user_data.get("totalBalance"))
        grant = _to_float(user_data.get("balance"))
        charge = _to_float(user_data.get("chargeBalance"))
        return total, total > 0, f"总余额: {total} | 赠送: {grant} | 充值: {charge}"
    return 0, False, "无法解析余额数据"


def _parse_openrouter(data):
    credit = data.get("data") or {}
    if isinstance(credit, dict):
        total = _to_float(credit.get("total_credits"))
        used = _to_float(credit.get("total_usage"))
        remain = total - used
        return remain, remain > 0, f"总共: {total} | 已用: {used} | 剩余: {remain}"
    return 0, False, "无法解析余额数据"


def _parse_zhipu(data):
    biz = data.get("data") or data
    if isinstance(biz, dict):
        total = _to_float(biz.get("totalBalance") or biz.get("total_balance") or 0)
        used = _to_float(biz.get("usedBalance") or biz.get("used_balance") or 0)
        remain = _to_float(biz.get("remainingBalance") or biz.get("remaining_balance") or biz.get("availableBalance") or 0)
        if remain == 0 and total > 0:
            remain = total - used
        currency = biz.get("currency", "CNY")
        if remain > 0 or total > 0:
            return remain, remain > 0, f"总余额: {total} | 已用: {used} | 剩余: {remain} | 币种: {currency}"
    balance = _to_float(data.get("balance") or data.get("amount") or 0)
    if balance > 0:
        return balance, True, f"余额: {balance}"
    return 0, False, "无法解析余额数据"


def _parse_kimi(data):
    if data.get("status") is True or data.get("code") == 0:
        biz = data.get("data") or {}
        balance = _to_float(biz.get("available_balance"))
        cash = _to_float(biz.get("cash_balance"))
        voucher = _to_float(biz.get("voucher_balance"))
        return balance, balance > 0, f"可用: {balance} | 现金: {cash} | 赠金: {voucher}"
    balance = _to_float(data.get("balance") or 0)
    return balance, balance > 0, f"余额: {balance}"


def _parse_openai(data):
    total_available = _to_float(data.get("total_available") or data.get("total_granted") or 0)
    total_used = _to_float(data.get("total_used") or 0)
    total_granted = _to_float(data.get("total_granted") or total_available)
    if total_available == 0 and total_granted > 0:
        total_available = total_granted - total_used
    return total_available, total_available > 0, f"总授予: {total_granted} | 已用: {total_used} | 可用: {total_available}"


# ──────────────────────────────────────────────
# 核心检测逻辑
# ──────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY = 0.5


def split_keys(raw_text):
    return [item.strip() for item in re.split(r"[\s,;/|&]+", raw_text) if item.strip()]


def deduplicate(keys):
    seen = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


def check_single_key(session, key, platform_name, platform_config):
    """检测单个 API Key，返回 (status, detail_str)"""
    api_url = platform_config["api_url"]
    headers = {"Authorization": f"Bearer {key}"}

    last_error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(api_url, headers=headers, timeout=15)
            break
        except requests.RequestException as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            response = None
    else:
        return "fail", f"网络错误: {last_error}"

    status_code = response.status_code
    try:
        data = response.json()
    except ValueError:
        data = {}

    # 特殊处理 OpenAI
    if platform_name == "OpenAI":
        return _check_openai_fallback(session, key, status_code, data)

    # 特殊处理 ZhipuAI（无公开余额接口，回落 chat 验证）
    if platform_name == "ZhipuAI (智谱)":
        return _check_zhipu_fallback(session, key, status_code, data, platform_config)

    # 通用错误处理
    if status_code == 401:
        return "invalid", "认证失败（401），请检查 API Key"
    if status_code == 403:
        return "invalid", "无权限（403）"
    if status_code == 429:
        return "invalid", "请求频率过高（429）"
    if status_code == 500:
        return "invalid", f"服务器错误（500）"

    if status_code == 200 and isinstance(data, dict):
        balance, is_positive, detail = platform_config["parse"](data)
        status = "positive" if is_positive else "zero"
        symbol = "✅" if is_positive else "⭕"
        label = "余额大于0" if is_positive else "余额为0"
        return status, f"{symbol}{label} - {detail}"

    message = _extract_error(data, response.text)
    return "invalid", f"状态: {status_code} | {message}"


def _check_openai_fallback(session, key, status_code, data):
    """OpenAI 特殊处理"""
    if status_code == 200 and isinstance(data, dict):
        balance, is_positive, detail = _parse_openai(data)
        if balance > 0 or data.get("total_granted"):
            status = "positive" if is_positive else "zero"
            symbol = "✅" if is_positive else "⭕"
            label = "余额大于0" if is_positive else "余额为0"
            return status, f"{symbol}{label} - {detail}"

    if status_code == 403:
        # credit_grants 需要 session key，回落检测 Key 有效性
        resp2, _ = _fetch_with_retry(session, key, "https://api.openai.com/v1/models")
        if resp2 and resp2.status_code == 200:
            return "zero", "⭕Key 有效（余额需浏览器 session key，无法直接查询）"
        if resp2 and resp2.status_code == 401:
            return "invalid", "❌认证失败（401）"
        return "invalid", f"❌不可用"

    if status_code == 401:
        return "invalid", "❌认证失败（401），请检查 API Key"
    if status_code == 429:
        return "invalid", "❌请求频率过高（429）"

    message = _extract_error(data, "")
    return "invalid", f"❌状态: {status_code} | {message}"


_CHAT_FALLBACK_MODEL = "glm-4-flash"


def _check_zhipu_fallback(session, key, status_code, data, config):
    """ZhipuAI 特殊处理：余额接口不可用 → 通过 chat 验证 Key"""
    # 余额接口返回了有效数据
    if status_code == 200:
        balance, is_positive, detail = config["parse"](data)
        if balance > 0 or data.get("success") is not False:
            # 确实解析到了余额数据
            if balance > 0:
                return "positive", f"✅余额大于0 - {detail}"
            return "zero", f"⭕余额为0 - {detail}"

    if status_code == 401:
        return "invalid", "❌认证失败（401）"

    # 余额接口不可用 → 通过 chat 验证
    payload = {
        "model": _CHAT_FALLBACK_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    resp2, _ = _fetch_with_retry_zhipu(session, key, payload)
    if resp2 is None:
        return "fail", "⚠️检测失败 - 网络错误"

    if resp2.status_code == 200:
        return "positive", "✅Key 有效（余额充足，可调用模型）"

    if resp2.status_code == 401:
        return "invalid", "❌认证失败（401）"
    if resp2.status_code == 429:
        return "invalid", "❌请求频率过高（429）"

    message = "请求失败"
    try:
        err_data = resp2.json()
        err = err_data.get("error") or {}
        if isinstance(err, dict):
            message = err.get("message") or err.get("code") or message
    except ValueError:
        pass
    return "invalid", f"❌不可用 - 状态: {resp2.status_code} | {message}"


def _fetch_with_retry_zhipu(session, key, payload):
    """POST to Zhipu chat completions with retry."""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=30)
            return resp, None
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None, "网络错误"


def _fetch_with_retry(session, key, url):
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=headers, timeout=15)
            return resp, None
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None, "网络错误"


def _extract_error(data, text_fallback):
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message", "")
            err_type = err.get("type", "")
            if err_type:
                return f"{err_type}: {msg}"
            return msg or "请求失败"
        msg = data.get("msg", "")
        if msg:
            return msg
    return text_fallback.strip() or "请求失败"


# ──────────────────────────────────────────────
# Streamlit UI
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="API Key Checker",
    page_icon="🔑",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式
st.markdown("""
<style>
    .stApp { font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .result-card { padding: 12px 16px; border-radius: 8px; margin: 4px 0; }
    .positive { background: #dcfce7; border-left: 4px solid #22c55e; }
    .zero { background: #fef9c3; border-left: 4px solid #eab308; }
    .invalid { background: #fee2e2; border-left: 4px solid #ef4444; }
    .fail { background: #f3f4f6; border-left: 4px solid #9ca3af; }
    .summary-card { background: #f8fafc; border-radius: 12px; padding: 24px; text-align: center; }
    .summary-number { font-size: 32px; font-weight: 700; }
    .summary-label { font-size: 13px; color: #64748b; }
    .stButton > button { width: 100%; }
    .key-display { font-family: monospace; font-size: 12px; color: #64748b; word-break: break-all; }
</style>
""", unsafe_allow_html=True)

# ─── 标题 ───
st.title("🔑 API Key Checker")
st.markdown("多平台 API Key 余额批量检测工具")

# ─── 侧边栏 ───
with st.sidebar:
    st.markdown("### 📋 平台选择")
    all_platforms = list(PLATFORMS.keys())
    select_all = st.checkbox("全选", value=True)

    selected_platforms = []
    for name in all_platforms:
        checked = st.checkbox(name, value=select_all, key=f"plat_{name}")
        if checked:
            selected_platforms.append(name)

    st.markdown("---")
    st.markdown("### ⚙️ 选项")

    # 去重选项
    dedup_enabled = st.checkbox("自动去重", value=True)

    # 报告导出
    export_report = st.checkbox("导出报告文件", value=False)

    st.markdown("---")
    st.markdown("**快捷操作**")

    # 清空按钮
    if st.button("🗑️ 清空所有 Key"):
        st.session_state["key_input"] = ""
        st.session_state["results"] = {}
        st.rerun()

    # 示例数据
    if st.button("📝 填入示例 Key"):
        st.session_state["key_input"] = (
            "sk-test-key-1\nsk-test-key-2\nsk-test-key-3"
        )
        st.rerun()

# ─── 主区域：输入 ───
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown("### 📝 API Key 输入")
    key_input = st.text_area(
        "输入 API Key（每行一个，支持逗号/空格/分号分隔）",
        height=150,
        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\nsk-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        key="key_input",
    )

    # 文件上传
    uploaded_file = st.file_uploader(
        "或上传 Key 文件（.txt）",
        type=["txt"],
        accept_multiple_files=False,
    )

with col2:
    st.markdown("### 📊 统计")
    st.metric("选中平台", len(selected_platforms))
    if key_input.strip():
        keys_in_input = split_keys(key_input.strip())
        st.metric("检测到 Key", len(keys_in_input))
    else:
        st.metric("检测到 Key", 0)
    if uploaded_file:
        content = uploaded_file.read().decode("utf-8")
        file_keys = split_keys(content)
        st.metric("文件内 Key", len(file_keys))

# ─── 合并所有 Key ───
all_raw_keys = []
if key_input.strip():
    all_raw_keys.extend(split_keys(key_input.strip()))
if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    all_raw_keys.extend(split_keys(content))

if dedup_enabled:
    all_keys = deduplicate(all_raw_keys)
else:
    all_keys = all_raw_keys

# ─── 开始检测按钮 ───
st.markdown("---")
col_btn, col_info = st.columns([1, 4])
with col_btn:
    start_btn = st.button(
        "🚀 开始检测",
        type="primary",
        use_container_width=True,
        disabled=not (all_keys and selected_platforms),
    )

with col_info:
    if not selected_platforms:
        st.warning("请至少选择一个平台")
    elif not all_keys:
        st.info("请至少输入一个 API Key")
    else:
        st.success(
            f"已准备: {len(all_keys)} 个 Key × {len(selected_platforms)} 个平台"
            f" = {len(all_keys) * len(selected_platforms)} 次检测"
            + (f"（去重后）" if dedup_enabled and len(all_raw_keys) > len(all_keys)
               else "")
        )

# ─── 执行检测 ───
if start_btn and all_keys and selected_platforms:
    results = {}  # platform -> list of (key, status, detail)

    progress_bar = st.progress(0, text="准备检测...")
    total_checks = len(all_keys) * len(selected_platforms)
    completed = 0

    status_placeholder = st.empty()

    with requests.Session() as session:
        for pi, platform_name in enumerate(selected_platforms):
            platform_config = PLATFORMS[platform_name]
            platform_results = []

            # 显示当前平台进度
            status_placeholder.info(f"正在检测: {platform_name} ({pi+1}/{len(selected_platforms)})")

            for ki, key in enumerate(all_keys):
                status, detail = check_single_key(session, key, platform_name, platform_config)
                platform_results.append((key, status, detail))

                completed += 1
                progress = completed / total_checks
                progress_bar.progress(
                    progress,
                    text=f"[{pi+1}/{len(selected_platforms)}] {platform_name} | Key {ki+1}/{len(all_keys)}",
                )

            results[platform_name] = platform_results

    progress_bar.progress(1.0, text="检测完成！")
    status_placeholder.success("所有检测已完成！")
    st.session_state["results"] = results
    st.rerun()

# ─── 显示结果 ───
if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]

    # ─── 全局汇总 ───
    st.markdown("---")
    st.markdown("### 📊 汇总")

    total_pos, total_zero, total_inv, total_fail = 0, 0, 0, 0
    for platform_name, platform_results in results.items():
        for _, status, _ in platform_results:
            if status == "positive":
                total_pos += 1
            elif status == "zero":
                total_zero += 1
            elif status == "invalid":
                total_inv += 1
            elif status == "fail":
                total_fail += 1

    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            f'<div class="summary-card"><div class="summary-number" style="color:#22c55e">{total_pos}</div>'
            f'<div class="summary-label">✅ 余额大于0</div></div>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            f'<div class="summary-card"><div class="summary-number" style="color:#eab308">{total_zero}</div>'
            f'<div class="summary-label">⭕ 余额为0</div></div>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            f'<div class="summary-card"><div class="summary-number" style="color:#ef4444">{total_inv}</div>'
            f'<div class="summary-label">❌ 不可用</div></div>',
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            f'<div class="summary-card"><div class="summary-number" style="color:#9ca3af">{total_fail}</div>'
            f'<div class="summary-label">⚠️ 检测失败</div></div>',
            unsafe_allow_html=True,
        )

    # ─── 各平台详细结果 ───
    st.markdown("---")
    st.markdown("### 📋 详细结果")

    tabs = st.tabs([name for name in results.keys()])

    for ti, (platform_name, platform_results) in enumerate(results.items()):
        with tabs[ti]:
            color = PLATFORMS[platform_name]["color"]
            st.markdown(
                f'<div style="border-left:4px solid {color}; padding-left:12px; margin-bottom:16px">'
                f'<strong style="font-size:18px; color:{color}">{platform_name}</strong>'
                f'<span style="margin-left:12px; font-size:13px; color:#64748b">'
                f'{len(platform_results)} 个 Key</span></div>',
                unsafe_allow_html=True,
            )

            # 表格显示
            table_data = []
            for key, status, detail in platform_results:
                if status == "positive":
                    badge = "✅ 余额大于0"
                    bg = "#dcfce7"
                elif status == "zero":
                    badge = "⭕ 余额为0"
                    bg = "#fef9c3"
                elif status == "invalid":
                    badge = "❌ 不可用"
                    bg = "#fee2e2"
                else:
                    badge = "⚠️ 检测失败"
                    bg = "#f3f4f6"
                masked_key = key[:12] + "..." + key[-4:] if len(key) > 20 else key
                table_data.append({
                    "状态": badge,
                    "API Key": masked_key,
                    "详情": detail,
                })

            if table_data:
                st.dataframe(
                    table_data,
                    use_container_width=True,
                    column_config={
                        "状态": st.column_config.TextColumn("状态", width="small"),
                        "API Key": st.column_config.TextColumn("API Key", width="medium"),
                        "详情": st.column_config.TextColumn("详情", width="large"),
                    },
                    hide_index=True,
                )

            # 汇总分类
            pos_keys = [k for k, s, _ in platform_results if s == "positive"]
            zero_keys = [k for k, s, _ in platform_results if s == "zero"]
            invalid_keys = [k for k, s, _ in platform_results if s == "invalid"]

            col1, col2, col3 = st.columns(3)
            if pos_keys:
                with col1:
                    st.markdown("**🟢 余额大于0**")
                    for k in pos_keys:
                        st.code(k, language="text")
            if zero_keys:
                with col2:
                    st.markdown("**🟡 余额为0**")
                    for k in zero_keys:
                        st.code(k, language="text")
            if invalid_keys:
                with col3:
                    st.markdown("**🔴 不可用**")
                    for k in invalid_keys:
                        st.code(k, language="text")

    # ─── 导出报告 ───
    if export_report:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_lines = [
            f"API Key Checker 检测报告",
            f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Key 数量: {len(all_keys)}",
            f"平台数量: {len(selected_platforms)}",
            "-" * 60,
        ]

        for platform_name, platform_results in results.items():
            report_lines.append(f"\n{'='*60}")
            report_lines.append(f"平台: {platform_name}")
            report_lines.append(f"{'='*60}")
            for key, status, detail in platform_results:
                report_lines.append(f"  Key: {key}")
                report_lines.append(f"  状态: [{status}] {detail}")
                report_lines.append("")

        st.download_button(
            "📥 下载检测报告",
            data="\n".join(report_lines),
            file_name=f"api-checker-report-{ts}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # ─── 一键复制有效 Key ───
    all_valid = set()
    for platform_name, platform_results in results.items():
        for key, status, _ in platform_results:
            if status == "positive":
                all_valid.add(key)
    if all_valid:
        st.markdown("---")
        st.markdown("### ✅ 所有平台中余额大于0的 Key")
        valid_text = "\n".join(sorted(all_valid))
        st.code(valid_text, language="text")

# ─── 页脚 ───
st.markdown("---")
st.markdown(
    '<div style="text-align:center; color:#94a3b8; font-size:12px">'
    'API Key Checker v1.0 | 基于 Streamlit 构建 | Key 仅用于检测，不会保存</div>',
    unsafe_allow_html=True,
)
