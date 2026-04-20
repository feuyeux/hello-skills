#Requires -Version 5.1
# toolcheck.ps1 - Cross-platform dev tool auditor (Windows)
#
# Architecture: Registry -> Discovery -> LatestFetch -> Classification -> Report
#
# Public API (dot-source to load without auto-running):
#   Invoke-ToolScan   — returns structured [PSCustomObject[]] results
#   Invoke-ToolCheck  — full pipeline: scan + table + summary + config audit
#   Format-ToolTable  — render result objects as formatted table lines
#   Write-ScanSummary — render summary counts
#   Test-ConfigAudit  — audit PATH/env for stale entries

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'

# ======================================================================
#  Module 1: Utility Helpers
# ======================================================================

function Truncate-Str([string]$s, [int]$max = 40) {
    if ($s.Length -le $max) { return $s }
    return "..." + $s.Substring($s.Length - ($max - 3))
}

function Extract-Semver([string]$s) {
    if ($s -match '(\d+\.\d+[\d.a-zA-Z_-]*)') { return $Matches[1] }
    return $null
}

function Version-Lt([string]$a, [string]$b) {
    if (-not $a -or -not $b -or $a -eq $b) { return $false }
    try {
        $clean = { param($v) $v -replace '-.*$' -replace '[^0-9.]', '' -replace '\.+$', '' -replace '^(\d+\.\d+)$', '$1.0' }
        $va = [version](& $clean $a)
        $vb = [version](& $clean $b)
        return $va -lt $vb
    } catch {
        return ($a -lt $b)
    }
}

# ======================================================================
#  Module 2: Tool Registry
# ======================================================================

# Maps macOS brew: sources to Windows-native equivalents (defined once)
$script:LatestSourceMap = @{
    'brew:openjdk'  = 'winget:Oracle.JDK.21'
    'brew:cmake'    = 'winget:Kitware.CMake'
    'brew:composer' = 'gh:composer/composer'
    'brew:dotnet'   = 'winget:Microsoft.DotNet.SDK.8'
    'brew:go'       = 'winget:GoLang.Go'
    'brew:php'      = 'gh:php/php-src'
    'brew:gradle'   = 'gh:gradle/gradle'
    'brew:maven'    = 'gh:apache/maven'
    'brew:node'     = 'winget:OpenJS.NodeJS'
}

$script:MacOnlyTools = @('swift')

