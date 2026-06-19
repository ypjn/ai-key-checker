#!/bin/bash
# API Key Checker Dashboard 启动脚本
cd "$(dirname "$0")"
echo "🔑 启动 API Key Checker..."
streamlit run dashboard.py --server.port 8501 --server.headless true &
for i in $(seq 1 20); do
    sleep 1
    curl -s -o /dev/null http://localhost:8501 2>/dev/null && break
done
open http://localhost:8501
echo "✅ 浏览器已打开"
