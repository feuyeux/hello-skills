@echo off
chcp 65001 >nul
setlocal

set "CONDA_ENV=qwen3-tts"
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "PY_SCRIPT=%PROJECT_ROOT%\scripts\translate_tts.py"

conda --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 conda，请先安装并创建环境: conda create -n %CONDA_ENV% python=3.12 -c conda-forge -y
    exit /b 1
)

if "%~1"=="" (
    echo 用法:
    echo   run_translate_tts.bat --text "你好世界" --langs "英文,日文,韩文"
    echo.
    echo 也可以使用:
    echo   run_translate_tts.bat --text-file C:\path\input.txt --langs "英文,日文,韩文"
    exit /b 0
)

conda run -n %CONDA_ENV% --no-capture-output python "%PY_SCRIPT%" %*