function Get-ToolRegistry {
    return @(
        [pscustomobject]@{ Name="clang";      Cmd="clang";    VerCmd="clang --version";    LatestMethod="none";                              UpgradeCmd="choco install llvm"                   }
        [pscustomobject]@{ Name="java";       Cmd="java";     VerCmd="java -version 2>&1"; LatestMethod="brew:openjdk";                      UpgradeCmd="winget upgrade Oracle.JDK.21"         }
        [pscustomobject]@{ Name="python";     Cmd="python";   VerCmd="python --version";   LatestMethod="none";                              UpgradeCmd="winget upgrade Python.Python.3.12"    }
        [pscustomobject]@{ Name="swift";      Cmd="swift";    VerCmd="swift --version";    LatestMethod="none";                              UpgradeCmd="Xcode update"                         }
        [pscustomobject]@{ Name="cmake";      Cmd="cmake";    VerCmd="cmake --version";    LatestMethod="brew:cmake";                        UpgradeCmd="winget upgrade Kitware.CMake"          }
        [pscustomobject]@{ Name="composer";   Cmd="composer";VerCmd="composer --version";   LatestMethod="brew:composer";                     UpgradeCmd="composer self-update"                  }
        [pscustomobject]@{ Name="conda";      Cmd="conda";    VerCmd="conda --version";    LatestMethod="none";                              UpgradeCmd="conda update conda"                   }
        [pscustomobject]@{ Name="dotnet";     Cmd="dotnet";   VerCmd="dotnet --version";   LatestMethod="brew:dotnet";                       UpgradeCmd="winget upgrade Microsoft.DotNet.SDK.8" }
        [pscustomobject]@{ Name="go";         Cmd="go";       VerCmd="go version";         LatestMethod="brew:go";                           UpgradeCmd="winget upgrade GoLang.Go"              }
        [pscustomobject]@{ Name="php";        Cmd="php";      VerCmd="php --version";      LatestMethod="brew:php";                          UpgradeCmd="choco upgrade php"                     }
        [pscustomobject]@{ Name="rust";       Cmd="rustc";    VerCmd="rustc --version";    LatestMethod="none";                              UpgradeCmd="rustup update"                        }
        [pscustomobject]@{ Name="bazel";      Cmd="bazel";    VerCmd="bazel --version";    LatestMethod="gh:bazelbuild/bazel";               UpgradeCmd="choco upgrade bazelisk"                }
        [pscustomobject]@{ Name="claude";     Cmd="claude";   VerCmd="claude --version";   LatestMethod="gh:anthropics/claude-code";         UpgradeCmd="claude update"                        }
        [pscustomobject]@{ Name="codex";      Cmd="codex";    VerCmd="codex --version";    LatestMethod="none";                              UpgradeCmd="npm i -g @openai/codex@latest"         }
        [pscustomobject]@{ Name="dart";       Cmd="dart";     VerCmd="dart --version";     LatestMethod="none";                              UpgradeCmd="flutter upgrade"                      }
        [pscustomobject]@{ Name="flutter";    Cmd="flutter";  VerCmd="flutter --version";  LatestMethod="none";                              UpgradeCmd="flutter upgrade"                      }
        [pscustomobject]@{ Name="gcc";        Cmd="gcc";      VerCmd="gcc --version";      LatestMethod="none";                              UpgradeCmd="choco install mingw"                   }
        [pscustomobject]@{ Name="gemini-cli"; Cmd="gemini";   VerCmd="gemini --version";   LatestMethod="none";                              UpgradeCmd="npm i -g @google/gemini-cli@latest"    }
        [pscustomobject]@{ Name="gradle";     Cmd="gradle";   VerCmd="gradle --version";   LatestMethod="brew:gradle";                       UpgradeCmd="choco upgrade gradle"                  }
        [pscustomobject]@{ Name="hermes";     Cmd="hermes";   VerCmd="hermes --version";   LatestMethod="gh_tags:NousResearch/hermes-agent"; UpgradeCmd="hermes update"                        }
        [pscustomobject]@{ Name="maven";      Cmd="mvn";      VerCmd="mvn --version";      LatestMethod="brew:maven";                        UpgradeCmd="choco upgrade maven"                   }
        [pscustomobject]@{ Name="node";       Cmd="node";     VerCmd="node --version";     LatestMethod="brew:node";                         UpgradeCmd="winget upgrade OpenJS.NodeJS"          }
        [pscustomobject]@{ Name="npm";        Cmd="npm";      VerCmd="npm --version";      LatestMethod="none";                              UpgradeCmd="npm install -g npm"                   }
        [pscustomobject]@{ Name="opencode";   Cmd="opencode"; VerCmd="opencode --version"; LatestMethod="gh:opencode-ai/opencode";           UpgradeCmd="npm i -g opencode@latest"              }
        [pscustomobject]@{ Name="uv";         Cmd="uv";       VerCmd="uv --version";       LatestMethod="gh:astral-sh/uv";                  UpgradeCmd="uv self update"                       }
    )
}

# ======================================================================
#  Module 3: Local Installation Discovery
# ======================================================================

# Find all install paths for a command, deduplicating Windows wrapper variants
function Find-CommandPaths([string]$cmd) {
    $rawPaths = @()
    $paths = @()
    $seenBase = @()

    $found = Get-Command $cmd -All -ErrorAction SilentlyContinue
    if ($found) {
        foreach ($c in $found) {
            if ($c.Source) { $rawPaths += $c.Source }
        }
    }

    foreach ($p in $rawPaths) {
        $rp = try { (Resolve-Path $p -ErrorAction Stop).Path } catch { $p }
        # Normalize: strip .ps1/.cmd/.bat to deduplicate wrapper scripts
        $rpBase = $rp -replace '\.(ps1|cmd|bat)$', ''
        $isDup = $false
        foreach ($s in $seenBase) {
            if ($s -eq $rpBase -or $s -eq $rp) { $isDup = $true; break }
        }
        if (-not $isDup) {
            $paths += $p
            $seenBase += $rpBase
        }
    }
    return ,$paths
}

