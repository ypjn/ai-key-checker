#!/usr/bin/env python3
import argparse
import os
import re
import sys
import time
from datetime import datetime

import requests


PLATFORM_NAME = "OpenAI"
PLATFORM_PREFIX = "openai"
API_URL = "https://api.openai.com/v1/dashboard/billing/credit_grants"
MAX_RETRIES = 3
RETRY_DELAY = 0.5


def split_keys(raw_text):
    return [item.strip() for item in re.split(r"[\s,;/|&]+", raw_text) if item.strip()]


def collect_keys(inputs):
    all_keys = []
    for item in inputs:
        if os.path.isfile(item):
            with open(item, "r", encoding="utf-8") as f:
                all_keys.extend(split_keys(f.read()))
        else:
            all_keys.extend(split_keys(item))
    return all_keys


def deduplicate_keep_order(keys):
    seen = set()
    result = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_with_retry(session, key, url=None, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}"}
    if extra_headers:
        headers.update(extra_headers)
    target_url = url or API_URL
    last_error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(target_url, headers=headers)
            return response, None
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None, last_error


def check_key(session, key):
    # Try credit_grants endpoint first (works with session keys / some API keys)
    response, net_error = fetch_with_retry(session, key)
    if response is None:
        return "fail", f"⚠️检测失败 - 网络错误: {net_error}"

    status_code = response.status_code
    try:
        data = response.json()
    except ValueError:
        data = {}

    # credit_grants endpoint succeeded
    if status_code == 200 and isinstance(data, dict):
        total_granted = to_float(data.get("total_granted") or data.get("total_available") or 0)
        total_used = to_float(data.get("total_used") or 0)
        total_available = to_float(data.get("total_available") or 0)
        if total_available == 0 and total_granted > 0:
            total_available = total_granted - total_used

        if total_available > 0:
            return "positive", f"✅余额大于0 - 总授予: {total_granted} | 已用: {total_used} | 可用: {total_available}"
        return "zero", f"⭕余额为0 - 总授予: {total_granted} | 已用: {total_used} | 可用: {total_available}"

    # Check if it's a 403 from credit_grants (session key required)
    # Fall back to checking models endpoint for key validity, then try admin usage API
    if status_code == 403 and isinstance(data, dict):
        error_msg = ""
        error_obj = data.get("error")
        if isinstance(error_obj, dict):
            error_msg = str(error_obj.get("message") or "")
            # credit_grants requires session key — inform user
            if "session" in error_msg.lower() or "credit_grants" in response.url:
                return _check_openai_fallback(session, key)

    if status_code == 401:
        return "invalid", f"❌不可用 - 认证失败（401），请检查 API Key"
    if status_code == 429:
        return "invalid", f"❌不可用 - 请求频率过高（429）"

    # Try admin API (organization usage) as last resort
    if _is_admin_key(key):
        return _check_admin_usage(session, key)

    # General error handling
    message = "请求失败"
    if isinstance(data, dict):
        error_obj = data.get("error")
        if isinstance(error_obj, dict):
            message = str(error_obj.get("message") or message)
    if message == "请求失败":
        message = response.text.strip() or message
    return "invalid", f"❌不可用 - 状态: {status_code} | 消息: {message}"


def _is_admin_key(key):
    return key.startswith("sk-admin-") or key.startswith("sk-org-")


def _check_admin_usage(session, key):
    """Try OpenAI admin API to get usage data."""
    now = int(time.time())
    # Last 30 days
    start_time = now - 30 * 24 * 3600
    admin_url = f"https://api.openai.com/v1/organization/usage/completions?start_time={start_time}&limit=1"
    response, net_error = fetch_with_retry(session, key, url=admin_url)
    if response is None:
        return "fail", f"⚠️检测失败 - 网络错误: {net_error}"

    if response.status_code == 200:
        try:
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                usage_data = data["data"]
                total_usage = sum(to_float(item.get("amount", 0)) for item in usage_data) if isinstance(usage_data, list) else 0
                return "positive", f"✅管理 API 有效 - 近期用量: {total_usage}"
        except ValueError:
            pass

    return _check_key_validity(session, key)


def _check_key_validity(session, key):
    """Fallback: check if the API key is valid via /v1/models."""
    response, net_error = fetch_with_retry(session, key, url="https://api.openai.com/v1/models")
    if response is None:
        return "fail", f"⚠️检测失败 - 网络错误: {net_error}"

    if response.status_code == 200:
        return "positive", f"✅API Key 有效（余额接口需浏览器 session key，当前仅确认 Key 可用）"
    if response.status_code == 401:
        return "invalid", f"❌不可用 - 认证失败（401）"
    return "invalid", f"❌不可用 - 状态: {response.status_code}"


