# GEMINI.md - Project Context & Guidelines

This repository, `hello-skills`, is a collection of specialized "skills" (plugins/tools) designed for AI agents (such as Gemini CLI, Codex, or Claude). Each skill is self-contained and provides specific functionality through scripts and a `SKILL.md` metadata file.

## Project Overview

- **Purpose:** To provide modular, script-based capabilities for translation, audio processing, system diagnostics, and code visualization.
- **Architecture:** The project is organized into skill-specific directories (kebab-case). Each directory MUST contain a `SKILL.md` (or `skill.md`) contract and optionally a `scripts/` folder (pure-prompt skills like `call-graph-image` have no scripts).
- **Core Technologies:** 
  - **Python:** 4-space indentation, type hints, standard-library-first.
  - **Bash:** `#!/usr/bin/env bash` with `set -euo pipefail`.
  - **PowerShell:** Cross-platform support for Windows tooling (toolcheck.ps1).
  - **Ollama:** Utilized for local LLM-based translation (defaults to `translategemma`).
  - **Qwen3-TTS:** Used for multi-lingual speech synthesis (10 languages).
  - **Conda:** Preferred for managing specialized Python environments (e.g., `qwen3-tts`).

## Key Skills & Execution

| Skill | Entry Point | Purpose |
| --- | --- | --- |
| **toolcheck** | `bash toolcheck/scripts/toolcheck.sh` (macOS/Linux) or `pwsh toolcheck/scripts/toolcheck.ps1` (Windows) | Local development tool audit with dedup/upgrade recommendations |
| **translate-tts** | `bash translate-tts/scripts/run_translate_tts.sh` | Chinese-to-multilingual translation + TTS |
| **ncm-to-wav** | `bash ncm-to-wav/scripts/ncm_to_wav.sh` | Batch `.ncm` to `.wav` conversion |
| **call-graph-image** | Invoke via skill system in Python project | Generate GPT-image-2 prompt for blueprint-style architecture diagram |
| **foreign-close-reading** | `python3 foreign-close-reading/scripts/split_sentences.py` + `build_reader.py` | Sentence-by-sentence close reading of foreign-language originals into an interactive HTML reader |

## Development & Validation

### Syntax Checks
Before committing, run the following to ensure script integrity:
- **Bash:** `bash -n <script_path>`
- **Python:** `python3 -m py_compile <script_path>`

### Coding Standards
- Python: Keep changes PEP 8-compliant.
- Bash: Ensure clean syntax and robust error handling (`set -euo pipefail`).
- Directory Naming: Use kebab-case for skill folders (e.g., `translate-tts`).

## Commit & PR Guidelines

### Tool Identity
When committing as **Gemini**, you MUST use the following identity:
- **Author:** `Gemini <noreply@google.com>`
- **Co-authored-by:** `Co-authored-by: Gemini <noreply@google.com>`

**Example Command:**
```bash
git commit -m "feat(scope): message" \
  --author="Gemini <noreply@google.com>" \
  -m "Co-authored-by: Gemini <noreply@google.com>"
```

### Commit Style
- Prefix: Use `feat:`, `fixed:`, `refactor:`, `docs:`.
- Tone: Short subject lines, imperative mood.

## Usage for AI Agents

These skills are designed to be triggered implicitly by the agent. The `SKILL.md` files provide the "Trigger Rules" and "Scope Boundaries" used to decide when to invoke a specific tool. Always verify output structure remains consistent with existing `result.json` or Markdown table formats.
