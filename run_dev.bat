@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   AI Web Tool — 开发模式启动 (SQLite)
echo ============================================

cd /d "%~dp0backend"

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

:: 创建虚拟环境 (如果不存在)
if not exist "venv" (
    echo [1/4] 创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 安装依赖
echo [2/4] 安装 Python 依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 检查 .env，不存在则从 .env.example 复制
if not exist ".env" (
    echo [3/4] 创建 .env 配置文件...
    copy .env.example .env >nul
)

:: 启动
echo [4/4] 数据库将在首次启动时自动创建 (dev.db)
echo.
echo [5/5] 启动服务...
echo.
echo   前端 (静态文件): http://localhost:8000
echo   API 文档:       http://localhost:8000/docs
echo   健康检查:       http://localhost:8000/health
echo.
echo   按 Ctrl+C 停止服务
echo ============================================
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

endlocal
