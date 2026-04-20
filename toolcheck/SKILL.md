---
name: toolcheck
description: "扫描 25 个常用开发工具，检测安装冲突、版本过期和缺失情况，生成 Markdown 诊断报告表格。当用户提到检查开发工具、审计已安装工具、查找版本冲突、检查更新，或提及以下任何工具名称时，都应使用此技能：clang/java/python/swift/cmake/composer/conda/dotnet/go/php/rust/bazel/claude/codex/dart/flutter/gcc/gemini-cli/gradle/hermes/maven/node/npm/opencode/uv。即使用户只是随口说「我的工具是不是该更新了」或「帮我看看环境有没有问题」，也应触发此技能。"
---

# Toolcheck

扫描 25 个开发工具，生成一份包含安装状态、版本对比和升级建议的诊断报告。

## 执行流程

脚本默认只保存报告文件，不向终端输出表格（避免终端截断导致表格丢失）。

**第一步：运行脚本**（需要 120 秒以上，脚本会从 winget/GitHub 拉取最新版本）

```bash
# Windows
pwsh -ExecutionPolicy Bypass -File "$HOME\.claude\skills\toolcheck\scripts\toolcheck.ps1"

# macOS / Linux
bash ~/.claude/skills/toolcheck/scripts/toolcheck.sh
```

脚本结束时会打印报告路径，格式如：`报告已保存到: ~/toolcheck/report_0420_181643.md`

**第二步：读取报告文件，将内容原样展示给用户**

用文件读取工具（如 `read_file`）打开上一步打印的路径。报告保存在 `~/toolcheck/` 目录下，文件名格式为 `report_MMdd_HHmmss.md`。

## 输出行为

报告表格是最终交付物。用户使用此技能的目的是获得一份**一眼可扫的全景视图**——哪些工具重复了、哪些过期了、哪些正常。如果把表格转述成 bullet points 或摘要，用户反而需要更多时间理解，也无法直接复制到工单或文档中。

因此：

- 将报告文件内容原样粘贴到回复中，包括所有 ✓ 正常 的行
- 不要转述、归纳或改变格式
- 表格后可以追加一句「需要我帮你升级过期工具吗？」，但不要添加其他分析
- 如果脚本超时，用更长的超时时间重新运行，不要放弃

## 重复工具去重规范

报告中标记为「⚠ 重复」的工具，备注列会自动标注「★ 保留」和「✗ 移除」。

### 选择算法（脚本已内置）

脚本按以下优先级自动选出最佳安装：

1. **版本最高者优先** — 直接比较 semver
2. **包管理器路径优先** — 版本相同时，homebrew/winget/choco/scoop/nvm 管理的路径优于手动安装目录
3. **PATH 顺序优先** — 以上都相同时，保留 PATH 中排位更前的（系统会优先调用它）

### 报告输出示例

```
|  3 | java       | ⚠ 重复 | 21.0.3     | D:\zoo\jdk-21.0.3\bin\java.exe           | 25.0.2 | 保留                | ✗ 移除 |
|    |   ↳        | ⚠ 重复 | 25.0.0.36  | ...Eclipse Adoptium\jdk-25...\bin\java.exe | 25.0.2 | winget upgrade ...  | ★ 保留 |
```

### 用户确认去重后，agent 必须按顺序执行以下操作

**第 A 步：移除「✗ 移除」的安装**

根据被移除项的安装路径，判断安装方式并执行对应的卸载操作：

