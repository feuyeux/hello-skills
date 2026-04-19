# 获取最新版本的方式

本文档规定了每种开发工具获取最新版本的标准方式。

格式说明：`|工具名|获取方式|`

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

|claude|https://github.com/anthropics/claude-code/releases/latest|
|codex|检查官方仓库或包管理器|
|gemini-cli|https://github.com/google/generative-ai-cli/releases/latest|
|opencode|检查官方仓库或包管理器|
|hermes|检查官方仓库或包管理器|

## 通用获取方式

1. **GitHub Releases**: `https://github.com/{org}/{repo}/releases/latest`
2. **官方下载页**: 访问工具官网的 Downloads 页面
3. **包管理器**: 
   - macOS: `brew upgrade {tool}`
   - Linux: `apt update && apt upgrade {tool}` 或 `yum update {tool}`
   - Windows: `choco upgrade {tool}` 或 `winget upgrade {tool}`
4. **版本管理器**:
   - Node.js: `nvm install node` (最新版) 或 `nvm install --lts` (LTS)
   - Python: `pyenv install {version}`
   - Java: `sdk install java {version}`
   - Rust: `rustup update`

## 自动化检查

可以使用以下 API 端点自动检查最新版本：

- GitHub: `https://api.github.com/repos/{org}/{repo}/releases/latest`
- npm: `https://registry.npmjs.org/{package}/latest`
- PyPI: `https://pypi.org/pypi/{package}/json`
- Maven Central: `https://search.maven.org/solrsearch/select?q=g:{group}+AND+a:{artifact}&rows=1&wt=json`
