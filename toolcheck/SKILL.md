---
name: toolcheck
description: "Scan 25 development tools for installation conflicts, outdated versions, and missing installs. Generates a markdown table report showing status (重复/过期/正常/缺失), local vs latest versions, install paths, and recommended actions. Use when: user asks to check dev tools, audit installed tools, find version conflicts, or check for updates on clang/java/python/swift/cmake/composer/conda/dotnet/go/php/rust/bazel/claude/codex/dart/flutter/gcc/gemini-cli/gradle/hermes/maven/node/npm/opencode/uv."
---

# Toolcheck

Scan 25 development tools and produce a diagnostic report table.

## Execution

Run this script and output its **full stdout verbatim** — do not summarize, truncate, or reformat:

```bash
bash ~/.claude/skills/toolcheck/scripts/toolcheck.sh
```

**IMPORTANT**: The script outputs a complete 25-row markdown table plus a summary line. Print ALL output exactly as-is. Do not omit any rows or columns. Do not add commentary between table rows.