# Run a version command against a specific install path (prepends its dir to PATH)
function Get-InstalledVersion([string]$verCmd, [string]$cmdPath) {
    $result = [PSCustomObject]@{ Display = '-'; Parsed = $null; Note = '' }
    $cmdDir = if ($cmdPath -and $cmdPath -ne '-') { Split-Path $cmdPath -Parent } else { $null }

    try {
        $job = Start-Job -ScriptBlock {
            param($vc, $dir)
            if ($dir) { $env:PATH = "$dir;$env:PATH" }
            & cmd /c "$vc" 2>&1 | Select-Object -First 3 | Out-String
        } -ArgumentList $verCmd, $cmdDir

        $completed = $job | Wait-Job -Timeout 8
        if (-not $completed) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
            $result.Note = "timeout"
            return $result
        }
        $raw = Receive-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue

        if (-not $raw) { $raw = "" }
        $firstLine = ($raw -split "`n")[0].Trim()
        if ($firstLine.Length -gt 36) { $firstLine = $firstLine.Substring(0, 36) }
        $result.Display = $firstLine
        $result.Parsed = Extract-Semver $raw

        if ($raw -match '(?i)(error[: ]|JAVA_HOME|exception[: ])') {
            $result.Note = $firstLine.Substring(0, [Math]::Min(20, $firstLine.Length))
        }
    } catch {
        $result.Note = "version_fetch_failed"
    }

    if (-not $result.Parsed) {
        $result.Note = if ($result.Note) { $result.Note } else { "version_parse_failed" }
        $result.Display = '-'
    }
    return $result
}

# Discover all installs of a tool: paths + per-path version info
function Find-LocalInstalls([PSCustomObject]$toolDef) {
    $paths = Find-CommandPaths $toolDef.Cmd
    if (-not $paths -or $paths.Count -eq 0) { return ,@() }

    $installs = @()
    foreach ($p in $paths) {
        $ver = Get-InstalledVersion $toolDef.VerCmd $p
        $installs += [PSCustomObject]@{
            Path          = $p
            PathDisplay   = Truncate-Str $p 40
            VersionRaw    = $ver.Display
            VersionParsed = $ver.Parsed
            Note          = $ver.Note
        }
    }
    return ,$installs
}

# ======================================================================
#  Module 4: Latest Version Resolution
# ======================================================================

# Resolve a method string to its Windows-native equivalent (using $LatestSourceMap)
function Resolve-LatestSource([string]$method) {
    if (-not $method -or $method -eq 'none') { return $null }
    if ($script:LatestSourceMap.ContainsKey($method)) {
        return $script:LatestSourceMap[$method]
    }
    return $method
}

