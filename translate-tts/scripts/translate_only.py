import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"


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


LANGUAGE_ALIASES = {
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


def normalize_target_language(lang: str) -> str:
    key = lang.strip().lower()
    if key in REMOVED_SHORT_LANGUAGE_CODES:
        raise ValueError(f"不支持语言短码: {lang}。请使用自然语言写法（例如：英文、日文、韩文）。")
    return LANGUAGE_ALIASES.get(key, lang.strip())


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
        futures = {}
        for index, lang in enumerate(target_langs):
            futures[
                executor.submit(
                    translate_one,
                    text,
                    lang,
                    ollama_url,
                    ollama_model,
                    timeout,
                )
            ] = (index, lang)

        for future in as_completed(futures):
            index, lang = futures[future]
            translation, err = future.result()
            if err:
                errors.append({"lang": lang, "stage": "translate", "message": err})
            else:
                translations[index] = translation

    return translations, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="将中文翻译为目标语言（支持自然语言语言名，如：英文、日文、韩文）。")
    parser.add_argument("--text", help="Chinese input text (or use --text-file)")
    parser.add_argument("--text-file", help="Read text from a file (UTF-8 encoded)")
    parser.add_argument("--langs", required=True, help="目标语言，逗号分隔或 JSON 数组（例如：英文,日文,韩文）")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="translategemma")
    parser.add_argument("--ollama-timeout", type=int, default=60)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--result-file", help="Optional output result file (JSON)")
    args = parser.parse_args()

    if args.text_file:
        try:
            with open(args.text_file, "r", encoding="utf-8") as f:
                input_text = f.read().strip()
        except Exception as exc:  # noqa: BLE001
            output = {"translations": [], "errors": [{"lang": "", "stage": "input", "message": str(exc)}]}
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 1
    elif args.text:
        input_text = args.text
    else:
        output = {
            "translations": [],
            "errors": [{"lang": "", "stage": "input", "message": "Either --text or --text-file is required"}],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    try:
        target_langs = [normalize_target_language(lang) for lang in parse_langs(args.langs)]
    except ValueError as exc:
        output = {"translations": [], "errors": [{"lang": "", "stage": "input", "message": str(exc)}]}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1
    translations, errors = translate_batch(
        text=input_text,
        target_langs=target_langs,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        timeout=args.ollama_timeout,
        max_workers=args.max_workers,
    )
    output = {"translations": translations, "errors": errors}
    text_output = json.dumps(output, ensure_ascii=False, indent=2)

    if args.result_file:
        with open(args.result_file, "w", encoding="utf-8") as f:
            f.write(text_output)
    else:
        print(text_output)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
