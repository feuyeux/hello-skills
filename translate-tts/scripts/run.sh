#!/usr/bin/env bash
set -euo pipefail

# Always run the tool inside the conda environment to ensure torch and deps are available.
# Usage examples:
#   ./run.sh --text "你好世界" --langs "en,ja,ko"

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)

CONDA_ENV="qwen3-tts"

# Prefer conda run to avoid shell-specific activation
if ! command -v conda >/dev/null 2>&1; then
  echo "[错误] 未找到 conda，请先安装并创建环境: conda create -n ${CONDA_ENV} python=3.12 -c conda-forge" >&2
  exit 1
fi

# Ensure output directory from script defaults is present (script also ensures it)
mkdir -p /d/talking 2>/dev/null || true

exec conda run -n "${CONDA_ENV}" --no-capture-output python "$PROJECT_ROOT/scripts/translate_then_tts.py" "$@"