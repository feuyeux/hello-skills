import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from translate_only import normalize_target_language, parse_langs, translate_batch


DEFAULT_MODEL_CANDIDATES = [
    os.path.expanduser("~/zoo/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    "/Users/han/zoo/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    r"D:\coding\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-CustomVoice",
]

# Fix encoding issues on Windows
if sys.platform == "win32":
    try:
        # Fix stdout encoding
        sys.stdout.reconfigure(encoding="utf-8")
        # Fix stdin encoding
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Set environment variables for Python subprocesses
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"


def require_conda_env(env_name: str = "qwen3-tts") -> None:
    """Check if running in a conda environment with required dependencies.

    Supports both:
    - conda activate qwen3-tts && python ...
    - conda run -n qwen3-tts python ...

    We detect by checking CONDA_DEFAULT_ENV or sys.prefix containing conda env path.
    """
    # Check if CONDA_DEFAULT_ENV is set (works with both conda run and conda activate)
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "").strip()

    # Also check if we're in a conda environment by looking at sys.prefix
    # Conda environments typically have conda-meta in sys.prefix
    in_conda_env = (
        conda_env and conda_env.lower() == env_name.lower()
    ) or (
        env_name.lower() in sys.prefix.lower()
    ) or (
        "conda" in sys.prefix.lower() and "envs" in sys.prefix.lower()
    )

    if not in_conda_env:
        # Try importing required packages to see if they're available
        try:
            import torch
            import soundfile
            # If we can import them, allow running anyway
            return
        except ImportError:
            pass

        output = {
            "translations": [],
            "audio_paths": [],
            "errors": [
                {
                    "lang": "",
                    "stage": "env",
                    "message": (
                        f"Not running in {env_name} conda environment. "
                        f"Current: {conda_env}, Prefix: {sys.prefix}. "
                        f"Use: conda run -n {env_name} python scripts/translate_tts.py ..."
                    ),
                }
            ],
        }
        print(json.dumps(output, ensure_ascii=False))
        raise SystemExit(2)


LANGUAGE_ALIASES_TO_SINGLE_TTS = {
    "chinese": "Chinese",
    "mandarin": "Chinese",
    "中文": "Chinese",
    "汉语": "Chinese",
    "国语": "Chinese",
    "english": "English",
    "英语": "English",
    "英文": "English",
    "japanese": "Japanese",
    "日语": "Japanese",
    "日文": "Japanese",
    "korean": "Korean",
    "韩语": "Korean",
    "韩文": "Korean",
    "german": "German",
    "德语": "German",
    "德文": "German",
    "french": "French",
    "法语": "French",
    "法文": "French",
    "russian": "Russian",
    "俄语": "Russian",
    "俄文": "Russian",
    "portuguese": "Portuguese",
    "葡萄牙语": "Portuguese",
    "葡萄牙文": "Portuguese",
    "葡语": "Portuguese",
    "葡文": "Portuguese",
    "spanish": "Spanish",
    "西班牙语": "Spanish",
    "西班牙文": "Spanish",
    "italian": "Italian",
    "意大利语": "Italian",
    "意大利文": "Italian",
}
SINGLE_TTS_SUPPORTED_LANGUAGES = set(LANGUAGE_ALIASES_TO_SINGLE_TTS.values())
FRIENDLY_LANGUAGE_LABELS = {
    "Chinese": "中文",
    "English": "英文",
    "French": "法语",
    "German": "德语",
    "Russian": "俄语",
    "Italian": "意大利语",
    "Spanish": "西班牙语",
    "Portuguese": "葡萄牙语",
    "Japanese": "日语",
    "Korean": "韩语",
}


def normalize_language_for_single_tts(lang: str) -> Optional[str]:
    return LANGUAGE_ALIASES_TO_SINGLE_TTS.get(lang.strip().lower())


def to_friendly_label(raw_lang: str, normalized_lang: str) -> str:
    return FRIENDLY_LANGUAGE_LABELS.get(normalized_lang, raw_lang)


