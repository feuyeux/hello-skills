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

## Standard Script Names

- `scripts/translate_tts.py`: 主流程（翻译 + TTS）
- `scripts/translate_only.py`: 仅翻译
- `scripts/single_tts.py`: 单句 TTS
- `scripts/run_single_tts.sh`: 单句 TTS（Bash 启动器）
- `scripts/run_translate_tts.sh`: Bash 启动器
- `scripts/run_translate_tts.ps1`: PowerShell 启动器
- `scripts/run_translate_tts.bat`: Windows CMD 启动器
- `scripts/install_translate_tts.py`: 全局安装到 Codex/Claude

## Language Input Style

Prefer natural language names instead of short codes.

Examples:

- `英文, 日文, 韩文`

`single_tts.py` and `translate_tts.py` both support:

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

```bash
bash scripts/run_translate_tts.sh --text "你好世界" --langs "英文,日文,韩文"
```

### Windows PowerShell

```powershell
./scripts/run_translate_tts.ps1 --text "你好世界" --langs "英文,日文,韩文"
```

### Windows CMD

```bat
scripts\run_translate_tts.bat --text "你好世界" --langs "英文,日文,韩文"
```
