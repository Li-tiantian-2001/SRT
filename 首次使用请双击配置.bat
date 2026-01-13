@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo     科技脉冲字幕 - 环境配置脚本
echo ========================================
echo.

:: 检查 Python 是否已安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/3] 检测到 Python:
python --version
echo.

:: 创建虚拟环境
if not exist "venv" (
    echo [2/3] 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo      虚拟环境创建成功
) else (
    echo [2/3] 虚拟环境已存在，跳过创建
)
echo.

:: 安装依赖
echo [3/3] 安装依赖 (requirements.txt)...
echo      这可能需要几分钟，请耐心等待...
echo.
venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [警告] 清华源安装失败，尝试官方源...
    venv\Scripts\pip install -r requirements.txt
)

echo.
echo ========================================
echo     环境配置完成！
echo ========================================
echo.
echo 现在可以双击 "启动.bat" 运行程序了
echo.
pause
