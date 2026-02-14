import argparse
import os
import shutil
from pathlib import Path


CLAUDE_AGENT_TEMPLATE = """---
name: translate-tts
description: Use when users ask to translate Chinese text to one or more languages and generate speech audio, dubbing clips, pronunciation audio, or multilingual read-aloud files.
model: sonnet
---

Use this workflow for translation + TTS tasks.

Skill directory:
{skill_dir}

Primary commands:

1) Full pipeline (translate + TTS)
   `conda run -n qwen3-tts --no-capture-output python "{translate_tts}" --text "你好世界" --langs "英文,日文,韩文"`

2) Translation only
   `conda run -n qwen3-tts --no-capture-output python "{translate_only}" --text "你好世界" --langs "英文,日文,韩文"`

Defaults:
- Output root: `~/Downloads/translate_tts`
- Each run creates a timestamp subdirectory
- Files: `translations.txt`, `result.json`, `*.wav`
"""


def safe_remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def install_codex_skill(skill_dir: Path, codex_home: Path, mode: str) -> Path:
    target = codex_home / "skills" / skill_dir.name
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_remove(target)

    if mode == "symlink":
        target.symlink_to(skill_dir, target_is_directory=True)
    else:
        shutil.copytree(skill_dir, target)
    return target


def install_claude_agent(skill_dir: Path, claude_home: Path) -> Path:
    agents_dir = claude_home / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    target = agents_dir / "translate-tts.md"
    content = CLAUDE_AGENT_TEMPLATE.format(
        skill_dir=str(skill_dir),
        translate_tts=str(skill_dir / "scripts" / "translate_tts.py"),
        translate_only=str(skill_dir / "scripts" / "translate_only.py"),
    )
    target.write_text(content, encoding="utf-8")
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install translate-tts as global skill for Codex and Claude Code.")
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent), help="translate-tts skill dir")
    parser.add_argument("--codex-home", default=os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    parser.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill_dir = Path(args.skill_dir).resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    claude_home = Path(args.claude_home).expanduser().resolve()

    codex_target = install_codex_skill(skill_dir, codex_home, args.mode)
    claude_target = install_claude_agent(skill_dir, claude_home)

    print(f"codex_skill={codex_target}")
    print(f"claude_agent={claude_target}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
