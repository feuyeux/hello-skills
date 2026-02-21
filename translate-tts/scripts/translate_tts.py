import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REMOTE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
DEFAULT_LOCAL_MODEL_PATHS = [
    os.path.join(SCRIPT_DIR, "Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    os.path.expanduser("~/zoo/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    os.path.expanduser("~/coding/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    r"D:\coding\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-CustomVoice",
]

# Fix encoding issues on Windows.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"


TRANSLATE_LANGUAGE_ALIASES = {
    "chinese": "Chinese",
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
    "french": "French",
    "法语": "French",
    "法文": "French",
    "german": "German",
    "德语": "German",
    "德文": "German",
    "russian": "Russian",
    "俄语": "Russian",
    "俄文": "Russian",
    "italian": "Italian",
    "意大利语": "Italian",
    "意大利文": "Italian",
    "spanish": "Spanish",
    "西班牙语": "Spanish",
    "西班牙文": "Spanish",
    "portuguese": "Portuguese",
    "葡萄牙语": "Portuguese",
    "葡萄牙文": "Portuguese",
    "葡语": "Portuguese",
    "葡文": "Portuguese",
    "arabic": "Arabic",
    "阿拉伯语": "Arabic",
    "hindi": "Hindi",
    "印地语": "Hindi",
    "thai": "Thai",
    "泰语": "Thai",
    "vietnamese": "Vietnamese",
    "越南语": "Vietnamese",
}

REMOVED_SHORT_LANGUAGE_CODES = {
    "zh",
    "en",
    "fr",
    "de",
    "ru",
    "it",
    "es",
    "pt",
    "ja",
    "ko",
    "ar",
    "hi",
    "th",
    "vi",
}

TTS_LANGUAGE_ALIASES = {
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

TTS_SUPPORTED_LANGUAGES = set(TTS_LANGUAGE_ALIASES.values())

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

LANGUAGE_TO_PREFERRED_SPEAKER = {
    "Chinese": "serena",
    "English": "aiden",
    "Japanese": "ono_anna",
    "Korean": "sohee",
    "French": "aiden",
    "German": "aiden",
    "Russian": "ryan",
    "Italian": "aiden",
    "Spanish": "aiden",
    "Portuguese": "aiden",
}


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
    return [part.strip() for part in re.split(r"[，,]", raw) if part.strip()]


def normalize_target_language(lang: str) -> str:
    key = lang.strip().lower()
    if key in REMOVED_SHORT_LANGUAGE_CODES:
        raise ValueError(f"不支持语言短码: {lang}。请使用自然语言写法（例如：英文、日文、韩文）。")
    return TRANSLATE_LANGUAGE_ALIASES.get(key, lang.strip())


def normalize_language_for_tts(lang: str) -> Optional[str]:
    return TTS_LANGUAGE_ALIASES.get(lang.strip().lower())


def to_friendly_label(raw_lang: str, normalized_lang: str) -> str:
    return FRIENDLY_LANGUAGE_LABELS.get(normalized_lang, raw_lang)


def build_prompt(text: str, target_lang: str) -> str:
    return (
        "Translate the following Chinese text to "
        f"{target_lang}. Output only the translation.\n\n"
        f"Text: {text}"
    )


def call_ollama_generate(url: str, model: str, prompt: str, timeout: int) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False}
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


def translate_batch(
    *,
    text: str,
    target_langs: List[str],
    ollama_url: str,
    ollama_model: str,
    timeout: int,
    max_workers: int,
) -> Tuple[List[Optional[str]], List[Dict[str, str]]]:
    translations: List[Optional[str]] = [None] * len(target_langs)
    errors: List[Dict[str, str]] = []

    if not target_langs:
        return translations, [{"lang": "", "stage": "input", "message": "no target languages"}]

    worker_count = min(max(max_workers, 1), len(target_langs))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                translate_one,
                text,
                lang,
                ollama_url,
                ollama_model,
                timeout,
            ): (index, lang)
            for index, lang in enumerate(target_langs)
        }

        for future in as_completed(futures):
            index, lang = futures[future]
            translation, err = future.result()
            if err:
                errors.append({"lang": lang, "stage": "translate", "message": err})
            else:
                translations[index] = translation

    return translations, errors