# Fetch latest versions for all unique methods in parallel via Start-Job
# Returns hashtable: { method -> version_string }
function Get-LatestVersionBatch([string[]]$methods) {
    $cache = @{}
    $uniqueMethods = $methods | Where-Object { $_ -and $_ -ne 'none' } | Sort-Object -Unique

    $jobs = @()
    foreach ($m in $uniqueMethods) {
        $resolved = Resolve-LatestSource $m
        if (-not $resolved) { $cache[$m] = "N/A"; continue }

        $parts = $resolved -split ':', 2
        $fetchType = $parts[0]; $fetchArg = $parts[1]

        $job = Start-Job -ScriptBlock {
            param($ft, $fa)
            $ErrorActionPreference = 'SilentlyContinue'

            if ($ft -eq 'gh') {
                try {
                    $r = Invoke-RestMethod -Uri "https://api.github.com/repos/$fa/releases/latest" `
                        -TimeoutSec 5 -Headers @{ 'User-Agent' = 'toolcheck-ps1' } -ErrorAction Stop
                    $tag = $r.tag_name -replace '^v', ''
                    if ($tag) { return $tag }
                } catch {}
                return "N/A"
            }
            elseif ($ft -eq 'gh_tags') {
                try {
                    $r = Invoke-RestMethod -Uri "https://api.github.com/repos/$fa/tags?per_page=30" `
                        -TimeoutSec 5 -Headers @{ 'User-Agent' = 'toolcheck-ps1' } -ErrorAction Stop
                    foreach ($t in $r) {
                        $name = $t.name -replace '^v', ''
                        if ($name -match '^\d+\.\d+') { return $name }
                    }
                } catch {}
                return "N/A"
            }
            elseif ($ft -eq 'winget') {
                if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return "N/A" }
                try {
                    $out = & winget show --id $fa --accept-source-agreements --disable-interactivity 2>$null
                    $line = $out | Where-Object { $_ -match '^\s*version\s*:' -or $_ -match '^\s*\u7248\u672c\s*[:\uff1a]' } | Select-Object -First 1
                    if ($line -and $line -match '[:\uff1a]\s*(.+)$') {
                        $ver = $Matches[1].Trim()
                        if ($ver) { return $ver }
                    }
                } catch {}
                return "N/A"
            }
            return "N/A"
        } -ArgumentList $fetchType, $fetchArg

        $jobs += @{ Job = $job; Method = $m }
    }

    # Collect results with 15s timeout per job
    foreach ($j in $jobs) {
        $completed = $j.Job | Wait-Job -Timeout 15
        if ($completed) {
            $result = Receive-Job -Job $j.Job -ErrorAction SilentlyContinue
            $cache[$j.Method] = if ($result) { "$result".Trim() } else { "N/A" }
        } else {
            Stop-Job -Job $j.Job -ErrorAction SilentlyContinue
            $cache[$j.Method] = "N/A"
        }
        Remove-Job -Job $j.Job -Force -ErrorAction SilentlyContinue
    }

    return $cache
}

# ======================================================================
#  Module 5: Status Classification & Conflict Detection
# ======================================================================

# Determine what operation to recommend for a single install instance
function Get-RecommendedOperation {
    param(
        [string]$status,
        [string]$versionParsed,
        [string]$latestVersion,
        [string]$upgradeCmd
    )
    switch ($status) {
        'missing'   { return $upgradeCmd }
        'na'        { return "skip" }
        'outdated'  { return $upgradeCmd }
        'duplicate' {
            if ($versionParsed -and $latestVersion -ne 'N/A' -and (Version-Lt $versionParsed $latestVersion)) {
                return $upgradeCmd
            }
            return "keep"
        }
        default     { return "keep" }
    }
}

# Classify a tool into one of: normal | outdated | duplicate | missing | na
# Returns a structured result object with per-install details
function Resolve-ToolStatus {
    param(
        [PSCustomObject]$ToolDef,
        [array]$Installs,
        [string]$LatestVersion
    )

    $base = @{
        Name          = $ToolDef.Name
        UpgradeCmd    = $ToolDef.UpgradeCmd
        LatestVersion = $LatestVersion
    }

    # macOS-only → not applicable
    if ($script:MacOnlyTools -contains $ToolDef.Name) {
        return [PSCustomObject]($base + @{
            Status      = 'na'
            StatusLabel = [char]0x2014 + ' ' + [char]0x4E0D + [char]0x9002 + [char]0x7528
            Installs    = @([PSCustomObject]@{
                Path = '-'; PathDisplay = '-'; VersionRaw = '-'; VersionParsed = $null
                Note = 'macOS only'; Operation = 'skip'
            })
        })
    }

    # Not installed
    if (-not $Installs -or $Installs.Count -eq 0) {
        return [PSCustomObject]($base + @{
            Status      = 'missing'
            StatusLabel = [char]0x2717 + ' ' + [char]0x7F3A + [char]0x5931
            Installs    = @([PSCustomObject]@{
                Path = '-'; PathDisplay = '-'; VersionRaw = '-'; VersionParsed = $null
                Note = 'not_installed'; Operation = $ToolDef.UpgradeCmd
            })
        })
    }

    # Multiple installs → duplicate
    if ($Installs.Count -gt 1) {
        $enriched = @()
        foreach ($inst in $Installs) {
            $op = Get-RecommendedOperation 'duplicate' $inst.VersionParsed $LatestVersion $ToolDef.UpgradeCmd
            $enriched += [PSCustomObject]@{
                Path          = $inst.Path
                PathDisplay   = $inst.PathDisplay
                VersionRaw    = $inst.VersionRaw
                VersionParsed = $inst.VersionParsed
                Note          = $inst.Note
                Operation     = $op
            }
        }
        return [PSCustomObject]($base + @{
            Status      = 'duplicate'
            StatusLabel = [char]0x26A0 + ' ' + [char]0x91CD + [char]0x590D
            Installs    = $enriched
        })
    }

    # Single install
    $inst = $Installs[0]

    # Check if outdated
    if ($inst.VersionParsed -and $LatestVersion -ne 'N/A' -and (Version-Lt $inst.VersionParsed $LatestVersion)) {
        return [PSCustomObject]($base + @{
            Status      = 'outdated'
            StatusLabel = [char]0x26A0 + ' ' + [char]0x8FC7 + [char]0x671F
            Installs    = @([PSCustomObject]@{
                Path = $inst.Path; PathDisplay = $inst.PathDisplay
                VersionRaw = $inst.VersionRaw; VersionParsed = $inst.VersionParsed
                Note = $inst.Note; Operation = $ToolDef.UpgradeCmd
            })
        })
    }

    # Normal
    return [PSCustomObject]($base + @{
        Status      = 'normal'
        StatusLabel = [char]0x2713 + ' ' + [char]0x6B63 + [char]0x5E38
        Installs    = @([PSCustomObject]@{
            Path = $inst.Path; PathDisplay = $inst.PathDisplay
            VersionRaw = $inst.VersionRaw; VersionParsed = $inst.VersionParsed
            Note = $inst.Note; Operation = 'keep'
        })
    })
}

