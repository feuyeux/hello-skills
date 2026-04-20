#!/usr/bin/env bash
# toolcheck.sh — Check 25 dev tools for conflicts, upgrades, and missing installs
# pipefail without -e: errors set $? but don't abort; handled manually per-command
set -o pipefail

# ── Parse flags ───────────────────────────────────────────────────
# Default: quiet (file-only). Use -v for verbose console output.
CONSOLE=false
while getopts "v" opt; do
  case $opt in
    v) CONSOLE=true ;;
    *) ;;
  esac
done

# macOS lacks coreutils timeout; detect available command
if command -v gtimeout &>/dev/null; then
  TOCMD=(gtimeout 3)
elif command -v timeout &>/dev/null; then
  TOCMD=(timeout 3)
else
  TOCMD=()
fi

# ── Helpers ───────────────────────────────────────────────────────

truncate_str() {
  local s="$1" max="${2:-40}"
  if [ ${#s} -le "$max" ]; then echo "$s"
  else echo "...${s: -$((max-3))}"; fi
}

extract_semver() {
  echo "$1" | grep -oE '[0-9]+\.[0-9]+[0-9.a-zA-Z_-]*' | head -1
}

gh_latest() {
  local repo="$1" response http_code body v
  response=$(curl -sfL --max-time 3 -w '\n%{http_code}' "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null) || { echo "N/A"; return; }
  http_code=$(tail -1 <<< "$response")
  body=$(sed '$d' <<< "$response")
  if [ "$http_code" = "403" ] || [ "$http_code" = "429" ]; then echo "N/A"; return; fi
  v=$(echo "$body" | python3 -c "import sys,json;d=json.load(sys.stdin);t=d.get('tag_name','');print(t.lstrip('v'))" 2>/dev/null)
  echo "${v:-N/A}"
}

# Get latest version from GitHub tags (for repos without formal releases)
# Fetches recent tags and picks the highest semver via sort -V to avoid
# TOCTOU issues with tag creation order (e.g. backport tags appearing first).
gh_tags_latest() {
  local repo="$1" response http_code body v
  response=$(curl -sfL --max-time 3 -w '\n%{http_code}' "https://api.github.com/repos/$repo/tags?per_page=30" 2>/dev/null) || { echo "N/A"; return; }
  http_code=$(tail -1 <<< "$response")
  body=$(sed '$d' <<< "$response")
  if [ "$http_code" = "403" ] || [ "$http_code" = "429" ]; then echo "N/A"; return; fi
  v=$(echo "$body" | python3 -c "
import sys, json, re
tags = json.load(sys.stdin)
versions = []
for t in tags:
    name = t['name'].lstrip('v')
    if re.match(r'^[0-9]+\\.[0-9]+', name):
        versions.append(name)
if versions:
    print(versions[0])  # GitHub returns newest first for semver repos
else:
    print('')
" 2>/dev/null)
  echo "${v:-N/A}"
}

brew_latest() {
  local formula="$1"
  [ -z "$formula" ] && echo "N/A" && return
  command -v brew &>/dev/null || { echo "N/A"; return; }
  local v
  v=$("${TOCMD[@]}" brew info --json=v2 "$formula" 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['formulae'][0]['versions']['stable'])" 2>/dev/null)
  echo "${v:-N/A}"
}

version_lt() {
  [ "$1" = "$2" ] && return 1
  [ -z "$1" ] && return 1
  [ -z "$2" ] && return 1
  local smallest
  smallest=$(printf '%s\n%s\n' "$1" "$2" | LC_ALL=C sort -V 2>/dev/null || printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -1)
  smallest=$(head -1 <<< "$smallest")
  [ "$smallest" = "$1" ]
}

# ── Storage ───────────────────────────────────────────────────────
# Each row: name|version|status|path|latest|operation|note
# For duplicate sub-rows: ↳|version_at_path|⚠ 重复|path|latest|operation|note

ROWS_DUP=()
ROWS_OLD=()
ROWS_OK=()
ROWS_NA=()
ROWS_MISS=()

# macOS-only tools — show "— 不适用" on Linux
MAC_ONLY_TOOLS=(swift)

LATEST_CACHE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/toolcheck.latest.XXXXXX")
LATEST_METHODS=()
LATEST_FILES=()
LATEST_PIDS=()

cleanup() {
  [ -n "${LATEST_CACHE_DIR:-}" ] && [ -d "$LATEST_CACHE_DIR" ] && rm -rf "$LATEST_CACHE_DIR"
}

trap cleanup EXIT

latest_file_for_method() {
  local method="$1"
  local i
  for (( i=0; i<${#LATEST_METHODS[@]}; i++ )); do
    if [ "${LATEST_METHODS[$i]}" = "$method" ]; then
      echo "${LATEST_FILES[$i]}"
      return 0
    fi
  done
  return 1
}

resolve_latest_method() {
  local latest_method="$1"
  case "$latest_method" in
    brew:*)      brew_latest "${latest_method#brew:}" ;;
    gh:*)        gh_latest "${latest_method#gh:}" ;;
    gh_tags:*)   gh_tags_latest "${latest_method#gh_tags:}" ;;
    none|"")     echo "N/A" ;;
    *)           echo "N/A" ;;
  esac
}

register_latest_prefetch() {
  local method="$1" file=""
  [ "$method" = "none" ] && return

  file=$(latest_file_for_method "$method" || true)
  if [ -n "$file" ]; then
    return
  fi

  file="${LATEST_CACHE_DIR}/latest_${#LATEST_METHODS[@]}.txt"
  LATEST_METHODS+=("$method")
  LATEST_FILES+=("$file")

  (
    resolve_latest_method "$method" > "$file"
  ) &
  LATEST_PIDS+=("$!")
}

prefetch_latest_versions() {
  # Accept method strings as arguments (deduplicates internally via register_latest_prefetch)
  local m
  for m in "$@"; do
    register_latest_prefetch "$m"
  done

  local pid
  for pid in "${LATEST_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

get_latest_version() {
  local latest_method="$1" file="" latest=""
  [ "$latest_method" = "none" ] && { echo "N/A"; return; }

  file=$(latest_file_for_method "$latest_method" || true)
  if [ -n "$file" ] && [ -f "$file" ]; then
    latest=$(cat "$file" 2>/dev/null)
    echo "${latest:-N/A}"
    return
  fi

  resolve_latest_method "$latest_method"
}

# Global return variables for collect_version_info (intentional — bash lacks
# multi-value returns; callers must read these immediately after each call).
VERSION_DISPLAY=""
VERSION_PARSED=""
VERSION_NOTE=""

collect_version_info() {
  local cmd_path="$1" ver_cmd="$2" cmd_dir="" raw_ver=""

  cmd_dir=$(cd -- "$(dirname -- "$cmd_path")" && pwd -P 2>/dev/null || dirname -- "$cmd_path")
  raw_ver=$(PATH="$cmd_dir:$PATH" "${TOCMD[@]}" bash -c "$ver_cmd" 2>&1 || echo "-")

  VERSION_DISPLAY=$(echo "$raw_ver" | head -1 | cut -c1-36)
  VERSION_PARSED=$(extract_semver "$raw_ver")
  VERSION_NOTE=""

  if echo "$raw_ver" | grep -qiE '^(.*error[: ]|.*JAVA_HOME|.*exception[: ])'; then
    VERSION_NOTE=$(echo "$raw_ver" | head -1 | cut -c1-20)
  fi
  if [ -z "$VERSION_PARSED" ]; then
    VERSION_NOTE="${VERSION_NOTE:+$VERSION_NOTE; }版本获取失败"
    VERSION_DISPLAY="-"
  fi
}

# Detect pip-installed tools and return appropriate upgrade command
# Returns pip upgrade command if installed via pip/conda, empty string otherwise
resolve_pip_upgrade() {
  local name="$1" cmd_path="$2"
  [ -z "$cmd_path" ] && return 1
  # Check if path is inside a conda/venv/python site-packages environment
  case "$cmd_path" in
    *anaconda*|*miniconda*|*conda*|*envs*|*venv*|*/site-packages/*)
      # Map tool name to pip package name
      local pip_pkg=""
      case "$name" in
        uv)      pip_pkg="uv" ;;
        hermes)  pip_pkg="hermes-agent" ;;
        *)       pip_pkg="$name" ;;
      esac
      [ -n "$pip_pkg" ] && echo "pip install --upgrade $pip_pkg" && return 0
      ;;
  esac
  return 1
}

# check_tool <name> <cmd> <ver_cmd> <latest_method> <upgrade_cmd>
check_tool() {
  local name="$1" cmd="$2" ver_cmd="$3" latest_method="$4" upgrade_cmd="$5"

  # Platform check: macOS-only tools on non-macOS → not applicable
  local is_mac_only=0
  for mot in "${MAC_ONLY_TOOLS[@]}"; do
    [ "$mot" = "$name" ] && is_mac_only=1 && break
  done
  if [ "$is_mac_only" -eq 1 ] && [ "$(uname -s)" != "Darwin" ]; then
    ROWS_NA+=("$name|-|— 不适用|-|N/A|跳过|仅 macOS")
    return
  fi

  # Find all paths, resolve symlinks to deduplicate
  local -a raw_paths=() paths=() seen_real=()
  while IFS= read -r p; do
    [ -n "$p" ] && raw_paths+=("$p")
  done < <(type -aP "$cmd" 2>/dev/null)
  for p in "${raw_paths[@]}"; do
    local rp
    rp=$(realpath "$p" 2>/dev/null || echo "$p")
    local dup=0
    for s in "${seen_real[@]}"; do
      [ "$s" = "$rp" ] && dup=1 && break
    done
    if [ "$dup" -eq 0 ]; then
      paths+=("$p")
      seen_real+=("$rp")
    fi
  done
  local num_paths=${#paths[@]}

  # Get latest version
  local latest="N/A"
  latest=$(get_latest_version "$latest_method")

  if [ "$num_paths" -eq 0 ]; then
    ROWS_MISS+=("$name|-|✗ 缺失|-|$latest|$upgrade_cmd|未安装")
    return
  fi

  local primary="${paths[0]}"
  # Override upgrade_cmd if installed via pip/conda
  local pip_cmd
  pip_cmd=$(resolve_pip_upgrade "$name" "$primary") && upgrade_cmd="$pip_cmd"
  collect_version_info "$primary" "$ver_cmd"
  local display_ver="$VERSION_DISPLAY"
  local parsed_ver="$VERSION_PARSED"
  local note="$VERSION_NOTE"

  if [ "$num_paths" -gt 1 ]; then
    # ── Duplicate: pick best install, mark others for removal ──
    # Best = highest version → managed path → earlier in PATH
    local best_idx=0 i

    # Score function: managed path gets higher score
    # AppData/Roaming gets lowest (-1) — prefer to remove user-roaming installs
    managed_score() {
      local p="$1"
      case "$p" in
        *AppData[/\\]Roaming*) echo -1 ;;
        *homebrew*|*Cellar*|*linuxbrew*|*nvm*|*rustup*|*cargo*|*npm*) echo 3 ;;
        */usr/local/*|*/usr/bin/*|*/opt/*) echo 1 ;;
        *) echo 0 ;;
      esac
    }

    for (( i=1; i<num_paths; i++ )); do
      collect_version_info "${paths[$i]}" "$ver_cmd"
      local cur_ver="$VERSION_PARSED"
      collect_version_info "${paths[$best_idx]}" "$ver_cmd"
      local best_ver="$VERSION_PARSED"

      # Higher version wins
      if [ -n "$cur_ver" ] && [ -n "$best_ver" ] && [ "$cur_ver" != "$best_ver" ]; then
        if version_lt "$best_ver" "$cur_ver"; then
          best_idx=$i; continue
        elif version_lt "$cur_ver" "$best_ver"; then
          continue
        fi
      fi

      # Same version: prefer managed path
      local cur_score best_score
      cur_score=$(managed_score "${paths[$i]}")
      best_score=$(managed_score "${paths[$best_idx]}")
      if [ "$cur_score" -gt "$best_score" ]; then
        best_idx=$i
      fi
      # If still tied, keep lower index (earlier in PATH)
    done

    for (( i=0; i<num_paths; i++ )); do
      local row_name version_i parsed_i note_i
      collect_version_info "${paths[$i]}" "$ver_cmd"
      version_i="$VERSION_DISPLAY"
      parsed_i="$VERSION_PARSED"
      note_i="$VERSION_NOTE"

      local op_i verdict_i
      if [ "$i" -eq "$best_idx" ]; then
        # Best: just keep (highest version wins)
        op_i="保留"
        verdict_i="★ 保留"
      else
        op_i="✗ 移除"
        verdict_i="✗ 移除"
      fi

      if [ "$i" -eq 0 ]; then
        row_name="$name"
      else
        row_name="  ↳"
      fi

      ROWS_DUP+=("$row_name|$version_i|⚠ 重复|$(truncate_str "${paths[$i]}" 40)|$latest|$op_i|$verdict_i")
    done
  elif [ -n "$parsed_ver" ] && [ "$latest" != "N/A" ] && version_lt "$parsed_ver" "$latest"; then
    ROWS_OLD+=("$name|$display_ver|⚠ 过期|$(truncate_str "$primary" 40)|$latest|$upgrade_cmd|$note")
  else
    ROWS_OK+=("$name|$display_ver|✓ 正常|$(truncate_str "$primary" 40)|$latest|保留|$note")
  fi
}

# ── Run checks ────────────────────────────────────────────────────
echo "正在扫描 25 个开发工具..." >&2

# Prefetch all non-none latest methods (single source of truth from check_tool args below)
ALL_LATEST_METHODS=(
  "brew:openjdk" "brew:cmake" "brew:composer" "brew:dotnet" "brew:go" "brew:php"
  "gh:bazelbuild/bazel" "gh:anthropics/claude-code" "brew:gradle"
  "gh_tags:NousResearch/hermes-agent" "brew:maven" "brew:node"
  "gh:opencode-ai/opencode" "gh:astral-sh/uv"
)
prefetch_latest_versions "${ALL_LATEST_METHODS[@]}"

check_tool "clang"      "clang"    "clang --version 2>&1 | head -1"                   "none"                      "xcode-select --install"
check_tool "java"       "java"     "java -version 2>&1 | head -1"                     "brew:openjdk"              "brew upgrade openjdk"
check_tool "python"     "python3"  "python3 --version 2>&1"                            "none"                      "conda update python"
check_tool "swift"      "swift"    "swift --version 2>&1 | head -1"                    "none"                      "Xcode 更新"
check_tool "cmake"      "cmake"    "cmake --version 2>&1 | head -1"                    "brew:cmake"                "brew upgrade cmake"
check_tool "composer"   "composer" "composer --version 2>&1 | head -1"                  "brew:composer"             "composer self-update"
check_tool "conda"      "conda"    "conda --version 2>&1"                              "none"                      "conda update conda"
check_tool "dotnet"     "dotnet"   "dotnet --version 2>&1"                              "brew:dotnet"               "brew upgrade dotnet"
check_tool "go"         "go"       "go version 2>&1"                                    "brew:go"                   "brew upgrade go"
check_tool "php"        "php"      "php --version 2>&1 | head -1"                       "brew:php"                  "brew upgrade php"
check_tool "rust"       "rustc"    "rustc --version 2>&1"                               "none"                      "rustup update"
check_tool "bazel"      "bazel"    "bazel --version 2>&1 | head -1"                     "gh:bazelbuild/bazel"       "brew upgrade bazel"
check_tool "claude"     "claude"   "claude --version 2>&1 | head -1"                    "gh:anthropics/claude-code"  "claude update"
check_tool "codex"      "codex"    "codex --version 2>&1 | head -1"                     "none"                      "npm i -g @openai/codex@latest"
check_tool "dart"       "dart"     "dart --version 2>&1"                                "none"                      "flutter upgrade"
check_tool "flutter"    "flutter"  "flutter --version 2>&1 | head -1"                   "none"                      "flutter upgrade"
check_tool "gcc"        "gcc"      "gcc --version 2>&1 | head -1"                       "none"                      "xcode-select --install"
check_tool "gemini-cli" "gemini"   "gemini --version 2>&1 | head -1"                    "none"                      "npm i -g @google/gemini-cli@latest"
check_tool "gradle"     "gradle"   "gradle --version 2>&1 | grep -i gradle | head -1"   "brew:gradle"               "brew upgrade gradle"
check_tool "hermes"     "hermes"   "hermes --version 2>&1 | head -1"                    "gh_tags:NousResearch/hermes-agent" "PYTHONIOENCODING=utf-8 hermes update"
check_tool "maven"      "mvn"      "mvn --version 2>&1 | head -1"                       "brew:maven"                "brew upgrade maven"
check_tool "node"       "node"     "node --version 2>&1"                                "brew:node"                 "brew upgrade node"
check_tool "npm"        "npm"      "npm --version 2>&1"                                 "none"                      "npm install -g npm"
check_tool "opencode"   "opencode" "opencode --version 2>&1 | head -1"                  "gh:opencode-ai/opencode"   "brew upgrade opencode"
check_tool "uv"         "uv"       "uv --version 2>&1"                                  "gh:astral-sh/uv"          "uv self update"

# ── Output table ──────────────────────────────────────────────────

ALL_ROWS=()
[ ${#ROWS_DUP[@]} -gt 0 ]  && ALL_ROWS+=("${ROWS_DUP[@]}")
[ ${#ROWS_OLD[@]} -gt 0 ]  && ALL_ROWS+=("${ROWS_OLD[@]}")
[ ${#ROWS_OK[@]} -gt 0 ]   && ALL_ROWS+=("${ROWS_OK[@]}")
[ ${#ROWS_NA[@]} -gt 0 ]   && ALL_ROWS+=("${ROWS_NA[@]}")
[ ${#ROWS_MISS[@]} -gt 0 ] && ALL_ROWS+=("${ROWS_MISS[@]}")

# Count logical tools (not sub-rows)
dup_tools=0; old_tools=0; ok_tools=0; na_tools=0; miss_tools=0
for row in "${ROWS_DUP[@]}"; do
  [[ "$row" != "  ↳"* ]] && ((dup_tools++))
done
for row in "${ROWS_OLD[@]}"; do ((old_tools++)); done
for row in "${ROWS_OK[@]}"; do ((ok_tools++)); done
na_tools=${#ROWS_NA[@]}
for row in "${ROWS_MISS[@]}"; do ((miss_tools++)); done

# pad_status: normalize CJK/emoji status strings to fixed visual width
# CJK chars and emoji occupy 2 columns in terminal; printf %-Ns counts bytes.
pad_status() {
  local s="$1" target=8
  # Count CJK/emoji extra width: each such char takes 2 cols but printf counts 1
  local extra
  extra=$(echo "$s" | python3 -c "
import sys, unicodedata
s = sys.stdin.read().strip()
w = sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in s)
print(w - len(s))" 2>/dev/null || echo 0)
  local pad=$((target - ${#s} - extra))
  [ "$pad" -lt 0 ] && pad=0
  printf '%s%*s' "$s" "$pad" ''
}

# Report file: ~/toolcheck/report_mmdd_hhmmss.md
REPORT_DIR="$HOME/toolcheck"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/report_$(date '+%m%d_%H%M%S').md"

{

echo '# Toolcheck Report'
printf '\n'
printf '| %4s | %-10s | %-8s | %-36s | %-40s | %-14s | %-30s | %-18s |\n' \
  "序号" "工具" "状态" "本地版本" "本地安装路径" "最新版本" "操作" "备注"
printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "----" "----------" "--------" "------------------------------------" \
  "----------------------------------------" "--------------" \
  "------------------------------" "------------------"

idx=0
for row in "${ALL_ROWS[@]}"; do
  IFS='|' read -r rname rver rstatus rpath rlatest roperation rnote <<< "$row"
  rstatus_padded=$(pad_status "$rstatus")
  if [[ "$rname" == "  ↳"* ]]; then
    # Sub-row for duplicate: no index increment
    printf '| %4s | %-10s | %s | %-36s | %-40s | %-14s | %-30s | %-18s |\n' \
      "" "$rname" "$rstatus_padded" "$rver" "$rpath" "$rlatest" "$roperation" "$rnote"
  else
    idx=$((idx+1))
    printf '| %4d | %-10s | %s | %-36s | %-40s | %-14s | %-30s | %-18s |\n' \
      "$idx" "$rname" "$rstatus_padded" "$rver" "$rpath" "$rlatest" "$roperation" "$rnote"
  fi
done

printf '\n'
echo "---"
total=$((dup_tools + old_tools + ok_tools + na_tools + miss_tools))
echo "扫描完成: $total 个工具"
echo "  ⚠ 重复: $dup_tools  |  ⚠ 过期: $old_tools  |  ✓ 正常: $ok_tools  |  — 不适用: $na_tools  |  ✗ 缺失: $miss_tools"

} > "$REPORT_FILE"

if [ "$CONSOLE" = true ]; then
  cat "$REPORT_FILE"
fi

echo "" >&2
echo "报告已保存到: $REPORT_FILE" >&2

# ── Config audit: check shell configs for stale paths ─────────────────
if [ "$CONSOLE" = true ]; then

CONFIG_FILES=(
  "$HOME/.zshrc"
  "$HOME/.zprofile"
  "$HOME/.zshenv"
  "$HOME/.bashrc"
  "$HOME/.bash_profile"
  "$HOME/.profile"
  "$HOME/.config/fish/config.fish"
)

# Patterns that may point to stale/hardcoded tool versions
# Format: label|grep_pattern
STALE_PATTERNS=(
  "硬编码 Python 版本路径|python3\.[0-9]"
  "硬编码 Node 版本路径|node/[0-9]"
  "硬编码 Go 版本路径|go[0-9]\.[0-9]"
  "硬编码 Java/JDK 版本路径|jdk[-/][0-9]"
  "硬编码 .NET 版本路径|dotnet/[0-9]"
  "硬编码 Rust toolchain 路径|rustup/toolchains/[a-z]*-[0-9]"
  "硬编码 Flutter 版本路径|flutter/[0-9]"
  "硬编码 PHP 版本路径|php@[0-9]"
  "旧版 Homebrew 路径 (Intel)|/usr/local/Cellar"
  "已弃用 JAVA_HOME 路径|JAVA_HOME.*jdk[0-9]"
  "已弃用 GOROOT/GOPATH|GOROOT\|GOPATH.*go[0-9]"
  "已弃用 conda activate 写法|source.*conda.*activate"
)

printf '\n'
echo "=========================================="
echo "  本地配置审计 (Shell RC / PATH)"
echo "=========================================="
printf '\n'

audit_found=0

for cf in "${CONFIG_FILES[@]}"; do
  [ -f "$cf" ] || continue
  cf_short="${cf/$HOME/~}"
  file_hits=0

  for pat_entry in "${STALE_PATTERNS[@]}"; do
    IFS='|' read -r label pattern <<< "$pat_entry"
    # Search non-comment lines only
    matches=$(grep -n "$pattern" "$cf" 2>/dev/null | grep -Ev '^[0-9]+:[[:space:]]*[#;]')
    if [ -n "$matches" ]; then
      if [ "$file_hits" -eq 0 ]; then
        echo "📄 $cf_short"
        file_hits=1
      fi
      while IFS= read -r line; do
        lineno=$(echo "$line" | cut -d: -f1)
        content=$(echo "$line" | cut -d: -f2- | sed 's/^[[:space:]]*//' | cut -c1-70)
        printf '  ⚠ L%-4s %-28s %s\n' "$lineno" "[$label]" "$content"
        audit_found=1
      done <<< "$matches"
    fi
  done

  [ "$file_hits" -gt 0 ] && echo ""
done

if [ "$audit_found" -eq 0 ]; then
  echo "✅ 未发现可疑的硬编码版本路径或过期配置"
fi

printf '\n'
fi  # end CONSOLE check