def translate_pairs(
    *,
    texts: List[str],
    target_langs: List[str],
    ollama_url: str,
    ollama_model: str,
    timeout: int,
    max_workers: int,
) -> Tuple[List[Optional[str]], List[Dict[str, str]]]:
    translations: List[Optional[str]] = [None] * len(texts)
    errors: List[Dict[str, str]] = []

    worker_count = min(max(max_workers, 1), len(texts))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                translate_one,
                text,
                lang,
                ollama_url,
                ollama_model,
                timeout,
            ): (index, lang)
            for index, (text, lang) in enumerate(zip(texts, target_langs))
        }

        for future in as_completed(futures):
            index, lang = futures[future]
            translation, err = future.result()
            if err:
                errors.append({"lang": lang, "stage": "translate", "message": err})
            else:
                translations[index] = translation

    return translations, errors


def require_conda_env(env_name: str = "qwen3-tts") -> None:
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "").strip()

    in_conda_env = (
        (conda_env and conda_env.lower() == env_name.lower())
        or (env_name.lower() in sys.prefix.lower())
        or ("conda" in sys.prefix.lower() and "envs" in sys.prefix.lower())
    )

    if in_conda_env:
        return

    try:
        import torch  # noqa: F401
        import soundfile  # noqa: F401
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


def resolve_model_path(cli_model_path: Optional[str]) -> str:
    candidates: List[str] = []
    if cli_model_path:
        candidates.append(os.path.expandvars(os.path.expanduser(cli_model_path)))

    env_repo_dir = os.getenv("QWEN3_TTS_REPO_DIR", "").strip()
    if env_repo_dir:
        candidates.append(
            os.path.join(
                os.path.expandvars(os.path.expanduser(env_repo_dir)),
                "Qwen3-TTS-12Hz-1.7B-CustomVoice",
            )
        )

    env_model_path = os.getenv("QWEN3_TTS_MODEL_PATH", "").strip()
    if env_model_path:
        candidates.append(os.path.expandvars(os.path.expanduser(env_model_path)))

    candidates.extend(DEFAULT_LOCAL_MODEL_PATHS)

    for path in candidates:
        if os.path.isdir(path):
            return path
    return DEFAULT_REMOTE_MODEL_ID


def get_device_config(torch_mod) -> dict:
    if torch_mod.cuda.is_available():
        config = {"device_map": "cuda:0", "dtype": torch_mod.bfloat16}
        try:
            import flash_attn  # noqa: F401
            config["attn_implementation"] = "flash_attention_2"
        except ImportError:
            pass
        return config

    if hasattr(torch_mod.backends, "mps") and torch_mod.backends.mps.is_available():
        return {"device_map": "mps", "dtype": torch_mod.float32}

    return {"device_map": "cpu", "dtype": torch_mod.float32}


def normalize_audio(np_mod, audio):
    if isinstance(audio, (list, tuple)):
        data = np_mod.asarray(audio[0])
    else:
        data = np_mod.asarray(audio)
        if data.ndim > 1:
            data = data[0]
    return data


def estimate_expected_duration_seconds(text: str, language: str) -> float:
    clean = text.strip()
    if not clean:
        return 1.0
    no_space_chars = len([ch for ch in clean if not ch.isspace()])
    if language in {"Chinese", "Japanese", "Korean"}:
        return max(0.8, no_space_chars / 4.0)
    words = clean.split()
    if len(words) >= 2:
        return max(0.8, len(words) / 2.5)
    return max(0.8, no_space_chars / 9.0)


def duration_upper_bound_seconds(text: str, language: str) -> float:
    expected = estimate_expected_duration_seconds(text, language)
    return max(3.5, expected * 2.2)


def build_recovery_generation_kwargs(text: str, language: str) -> dict:
    expected = estimate_expected_duration_seconds(text, language)
    max_new_tokens = int(expected * 14 * 1.4)
    max_new_tokens = max(24, min(220, max_new_tokens))
    if language in {"Japanese", "Russian"}:
        max_new_tokens = min(max_new_tokens, 120)
    return {
        "do_sample": False,
        "subtalker_dosample": False,
        "repetition_penalty": 1.0,
        "max_new_tokens": max_new_tokens,
    }


def generate_once(
    model,
    *,
    text: str,
    language: str,
    speaker: str,
    instruct: Optional[str],
    generation_kwargs: Optional[dict] = None,
):
    kwargs = {"text": text, "language": language, "speaker": speaker}
    if instruct is not None:
        kwargs["instruct"] = instruct
    if generation_kwargs:
        kwargs.update(generation_kwargs)
    return model.generate_custom_voice(**kwargs)


