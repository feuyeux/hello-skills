---
name: translate-tts
description: Translate Chinese text to multiple languages and generate speech audio using Qwen3-TTS. Use when user wants to translate Chinese text to other languages and convert to speech.
---

# Translate TTS

## Quick Start (PowerShell on Windows — recommended)

For reliable Unicode handling, write the Chinese text to a temp file first, then pass `--text-file`:

```powershell
$textFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($textFile, "你好世界", [System.Text.Encoding]::UTF8)
conda run -n qwen3-tts --no-capture-output python "D:\zoo\skills\translate-tts\scripts\translate_then_tts.py" --text-file $textFile --langs "en,ja,ko"
Remove-Item $textFile -ErrorAction SilentlyContinue
```

Or use the wrapper script:

```powershell
D:\zoo\skills\translate-tts\scripts\run.ps1 --text-file $textFile --langs "en,ja,ko"
```

If the text is pure ASCII / short, `--text` also works:

```powershell
conda run -n qwen3-tts --no-capture-output python "D:\zoo\skills\translate-tts\scripts\translate_then_tts.py" --text "你好" --langs "en,ja"
```

## Important Notes

- **Always** use `conda run -n qwen3-tts --no-capture-output` (the `--no-capture-output` flag is required to avoid encoding corruption on Windows).
- **Prefer `--text-file`** over `--text` for any Chinese input to avoid PowerShell / CMD encoding issues.
- On Windows the script auto-writes result JSON to `D:\talking\result.json` — read that file for structured output.

## Other Platforms

```bash
# Bash (Unix/Git Bash)
D:\zoo\skills\translate-tts\scripts\run.sh --text "你好世界" --langs "en,ja,ko"

# Windows CMD (interactive)
D:\zoo\skills\translate-tts\scripts\run-translate-tts.bat
```

## Supported Languages

**Translation**: en, ja, ko, zh, ru, es, fr, de, it, pt, ar, th, vi, hi

**TTS (语音合成)**: en, ja, ko, zh, ru, es, fr, de, it, pt

Note: Arabic (ar), Hindi (hi), Thai (th), and Vietnamese (vi) are supported for translation but NOT for TTS due to model limitations.
