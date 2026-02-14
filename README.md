# translate-tts

基于本目录 `scripts/` 的真实实现，`translate-tts` 的主流程是：
先把中文并发翻译到多个目标语言，再按语言调用 Qwen3-TTS 逐条生成音频。

## 原理图（Implementation-Based）

```mermaid
---
config:
  layout: dagre
  theme: neo
  look: neo
---
flowchart TB
    A["run_translate_tts.sh"] --> B["conda run -n qwen3-tts python translate_tts.py"]
    B --> C{"输入检查"}
    C -- "text 或 text-file" --> D["parse_langs + normalize_target_language"]
    C -- 缺失输入 --> X1["errors stage input"]
    D --> E["translate_batch 并发翻译"]
    E --> F["调用 Ollama api generate 默认 translategemma"]
    F --> G["得到 translations 和 translation errors"]
    G --> H["写入 translations.txt"]
    H --> I{"逐语言是否支持 TTS"}
    I -- 支持10种 --> J["subprocess 调用 single_tts.py"]
    I -- 不支持 --> X2["errors stage tts"]
    J --> K["single_tts 解析语言并选择 speaker"]
    K --> L["加载 Qwen3TTSModel 本地或远端"]
    L --> M["生成音频 时长异常则重试和兜底"]
    M --> N["输出 lang timestamp wav"]
    N --> O["汇总 result.json"]
    X1 --> O
    X2 --> O
    O --> P["返回 translations audio_paths task_dir translations_text_path errors"]

    F@{ shape: rounded}
    L@{ shape: rounded}
    M@{ shape: rounded}
    style F stroke:#2962FF,fill:#FFE0B2,color:#000000
    style L fill:#FFE0B2
    style M stroke:#FFE0B2,fill:#FFE0B2
```

## 关键实现点

- 翻译层：`translate_only.py` 使用 `ThreadPoolExecutor` 并发调用 Ollama。
- TTS 层：`translate_tts.py` 对每种语言单独调用 `single_tts.py`，失败不阻断其他语言。
- 语言支持：
  - 翻译支持更多语言别名（含阿拉伯语、印地语、泰语、越南语等）。
  - TTS 仅支持 `single_tts.py` 中的 10 种语言（中文/英文/法语/德语/俄语/意大利语/西班牙语/葡萄牙语/日语/韩语）。
- 输出目录默认：`~/Downloads/translate_tts/<YYYYmmdd_HHMMSS_mmm>/`
  - `translations.txt`
  - `result.json`
  - `*.wav`

## 相关脚本

- `scripts/translate_tts.py`：主流程（翻译 + TTS）
- `scripts/translate_only.py`：翻译实现
- `scripts/single_tts.py`：单条 TTS 实现
- `scripts/run_translate_tts.sh`：Bash 启动入口