def choose_preferred_speaker(language: str, speaker_override: Optional[str]) -> str:
    if speaker_override:
        return speaker_override.strip().lower()
    return LANGUAGE_TO_PREFERRED_SPEAKER.get(language, "aiden")


def resolve_speaker(preferred: str, supported_speakers: List[str]) -> str:
    if not supported_speakers:
        return preferred

    supported_set = {s.lower() for s in supported_speakers}
    preferred_lower = preferred.lower()
    if preferred_lower in supported_set:
        return preferred_lower

    return "serena" if "serena" in supported_set else sorted(supported_set)[0]


def synthesize_with_retries(
    np_mod,
    model,
    *,
    sentence: str,
    language: str,
    speaker: str,
    instruct: Optional[str],
):
    audio, sample_rate = generate_once(
        model,
        text=sentence,
        language=language,
        speaker=speaker,
        instruct=instruct,
    )
    best_audio = normalize_audio(np_mod, audio)
    best_sample_rate = sample_rate
    best_duration = len(best_audio) / best_sample_rate
    upper_bound = duration_upper_bound_seconds(sentence, language)

    if best_duration > upper_bound:
        retry_audio, retry_sample_rate = generate_once(
            model,
            text=sentence,
            language=language,
            speaker=speaker,
            instruct=instruct,
        )
        retry_data = normalize_audio(np_mod, retry_audio)
        retry_duration = len(retry_data) / retry_sample_rate
        if retry_duration < best_duration:
            best_audio = retry_data
            best_sample_rate = retry_sample_rate
            best_duration = retry_duration

        if best_duration > upper_bound:
            recovery_kwargs = build_recovery_generation_kwargs(sentence, language)
            recovery_audio, recovery_sample_rate = generate_once(
                model,
                text=sentence,
                language=language,
                speaker=speaker,
                instruct=instruct,
                generation_kwargs=recovery_kwargs,
            )
            recovery_data = normalize_audio(np_mod, recovery_audio)
            recovery_duration = len(recovery_data) / recovery_sample_rate
            if recovery_duration < best_duration:
                best_audio = recovery_data
                best_sample_rate = recovery_sample_rate
                best_duration = recovery_duration

    return best_audio, best_sample_rate, best_duration


def build_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def build_audio_path(base_dir: str, lang: str, sequence: int) -> str:
    safe_lang = "".join(ch for ch in lang if ch.isalnum() or ch in ("-", "_"))
    if not safe_lang:
        safe_lang = "lang"
    filename = f"{sequence:02d}_{safe_lang}.wav"
    return os.path.join(base_dir, filename)


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