def run_single_tts(
    *,
    script_path: str,
    sentence: str,
    language: str,
    output_path: str,
    model_path: str,
    speaker: Optional[str],
    instruct: Optional[str],
    timeout: int,
) -> Tuple[bool, str]:
    cmd = [
        sys.executable,
        script_path,
        sentence,
        language,
        "--output",
        output_path,
    ]
    if model_path:
        cmd.extend(["--model-path", model_path])
    if speaker:
        cmd.extend(["--speaker", speaker])
    if instruct is not None:
        cmd.extend(["--instruct", instruct])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"single_tts timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    if result.returncode == 0 and os.path.isfile(output_path):
        return True, ""

    detail = (result.stderr or result.stdout or "").strip()
    if len(detail) > 1200:
        detail = detail[-1200:]
    return False, f"single_tts failed (code={result.returncode}): {detail}"


def build_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def unique_path(base_dir: str, lang: str, timestamp: str) -> str:
    safe_lang = "".join(ch for ch in lang if ch.isalnum() or ch in ("-", "_"))
    if not safe_lang:
        safe_lang = "lang"
    filename = f"{safe_lang}_{timestamp}.wav"
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        return path
    index = 1
    while True:
        filename = f"{safe_lang}_{timestamp}_{index}.wav"
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            return path
        index += 1


def save_translations_text(output_dir: str, target_langs: List[str], translations: List[Optional[str]]) -> str:
    path = os.path.join(output_dir, "translations.txt")
    lines: List[str] = []
    for lang, text in zip(target_langs, translations):
        lines.append(f"[{lang}]")
        lines.append(text or "")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


def default_output_root() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", "translate_tts")


def resolve_model_path(cli_model_path: Optional[str]) -> Optional[str]:
    if cli_model_path:
        return os.path.expanduser(cli_model_path)

    env_model_path = os.getenv("QWEN3_TTS_MODEL_PATH", "").strip()
    if env_model_path:
        return os.path.expanduser(env_model_path)

    for candidate in DEFAULT_MODEL_CANDIDATES:
        if os.path.isdir(candidate):
            return candidate
    return None


