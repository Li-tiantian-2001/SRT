@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 检查虚拟环境是否存在
if not exist "venv\Scripts\python.exe" (
    echo [提示] 首次使用请先运行 "首次配置.bat" 安装环境
    echo.
    pause
    exit /b 1
)

:: 启动程序
venv\Scripts\python.exe app\launcher\main.py
