#!/bin/bash

set -euo pipefail

ENV_NAME="qwen3-tts"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

log() { echo "$*"; }
warn() { echo "⚠ $*"; }
die() { echo "错误: $*" >&2; exit 1; }

usage() {
    cat <<'EOF'
用法:
  ./run_single_tts.sh "句子" 语种 [--output output.wav] [--model-path /path/to/model] [--speaker name] [--instruct text]

语种支持（自然语言）:
  中文、英文/英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语/日文、韩语/韩文

说明:
  默认按语种自动选择 speaker（可用 --speaker 手动覆盖）。
  默认不传 instruct，以获得更高文本一致性；需要风格控制时再传 --instruct。
EOF
}

first_existing_dir() {
    for p in "$@"; do
        [ -n "$p" ] && [ -d "$p" ] && echo "$p" && return 0
    done
    return 1
}

first_project_dir() {
    for p in "$@"; do
        if [ -n "$p" ] && [ -d "$p" ] && { [ -f "$p/pyproject.toml" ] || [ -f "$p/setup.py" ]; }; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

detect_os() {
    if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "WSL"
        return
    fi
    case "$(uname -s)" in
        Darwin*) echo "Mac" ;;
        Linux*) echo "Linux" ;;
        CYGWIN*|MINGW*|MSYS*) echo "Windows" ;;
        *) echo "Unknown" ;;
    esac
}

find_conda_base() {
    local candidates=()
    if [ -n "${CONDA_PREFIX:-}" ]; then
        candidates+=("$(dirname "$(dirname "$CONDA_PREFIX")")")
    fi
    candidates+=(
        "${HOME}/miniconda3"
        "${HOME}/anaconda3"
        "/opt/miniconda3"
        "/opt/anaconda3"
        "/usr/local/miniconda3"
        "/usr/local/anaconda3"
        "${USERPROFILE:-}/miniconda3"
        "${USERPROFILE:-}/anaconda3"
    )

    local from_candidates
    from_candidates="$(first_existing_dir "${candidates[@]}")" || true
    if [ -n "$from_candidates" ] && [ -f "$from_candidates/etc/profile.d/conda.sh" ]; then
        echo "$from_candidates"
        return
    fi

    if command -v conda >/dev/null 2>&1; then
        local conda_bin
        conda_bin="$(command -v conda)"
        local inferred
        inferred="$(dirname "$(dirname "$conda_bin")")"
        if [ -f "$inferred/etc/profile.d/conda.sh" ]; then
            echo "$inferred"
            return
        fi
    fi
}

resolve_source_dir() {
    first_project_dir \
        "${QWEN3_TTS_SOURCE_DIR:-}" \
        "/Users/han/zoo/Qwen3-TTS" \
        "${HOME}/zoo/Qwen3-TTS" \
        "${SCRIPT_DIR}/Qwen3-TTS" \
        "${SCRIPT_DIR}" || true
}

resolve_model_dir() {
    first_existing_dir \
        "${QWEN3_TTS_MODEL_PATH:-}" \
        "${QWEN3_TTS_LOCAL_SOURCE:-}/Qwen3-TTS-12Hz-1.7B-CustomVoice" \
        "/Users/han/zoo/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice" \
        "${HOME}/zoo/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice" \
        "${SCRIPT_DIR}/Qwen3-TTS-12Hz-1.7B-CustomVoice" || true
}

ensure_torch() {
    if python -c "import torch" >/dev/null 2>&1; then
        local version cuda
        version="$(python -c "import torch;print(torch.__version__)")"
        cuda="$(python -c "import torch;print('Yes' if torch.cuda.is_available() else 'No')")"
        log "✓ PyTorch 已安装: ${version} (CUDA: ${cuda})"
        return
    fi

    local os_name="$1"
    log "安装 PyTorch..."
    if [ "$os_name" = "Linux" ] || [ "$os_name" = "WSL" ]; then
        if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
        else
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
        fi
    else
        pip install torch torchvision torchaudio
    fi
}

