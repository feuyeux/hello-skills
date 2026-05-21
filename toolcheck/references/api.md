# PowerShell API 参考

Windows 脚本 (`toolcheck.ps1`) 提供模块化函数 API。通过 dot-source 加载（不自动运行）：

```powershell
. toolcheck/scripts/toolcheck.ps1
```

## 版本历史

- **v1.0** (2026-05): 初始版本，基础工具扫描
- **v2.0** (2026-05): 添加去重算法、动态升级命令解析、pip/conda 自动探测

## 核心函数

| 函数                         | 返回值             | 说明                                             |
| ---------------------------- | ------------------ | ------------------------------------------------ |
| `Invoke-ToolScan`            | `PSCustomObject[]` | 完整扫描流水线：注册表 → 发现 → 拉取最新 → 分类 |
| `Invoke-ToolCheck [-Quiet]`  | `PSCustomObject[]` | `Invoke-ToolScan` + 输出表格 + 汇总 + 配置审计   |
| `Format-ToolTable $results`  | `string[]`         | 将结果对象渲染为格式化表格行                     |
| `Write-ScanSummary $results` | _(控制台)_         | 输出汇总计数                                     |
| `Test-ConfigAudit`           | _(控制台)_         | 审计 PATH/环境变量中的过期条目                   |

`-Quiet` 开关：跳过控制台表格/汇总/审计输出，仅保存报告文件并打印路径。

## 流水线构建块

| 函数                                                                       | 说明                                              |
| -------------------------------------------------------------------------- | ------------------------------------------------- |
| `Get-ToolRegistry`                                                         | 返回 25 个工具定义（Name/Cmd/VerCmd/LatestMethod/UpgradeCmd） |
| `Find-CommandPaths $cmd`                                                   | 查找所有安装路径，去重 Windows 包装器（.ps1/.cmd/.bat）       |
| `Get-InstalledVersion $verCmd $cmdPath`                                    | 对指定路径执行版本命令（8 秒超时）                            |
| `Find-LocalInstalls $toolDef`                                              | 发现所有安装，含每路径版本信息                                |
| `Get-LatestVersionBatch $methods`                                          | 并行拉取最新版本（winget/GitHub，15 秒超时）                  |
| `Resolve-ToolStatus -ToolDef $def -Installs $installs -LatestVersion $ver` | 分类：normal/outdated/duplicate/missing/na                    |
| `Get-RecommendedOperation $status $ver $latest $upgradeCmd`                | 确定推荐操作                                                  |
| `Resolve-UpgradeCmd $toolName $cmdPath $upgradeTemplate`                   | 动态探测安装方式并生成正确的升级命令                          |
| `Select-PreferredInstall $installs`                                        | 从重复安装中选择最佳保留项（版本→包管理器→PATH顺序）          |
| `Find-WingetPackageId $toolName`                                           | 自动查找工具的 winget 包 ID                                   |

## 结果对象结构

`Invoke-ToolScan` 返回的每个元素包含：

```
Name          : string        — 工具名称
Status        : string        — normal|outdated|duplicate|missing|na
StatusLabel   : string        — 显示标签（✓ 正常, ⚠ 过期 等）
LatestVersion : string        — 最新可用版本或 "N/A"
UpgradeCmd    : string        — 升级命令模板
Installs[]    : object[]      — 每个安装路径的详细信息：
  .Path          : string     — 完整文件路径
  .PathDisplay   : string     — 截断后的路径（用于表格显示）
  .VersionRaw    : string     — 原始版本输出（首行）
  .VersionParsed : string     — 提取的 semver
  .Note          : string     — 错误/超时备注
  .Operation     : string     — 该安装的推荐操作
  .IsPreferred   : bool       — 是否为去重算法选中的保留项（仅重复工具）
  .Verdict       : string     — "★ 保留" 或 "✗ 移除"（仅重复工具）
```

## 使用示例

### 示例 1：筛选过期工具

```powershell
. toolcheck/scripts/toolcheck.ps1
$results = Invoke-ToolScan
$results | Where-Object Status -eq 'outdated' | ForEach-Object {
    Write-Host "$($_.Name): $($_.Installs[0].VersionParsed) -> $($_.LatestVersion)"
    Write-Host "  Run: $($_.UpgradeCmd)"
}
```

### 示例 2：自动升级所有过期工具

```powershell
. toolcheck/scripts/toolcheck.ps1
$results = Invoke-ToolScan
$outdated = $results | Where-Object Status -eq 'outdated'

foreach ($tool in $outdated) {
    $cmd = $tool.Installs[0].Operation
    if ($cmd -notmatch '^Manual:') {
        Write-Host "Upgrading $($tool.Name)..."
        Invoke-Expression $cmd
    }
}
```

### 示例 3：处理重复安装

```powershell
. toolcheck/scripts/toolcheck.ps1
$results = Invoke-ToolScan
$duplicates = $results | Where-Object Status -eq 'duplicate'

foreach ($tool in $duplicates) {
    Write-Host "`n$($tool.Name) has multiple installations:"
    foreach ($install in $tool.Installs) {
        $marker = if ($install.IsPreferred) { "★ KEEP" } else { "✗ REMOVE" }
        Write-Host "  $marker $($install.Path) (v$($install.VersionParsed))"
    }
}
```

### 示例 4：生成 JSON 报告

```powershell
. toolcheck/scripts/toolcheck.ps1
$results = Invoke-ToolScan
$results | ConvertTo-Json -Depth 5 | Out-File ~/toolcheck/report.json
```