# ======================================================================
#  Module 6: Report Generation
# ======================================================================

# Map internal operation codes to display strings
function Format-Operation([string]$op) {
    switch ($op) {
        'keep' { return [string]([char]0x4FDD + [char]0x7559) }
        'skip' { return [string]([char]0x8DF3 + [char]0x8FC7) }
        default { return $op }
    }
}

function Format-Note([string]$note) {
    switch ($note) {
        'not_installed'      { return [string]([char]0x672A + [char]0x5B89 + [char]0x88C5) }
        'macOS only'         { return [string]([char]0x4EC5 + ' macOS') }
        'timeout'            { return [string]([char]0x8D85 + [char]0x65F6) }
        'version_fetch_failed'  { return [string]([char]0x7248 + [char]0x672C + [char]0x83B7 + [char]0x53D6 + [char]0x5931 + [char]0x8D25) }
        'version_parse_failed'  { return [string]([char]0x7248 + [char]0x672C + [char]0x83B7 + [char]0x53D6 + [char]0x5931 + [char]0x8D25) }
        default              { return $note }
    }
}

# Format a single table row with fixed-width columns
function Format-TableRow([string]$idx, [string]$name, [string]$status, [string]$ver, [string]$path, [string]$latest, [string]$operation, [string]$note) {
    '| {0,4} | {1,-10} | {2,-8} | {3,-36} | {4,-40} | {5,-14} | {6,-30} | {7,-18} |' -f `
        $idx, $name, $status, $ver, $path, $latest, $operation, $note
}

# Render full table from result objects; returns string array
function Format-ToolTable([array]$Results) {
    $lines = @()
    $lines += ""
    $hdr = [string]([char]0x5E8F + [char]0x53F7)
    $hdr2 = [string]([char]0x5DE5 + [char]0x5177)
    $hdr3 = [string]([char]0x72B6 + [char]0x6001)
    $hdr4 = [string]([char]0x672C + [char]0x5730 + [char]0x7248 + [char]0x672C)
    $hdr5 = [string]([char]0x672C + [char]0x5730 + [char]0x5B89 + [char]0x88C5 + [char]0x8DEF + [char]0x5F84)
    $hdr6 = [string]([char]0x6700 + [char]0x65B0 + [char]0x7248 + [char]0x672C)
    $hdr7 = [string]([char]0x64CD + [char]0x4F5C)
    $hdr8 = [string]([char]0x5907 + [char]0x6CE8)
    $lines += Format-TableRow $hdr $hdr2 $hdr3 $hdr4 $hdr5 $hdr6 $hdr7 $hdr8
    $lines += Format-TableRow "----" "----------" "--------" "------------------------------------" `
        "----------------------------------------" "--------------" "------------------------------" "------------------"

    # Sort: duplicate -> outdated -> normal -> na -> missing
    $order = @{ 'duplicate' = 1; 'outdated' = 2; 'normal' = 3; 'na' = 4; 'missing' = 5 }
    $sorted = $Results | Sort-Object { $order[$_.Status] }

    $idx = 0
    foreach ($tool in $sorted) {
        for ($i = 0; $i -lt $tool.Installs.Count; $i++) {
            $inst = $tool.Installs[$i]
            $opDisplay = Format-Operation $inst.Operation
            $noteDisplay = Format-Note $inst.Note
            if ($i -eq 0) {
                $idx++
                $lines += Format-TableRow "$idx" $tool.Name $tool.StatusLabel $inst.VersionRaw $inst.PathDisplay $tool.LatestVersion $opDisplay $noteDisplay
            } else {
                $lines += Format-TableRow "" "  $([char]0x21B3)" $tool.StatusLabel $inst.VersionRaw $inst.PathDisplay $tool.LatestVersion $opDisplay $noteDisplay
            }
        }
    }
    return $lines
}

