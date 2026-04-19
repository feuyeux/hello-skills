# Repository Guidelines

## Project Structure & Module Organization

This repository is a small collection of independent skills. Each skill lives in its own top-level directory with a `SKILL.md` contract and a `scripts/` folder:

- `translate-tts/`: Chinese-to-multilingual translation plus TTS (`scripts/translate_tts.py`, `scripts/run_translate_tts.sh`)
- `ncm-to-wav/`: batch `.ncm` to `.wav` conversion (`scripts/ncm_to_wav.sh`)
- `toolcheck/`: local development tool audit (`scripts/toolcheck.sh`)

Top-level docs such as `README.md` and `get_latest.md` explain usage and version-source rules. Hidden folders like `.agents/` and `.claude/` are agent mirrors and are ignored by Git.

## Build, Test, and Development Commands

There is no repo-wide build step. Run skills from their script entry points:

```bash
bash translate-tts/scripts/run_translate_tts.sh --text "你好" --langs "英文,日文"
bash ncm-to-wav/scripts/ncm_to_wav.sh -i "$HOME/Music/网易云音乐"
bash toolcheck/scripts/toolcheck.sh
```

Checks before committing:

```bash
bash -n translate-tts/scripts/run_translate_tts.sh
bash -n ncm-to-wav/scripts/ncm_to_wav.sh
python3 -m py_compile translate-tts/scripts/translate_tts.py
```

## Coding Style & Naming Conventions

Follow the existing style:

- Python: 4-space indentation, type hints where useful, standard-library-first code.
- Bash: `#!/usr/bin/env bash` with `set -euo pipefail` for executable scripts.
- Skill directories use kebab-case (`translate-tts`); entry documents are always named `SKILL.md`.
- Keep helper scripts under `scripts/` and name them by action, for example `run_translate_tts.sh`.

No formatter or linter config is checked in, so keep changes PEP 8-compliant and shell syntax clean.

## Testing Guidelines

No automated test framework is committed yet. For script changes, run syntax checks and one smoke test. Document local dependencies in `SKILL.md` when behavior changes.

## Commit & Pull Request Guidelines

Recent history uses short subject lines with a leading change type, such as `feat: ...`, `fixed: ...`, and `refactor: ...`. Keep commits focused and imperative, and keep the prefix consistent.

When committing as an AI tool, both the Git author and the `Co-authored-by` trailer must match the tool identity making the commit:

| Tool | Author | Co-authored-by |
| --- | --- | --- |
| Claude | `Claude <noreply@anthropic.com>` | `Co-authored-by: Claude <noreply@anthropic.com>` |
| Codex | `Codex <noreply@openai.com>` | `Co-authored-by: Codex <noreply@openai.com>` |
| Gemini | `Gemini <noreply@google.com>` | `Co-authored-by: Gemini <noreply@google.com>` |
| OpenCode | `OpenCode <opencode@ai.local>` | `Co-authored-by: OpenCode <opencode@ai.local>` |

Example:

```sh
git commit -m "<type>(<scope>): <message>" \
  --author="<ToolName> <noreply@xxx.com>" \
  -m "Co-authored-by: <ToolName> <noreply@xxx.com>"
```

Pull requests should include:

- a brief summary of the skill or script changed
- manual validation steps and sample commands run
- any dependency or environment changes
- example output or screenshots when the user-facing behavior changes
