# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A collection of independent AI agent skills (for Claude Code, Gemini CLI, Codex, etc.). Each skill is a self-contained directory with a `SKILL.md` (metadata + instructions) and a `scripts/` folder. Top-level docs (`README.md`, `get_latest.md`) explain usage and version-source rules. Hidden folders (`.agents/`, `.claude/`) are agent mirrors ignored by Git.

## Skills

| Skill | Entry Point | Description |
|-------|------------|-------------|
| `toolcheck` | `bash toolcheck/scripts/toolcheck.sh` (macOS/Linux) or `pwsh toolcheck/scripts/toolcheck.ps1` (Windows) | Scans 25 dev tools for version conflicts, duplicates, outdated versions, and audits shell config files for stale paths. Generates Markdown report with dedup/upgrade recommendations. |
| `translate-tts` | `bash translate-tts/scripts/run_translate_tts.sh --text "你好" --langs "英文,日文"` | Chinese → multi-language translation + TTS via Ollama + Qwen3-TTS (requires conda env `qwen3-tts`). Supports 10 languages with concurrent translation and retry logic. |
| `ncm-to-wav` | `bash ncm-to-wav/scripts/ncm_to_wav.sh -i "$HOME/Music/网易云音乐"` | Batch decode NetEase `.ncm` files to `.wav` with optional output directory, force overwrite, and source deletion. |
| `call-graph-image` | Invoke via `/call-graph-image` skill in any Python project | Analyzes Python codebase method-level call graph, generates GPT-image-2 prompt for blueprint-style architecture topology diagram. Auto-detects project type (web/library/CLI/pipeline). |

## Build & Validation

No repo-wide build step. Syntax checks before committing:

```bash
bash -n translate-tts/scripts/run_translate_tts.sh
bash -n ncm-to-wav/scripts/ncm_to_wav.sh
python3 -m py_compile translate-tts/scripts/translate_tts.py
```

## Coding Style

- **Python**: 4-space indent, type hints where useful, standard-library-first. PEP 8 compliant.
- **Bash**: `#!/usr/bin/env bash` with `set -euo pipefail` (or `set -o pipefail` when `set -e` causes issues).
- Skill directories use kebab-case (`translate-tts`); entry documents always named `SKILL.md`.
- Helper scripts under `scripts/`, named by action (e.g. `run_translate_tts.sh`).

## Commit Convention

Short subject with leading type: `feat:`, `fix:`, `refactor:`. Imperative mood.

When committing, use this trailer:
```
Co-authored-by: Claude <noreply@anthropic.com>
```

## Skill Structure Convention

Each skill directory must contain:
- `SKILL.md` (or `skill.md` for newer skills) — YAML frontmatter (`name`, `description`) + markdown body. The description is the primary trigger mechanism for AI agents.
- `scripts/` — Executable bash/python/powershell scripts (optional for pure-prompt skills like `call-graph-image`).

**Discovery mechanism:** Skills are symlinked into `~/.claude/skills/` for Claude Code discovery. 

**Packaging:** Uses the skill-creator toolchain:
```bash
python3 ~/.claude/skills/skill-creator/scripts/init_skill.py <name> --path .
python3 ~/.claude/skills/skill-creator/scripts/package_skill.py ./<name>
```

**Pure-prompt skills:** Skills like `call-graph-image` contain only instructions in the skill file, no executable scripts. The AI agent performs all analysis and prompt generation directly.

## toolcheck Internals

**Cross-platform architecture:**
- Bash script (`toolcheck.sh`) for macOS/Linux with three version-fetching backends: `brew:`, `gh:`, `gh_tags:`
- PowerShell script (`toolcheck.ps1`) for Windows with dynamic upgrade command resolution (`Resolve-UpgradeCmd`) that auto-detects winget/choco/pip/conda installations
- Both scripts include symlink-deduplicating path scanner and config file audit

**Deduplication algorithm:**
1. Version highest → keep
2. Package manager path (homebrew/winget/choco/scoop) → prioritize over manual installs
3. PATH order → keep earlier entry

**Config audit:** Scans `~/.zshrc`, `~/.zprofile`, `~/.bashrc`, `~/.config/fish/config.fish` (Unix) or user/system PATH (Windows) for hardcoded version paths.

**Adding new tools:** Append a `check_tool` call with 5 args: `name`, `cmd`, `ver_cmd`, `latest_method`, `upgrade_cmd`. PowerShell version uses `Check-Tool` function with similar signature.

## translate-tts Internals

**Translation layer:** Concurrent `ThreadPoolExecutor` calls to Ollama (`translategemma` model by default). Automatic retry logic (3 attempts with exponential backoff: 1s, 2s, 4s) handles transient Ollama errors.

**TTS layer:** Supports 10 languages (zh/en/fr/de/ru/it/es/pt/ja/ko) via Qwen3-TTS. Each language has predefined speaker mappings. Audio generation includes duration validation and retry/fallback mechanisms.

**Input formats:**
- Simple: `--text "你好" --langs "英文,日文"`
- Per-line pairs: Each line as `语言:句子` (auto-detected, `--langs` ignored)

**Output structure:** `~/Downloads/translate_tts/<YYYYmmdd_HHMMSS_mmm>/` containing `translations.txt`, `result.json`, and `*.wav` files.

**Windows compatibility:** Direct Python path usage avoids GBK encoding issues with `conda run`. Script auto-detects conda environment from `sys.executable`.