def parse_language_sentence_pairs(text: str) -> Optional[List[Tuple[str, str]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    pairs: List[Tuple[str, str]] = []
    for line in lines:
        match = re.match(r"^([^:：]+)\s*[:：]\s*(.+)$", line)
        if not match:
            return None
        lang = match.group(1).strip()
        sentence = match.group(2).strip()
        if not lang or not sentence:
            return None
        pairs.append((lang, sentence))

    return pairs if pairs else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="先翻译中文，再生成多语种语音（支持自然语言语言名）。")
    parser.add_argument("--text", help="Chinese input text (or use --text-file)")
    parser.add_argument("--text-file", help="Read text from a file (UTF-8 encoded)")
    parser.add_argument("--langs", help="目标语言，逗号分隔或 JSON 数组（例如：英文,日文,韩文）")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="translategemma")
    parser.add_argument("--ollama-timeout", type=int, default=60)
    parser.add_argument("--model-path", default=None, help="Optional local Qwen3-TTS model directory")
    parser.add_argument("--output-root", default=None, help="Base directory for task outputs")
    parser.add_argument("--output-dir", default=None, help="Optional: explicit task output directory")
    parser.add_argument("--result-file", help="Output result JSON to file (recommended on Windows)")
    parser.add_argument("--speaker", default=None, help="Optional: specify speaker (e.g. serena/aiden/ono_anna)")
    parser.add_argument("--instruct", default=None, help="Optional: style instruction for TTS generation")
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_conda_env("qwen3-tts")

    output_root = os.path.expanduser(args.output_root) if args.output_root else default_output_root()
    task_output_dir = args.output_dir or os.path.join(output_root, build_timestamp())
    os.makedirs(task_output_dir, exist_ok=True)

    if not args.result_file:
        args.result_file = os.path.join(task_output_dir, "result.json")

    errors: List[Dict[str, str]] = []

    if args.text_file:
        try:
            with open(args.text_file, "r", encoding="utf-8") as f:
                input_text = f.read().strip()
        except Exception as exc:  # noqa: BLE001
            errors.append({"lang": "", "stage": "input", "message": f"Failed to read text file: {exc}"})
            output = {"translations": [], "audio_paths": [], "errors": errors}
            print(json.dumps(output, ensure_ascii=False))
            return 1
    elif args.text:
        input_text = args.text
    else:
        errors.append({"lang": "", "stage": "input", "message": "Either --text or --text-file is required"})
        output = {"translations": [], "audio_paths": [], "errors": errors}
        print(json.dumps(output, ensure_ascii=False))
        return 1

    language_sentence_pairs = parse_language_sentence_pairs(input_text)
    if language_sentence_pairs:
        raw_target_langs = [lang for lang, _ in language_sentence_pairs]
        sentences = [sentence for _, sentence in language_sentence_pairs]
    else:
        if not args.langs:
            errors.append({"lang": "", "stage": "input", "message": "--langs is required when not using language:sentence lines"})
            output = {"translations": [], "audio_paths": [], "errors": errors}
            print(json.dumps(output, ensure_ascii=False))
            return 1
        raw_target_langs = parse_langs(args.langs)
        sentences = [input_text] * len(raw_target_langs)

    try:
        target_langs = [normalize_target_language(lang) for lang in raw_target_langs]
    except ValueError as exc:
        errors.append({"lang": "", "stage": "input", "message": str(exc)})
        output = {"translations": [], "audio_paths": [], "errors": errors}
        print(json.dumps(output, ensure_ascii=False))
        return 1

    target_lang_labels = [
        to_friendly_label(raw_lang, normalized_lang)
        for raw_lang, normalized_lang in zip(raw_target_langs, target_langs)
    ]

    if language_sentence_pairs:
        translations, translation_errors = translate_pairs(
            texts=sentences,
            target_langs=target_langs,
            ollama_url=args.ollama_url,
            ollama_model=args.ollama_model,
            timeout=args.ollama_timeout,
            max_workers=args.max_workers,
        )
    else:
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

    audio_paths: List[Optional[str]] = [None] * len(target_langs)
    tts_items = []
    for idx, (label, normalized, text) in enumerate(zip(target_lang_labels, target_langs, translations)):
        if not text:
            continue
        tts_lang = normalize_language_for_tts(normalized)
        if tts_lang and tts_lang in TTS_SUPPORTED_LANGUAGES:
            tts_items.append((idx, label, tts_lang, text))
        else:
            errors.append(
                {
                    "lang": label,
                    "stage": "tts",
                    "message": (
                        f"Language '{label}' not supported by TTS. "
                        "Supported: 中文, 英文/英语, 法语, 德语, 俄语, 意大利语, 西班牙语, 葡萄牙语, 日语/日文, 韩语/韩文"
                    ),
                }
            )

    if tts_items:
        model_path = resolve_model_path(args.model_path)
        try:
            import numpy as np
            import soundfile as sf
            import torch
            from qwen_tts import Qwen3TTSModel

            model = Qwen3TTSModel.from_pretrained(model_path, **get_device_config(torch))
            supported_speakers = model.get_supported_speakers() or []

            sequence = 1
            for index, lang_label, tts_lang, translated_text in tts_items:
                output_path = build_audio_path(task_output_dir, lang_label, sequence)
                sequence += 1
                try:
                    preferred_speaker = choose_preferred_speaker(tts_lang, args.speaker)
                    speaker = resolve_speaker(preferred_speaker, supported_speakers)
                    best_audio, best_sample_rate, _ = synthesize_with_retries(
                        np,
                        model,
                        sentence=translated_text,
                        language=tts_lang,
                        speaker=speaker,
                        instruct=args.instruct,
                    )
                    sf.write(output_path, best_audio, best_sample_rate)
                    audio_paths[index] = output_path
                except Exception as exc:  # noqa: BLE001
                    errors.append({"lang": lang_label, "stage": "tts", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            for _, lang_label, _, _ in tts_items:
                errors.append({
                    "lang": lang_label,
                    "stage": "tts",
                    "message": f"Failed to initialize TTS model '{model_path}': {exc}",
                })

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
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: Failed to write result file: {exc}", file=sys.stderr)
            print(json_output)
    else:
        print(json_output)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
