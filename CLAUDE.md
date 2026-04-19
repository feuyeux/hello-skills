# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A collection of independent AI agent skills (for Claude Code, Gemini CLI, Codex, etc.). Each skill is a self-contained directory with a `SKILL.md` (metadata + instructions) and a `scripts/` folder. Top-level docs (`README.md`, `get_latest.md`) explain usage and version-source rules. Hidden folders (`.agents/`, `.claude/`) are agent mirrors ignored by Git.

## Skills

| Skill | Entry Point | Description |
|-------|------------|-------------|
| `toolcheck` | `bash toolcheck/scripts/toolcheck.sh` | Scans 25 dev tools for version conflicts, duplicates, outdated versions, and audits shell config files for stale paths |
| `translate-tts` | `bash translate-tts/scripts/run_translate_tts.sh --text "你好" --langs "英文,日文"` | Chinese → multi-language translation + TTS via Ollama + Qwen3-TTS (requires conda env `qwen3-tts`) |
| `ncm-to-wav` | `bash ncm-to-wav/scripts/ncm_to_wav.sh -i "$HOME/Music/网易云音乐"` | Batch decode NetEase `.ncm` files to `.wav` |

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
- `SKILL.md` — YAML frontmatter (`name`, `description`) + markdown body. The description is the primary trigger mechanism for AI agents.
- `scripts/` — Executable bash/python scripts.

Skills are symlinked into `~/.claude/skills/` for Claude Code discovery. Packaging uses the skill-creator toolchain:
```bash
python3 ~/.claude/skills/skill-creator/scripts/init_skill.py <name> --path .
python3 ~/.claude/skills/skill-creator/scripts/package_skill.py ./<name>
```

## toolcheck Internals

The script has three version-fetching backends (`brew:`, `gh:`, `gh_tags:`) and a symlink-deduplicating path scanner. After the tool table, it runs a config audit scanning `~/.zshrc`, `~/.zprofile`, `~/.bashrc`, etc. for hardcoded version paths. To add a new tool, append a `check_tool` call with 5 args: `name`, `cmd`, `ver_cmd`, `latest_method`, `upgrade_cmd`.

## translate-tts Internals

Translation uses concurrent `ThreadPoolExecutor` calls to Ollama (`translategemma` model). TTS supports 10 languages (zh/en/fr/de/ru/it/es/pt/ja/ko) via Qwen3-TTS. Output goes to `~/Downloads/translate_tts/`.
