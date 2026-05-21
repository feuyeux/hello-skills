# 获取最新版本的方式

本文档规定了每种开发工具获取最新版本的标准方式。toolcheck 脚本使用这些方法自动检测最新版本。

格式说明：`|工具名|获取方式|`

## 版本检测方法

toolcheck 支持三种自动化检测方式：

1. **`brew:`** - 通过 Homebrew formulae API 获取（仅 macOS/Linux）
2. **`gh:`** - 通过 GitHub Releases API 获取 latest release
3. **`gh_tags:`** - 通过 GitHub Tags API 获取最新 tag（适用于无 release 的仓库）
4. **`winget:`** - 通过 winget search 获取（仅 Windows PowerShell 版本）

PowerShell 版本额外支持动态探测 pip/conda 安装的工具。

## Python / Conda

|python|https://www.python.org/downloads/|
|conda|https://docs.conda.io/en/latest/miniconda.html|
|uv|https://github.com/astral-sh/uv/releases/latest|

## Node.js

|node|https://nodejs.org/en/download/|
|npm|随 Node.js 自动安装，或 https://www.npmjs.com/package/npm|

## JDK / Build Tools

|java|https://adoptium.net/temurin/releases/ 或 https://www.oracle.com/java/technologies/downloads/|
|gradle|https://gradle.org/releases/|
|maven|https://maven.apache.org/download.cgi|

## Rust

|rust|https://www.rust-lang.org/tools/install 或 rustup update|

## Go / C / C++

|go|https://go.dev/dl/|
|gcc|系统包管理器 (brew/apt/yum) 或 https://gcc.gnu.org/releases.html|
|clang|系统包管理器 (brew/apt/yum) 或 https://releases.llvm.org/|
|cmake|https://cmake.org/download/|
|bazel|https://github.com/bazelbuild/bazel/releases/latest|

## .NET / PHP / Dart / Swift

|dotnet|https://dotnet.microsoft.com/download|
|php|https://www.php.net/downloads.php|
|composer|https://getcomposer.org/download/|
|dart|https://dart.dev/get-dart|
|flutter|https://flutter.dev/docs/get-started/install|
|swift|https://www.swift.org/download/ 或 Xcode 更新|

## AI CLI Tools

|claude|https://github.com/anthropics/claude-code/releases/latest 或 `claude update`|
|codex|检查官方仓库或包管理器|
|gemini-cli|https://github.com/google-gemini/generative-ai-cli/releases/latest|
|opencode|检查官方仓库或包管理器|
|hermes|https://pypi.org/project/hermes-agent/ 或 `hermes update` (需 UTF-8 环境)|
|uv|https://github.com/astral-sh/uv/releases/latest 或 `pip install --upgrade uv`|

## 通用获取方式

1. **GitHub Releases**: `https://github.com/{org}/{repo}/releases/latest`
2. **官方下载页**: 访问工具官网的 Downloads 页面
3. **包管理器**: 
   - macOS: `brew upgrade {tool}`
   - Linux: `apt update && apt upgrade {tool}` 或 `yum update {tool}`
   - Windows: `winget upgrade {tool}` 或 `choco upgrade {tool}` (需管理员权限)
4. **版本管理器**:
   - Node.js: `nvm install node` (最新版) 或 `nvm install --lts` (LTS)
   - Python: `pyenv install {version}` 或 `conda update python`
   - Java: `sdk install java {version}` 或 `winget upgrade EclipseAdoptium.Temurin.{version}.JDK`
   - Rust: `rustup update`
5. **Python 包管理器**:
   - pip: `pip install --upgrade {package}`
   - conda: `conda update {package}` 或 `conda update --all`

## 自动化检查

可以使用以下 API 端点自动检查最新版本：

- **GitHub Releases**: `https://api.github.com/repos/{org}/{repo}/releases/latest`
- **GitHub Tags**: `https://api.github.com/repos/{org}/{repo}/tags` (取第一个)
- **npm**: `https://registry.npmjs.org/{package}/latest`
- **PyPI**: `https://pypi.org/pypi/{package}/json`
- **Maven Central**: `https://search.maven.org/solrsearch/select?q=g:{group}+AND+a:{artifact}&rows=1&wt=json`
- **Homebrew**: `https://formulae.brew.sh/api/formula/{formula}.json`
- **winget**: `winget show {package-id}` (需解析输出)

## toolcheck 使用的检测方法映射

| 工具 | Bash 脚本方法 | PowerShell 脚本方法 |
|------|--------------|-------------------|
| python | `brew:python@3` | `winget:Python.Python.3.13` 或动态探测 |
| node | `brew:node` | `winget:OpenJS.NodeJS.LTS` |
| java | `brew:openjdk` | 动态探测已安装的 JDK 包 ID |
| go | `gh:golang/go` | `winget:GoLang.Go` |
| rust | `gh:rust-lang/rust` | `winget:Rustlang.Rust.MSVC` |
| claude | `gh:anthropics/claude-code` | `gh:anthropics/claude-code` |
| uv | `gh:astral-sh/uv` | 动态探测 pip/conda 安装 |
| hermes | PyPI | 动态探测 pip/conda 安装 |
