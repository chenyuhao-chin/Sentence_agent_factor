@echo off
chcp 65001 >nul
title {{AGENT_NAME}}
echo ============================================
echo   🚀 {{AGENT_NAME}}
echo   Agent Factory 🏭 全自动生成
echo ============================================
echo.
echo 📦 正在检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到 Python！请先安装 Python 3.10+
    echo 📥 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
echo.
echo 📥 正在安装依赖...
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
echo.
echo 🔑 请确保已配置 .env 文件中的 API Key
echo.
echo 🚀 启动智能体...
python "{{AGENT_FILENAME}}.py"
echo.
echo 🏁 智能体运行结束，按任意键退出...
pause