# Print summary counts
function Write-ScanSummary([array]$Results) {
    $dup  = ($Results | Where-Object Status -eq 'duplicate').Count
    $old  = ($Results | Where-Object Status -eq 'outdated').Count
    $ok   = ($Results | Where-Object Status -eq 'normal').Count
    $na   = ($Results | Where-Object Status -eq 'na').Count
    $miss = ($Results | Where-Object Status -eq 'missing').Count
    $total = $Results.Count

    Write-Host ""
    Write-Host "---"
    $lbl1 = [string]([char]0x626B + [char]0x63CF + [char]0x5B8C + [char]0x6210)
    $lbl2 = [string]([char]0x4E2A + [char]0x5DE5 + [char]0x5177)
    Write-Host "$lbl1`: $total $lbl2"
    $s1 = [string]([char]0x26A0 + ' ' + [char]0x91CD + [char]0x590D)
    $s2 = [string]([char]0x26A0 + ' ' + [char]0x8FC7 + [char]0x671F)
    $s3 = [string]([char]0x2713 + ' ' + [char]0x6B63 + [char]0x5E38)
    $s4 = [string]([char]0x2014 + ' ' + [char]0x4E0D + [char]0x9002 + [char]0x7528)
    $s5 = [string]([char]0x2717 + ' ' + [char]0x7F3A + [char]0x5931)
    Write-Host "  $s1`: $dup  |  $s2`: $old  |  $s3`: $ok  |  $s4`: $na  |  $s5`: $miss"
}

