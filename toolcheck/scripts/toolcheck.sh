#!/usr/bin/env bash
# toolcheck.sh — Check 25 dev tools for conflicts, upgrades, and missing installs
set -o pipefail

# macOS lacks coreutils timeout; detect available command
if command -v gtimeout &>/dev/null; then
  TOCMD="gtimeout 3"
elif command -v timeout &>/dev/null; then
  TOCMD="timeout 3"
else
  TOCMD=""
fi

# ── Helpers ───────────────────────────────────────────────────────

truncate_str() {
  local s="$1" max="${2:-40}"
  if [ ${#s} -le "$max" ]; then echo "$s"
  else echo "...${s: -$((max-3))}"; fi
}

classify_source() {
  case "$1" in
    /usr/bin/*|/usr/sbin/*) echo "system" ;;
    /opt/homebrew/*|/usr/local/Cellar/*|/usr/local/opt/*) echo "homebrew" ;;
    */.cargo/*) echo "cargo" ;;
    */miniconda*|*/anaconda*|*/conda*) echo "conda" ;;
    */.local/*) echo "user" ;;
    */flutter/*) echo "flutter-sdk" ;;
    *) echo "other" ;;
  esac
}

extract_semver() {
  echo "$1" | grep -oE '[0-9]+\.[0-9]+[0-9.a-zA-Z_-]*' | head -1
}

gh_latest() {
  local repo="$1" raw v
  raw=$(curl -sfL --max-time 5 "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null) || { echo "N/A"; return; }
  v=$(echo "$raw" | python3 -c "import sys,json;d=json.load(sys.stdin);t=d.get('tag_name','');print(t.lstrip('v'))" 2>/dev/null)
  echo "${v:-N/A}"
}

# Get latest version from GitHub tags (for repos without formal releases)
gh_tags_latest() {
  local repo="$1" raw v
  raw=$(curl -sfL --max-time 5 "https://api.github.com/repos/$repo/tags?per_page=1" 2>/dev/null) || { echo "N/A"; return; }
  v=$(echo "$raw" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['name'].lstrip('v'))" 2>/dev/null)
  echo "${v:-N/A}"
}

brew_latest() {
  local formula="$1"
  [ -z "$formula" ] && echo "N/A" && return
  local v
  v=$($TOCMD brew info --json=v2 "$formula" 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['formulae'][0]['versions']['stable'])" 2>/dev/null)
  echo "${v:-N/A}"
}

version_lt() {
  [ "$1" = "$2" ] && return 1
  [ -z "$1" ] && return 1
  [ -z "$2" ] && return 1
  local smallest
  smallest=$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)
  [ "$smallest" = "$1" ]
}

# ── Storage ───────────────────────────────────────────────────────
# Each row: name|version|status|path|latest|action|upgrade_cmd|source|note
# For duplicate sub-rows: ↳|version_at_path|⚠ 重复|path|...|...|...|source|...

ROWS_DUP=()
ROWS_OLD=()
ROWS_OK=()
ROWS_MISS=()

# check_tool <name> <cmd> <ver_cmd> <latest_method> <upgrade_cmd>
check_tool() {
  local name="$1" cmd="$2" ver_cmd="$3" latest_method="$4" upgrade_cmd="$5"

  # Find all paths, resolve symlinks to deduplicate
  local -a raw_paths=() paths=() seen_real=()
  while IFS= read -r p; do
    [ -n "$p" ] && raw_paths+=("$p")
  done < <(which -a "$cmd" 2>/dev/null)
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
  case "$latest_method" in
    brew:*)      latest=$(brew_latest "${latest_method#brew:}") ;;
    gh:*)        latest=$(gh_latest "${latest_method#gh:}") ;;
    gh_tags:*)   latest=$(gh_tags_latest "${latest_method#gh_tags:}") ;;
    none)        latest="N/A" ;;
  esac

  if [ "$num_paths" -eq 0 ]; then
    ROWS_MISS+=("$name|-|✗ 缺失|-|$latest|安装|$upgrade_cmd|-|未安装")
    return
  fi

  local primary="${paths[0]}"
  local raw_ver display_ver parsed_ver

  raw_ver=$($TOCMD bash -c "$ver_cmd" 2>&1 || echo "-")
  display_ver=$(echo "$raw_ver" | head -1 | cut -c1-36)
  parsed_ver=$(extract_semver "$raw_ver")

  local note=""
  # Check for error output
  if echo "$raw_ver" | grep -qiE 'ERROR|JAVA_HOME|exception'; then
    note=$(echo "$raw_ver" | head -1 | cut -c1-20)
  fi
  if [ -z "$parsed_ver" ]; then
    note="${note:+$note; }版本获取失败"
    display_ver="-"
  fi

  if [ "$num_paths" -gt 1 ]; then
    # ── Duplicate: emit one row per path ──
    local action
    if [ -n "$parsed_ver" ] && [ "$latest" != "N/A" ] && version_lt "$parsed_ver" "$latest"; then
      action="升级"
    else
      action="保留"
    fi

    # First row: full info
    local src0
    src0=$(classify_source "${paths[0]}")
    ROWS_DUP+=("$name|$display_ver|⚠ 重复|$(truncate_str "${paths[0]}" 40)|$latest|$action|$upgrade_cmd|$src0|$note")

    # Subsequent rows: continuation with ↳ prefix
    local i
    for (( i=1; i<num_paths; i++ )); do
      local src_i
      src_i=$(classify_source "${paths[$i]}")
      ROWS_DUP+=("  ↳||⚠ 重复|$(truncate_str "${paths[$i]}" 40)||||$src_i|")
    done
  elif [ -n "$parsed_ver" ] && [ "$latest" != "N/A" ] && version_lt "$parsed_ver" "$latest"; then
    local src0
    src0=$(classify_source "$primary")
    ROWS_OLD+=("$name|$display_ver|⚠ 过期|$(truncate_str "$primary" 40)|$latest|升级|$upgrade_cmd|$src0|$note")
  else
    local src0
    src0=$(classify_source "$primary")
    ROWS_OK+=("$name|$display_ver|✓ 正常|$(truncate_str "$primary" 40)|$latest|保留|$upgrade_cmd|$src0|$note")
  fi
}

# ── Run checks ────────────────────────────────────────────────────
echo "正在扫描 25 个开发工具..." >&2

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
check_tool "hermes"     "hermes"   "hermes --version 2>&1 | head -1"                    "gh_tags:NousResearch/hermes-agent" "hermes update"
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
[ ${#ROWS_MISS[@]} -gt 0 ] && ALL_ROWS+=("${ROWS_MISS[@]}")

# Count logical tools (not sub-rows)
dup_tools=0; old_tools=0; ok_tools=0; miss_tools=0
for row in "${ROWS_DUP[@]}"; do
  [[ "$row" != "  ↳"* ]] && ((dup_tools++))
done
for row in "${ROWS_OLD[@]}"; do ((old_tools++)); done
for row in "${ROWS_OK[@]}"; do ((ok_tools++)); done
for row in "${ROWS_MISS[@]}"; do ((miss_tools++)); done

printf '\n'
printf '| %4s | %-10s | %-6s | %-36s | %-40s | %-14s | %-4s | %-30s | %-10s | %-18s |\n' \
  "序号" "工具" "状态" "本地版本" "本地安装路径" "最新版本" "动作" "升级命令" "来源" "备注"
printf '| %s: | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "----" "----------" "------" "------------------------------------" \
  "----------------------------------------" "--------------" "----" \
  "------------------------------" "----------" "------------------"

idx=0
for row in "${ALL_ROWS[@]}"; do
  IFS='|' read -r rname rver rstatus rpath rlatest raction rupgrade rsource rnote <<< "$row"
  if [[ "$rname" == "  ↳"* ]]; then
    # Sub-row for duplicate: no index increment
    printf '| %4s | %-10s | %-6s | %-36s | %-40s | %-14s | %-4s | %-30s | %-10s | %-18s |\n' \
      "" "$rname" "$rstatus" "$rver" "$rpath" "$rlatest" "$raction" "$rupgrade" "$rsource" "$rnote"
  else
    idx=$((idx+1))
    printf '| %4d | %-10s | %-6s | %-36s | %-40s | %-14s | %-4s | %-30s | %-10s | %-18s |\n' \
      "$idx" "$rname" "$rstatus" "$rver" "$rpath" "$rlatest" "$raction" "$rupgrade" "$rsource" "$rnote"
  fi
done

printf '\n'
echo "---"
total=$((dup_tools + old_tools + ok_tools + miss_tools))
echo "扫描完成: $total 个工具"
echo "  ⚠ 重复: $dup_tools  |  ⚠ 过期: $old_tools  |  ✓ 正常: $ok_tools  |  ✗ 缺失: $miss_tools"

# ── Config audit: check shell configs for stale paths ─────────────

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
echo "  本地配置审计 (Shell RC / Profile)"
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
    matches=$(grep -n "$pattern" "$cf" 2>/dev/null | grep -v '^\s*#' | grep -v '^\s*;')
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
