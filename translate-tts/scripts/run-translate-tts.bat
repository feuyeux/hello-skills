@echo off
chcp 65001 >nul

setlocal ENABLEDELAYEDEXPANSION

set CONDA_ENV=qwen3-tts
set OUTPUT_DIR=D:\talking

rem Resolve project root relative to this .bat file
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI

rem Prefer conda run so we don't need to hardcode python.exe path
set RUN_CMD=conda run -n %CONDA_ENV% --no-capture-output python "%PROJECT_ROOT%\scripts\translate_then_tts.py"

echo.
echo ============================================================
echo        全局翻译 + TTS 工具 (使用 Conda 环境)
echo ============================================================
echo.

:: 检查 conda 是否可用
conda --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 conda，请先安装并创建环境: conda create -n %CONDA_ENV% python=3.12 -c conda-forge -y
    pause
    exit /b 1
)

echo [OK] Conda 可用，将使用环境: %CONDA_ENV%

:: 检查 Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [警告] Ollama 未安装，翻译功能不可用
    echo 请安装 Ollama: https://ollama.com
)

:: 创建输出目录
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
echo [OK] 输出目录已准备: %OUTPUT_DIR%

echo.
echo 使用方法:
echo   translate-tts "你好" "en,ja,fr"
echo.
echo ============================================================
echo.

:: 检查是否带参数启动
if "%~1"=="" (
    echo 请输入要翻译的中文文本和目标语言
    echo 例如: translate-tts "你好世界" "en,ja,ko"
    echo.
    set /p INPUT_TEXT="请输入中文文本: "
    set /p INPUT_LANGS="请输入目标语言(逗号分隔): "
    echo.
    echo 正在处理...
    %RUN_CMD% --text "%INPUT_TEXT%" --langs "%INPUT_LANGS%"
) else (
    echo 正在处理...
    %RUN_CMD% %*
)

echo.
pause