# Audit PATH and environment variables for stale/hardcoded version entries
function Test-ConfigAudit {
    Write-Host ""
    Write-Host "=========================================="
    $title = [string]('  ' + [char]0x672C + [char]0x5730 + [char]0x914D + [char]0x7F6E + [char]0x5BA1 + [char]0x8BA1 + ' (PATH / Environment)')
    Write-Host $title
    Write-Host "=========================================="
    Write-Host ""

    $auditFound = $false
    $pathEntries = $env:PATH -split ';'

    $stalePatterns = @(
        @{ Label = "Python version path";   Pattern = 'Python3\d' }
        @{ Label = "Node version path";     Pattern = 'node[\\/]\d' }
        @{ Label = "Go version path";       Pattern = 'go\d\.\d' }
        @{ Label = "Java/JDK version path"; Pattern = 'jdk[-\\/]\d' }
        @{ Label = ".NET version path";     Pattern = 'dotnet[\\/]\d' }
        @{ Label = "Rust toolchain path";   Pattern = 'rustup[\\/]toolchains[\\/][a-z]+-\d' }
        @{ Label = "Flutter version path";  Pattern = 'flutter[\\/]\d' }
        @{ Label = "PHP version path";      Pattern = 'php[\\/]?\d' }
    )

    foreach ($entry in $pathEntries) {
        if (-not $entry) { continue }
        if (-not (Test-Path $entry -ErrorAction SilentlyContinue)) {
            $lbl = [string]([char]0x4E0D + [char]0x5B58 + [char]0x5728 + [char]0x7684 + ' PATH ' + [char]0x76EE + [char]0x5F55)
            Write-Host "  $([char]0x26A0) [$lbl]  $entry"
            $auditFound = $true
            continue
        }
        foreach ($sp in $stalePatterns) {
            if ($entry -match $sp.Pattern) {
                Write-Host "  $([char]0x26A0) [$($sp.Label)]  $entry"
                $auditFound = $true
            }
        }
    }

    $envChecks = @(
        @{ Var = 'JAVA_HOME'; Label = 'Stale JAVA_HOME';  Pattern = 'jdk[\-/]\d' }
        @{ Var = 'GOROOT';    Label = 'Stale GOROOT';     Pattern = 'go\d\.\d' }
        @{ Var = 'GOPATH';    Label = 'Stale GOPATH';     Pattern = 'go\d\.\d' }
    )

    foreach ($ec in $envChecks) {
        $val = [Environment]::GetEnvironmentVariable($ec.Var)
        if ($val -and $val -match $ec.Pattern) {
            Write-Host "  $([char]0x26A0) [$($ec.Label)]  $($ec.Var)=$val"
            $auditFound = $true
        }
    }

    if (-not $auditFound) {
        $ok = [string]([char]0x2705 + ' ' + [char]0x672A + [char]0x53D1 + [char]0x73B0 + [char]0x53EF + [char]0x7591 + [char]0x7684 + [char]0x786C + [char]0x7F16 + [char]0x7801 + [char]0x7248 + [char]0x672C + [char]0x8DEF + [char]0x5F84 + [char]0x6216 + [char]0x8FC7 + [char]0x671F + [char]0x914D + [char]0x7F6E)
        Write-Host $ok
    }

    Write-Host ""
}

# ======================================================================
#  Module 7: Main Pipeline
# ======================================================================

# Core scan pipeline — returns structured PSCustomObject[] for programmatic use
function Invoke-ToolScan {
    $registry = Get-ToolRegistry
    $total = $registry.Count
    $lbl = [string]([char]0x6B63 + [char]0x5728 + [char]0x626B + [char]0x63CF)
    $lbl2 = [string]([char]0x4E2A + [char]0x5F00 + [char]0x53D1 + [char]0x5DE5 + [char]0x5177 + '...')
    Write-Host "$lbl $total $lbl2" -ForegroundColor Cyan

    # Phase 1: Prefetch latest versions in parallel
    $allMethods = $registry | ForEach-Object { $_.LatestMethod } |
        Where-Object { $_ -and $_ -ne 'none' } | Sort-Object -Unique
    $latestCache = Get-LatestVersionBatch $allMethods

    # Phase 2: Discover installs + classify each tool
    $results = @()
    foreach ($def in $registry) {
        $chk = [string]([char]0x68C0 + [char]0x67E5)
        Write-Host "`r  $chk $($def.Name)...       " -ForegroundColor DarkGray -NoNewline

        $latest = if ($def.LatestMethod -ne 'none' -and $latestCache.ContainsKey($def.LatestMethod)) {
            $latestCache[$def.LatestMethod]
        } else { "N/A" }

        $installs = Find-LocalInstalls $def
        $result = Resolve-ToolStatus -ToolDef $def -Installs $installs -LatestVersion $latest
        $results += $result
    }
    Write-Host "`r                              " -NoNewline
    Write-Host ""

    return ,$results
}

# Full entry point: scan -> table -> summary -> config audit
# Returns result objects for further processing
function Invoke-ToolCheck {
    $results = Invoke-ToolScan

    $tableLines = Format-ToolTable $results
    foreach ($line in $tableLines) { Write-Host $line }

    Write-ScanSummary $results
    Test-ConfigAudit

    return ,$results
}

# ── Auto-run when executed directly (not dot-sourced) ─────────────
if ($MyInvocation.InvocationName -ne '.') {
    $null = Invoke-ToolCheck
}
