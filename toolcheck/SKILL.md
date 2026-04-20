---
name: toolcheck
description: "Scan 25 development tools for installation conflicts, outdated versions, and missing installs. Generates a markdown table report showing status (重复/过期/正常/缺失), local vs latest versions, install paths, and recommended actions. Use when: user asks to check dev tools, audit installed tools, find version conflicts, or check for updates on clang/java/python/swift/cmake/composer/conda/dotnet/go/php/rust/bazel/claude/codex/dart/flutter/gcc/gemini-cli/gradle/hermes/maven/node/npm/opencode/uv."
---

# Toolcheck

Scan 25 development tools and produce a diagnostic report table.

## Execution

Run the script matching the current platform and output its **full stdout verbatim** — do not summarize, truncate, or reformat.

### macOS / Linux (bash)

```bash
bash ~/.claude/skills/toolcheck/scripts/toolcheck.sh
```

Or from the repo directly:

```bash
bash toolcheck/scripts/toolcheck.sh
```

### Windows (PowerShell)

```powershell
pwsh -ExecutionPolicy Bypass -File "$HOME\.claude\skills\toolcheck\scripts\toolcheck.ps1"
```

Or from the repo directly:

```powershell
pwsh -ExecutionPolicy Bypass -File toolcheck\scripts\toolcheck.ps1
```

### Platform detection (auto)

```bash
if command -v pwsh &>/dev/null && [[ "$(uname -s)" == MINGW* || "$(uname -s)" == CYGWIN* ]] || [[ "$OS" == "Windows_NT" ]]; then
  pwsh -ExecutionPolicy Bypass -File toolcheck/scripts/toolcheck.ps1
else
  bash toolcheck/scripts/toolcheck.sh
fi
```

**IMPORTANT**: The script outputs a complete 25-row markdown table plus a summary line. Print ALL output exactly as-is. Do not omit any rows or columns. Do not add commentary between table rows.

## PowerShell API (programmatic use)

The Windows script (`toolcheck.ps1`) exposes a modular function API. Dot-source to load without auto-running:

```powershell
. toolcheck/scripts/toolcheck.ps1
```

### Core functions

| Function                     | Returns            | Description                                                              |
| ---------------------------- | ------------------ | ------------------------------------------------------------------------ |
| `Invoke-ToolScan`            | `PSCustomObject[]` | Full scan pipeline: registry → discovery → latest fetch → classification |
| `Invoke-ToolCheck`           | `PSCustomObject[]` | `Invoke-ToolScan` + table display + summary + config audit               |
| `Format-ToolTable $results`  | `string[]`         | Render result objects as formatted table lines                           |
| `Write-ScanSummary $results` | _(console)_        | Print summary counts                                                     |
| `Test-ConfigAudit`           | _(console)_        | Audit PATH/env for stale entries                                         |

### Pipeline building blocks

| Function                                                                   | Description                                                                         |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `Get-ToolRegistry`                                                         | Returns 25 tool definitions (`Name`, `Cmd`, `VerCmd`, `LatestMethod`, `UpgradeCmd`) |
| `Find-CommandPaths $cmd`                                                   | Find all install paths, dedup Windows wrappers (.ps1/.cmd/.bat)                     |
| `Get-InstalledVersion $verCmd $cmdPath`                                    | Run version command against a specific path (8s timeout)                            |
| `Find-LocalInstalls $toolDef`                                              | Discover all installs with per-path version info                                    |
| `Get-LatestVersionBatch $methods`                                          | Parallel-fetch latest versions (winget/GitHub, 15s timeout)                         |
| `Resolve-ToolStatus -ToolDef $def -Installs $installs -LatestVersion $ver` | Classify: normal/outdated/duplicate/missing/na                                      |
| `Get-RecommendedOperation $status $ver $latest $upgradeCmd`                | Determine recommended action                                                        |

### Result object shape

Each element returned by `Invoke-ToolScan` has:

```
Name          : string        — tool name
Status        : string        — normal|outdated|duplicate|missing|na
StatusLabel   : string        — display label (✓ 正常, ⚠ 过期, etc.)
LatestVersion : string        — latest available version or "N/A"
UpgradeCmd    : string        — upgrade command template
Installs[]    : object[]      — per-install-path details:
  .Path          : string     — full file path
  .PathDisplay   : string     — truncated path for table
  .VersionRaw    : string     — raw version output (first line)
  .VersionParsed : string     — extracted semver
  .Note          : string     — error/timeout notes
  .Operation     : string     — recommended action for this install
```

### Example: filter outdated tools

```powershell
. toolcheck/scripts/toolcheck.ps1
$results = Invoke-ToolScan
$results | Where-Object Status -eq 'outdated' | ForEach-Object {
    Write-Host "$($_.Name): $($_.Installs[0].VersionParsed) -> $($_.LatestVersion)"
    Write-Host "  Run: $($_.UpgradeCmd)"
}
```
