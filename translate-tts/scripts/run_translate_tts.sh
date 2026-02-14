#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Resolve symlinks to get actual project directory
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
CONDA_ENV="qwen3-tts"
PY_SCRIPT="$PROJECT_ROOT/scripts/translate_tts.py"

ensure_conda() {
  if command -v conda >/dev/null 2>&1; then
    return 0
  fi
  local candidates=(
    "$HOME/miniconda3/etc/profile.d/conda.sh"
    "$HOME/anaconda3/etc/profile.d/conda.sh"
    "/opt/miniconda3/etc/profile.d/conda.sh"
    "/opt/anaconda3/etc/profile.d/conda.sh"
    "/usr/local/miniconda3/etc/profile.d/conda.sh"
    "/usr/local/anaconda3/etc/profile.d/conda.sh"
  )
  local c
  for c in "${candidates[@]}"; do
    if [ -f "$c" ]; then
      # shellcheck disable=SC1090
      source "$c"
      break
    fi
  done
  command -v conda >/dev/null 2>&1
}

if ! ensure_conda; then
  echo "[错误] 未找到 conda，请先安装并创建环境: conda create -n ${CONDA_ENV} python=3.12 -c conda-forge" >&2
  exit 1
fi

exec conda run -n "${CONDA_ENV}" --no-capture-output python "$PY_SCRIPT" "$@"
