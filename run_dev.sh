#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================"
echo "  AI Web Tool — 开发模式启动 (SQLite)"
echo "============================================"

# Check Python
python3 --version >/dev/null 2>&1 || { echo "[错误] 未找到 Python3"; exit 1; }

cd backend

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo "[2/4] 安装 Python 依赖..."
pip install -r requirements.txt -q

# Create .env from example if missing
if [ ! -f ".env" ]; then
    echo "[3/4] 创建 .env 配置文件..."
    cp .env.example .env
fi

echo "[4/5] 数据库将在首次启动时自动创建 (dev.db)"
echo ""
echo "[5/5] 启动服务..."
echo ""
echo "  前端 + API: http://localhost:8000"
echo "  API 文档:   http://localhost:8000/docs"
echo "  健康检查:   http://localhost:8000/health"
echo ""
echo "  按 Ctrl+C 停止"
echo "============================================"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
