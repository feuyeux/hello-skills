import argparse
import json
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


import re


def require_conda_env(env_name: str = "qwen3-tts") -> None:
    """Check if running in a conda environment with required dependencies.

    Supports both:
    - conda activate qwen3-tts && python ...
    - conda run -n qwen3-tts python ...

    We detect by checking CONDA_DEFAULT_ENV or sys.prefix containing conda env path.
    """
    try:
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
                            f"Use: conda run -n {env_name} python scripts/translate_then_tts.py ..."
                        ),
                    }
                ],
            }
            print(json.dumps(output, ensure_ascii=False))
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception:
        # As a last resort, try importing - if it fails, we'll get a clear error
        pass


def parse_langs(raw: str) -> List[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
        except json.JSONDecodeError:
            pass
    # Support both ASCII comma and Chinese comma
    return [part.strip() for part in re.split(r'[，,]', raw) if part.strip()]


def normalize_language(lang: str) -> str:
    key = lang.strip().lower()
    # Use lowercase for Qwen3-TTS model
    mapping = {
        "zh": "chinese",
        "chinese": "chinese",
        "mandarin": "chinese",
        "en": "english",
        "english": "english",
        "ja": "japanese",
        "japanese": "japanese",
        "ko": "korean",
        "korean": "korean",
        "de": "german",
        "german": "german",
        "fr": "french",
        "french": "french",
        "ru": "russian",
        "russian": "russian",
        "pt": "portuguese",
        "portuguese": "portuguese",
        "es": "spanish",
        "spanish": "spanish",
        "it": "italian",
        "italian": "italian",
    }
    return mapping.get(key, lang)


# Languages supported by Qwen3-TTS model
TTS_SUPPORTED_LANGUAGES = {
    "auto", "chinese", "english", "french", "german",
    "italian", "japanese", "korean", "portuguese", "russian", "spanish",
}


def build_prompt(text: str, target_lang: str) -> str:
    return (
        "Translate the following Chinese text to "
        f"{target_lang}. Output only the translation.\n\n"
        f"Text: {text}"
    )


def call_ollama_generate(url: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url.rstrip("/") + "/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(body)
    if "response" in obj:
        return str(obj["response"]).strip()
    raise ValueError("Ollama response missing 'response' field")


def translate_one(
    text: str,
    target_lang: str,
    ollama_url: str,
    ollama_model: str,
    timeout: int,
) -> Tuple[Optional[str], Optional[str]]:
    try:
        prompt = build_prompt(text, target_lang)
        translation = call_ollama_generate(ollama_url, ollama_model, prompt, timeout)
        if not translation:
            return None, "empty translation"
        return translation, None
    except (HTTPError, URLError, json.JSONDecodeError, ValueError) as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def ensure_qwen_import(repo_path: str) -> None:
    try:
        import qwen_tts  # noqa: F401
    except Exception:
        if os.path.isdir(repo_path):
            sys.path.insert(0, repo_path)
        else:
            raise


def install_flash_attn() -> bool:
    """Auto-install flash-attn if not available. Returns True if installed successfully."""
    try:
        import flash_attn  # noqa: F401
        print("✓ flash-attn 已安装")
        return True  # Already installed
    except Exception:
        pass

    import torch
    if not torch.cuda.is_available():
        print("⚠ 无 CUDA 环境，跳过 flash-attn 安装")
        return False

    print("正在安装 flash-attn (可能需要几分钟)...")
    import subprocess
    import sys

    try:
        # Try installing flash-attn from pip
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "flash-attn", "--no-build-isolation",
                "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            print("✓ flash-attn 安装成功")
            return True
        else:
            # Check if it's a compilation error
            if "error" in result.stderr.lower() or "failed" in result.stderr.lower():
                print("⚠ flash-attn 编译失败，将使用 PyTorch 手动版本")
            else:
                print(f"⚠ flash-attn 安装失败: {result.stderr[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        print("⚠ flash-attn 安装超时，跳过")
        return False
    except Exception as e:
        print(f"⚠ 安装 flash-attn 时出错: {e}")
        return False


def load_qwen_model(model_path: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    def get_optimal_device_config() -> Dict[str, Any]:
        if torch.cuda.is_available():
            config = {
                "device_map": "cuda:0",
                "dtype": torch.bfloat16,
            }
            # Try to auto-install flash-attn if CUDA is available
            if install_flash_attn():
                try:
                    import flash_attn  # noqa: F401
                    config["attn_implementation"] = "flash_attention_2"
                except Exception:
                    pass
            return config
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return {"device_map": "mps", "dtype": torch.float32}
        return {"device_map": "cpu", "dtype": torch.float32}

    config = get_optimal_device_config()
    return Qwen3TTSModel.from_pretrained(model_path, **config)


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


def main() -> int:
    # Enforce correct environment before parsing args to fail fast
    require_conda_env("qwen3-tts")

    parser = argparse.ArgumentParser(description="Translate Chinese then run Qwen3-TTS")
    parser.add_argument("--text", help="Chinese input text (or use --text-file)")
    parser.add_argument("--text-file", help="Read text from a file (UTF-8 encoded)")
    parser.add_argument("--langs", required=True, help="Target languages, CSV or JSON array")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="translategemma")
    parser.add_argument("--ollama-timeout", type=int, default=60)
    parser.add_argument(
        "--model-path",
        default=r"D:\coding\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-CustomVoice",
    )
    parser.add_argument("--repo-path", default=r"D:\coding\Qwen3-TTS")
    parser.add_argument("--output-dir", default=r"D:\talking")
    parser.add_argument("--result-file", help="Output result JSON to file (recommended on Windows)")
    parser.add_argument("--speaker", default="Serena")
    parser.add_argument("--instruct", default="自然地说")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()

    # On Windows, default to writing result to file to avoid console encoding issues
    if sys.platform == "win32" and not args.result_file:
        args.result_file = os.path.join(args.output_dir, "result.json")

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

    target_langs = parse_langs(args.langs)
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

    os.makedirs(args.output_dir, exist_ok=True)

    max_workers = min(max(args.max_workers, 1), len(target_langs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for index, lang in enumerate(target_langs):
            futures[executor.submit(
                translate_one,
                input_text,
                lang,
                args.ollama_url,
                args.ollama_model,
                args.ollama_timeout,
            )] = (index, lang)

        for future in as_completed(futures):
            index, lang = futures[future]
            translation, err = future.result()
            if err:
                errors.append({"lang": lang, "stage": "translate", "message": err})
            else:
                translations[index] = translation

    valid_items = [
        (idx, lang, translations[idx])
        for idx, lang in enumerate(target_langs)
        if translations[idx]
    ]

    # Filter out languages not supported by TTS
    tts_supported_items = []
    for idx, lang, text in valid_items:
        normalized = normalize_language(lang)
        if normalized.lower() in TTS_SUPPORTED_LANGUAGES:
            tts_supported_items.append((idx, lang, text))
        else:
            errors.append({
                "lang": lang,
                "stage": "tts",
                "message": f"Language '{lang}' not supported by TTS. Supported: {', '.join(sorted(TTS_SUPPORTED_LANGUAGES))}"
            })

    if tts_supported_items:
        try:
            # Suppress flash-attn warning from qwen_tts module (printed with print())
            import contextlib
            import io

            # Capture stdout/stderr during import and model loading
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                warnings.filterwarnings("ignore", message=".*flash-attn.*")
                ensure_qwen_import(args.repo_path)
                model = load_qwen_model(args.model_path)

            texts = [item[2] for item in tts_supported_items]
            languages = [normalize_language(item[1]) for item in tts_supported_items]
            speakers = [args.speaker for _ in tts_supported_items]
            instructs = [args.instruct for _ in tts_supported_items]

            audio_segments, sample_rate = model.generate_custom_voice(
                text=texts,
                language=languages,
                speaker=speakers,
                instruct=instructs,
            )

            import soundfile as sf

            timestamp = build_timestamp()
            for i, (index, lang, _text) in enumerate(tts_supported_items):
                path = unique_path(args.output_dir, lang, timestamp)
                sf.write(path, audio_segments[i], sample_rate)
                audio_paths[index] = path
        except Exception as exc:  # noqa: BLE001
            for index, lang, _text in tts_supported_items:
                errors.append({"lang": lang, "stage": "tts", "message": str(exc)})

    output = {
        "translations": translations,
        "audio_paths": audio_paths,
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
