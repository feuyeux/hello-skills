#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)

exec bash "$PROJECT_ROOT/translate-tts/scripts/run_translate_tts.sh" "$@"
