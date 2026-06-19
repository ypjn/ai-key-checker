#!/usr/bin/env python3
"""
API Key Checker Dashboard - 多平台 API Key 余额仪表盘
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

CONFIG_FILE = Path(__file__).parent / "api-keys.json"
MAX_RETRIES = 3
RETRY_DELAY = 0.5

def _to_float(v):
    try: return float(v)
    except: return 0.0

# ── 平台定义 ──
PLATFORMS = [
    {"id":"deepseek","name":"DeepSeek","api_url":"https://api.deepseek.com/user/balance","color":"#4F46E5","check":lambda s,k,u:_check_get(s,k,u,_parse_deepseek)},
    {"id":"siliconflow","name":"SiliconFlow","api_url":"https://api.siliconflow.cn/v1/user/info","color":"#0EA5E9","check":lambda s,k,u:_check_get(s,k,u,_parse_siliconflow)},
    {"id":"openrouter","name":"OpenRouter","api_url":"https://openrouter.ai/api/v1/credits","color":"#F59E0B","check":lambda s,k,u:_check_get(s,k,u,_parse_openrouter)},
    {"id":"zhipu","name":"智谱AI","api_url":"https://open.bigmodel.cn/api/llm/balance","color":"#10B981","check":lambda s,k,u:_check_zhipu(s,k,u),"has_balance":False},
    {"id":"kimi","name":"Kimi Moonshot","api_url":"https://api.moonshot.cn/v1/users/me/balance","color":"#EC4899","check":lambda s,k,u:_check_get(s,k,u,_parse_kimi)},
    {"id":"openai","name":"OpenAI","api_url":"https://api.openai.com/v1/dashboard/billing/credit_grants","color":"#111827","check":lambda s,k,u:_check_openai(s,k,u),"has_balance":False},
    {"id":"qwen","name":"阿里通义千问","api_url":"https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","color":"#FF6A00","check":lambda s,k,u:_check_qwen(s,k,u),"has_balance":False},
]

# ── 解析函数 ──
def _parse_deepseek(d):
    infos = d.get("balance_infos") or []
    if isinstance(infos, list) and infos:
        i = infos[0] if isinstance(infos[0], dict) else {}
        t = _to_float(i.get("total_balance"))
        return t, t > 0, f"总余额 {t} {i.get('currency','CNY')}"
    return 0, False, "解析失败"

def _parse_siliconflow(d):
    u = d.get("data") or {}
    if isinstance(u, dict): t = _to_float(u.get("totalBalance")); return t, t > 0, f"总余额 {t}"
    return 0, False, "解析失败"

def _parse_openrouter(d):
    c = d.get("data") or {}
    if isinstance(c, dict): t=_to_float(c.get("total_credits")); u=_to_float(c.get("total_usage")); return t-u, (t-u)>0, f"剩余 {t-u:.2f} / 总计 {t:.2f}"
    return 0, False, "解析失败"

def _parse_kimi(d):
    if d.get("status") is True or d.get("code") == 0:
        biz = d.get("data") or {}
        b = _to_float(biz.get("available_balance"))
        return b, b > 0, f"可用 {b}（现金 {biz.get('cash_balance',0)} + 赠金 {biz.get('voucher_balance',0)}）"
    b = _to_float(d.get("balance")); return b, b > 0, f"余额 {b}"

def _parse_openai(d):
    a = _to_float(d.get("total_available") or d.get("total_granted")); u = _to_float(d.get("total_used"))
    return a, a > 0, f"可用 {a} / 已用 {u}"

# ── 网络请求 ──
def _fetch(session, method, url, key, json_data=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for i in range(MAX_RETRIES + 1):
        try:
            if method == "GET": return session.get(url, headers=h, timeout=15), None
            return session.post(url, headers=h, json=json_data, timeout=30), None
        except requests.RequestException as e:
            if i < MAX_RETRIES: time.sleep(RETRY_DELAY)
            last = str(e)
    return None, last

def _check_get(s, k, u, parser):
    resp, err = _fetch(s, "GET", u, k)
    if resp is None: return "fail", f"网络错误: {err}"
    if resp.status_code == 401: return "invalid", "认证失败"
    try: d = resp.json()
    except: d = {}
    if resp.status_code == 200 and isinstance(d, dict):
        bal, ok, msg = parser(d)
        return ("positive" if ok else "zero", msg)
    return "invalid", f"HTTP {resp.status_code}"

def _check_zhipu(s, k, url):
    # 尝试余额接口
    resp, err = _fetch(s, "GET", url, k)
    if resp and resp.status_code == 200:
        try:
            d = resp.json()
            if d.get("success") is not False:
                data = d.get("data")
                if isinstance(data, dict):
                    bal = _to_float(data.get("totalBalance") or data.get("remainingBalance") or data.get("availableBalance") or 0)
                    if bal > 0:
                        return "positive", f"余额 {bal}"
        except: pass

    # 尝试新版用户信息接口
    resp2, _ = _fetch(s, "GET", "https://open.bigmodel.cn/api/user/info", k)
    if resp2 and resp2.status_code == 200:
        try:
            d = resp2.json()
            data = d.get("data") or d
            bal = _to_float(data.get("totalBalance") or data.get("balance") or data.get("credit") or 0)
            if bal > 0:
                return "positive", f"余额 {bal}"
        except: pass

    # 尝试计费/用量汇总接口
    resp3, _ = _fetch(s, "GET", "https://open.bigmodel.cn/api/billing/summary", k)
    if resp3 and resp3.status_code == 200:
        try:
            d = resp3.json()
            data = d.get("data") or d
            bal = _to_float(data.get("remainingAmount") or data.get("balance") or 0)
            if bal > 0:
                return "positive", f"余额 {bal}"
        except: pass

    # 最终 fallback: 调一次模型确认 Key 是否有效
    payload = {"model":"glm-4-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":1}
    r, _ = _fetch(s, "POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions", k, payload)
    if r and r.status_code == 200: return "positive", "可用（余额未知）"
    if r and r.status_code == 429: return "zero", "余额不足"
    return "invalid", "不可用"

def _check_openai(s, k, url):
    resp, err = _fetch(s, "GET", url, k)
    if resp is None: return "fail", f"网络错误: {err}"
    if resp.status_code == 200:
        try: d = resp.json(); bal, ok, msg = _parse_openai(d); return ("positive" if ok else "zero", msg)
        except: pass
    if resp.status_code == 403:
        r2, _ = _fetch(s, "GET", "https://api.openai.com/v1/models", k)
        if r2 and r2.status_code == 200: return "positive", "Key 有效（余额需登录查看）"
        return "invalid", "不可用"
    return "invalid", f"HTTP {resp.status_code}"

def _check_qwen(s, k, url):
    payload = {"model":"qwen-turbo","messages":[{"role":"user","content":"hi"}],"max_tokens":1}
    resp, err = _fetch(s, "POST", url, k, payload)
    if resp is None: return "fail", f"网络错误: {err}"
    if resp.status_code == 200: return "positive", "余额充足"
    if resp.status_code == 401: return "invalid", "Key 无效或已过期"
    if resp.status_code == 429: return "zero", "余额不足/限流"
    return "invalid", f"HTTP {resp.status_code}"

def load_keys():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text())
        except: pass
    return {}

def save_keys(keys):
    CONFIG_FILE.write_text(json.dumps(keys, indent=2, ensure_ascii=False))

# ── Streamlit ──
st.set_page_config(page_title="API Key 仪表盘", page_icon="🔑", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container { padding-top: 6rem !important; max-width: 1200px !important; }

.card {
    border-radius: 12px; padding: 16px 20px;
    border: 1px solid #eee;
    margin-bottom: 8px;
}
.card-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px; }
.card-name { font-size: 13px; font-weight: 600; }
.card-badge { display:inline-block; padding:1px 10px; border-radius:10px; font-size:11px; font-weight:600; }
.card-balance { font-size: 22px; font-weight: 700; margin: 4px 0 2px; }
.card-detail { font-size: 12px; color: #64748b; }
.card-key { font-size: 11px; color: #94a3b8; word-break:break-all; margin-top:6px; padding:4px 8px; background:#f8f8f8; border-radius:6px; font-family:monospace; }

.badge-ok { background:#dcfce7; color:#166534; }
.badge-zero { background:#fef9c3; color:#854d0e; }
.badge-invalid { background:#fee2e2; color:#991b1b; }
.badge-fail { background:#f3f4f6; color:#475569; }

.stat-box { text-align:center; padding:8px 0; border-radius:10px; }
.stat-num { font-size: 24px; font-weight: 700; }
.stat-label { font-size: 13px; color: #64748b; margin-top: 2px; }

.stApp { font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
section[data-testid="stSidebar"] { width: 280px !important; }
div[data-testid="stHorizontalBlock"] { gap: 12px; }
hr { margin: .8rem 0; opacity: .2; }
section[data-testid="stSidebar"] .stButton>button { font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)

# ── 状态初始化 ──
if "saved_keys" not in st.session_state: st.session_state.saved_keys = load_keys()
if "results" not in st.session_state: st.session_state.results = {}
if "last_check" not in st.session_state: st.session_state.last_check = None
if "needs_check" not in st.session_state: st.session_state.needs_check = True

# ── 顶栏 ──
c1, c2 = st.columns([3, 2])
with c1:
    st.markdown("### API Key 仪表盘")
    if st.session_state.last_check:
        st.caption(f"上次检测 · {st.session_state.last_check}")
with c2:
    if st.button("重新检测", use_container_width=True, type="primary"):
        st.session_state.needs_check = True; st.rerun()

# ── 侧栏: 配置 ──
with st.sidebar:
    st.markdown("### 配置 API Key")
    st.markdown("在各平台输入 Key 后保存，自动开始检测。")
    new_keys = {}
    for pf in PLATFORMS:
        existing = st.session_state.saved_keys.get(pf["id"], "")
        val = st.text_input(pf["name"], value=existing,
            placeholder=f"输入 {pf['name']} Key...", key=f"key_{pf['id']}", type="password", label_visibility="collapsed")
        if val.strip(): new_keys[pf["id"]] = val.strip()
        elif pf["id"] in st.session_state.saved_keys and st.session_state.saved_keys[pf["id"]]:
            new_keys[pf["id"]] = st.session_state.saved_keys[pf["id"]]
    ca, cb = st.columns(2)
    with ca:
        if st.button("保存并检测", use_container_width=True, type="primary"):
            save_keys(new_keys); st.session_state.saved_keys = new_keys
            st.session_state.needs_check = True; st.rerun()
    with cb:
        if st.button("清空全部", use_container_width=True):
            save_keys({}); st.session_state.saved_keys = {}; st.session_state.results = {}
            st.session_state.needs_check = False; st.rerun()
    st.markdown("---")
    configured = [pf["name"] for pf in PLATFORMS if st.session_state.saved_keys.get(pf["id"])]
    if configured: st.markdown(f"**已配置 {len(configured)} 个**: " + " · ".join(f"{n}" for n in configured))
    else: st.markdown("尚未配置任何 Key")

# ── 单独平台检测 ──
_detect_status = st.empty()
_detect_prog = st.empty()

if st.session_state.get("single_check_platform_id"):
    pf_id = st.session_state.pop("single_check_platform_id")
    pf = next((p for p in PLATFORMS if p["id"] == pf_id), None)
    if pf and st.session_state.saved_keys.get(pf["id"]):
        key = st.session_state.saved_keys[pf["id"]]
        _detect_status.info(f"{pf['name']} 检测中...")
        with requests.Session() as sess:
            status, msg = pf["check"](sess, key, pf["api_url"])
        results = st.session_state.get("results", {})
        results[pf["id"]] = {"status": status, "msg": msg, "key": key}
        st.session_state.results = results
        st.session_state.last_check = datetime.now().strftime("%H:%M:%S")
        _detect_status.success(f"{pf['name']} 检测完成")
        time.sleep(.5)
        st.rerun()

# ── 自动检测 ──
_detect_status2 = st.empty()
_detect_prog2 = st.empty()

if st.session_state.needs_check and st.session_state.saved_keys:
    results = {}
    total = len([pf for pf in PLATFORMS if st.session_state.saved_keys.get(pf["id"])])
    done = 0
    with requests.Session() as sess:
        for pf in PLATFORMS:
            key = st.session_state.saved_keys.get(pf["id"])
            if not key: continue
            done += 1
            _detect_prog2.progress(done/total)
            _detect_status2.info(f"{pf['name']} 检测中...")
            status, msg = pf["check"](sess, key, pf["api_url"])
            results[pf["id"]] = {"status": status, "msg": msg, "key": key}
    st.session_state.results = results
    st.session_state.last_check = datetime.now().strftime("%H:%M:%S")
    st.session_state.needs_check = False
    _detect_status2.success(f"检测完成（{total} 个平台）")
    _detect_prog2.empty()
    time.sleep(.5)
    st.rerun()

# ── 展示结果 ──
results = st.session_state.results

for pi, pf in enumerate(PLATFORMS):
    r = results.get(pf["id"]) if results else None
    color = pf["color"]
    has_key = bool(st.session_state.saved_keys.get(pf["id"]))
    has_balance = pf.get("has_balance", True)
    btn_disabled = not (has_balance and has_key)

    card_col, btn_col = st.columns([5, 1], vertical_alignment="center")
    with card_col:
        if r:
            k = r["key"]; masked = k[:8]+"..."+k[-4:] if len(k)>16 else k
            sts = r["status"]; msg = r["msg"]
            if sts == "positive":
                badge_cls, badge_txt, bal_clr = "badge-ok", "可用", "#22c55e"
                bal_display = msg.split("（")[0] if "（" in msg else msg.split(" - ")[0] if " - " in msg else msg
            elif sts == "zero":
                badge_cls, badge_txt, bal_clr = "badge-zero", "余额为 0", "#eab308"
                bal_display = msg
            elif sts == "invalid":
                badge_cls, badge_txt, bal_clr = "badge-invalid", "不可用", "#ef4444"
                bal_display = msg
            else:
                badge_cls, badge_txt, bal_clr = "badge-fail", "失败", "#94a3b8"
                bal_display = msg
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {color}">
                <div class="card-header">
                    <span class="card-name" style="color:{color}">{pf['name']}</span>
                    <span class="card-badge {badge_cls}">{badge_txt}</span>
                </div>
                <div class="card-balance" style="color:{bal_clr}">{bal_display}</div>
                <div class="card-detail">{msg}</div>
                <div class="card-key">{masked}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {color}; opacity:0.5">
                <div class="card-header">
                    <span class="card-name" style="color:{color}">{pf['name']}</span>
                    <span class="card-badge badge-fail">--</span>
                </div>
                <div class="card-detail" style="padding:8px 0; color:#94a3b8">
                    {'等待检测' if has_key else '请在左侧输入 API Key'}
                </div>
            </div>
            """, unsafe_allow_html=True)
    with btn_col:
        if st.button("检测", key=f"sb_{pf['id']}", disabled=btn_disabled, use_container_width=True):
            st.session_state["single_check_platform_id"] = pf["id"]

# ── 统计 ──
if results:
    pos = sum(1 for r in results.values() if r["status"]=="positive")
    zero = sum(1 for r in results.values() if r["status"]=="zero")
    inv = sum(1 for r in results.values() if r["status"]=="invalid")
    fail = sum(1 for r in results.values() if r["status"]=="fail")

    st.markdown("---")
    cols = st.columns(4)
    for i, (lbl, cnt, clr) in enumerate([
        ("可用", pos, "#22c55e"),
        ("余额为 0", zero, "#eab308"),
        ("不可用", inv, "#ef4444"),
        ("检测失败", fail, "#94a3b8"),
    ]):
        with cols[i]:
            st.markdown(f'<div class="stat-box" style="background:{clr}08"><div class="stat-num" style="color:{clr}">{cnt}</div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    valid = {pf["name"]:r["key"] for pf in PLATFORMS if results.get(pf["id"],{}).get("status")=="positive"}
    if valid:
        with st.expander("所有可用的 Key"):
            for name, key in valid.items(): st.code(f"# {name}\n{key}", language="text")

st.markdown("---")
st.markdown('<div style="text-align:center;color:#94a3b8;font-size:12px">API Key 仪表盘 · Key 仅用于检测，不会上传</div>', unsafe_allow_html=True)
