---
name: ncm-to-wav
description: Use when users need to convert NetEase Cloud Music .ncm files to .wav, including batch folder conversion, output path control, overwrite behavior, or source cleanup after conversion.
---

# NCM To WAV Skill

## Trigger Rules

Trigger this skill when the request implies:

- 将网易云 `.ncm` 音频转换为 `.wav`
- 批量转换音乐目录中的 `.ncm` 文件
- 控制输出目录、覆盖策略、是否删除源文件

Do not require explicit `$ncm-to-wav`.

## Scope Boundary

This skill is independent from `translate-tts`.

- `ncm-to-wav` only handles `.ncm -> .wav` conversion.
- `translate-tts` only handles translation + TTS.
- No ordering dependency between the two skills.

## Core Script

Core implementation script:

- `${CODEX_HOME:-$HOME/.codex}/skills/ncm-to-wav/scripts/ncm_to_wav.sh`

## Recommended Commands

Global skill root:

```bash
SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/ncm-to-wav"
bash "$SKILL_ROOT/scripts/ncm_to_wav.sh" -i "$HOME/Music/网易云音乐"
```

With output directory:

```bash
bash "$SKILL_ROOT/scripts/ncm_to_wav.sh" -i "$HOME/Music/网易云音乐" -o "$HOME/Music/wav"
```

## Common Options

- `-i, --input`：输入 `.ncm` 文件或目录（默认 `~/Music/网易云音乐`）
- `-o, --output`：输出根目录（保持原目录结构）
- `-f, --force`：覆盖已有 `.wav`
- `--delete-source`：转换成功后删除源 `.ncm`
- `--keep-temp`：保留临时解码文件用于排障