| 安装方式 | 路径特征 | 移除命令 |
|---------|---------|---------|
| winget | `winget list` 能找到对应包 | `winget uninstall <包ID>` |
| choco | 路径含 `chocolatey` | `gsudo choco uninstall <pkg> -y`（需提权） |
| brew | 路径含 `homebrew`/`Cellar` | `brew uninstall <formula>` |
| scoop | 路径含 `scoop` | `scoop uninstall <pkg>` |
| npm -g | 路径含 `npm`/`node_modules` | `npm uninstall -g <pkg>` |
| rustup | 路径含 `rustup/toolchains` | `rustup toolchain uninstall <toolchain>` |
| conda | 路径含 `conda`/`envs` | `conda remove <pkg>` 或删除环境目录 |
| 手动安装 | 自定义目录（如 `D:\zoo\jdk-21.0.3\`） | 直接删除该目录：`rm -rf <目录>`（macOS/Linux）或 `Remove-Item -Recurse -Force <目录>`（Windows） |

**第 B 步：清理 PATH 和环境变量中的残留引用**

移除目录后，其路径仍可能残留在 PATH 或环境变量中，**必须同步清理**：

macOS/Linux：
```bash
# 1. 备份
cp ~/.zshrc ~/.zshrc.bak.$(date +%s)
# 2. 从 .zshrc / .bashrc / .profile 中删除指向已移除目录的 export PATH=... 行
# 3. 如果有 JAVA_HOME / GOROOT 指向已删除路径，更新为保留项的路径
# 4. source ~/.zshrc
```

Windows：
```powershell
# 1. 查看当前 PATH
[Environment]::GetEnvironmentVariable('PATH', 'User')
# 2. 移除包含已删除目录的条目
$path = [Environment]::GetEnvironmentVariable('PATH', 'User')
$newPath = ($path -split ';' | Where-Object { $_ -notmatch '已删除目录的关键词' }) -join ';'
[Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
# 3. 如果有 JAVA_HOME 等指向已删除路径，同步更新
[Environment]::SetEnvironmentVariable('JAVA_HOME', '新路径', 'User')
# 4. 提醒用户重启终端
```

**第 C 步：验证**

```bash
# 确认只剩一个安装
type -aP <cmd>          # macOS/Linux
Get-Command <cmd> -All  # Windows

# 确认版本正确
<cmd> --version
```

如果验证后仍有多个路径，说明还有残留未清理，重复 A-B 步。

## 升级后清理规范

当用户确认升级过期工具后，**必须**执行以下三步，缺一不可：

### 1. 执行升级命令

使用报告中「操作」列给出的升级命令。PS1 脚本会**动态探测**实际安装方式并生成正确命令（见 `Resolve-UpgradeCmd`），但 AI agent 执行时仍需注意：

#### 权限问题
- **choco** 命令需要管理员权限。优先检查 `gsudo` 是否可用：
  - 有 gsudo：`gsudo choco upgrade <pkg> -y`
  - 无 gsudo：提示用户「请在管理员终端中运行」，**不要**在普通终端强行执行
- **composer self-update** 若安装在 `C:\ProgramData\` 下，同样需要提权
- **winget** 通常不需要管理员权限

#### 包 ID 匹配问题
- **不要硬猜 winget 包 ID**。升级前先用 `winget list --name <关键词>` 确认实际已安装的包 ID
  - Java: 可能是 `EclipseAdoptium.Temurin.25.JDK`、`Oracle.JDK.21` 等，取决于用户安装的发行版
  - Node: 可能是 `OpenJS.NodeJS.LTS` 或 `OpenJS.NodeJS`（Current）
  - 若 `winget list` 找不到（手动安装的），则 winget upgrade 无法使用，应提示手动下载
- PS1 脚本已内置 `Find-WingetPackageId` 自动探测，报告中的命令通常已是正确的

#### 手动安装的工具
- gradle/maven 等若安装在自定义目录（如 `D:\zoo\gradle-9.3.1\`），choco/winget 都无法管理
- 报告会显示 `Manual: download from <URL>`，agent 应提示用户手动下载并替换旧目录

#### 特殊工具
- `hermes update`：Windows 上需要 `chcp 65001` + `PYTHONIOENCODING=utf-8` 避免 GBK 编码崩溃（PS1 已内置）
- `uv`/`hermes` 等：脚本会**自动检测 pip/conda 安装**，若路径在 anaconda/miniconda/venv/envs 下，升级命令自动替换为 `pip install --upgrade <包名>`（如 `pip install --upgrade uv`、`pip install --upgrade hermes-agent`）
- `claude update`：自带升级器，直接运行即可

### 2. 删除老版本残留

升级完成后，检查并清理旧版本：

```bash
# 检查是否仍有多个版本共存（升级后重新扫描路径）
type -aP <cmd>          # macOS/Linux
Get-Command <cmd> -All  # Windows PowerShell
```

常见清理操作：
- **brew**: `brew cleanup <formula>` 删除旧版本缓存
- **winget**: 旧版本通常自动替换；若残留，用 `winget uninstall <旧包ID>` 移除
- **npm -g**: `npm ls -g <pkg>` 确认只有一个版本，多余的 `npm uninstall -g <pkg>` 后重装
- **conda**: `conda clean --all` 清理缓存；手动删除 `envs/` 下废弃环境
- **rustup**: `rustup toolchain uninstall <旧toolchain>`
- **手动安装的工具**: 直接删除旧目录（如 `/usr/local/go.old`、`C:\Go1.21\`）

### 3. 更新 Shell 配置文件

升级后**必须**检查并更新以下配置文件中的硬编码版本路径：

**需检查的文件：**
- `~/.zshrc`、`~/.zprofile`、`~/.zshenv`
- `~/.bashrc`、`~/.bash_profile`、`~/.profile`
- `~/.config/fish/config.fish`
- Windows: 用户/系统 PATH 环境变量

**需更新的典型模式：**

| 模式 | 示例 | 操作 |
|------|------|------|
| 硬编码版本号的 PATH | `export PATH="/usr/local/go1.21/bin:$PATH"` | 改为 `go1.22` 或去掉版本号 |
| JAVA_HOME 指向旧 JDK | `export JAVA_HOME=/Library/Java/.../jdk-17` | 更新为新版本路径 |
| GOROOT / GOPATH | `export GOROOT=/usr/local/go1.21` | 更新或删除（Go 模块模式不需要） |
| Python 版本路径 | `alias python3=/usr/local/bin/python3.11` | 更新为 `python3.12` |
| conda init 块 | 指向旧 conda 路径 | 重新运行 `conda init zsh` |
| Windows PATH 残留 | `C:\Python311\` 仍在 PATH 中 | 通过系统设置移除旧条目，添加新版本路径 |

**操作原则：**
- 优先使用**不含版本号的符号链接路径**（如 `/usr/local/bin/python3` 而非 `/usr/local/bin/python3.11`），减少未来升级的维护成本
- 修改配置文件前先备份：`cp ~/.zshrc ~/.zshrc.bak.$(date +%s)`
- 修改后提醒用户执行 `source ~/.zshrc`（或重启终端）使变更生效
- Windows 上修改系统 PATH 后提醒用户重启终端

## 从仓库目录运行（替代路径）

```bash
# Windows
pwsh -ExecutionPolicy Bypass -File toolcheck/scripts/toolcheck.ps1
# macOS / Linux
bash toolcheck/scripts/toolcheck.sh
```

加 `-Console`（PS1）或 `-v`（bash）可以同时将表格输出到终端，适合人类直接查看。

## 覆盖的 25 个工具

```
clang  java  python  swift  cmake  composer  conda  dotnet  go  php
rust  bazel  claude  codex  dart  flutter  gcc  gemini-cli  gradle  hermes
maven  node  npm  opencode  uv
```

## 报告格式速览

报告包含一个 8 列表格（序号 / 工具 / 状态 / 本地版本 / 本地安装路径 / 最新版本 / 操作 / 备注），按状态分组排序：⚠ 重复 → ⚠ 过期 → ✓ 正常 → — 不适用 → ✗ 缺失。重复安装的工具每条路径独占一行（子行用 ↳ 标记）。

表格后紧跟一行汇总，例如：`⚠ 重复: 4 | ⚠ 过期: 10 | ✓ 正常: 9 | — 不适用: 1 | ✗ 缺失: 1`。

> 完整的列定义、状态枚举和排序规则见 `references/output_spec.md`。

## 参考文档

| 文档                        | 内容                                              | 何时查阅                      |
| --------------------------- | ------------------------------------------------- | ----------------------------- |
| `references/output_spec.md` | 表格列定义、状态枚举、排序规则、配置审计规格      | 需要解析或验证输出格式时      |
| `references/api.md`         | PowerShell 模块化函数 API、结果对象结构、使用示例 | 需要编程调用 toolcheck 函数时 |
