#!/usr/bin/env pwsh
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ScriptArgs
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$CondaEnv = 'qwen3-tts'

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
  Write-Error "未找到 conda，请先安装并创建环境: conda create -n $CondaEnv python=3.12 -c conda-forge"
  exit 1
}

$pyScript = Join-Path $ProjectRoot "scripts" "translate_then_tts.py"

# Use --no-capture-output to preserve encoding and allow real-time output
if ($ScriptArgs -and $ScriptArgs.Count -gt 0) {
  & conda run -n $CondaEnv --no-capture-output python $pyScript @ScriptArgs
} else {
  & conda run -n $CondaEnv --no-capture-output python $pyScript
}