def main() -> int:
    # Enforce correct environment before parsing args to fail fast
    require_conda_env("qwen3-tts")

    parser = argparse.ArgumentParser(description="先翻译中文，再生成多语种语音（支持自然语言语言名）。")
    parser.add_argument("--text", help="Chinese input text (or use --text-file)")
    parser.add_argument("--text-file", help="Read text from a file (UTF-8 encoded)")
    parser.add_argument("--langs", required=True, help="目标语言，逗号分隔或 JSON 数组（例如：英文,日文,韩文）")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="translategemma")
    parser.add_argument("--ollama-timeout", type=int, default=60)
    parser.add_argument("--model-path", default=None, help="Optional local Qwen3-TTS model directory")
    parser.add_argument("--output-root", default=None, help="Base directory for task outputs")
    parser.add_argument("--output-dir", default=None, help="Optional: explicit task output directory")
    parser.add_argument("--result-file", help="Output result JSON to file (recommended on Windows)")
    parser.add_argument("--speaker", default=None, help="Optional: pass through to single_tts.py")
    parser.add_argument("--instruct", default=None, help="Optional: pass through to single_tts.py")
    parser.add_argument(
        "--single-tts-script",
        default=os.path.join(os.path.dirname(__file__), "single_tts.py"),
        help="Path to single_tts.py",
    )
    parser.add_argument("--tts-timeout", type=int, default=180, help="Timeout (seconds) per TTS item")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()

    model_path = resolve_model_path(args.model_path)
    output_root = os.path.expanduser(args.output_root) if args.output_root else default_output_root()

    task_timestamp = build_timestamp()
    task_output_dir = args.output_dir or os.path.join(output_root, task_timestamp)
    os.makedirs(task_output_dir, exist_ok=True)
    if not args.result_file:
        args.result_file = os.path.join(task_output_dir, "result.json")

    # Initialize errors list early for error handling
    errors: List[Dict[str, str]] = []

    # Handle text input from file or argument
    input_text = ""
    if args.text_file:
        try:
            with open(args.text_file, "r", encoding="utf-8") as f:
                input_text = f.read().strip()
        except Exception as e:
            errors.append({"lang": "", "stage": "input", "message": f"Failed to read text file: {e}"})
            output = {
                "translations": [],
                "audio_paths": [],
                "errors": errors,
            }
            print(json.dumps(output, ensure_ascii=False))
            return 1
    elif args.text:
        input_text = args.text
    else:
        errors.append({"lang": "", "stage": "input", "message": "Either --text or --text-file is required"})
        output = {
            "translations": [],
            "audio_paths": [],
            "errors": errors,
        }
        print(json.dumps(output, ensure_ascii=False))
        return 1

    raw_target_langs = parse_langs(args.langs)
    try:
        target_langs = [normalize_target_language(lang) for lang in raw_target_langs]
    except ValueError as exc:
        errors.append({"lang": "", "stage": "input", "message": str(exc)})
        output = {
            "translations": [],
            "audio_paths": [],
            "errors": errors,
        }
        print(json.dumps(output, ensure_ascii=False))
        return 1
    target_lang_labels = [
        to_friendly_label(raw_lang, normalized_lang)
        for raw_lang, normalized_lang in zip(raw_target_langs, target_langs)
    ]
    translations: List[Optional[str]] = [None] * len(target_langs)
    audio_paths: List[Optional[str]] = [None] * len(target_langs)

    if not target_langs:
        errors.append({"lang": "", "stage": "input", "message": "no target languages"})
        output = {
            "translations": translations,
            "audio_paths": audio_paths,
            "errors": errors,
        }
        print(json.dumps(output, ensure_ascii=False))
        return 1

    translations, translation_errors = translate_batch(
        text=input_text,
        target_langs=target_langs,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        timeout=args.ollama_timeout,
        max_workers=args.max_workers,
    )
    errors.extend(translation_errors)
    translations_text_path = ""
    try:
        translations_text_path = save_translations_text(task_output_dir, target_lang_labels, translations)
    except Exception as exc:  # noqa: BLE001
        errors.append({"lang": "", "stage": "output", "message": f"Failed to save translations.txt: {exc}"})

    valid_items = [
        (idx, target_lang_labels[idx], target_langs[idx], translations[idx])
        for idx in range(len(target_langs))
        if translations[idx]
    ]

    tts_supported_items = []
    for idx, lang_label, normalized_lang, text in valid_items:
        normalized = normalize_language_for_single_tts(normalized_lang)
        if normalized and normalized in SINGLE_TTS_SUPPORTED_LANGUAGES:
            tts_supported_items.append((idx, lang_label, normalized, text))
        else:
            errors.append(
                {
                    "lang": lang_label,
                    "stage": "tts",
                    "message": (
                        f"Language '{lang_label}' not supported by single_tts. "
                        "Supported: 中文, 英文/英语, 法语, 德语, 俄语, 意大利语, 西班牙语, 葡萄牙语, 日语/日文, 韩语/韩文"
                    ),
                }
            )

    if tts_supported_items:
        script_path = os.path.abspath(args.single_tts_script)
        if not os.path.isfile(script_path):
            for _, lang_label, _, _ in tts_supported_items:
                errors.append(
                    {
                        "lang": lang_label,
                        "stage": "tts",
                        "message": f"single_tts script not found: {script_path}",
                    }
                )
        else:
            timestamp = build_timestamp()
            for index, lang_label, normalized_lang, translated_text in tts_supported_items:
                path = unique_path(task_output_dir, lang_label, timestamp)
                ok, err = run_single_tts(
                    script_path=script_path,
                    sentence=translated_text,
                    language=normalized_lang,
                    output_path=path,
                    model_path=model_path or "",
                    speaker=args.speaker,
                    instruct=args.instruct,
                    timeout=args.tts_timeout,
                )
                if ok:
                    audio_paths[index] = path
                else:
                    errors.append({"lang": lang_label, "stage": "tts", "message": err})

    output = {
        "translations": translations,
        "audio_paths": audio_paths,
        "task_dir": task_output_dir,
        "translations_text_path": translations_text_path,
        "errors": errors,
    }
    json_output = json.dumps(output, ensure_ascii=False, indent=2)

    if args.result_file:
        try:
            with open(args.result_file, "w", encoding="utf-8") as f:
                f.write(json_output)
        except Exception as e:
            print(f"Warning: Failed to write result file: {e}", file=sys.stderr)
            print(json_output)
    else:
        print(json_output)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
