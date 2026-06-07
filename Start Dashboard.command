#!/bin/bash
# API Key Checker Dashboard 启动器
# 双击此文件即可启动（macOS .command 文件）

cd "$(dirname "$0")"

echo "================================================"
echo "  🔑 API Key Checker Dashboard"
echo "================================================"
echo ""
echo "⏳ 启动中，请稍候..."
echo ""

# 后台启动 Streamlit
streamlit run dashboard.py --server.port 8501 --server.headless true &
STREAMLIT_PID=$!

# 等待服务器就绪
for i in $(seq 1 20); do
    sleep 1
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 2>/dev/null | grep -q 200; then
        break
    fi
done

# 自动打开浏览器
open http://localhost:8501

echo ""
echo "✅ 已启动！浏览器已自动打开"
echo "   关闭此窗口即可停止服务"
echo ""

# 等待进程结束
wait $STREAMLIT_PID
