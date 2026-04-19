---
name: translate-tts
description: Use when users want Chinese text translated and converted to speech (translate-then-TTS), including multilingual dubbing, pronunciation clips, or “翻译后朗读”. Trigger implicitly even when users do not explicitly mention this skill.
---

# Translate TTS Skill

## Trigger Rules

Trigger this skill when the request implies:

- 中文内容翻译成一种或多种语言
- 翻译结果生成音频（TTS）
- 多语种配音 / 朗读 / 发音文件

Do not require explicit `$translate-tts`.

## Scope Boundary

`translate-tts` only handles translation + TTS.

- It does not include `.ncm -> .wav` conversion.
- For `.ncm` conversion, use the independent `ncm-to-wav` skill.

## Standard Script Names

- `scripts/translate_tts.py`: 主流程（翻译 + TTS）
- `scripts/run_translate_tts.sh`: Bash 启动器

## Language Input Style

Prefer natural language names instead of short codes.

Examples:

- `英文, 日文, 韩文`

Also supported: per-line language and sentence pairs (auto-detected when each line contains `语言:句子`).

Example:

```
英文：人生总是有喜有悲
日语：有欢笑也有泪水
西班牙语：风雨过后才能看到彩虹
```

When using this format, `--langs` is optional and will be ignored if provided.

`translate_tts.py` supports:

- 中文、英文/英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语/日文、韩语/韩文

## Output Convention

Default output root:

- `~/Downloads/translate_tts`

Each task creates a timestamp directory:

- `~/Downloads/translate_tts/<YYYYmmdd_HHMMSS_mmm>/`

Files per task:

- `translations.txt`
- `result.json`
- `*.wav`

## Recommended Commands

### macOS / Linux / WSL

Global skill root:

```bash
SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/translate-tts"
```

Run:

```bash
bash "$SKILL_ROOT/scripts/run_translate_tts.sh" --text "你好世界" --langs "英文,日文,韩文"
```

### Windows PowerShell

Global skill root:

```powershell
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillRoot = Join-Path $CodexHome "skills/translate-tts"
conda run -n qwen3-tts --no-capture-output python "$SkillRoot/scripts/translate_tts.py" --text "你好世界" --langs "英文,日文,韩文"
```

### Windows CMD

```bat
if "%CODEX_HOME%"=="" (
  set "SKILL_ROOT=%USERPROFILE%\.codex\skills\translate-tts"
) else (
  set "SKILL_ROOT=%CODEX_HOME%\skills\translate-tts"
)
conda run -n qwen3-tts --no-capture-output python "%SKILL_ROOT%\scripts\translate_tts.py" --text "你好世界" --langs "英文,日文,韩文"
```

## Windows Troubleshooting

### GBK Encoding Error with `conda run`

If you encounter `UnicodeEncodeError: 'gbk' codec can't encode character` when using `conda run`, use the direct Python path instead:

```bash
export CONDA_DEFAULT_ENV=qwen3-tts
export PYTHONIOENCODING=utf-8
/d/garden/anaconda3/envs/qwen3-tts/python.exe scripts/translate_tts.py --text "你好" --langs "英文,日文"
```

The script now detects the conda environment from `sys.executable` path, so setting `CONDA_DEFAULT_ENV` is sufficient.

### Ollama Connection Issues

If translations fail with "Connection error" or "HTTP 404":

1. Ensure Ollama is running: `ollama serve`
2. Verify the translategemma model is loaded: `ollama list | grep translategemma`
3. If missing, pull it: `ollama pull translategemma`

### Translation Retry Logic

The script now automatically retries failed translations up to 3 times with exponential backoff (1s, 2s, 4s) to handle transient Ollama errors.
```
