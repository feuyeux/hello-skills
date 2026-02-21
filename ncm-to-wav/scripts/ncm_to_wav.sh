#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Batch convert Netease Cloud Music .ncm files to .wav

Usage:
  ncm_to_wav.sh [options]

Options:
  -i, --input PATH      Input .ncm file or directory (default: ~/Music/网易云音乐)
  -o, --output DIR      Output root directory. If omitted, writes beside each source file.
  -f, --force           Overwrite existing .wav files.
  --delete-source       Delete .ncm after successful conversion.
  --keep-temp           Keep temporary decoded files for debugging.
  -h, --help            Show this help message.

Examples:
  ncm_to_wav.sh
  ncm_to_wav.sh -i "$HOME/Music/网易云音乐"
  ncm_to_wav.sh -i "$HOME/Music/网易云音乐" -o "$HOME/Music/wav"
EOF
}

log() {
  printf '%s\n' "$*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing dependency: $1"
    exit 1
  fi
}

INPUT_PATH="${HOME}/Music/网易云音乐"
OUTPUT_ROOT=""
FORCE=0
DELETE_SOURCE=0
KEEP_TEMP=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    -i|--input)
      INPUT_PATH="$2"
      shift 2
      ;;
    -o|--output)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    -f|--force)
      FORCE=1
      shift
      ;;
    --delete-source)
      DELETE_SOURCE=1
      shift
      ;;
    --keep-temp)
      KEEP_TEMP=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [ ! -e "$INPUT_PATH" ]; then
  log "Input does not exist: $INPUT_PATH"
  exit 1
fi

require_cmd ffmpeg
require_cmd python3

NCMDUMP_BIN=""

if command -v ncmdump >/dev/null 2>&1; then
  NCMDUMP_BIN="$(command -v ncmdump)"
else
  CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/ncm-to-wav"
  VENV_DIR="${CACHE_ROOT}/venv"
  NCMDUMP_BIN="${VENV_DIR}/bin/ncmdump"
  if [ ! -x "$NCMDUMP_BIN" ]; then
    log "ncmdump not found; preparing private venv at: $VENV_DIR"
    mkdir -p "$CACHE_ROOT"
    python3 -m venv "$VENV_DIR"
    "${VENV_DIR}/bin/pip" install --quiet ncmdump
  fi
fi

if [ ! -x "$NCMDUMP_BIN" ]; then
  log "Failed to prepare ncmdump binary."
  exit 1
fi

if [ -n "$OUTPUT_ROOT" ]; then
  mkdir -p "$OUTPUT_ROOT"
fi

INPUT_IS_FILE=0
INPUT_ROOT="$INPUT_PATH"
if [ -f "$INPUT_PATH" ]; then
  INPUT_IS_FILE=1
  case "$INPUT_PATH" in
    *.ncm) ;;
    *)
      log "Input file must end with .ncm: $INPUT_PATH"
      exit 1
      ;;
  esac
  INPUT_ROOT="$(cd -- "$(dirname -- "$INPUT_PATH")" && pwd -P)"
else
  INPUT_ROOT="$(cd -- "$INPUT_PATH" && pwd -P)"
fi

to_process=0
success=0
failed=0
skipped=0

convert_one() {
  local ncm="$1"
  local out_wav=""
  local rel=""
  local base=""
  local out_dir=""
  local tmpdir=""
  local decoded=""

  to_process=$((to_process + 1))
  base="$(basename "$ncm" .ncm)"

  if [ -n "$OUTPUT_ROOT" ]; then
    if [ "$INPUT_IS_FILE" -eq 1 ]; then
      out_wav="${OUTPUT_ROOT}/${base}.wav"
    else
      rel="${ncm#${INPUT_ROOT}/}"
      rel="${rel%.ncm}"
      out_wav="${OUTPUT_ROOT}/${rel}.wav"
    fi
  else
    out_wav="$(dirname "$ncm")/${base}.wav"
  fi

  out_dir="$(dirname "$out_wav")"
  mkdir -p "$out_dir"

  if [ -f "$out_wav" ] && [ "$FORCE" -ne 1 ]; then
    log "[SKIP] Exists: $out_wav"
    skipped=$((skipped + 1))
    return
  fi

  tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/ncm-to-wav.XXXXXX")"

  if ! "$NCMDUMP_BIN" -c -o "$tmpdir" "$ncm" >/dev/null 2>&1; then
    log "[FAIL] Decode failed: $ncm"
    failed=$((failed + 1))
    if [ "$KEEP_TEMP" -ne 1 ]; then
      rm -rf "$tmpdir"
    fi
    return
  fi

  while IFS= read -r -d '' file; do
    decoded="$file"
    break
  done < <(find "$tmpdir" -type f -print0)

  if [ -z "$decoded" ]; then
    log "[FAIL] Decoded file missing: $ncm"
    failed=$((failed + 1))
    if [ "$KEEP_TEMP" -ne 1 ]; then
      rm -rf "$tmpdir"
    fi
    return
  fi

  if ffmpeg -y -loglevel error -i "$decoded" -vn -acodec pcm_s16le "$out_wav"; then
    log "[OK] $out_wav"
    success=$((success + 1))
    if [ "$DELETE_SOURCE" -eq 1 ]; then
      rm -f "$ncm"
    fi
  else
    log "[FAIL] ffmpeg failed: $ncm"
    failed=$((failed + 1))
  fi

  if [ "$KEEP_TEMP" -ne 1 ]; then
    rm -rf "$tmpdir"
  fi
}

if [ "$INPUT_IS_FILE" -eq 1 ]; then
  convert_one "$INPUT_PATH"
else
  while IFS= read -r -d '' ncm; do
    convert_one "$ncm"
  done < <(find "$INPUT_PATH" -type f -name '*.ncm' -print0)
fi

log "Summary: total=${to_process}, success=${success}, skipped=${skipped}, failed=${failed}"
if [ "$failed" -gt 0 ]; then
  exit 2
fi