def _check_openai_fallback(session, key):
    """Called when credit_grants returns 403 — check key via models endpoint."""
    message = (
        "OpenAI 余额接口需要浏览器 session key（非 API Key），\n"
        "  无法从 API Key 直接查询余额。请使用 OpenAI 管理员 API Key\n"
        "  （sk-admin-...）或登录 dashboard 查看。"
    )
    # Still check if the key is valid
    response, net_error = fetch_with_retry(session, key, url="https://api.openai.com/v1/models")
    if response is None:
        return "fail", f"⚠️检测失败 - 网络错误: {net_error}"

    if response.status_code == 200:
        return "zero", f"⭕API Key 有效但无法查询余额 - {message}"
    if response.status_code == 401:
        return "invalid", f"❌不可用 - 认证失败（401）"
    return "invalid", f"❌不可用 - 状态: {response.status_code}"


def default_report_name():
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{PLATFORM_PREFIX}-report-{ts}.txt"


def build_report(total_count, lines, positive_keys, zero_keys, fail_keys, invalid_keys, sep):
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines = [
        f"{PLATFORM_NAME} API Key 检测报告",
        f"密钥数量: {total_count}",
        f"检测时间: {now_text}",
        "-" * 60,
    ]
    report_lines.extend(lines)
    report_lines.extend(
        [
            f"🟢余额大于0的 API Key ({len(positive_keys)}):",
            sep.join(positive_keys),
            f"🟡余额为0/仅 Key 有效的 API Key ({len(zero_keys)}):",
            sep.join(zero_keys),
            f"🔴不可用的 API Key ({len(invalid_keys)}):",
            sep.join(invalid_keys),
            f"⚠️检测失败的 API Key ({len(fail_keys)}):",
            sep.join(fail_keys),
        ]
    )
    return "\n".join(report_lines)


def parse_args():
    parser = argparse.ArgumentParser(description=f"{PLATFORM_NAME} API Key 批量检测脚本")
    parser.add_argument("inputs", nargs="+", help="输入 key 或 txt 文件路径，可混合")
    parser.add_argument("--report", nargs="?", const="", default=None, help="输出报告到文件，可选自定义文件名")
    parser.add_argument("--sep", default=",", help="最终汇总时 key 的分隔符，默认英文逗号")
    return parser.parse_args()


def main():
    args = parse_args()
    raw_keys = collect_keys(args.inputs)
    keys = deduplicate_keep_order(raw_keys)

    print("▶️开始批量检测 API Key")
    print(f"🔢总输入: {len(raw_keys)} | 去重后: {len(keys)}")
    print("-" * 60)

    positive_keys = []
    zero_keys = []
    fail_keys = []
    invalid_keys = []
    detail_lines = []

    with requests.Session() as session:
        for idx, key in enumerate(keys, start=1):
            line1 = f"[{idx}/{len(keys)}] {key}"
            status, line2 = check_key(session, key)

            print(line1)
            print(line2)
            print("-" * 60)

            detail_lines.append(line1)
            detail_lines.append(line2)
            detail_lines.append("-" * 60)

            if status == "positive":
                positive_keys.append(key)
            elif status == "zero":
                zero_keys.append(key)
            elif status == "fail":
                fail_keys.append(key)
            else:
                invalid_keys.append(key)

    report_file = None
    if args.report is not None:
        report_file = args.report.strip() if args.report else default_report_name()
        report = build_report(len(keys), detail_lines, positive_keys, zero_keys, fail_keys, invalid_keys, args.sep)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)

    print("⏹️所有 API Key 检测完成")
    if report_file is not None:
        print(f"📄报告已保存: {report_file}")
    print(f"🔢总共: {len(keys)} | ✅余额大于0/有效: {len(positive_keys)} | ⭕余额为0/仅Key有效: {len(zero_keys)} | ❌不可用: {len(invalid_keys)} | ⚠️检测失败: {len(fail_keys)}")
    print("-" * 60)
    if len(positive_keys) > 0:
        print("🟢余额大于0/有效的 API Key:")
        print(",".join(positive_keys))
    if len(zero_keys) > 0:
        print("🟡余额为0/仅Key有效的 API Key:")
        print(",".join(zero_keys))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\n已中断")