ensure_basic_deps() {
    local missing=()
    python -c "import soundfile" >/dev/null 2>&1 || missing+=("soundfile")
    python -c "import numpy" >/dev/null 2>&1 || missing+=("numpy")
    python -c "import transformers" >/dev/null 2>&1 || missing+=("transformers")
    python -c "import accelerate" >/dev/null 2>&1 || missing+=("accelerate")
    if [ "${#missing[@]}" -gt 0 ]; then
        log "安装缺失依赖: ${missing[*]}"
        pip install -q "${missing[@]}"
    else
        log "✓ 所有依赖已安装"
    fi
}

ensure_qwen_tts() {
    if ! python -c "import qwen_tts" >/dev/null 2>&1; then
        log "安装 qwen_tts..."
        if [ -n "${QWEN3_TTS_LOCAL_SOURCE:-}" ]; then
            pip install -e "$QWEN3_TTS_LOCAL_SOURCE" --no-build-isolation
        else
            pip install "git+https://github.com/QwenLM/Qwen3-TTS.git"
        fi
    fi

    if [ -n "${QWEN3_TTS_LOCAL_SOURCE:-}" ]; then
        local installed
        installed="$(python -c "import importlib.util, os; s=importlib.util.find_spec('qwen_tts'); print(os.path.realpath(s.origin) if s and s.origin else '')" 2>/dev/null || true)"
        if [[ "$installed" != "$QWEN3_TTS_LOCAL_SOURCE"* ]]; then
            log "切换到本地源码版本: $QWEN3_TTS_LOCAL_SOURCE"
            pip install -e "$QWEN3_TTS_LOCAL_SOURCE" --no-build-isolation || warn "本地源码切换失败，继续使用当前版本"
        else
            log "✓ qwen_tts 来源已是本地源码"
        fi
    fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "$#" -lt 2 ]; then
    usage
    exit 0
fi

OS="$(detect_os)"
log "检测到操作系统: $OS"

if [ "$OS" = "Windows" ]; then
    export HF_HOME="${HF_HOME:-${USERPROFILE}/.cache/huggingface}"
else
    export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
fi
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
if ! mkdir -p "$HF_HOME" "$HUGGINGFACE_HUB_CACHE" 2>/dev/null; then
    warn "当前 HuggingFace 缓存目录不可写，回退到 ${HOME}/.cache/huggingface"
    export HF_HOME="${HOME}/.cache/huggingface"
    export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
    mkdir -p "$HF_HOME" "$HUGGINGFACE_HUB_CACHE"
fi

CONDA_BASE="$(find_conda_base)"
[ -n "$CONDA_BASE" ] || die "无法找到 conda，请先安装 Miniconda/Anaconda。"
source "$CONDA_BASE/etc/profile.d/conda.sh"
log "激活 ${ENV_NAME} 环境..."
conda activate "$ENV_NAME" || die "无法激活环境 ${ENV_NAME}。"
log "✓ 已激活 ${ENV_NAME} 环境"

QWEN3_TTS_LOCAL_SOURCE="$(resolve_source_dir)"
[ -n "$QWEN3_TTS_LOCAL_SOURCE" ] && log "检测到本地 Qwen3-TTS 源码: $QWEN3_TTS_LOCAL_SOURCE"

log ""
log "=== 检查依赖 ==="
python --version >/dev/null 2>&1 || die "Python 不可用"
ensure_torch "$OS"
ensure_basic_deps
ensure_qwen_tts

RESOLVED_MODEL_PATH="$(resolve_model_dir)"
if [ -n "$RESOLVED_MODEL_PATH" ]; then
    export QWEN3_TTS_MODEL_PATH="$RESOLVED_MODEL_PATH"
    log "✓ 使用模型目录: $QWEN3_TTS_MODEL_PATH"
else
    warn "未找到本地模型目录，将在运行时尝试在线加载模型"
fi

if python -c "import torch; exit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1; then
    python -c "import flash_attn" >/dev/null 2>&1 || warn "flash-attn 未安装（可选优化）"
fi

log ""
log "运行 single_tts.py..."
python -u single_tts.py "$@"
