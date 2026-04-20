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
