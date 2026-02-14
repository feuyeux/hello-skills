import argparse
import os

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REMOTE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
HOME = os.path.expanduser("~")
DEFAULT_LOCAL_MODEL_PATHS = [
    os.path.join(SCRIPT_DIR, "Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    os.path.join(HOME, "zoo", "Qwen3-TTS", "Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    os.path.join(HOME, "coding", "Qwen3-TTS", "Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    r"D:\coding\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-CustomVoice",
]
SUPPORTED_LANGUAGES = [
    "Chinese",
    "English",
    "French",
    "German",
    "Russian",
    "Italian",
    "Spanish",
    "Portuguese",
    "Japanese",
    "Korean",
]

# Based on model README: use native-language speakers for best quality.
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

LANGUAGE_INPUT_ALIASES = {
    "chinese": "Chinese",
    "中文": "Chinese",
    "汉语": "Chinese",
    "国语": "Chinese",
    "english": "English",
    "英语": "English",
    "英文": "English",
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
    "japanese": "Japanese",
    "日语": "Japanese",
    "日文": "Japanese",
    "korean": "Korean",
    "韩语": "Korean",
    "韩文": "Korean",
}


def resolve_model_path(cli_model_path: str | None) -> str:
    candidates = []
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


def get_device_config() -> dict:
    if torch.cuda.is_available():
        print("检测到 CUDA GPU，使用 GPU 加速")
        config = {"device_map": "cuda:0", "dtype": torch.bfloat16}
        try:
            import flash_attn  # noqa: F401

            config["attn_implementation"] = "flash_attention_2"
            print("使用 Flash Attention 2 加速")
        except ImportError:
            print("Flash Attention 未安装，使用标准注意力机制")
        return config

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        print("检测到 Apple Silicon GPU，使用 MPS 加速")
        return {"device_map": "mps", "dtype": torch.float32}

    print("使用 CPU 运行")
    return {"device_map": "cpu", "dtype": torch.float32}


def normalize_audio(audio) -> np.ndarray:
    if isinstance(audio, (list, tuple)):
        data = np.asarray(audio[0])
    else:
        data = np.asarray(audio)
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
    model: Qwen3TTSModel,
    *,
    text: str,
    language: str,
    speaker: str,
    instruct: str | None,
    generation_kwargs: dict | None = None,
):
    kwargs = {"text": text, "language": language, "speaker": speaker}
    if instruct is not None:
        kwargs["instruct"] = instruct
    if generation_kwargs:
        kwargs.update(generation_kwargs)
    return model.generate_custom_voice(**kwargs)


def resolve_speaker(model: Qwen3TTSModel, preferred: str) -> str:
    supported = model.get_supported_speakers() or []
    if not supported:
        return preferred

    supported_set = {s.lower() for s in supported}
    preferred_lower = preferred.lower()
    if preferred_lower in supported_set:
        return preferred_lower

    fallback = "serena" if "serena" in supported_set else sorted(supported_set)[0]
    print(f"提示: 当前模型不支持 speaker='{preferred}'，自动回退为 '{fallback}'。")
    return fallback


def choose_preferred_speaker(language: str, speaker_override: str | None) -> str:
    if speaker_override:
        return speaker_override.strip().lower()
    return LANGUAGE_TO_PREFERRED_SPEAKER.get(language, "aiden")


def normalize_language_input(raw_language: str) -> str:
    key = raw_language.strip().lower()
    normalized = LANGUAGE_INPUT_ALIASES.get(key)
    if normalized:
        return normalized
    if raw_language in SUPPORTED_LANGUAGES:
        return raw_language
    supported = "、".join(["中文", "英文", "法语", "德语", "俄语", "意大利语", "西班牙语", "葡萄牙语", "日语", "韩语"])
    raise ValueError(f"不支持的语言: {raw_language}。支持: {supported}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单句 TTS 生成脚本（按语种自动选 speaker，中性语速语气）")
    parser.add_argument("sentence", help="要合成的句子")
    parser.add_argument("language", help="语种（如：英文/英语、日文/日语、韩文/韩语）")
    parser.add_argument("--output", default="output.wav", help="输出音频文件路径，默认 output.wav")
    parser.add_argument("--model-path", default=None, help="可选：显式指定本地模型目录")
    parser.add_argument("--speaker", default=None, help="可选：手动指定 speaker（如 serena/aiden/ono_anna/sohee）")
    parser.add_argument("--instruct", default=None, help="可选：风格指令；不传时使用最小中性设定")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    language = normalize_language_input(args.language)
    model_path = resolve_model_path(args.model_path)
    print(f"正在加载模型: {model_path}")
    model = Qwen3TTSModel.from_pretrained(model_path, **get_device_config())

    preferred = choose_preferred_speaker(language, args.speaker)
    speaker = resolve_speaker(model, preferred)
    print(f"使用 speaker: {speaker}")
    instruct = args.instruct if args.instruct is not None else None

    audio, sample_rate = generate_once(
        model,
        text=args.sentence,
        language=language,
        speaker=speaker,
        instruct=instruct,
    )
    best_audio = normalize_audio(audio)
    best_sample_rate = sample_rate
    best_duration = len(best_audio) / best_sample_rate
    upper_bound = duration_upper_bound_seconds(args.sentence, language)

    if best_duration > upper_bound:
        print(f"提示: 首次生成时长 {best_duration:.2f}s 超出预期阈值 {upper_bound:.2f}s，执行重试。")
        retry_audio, retry_sample_rate = generate_once(
            model,
            text=args.sentence,
            language=language,
            speaker=speaker,
            instruct=instruct,
        )
        retry_data = normalize_audio(retry_audio)
        retry_duration = len(retry_data) / retry_sample_rate
        if retry_duration < best_duration:
            best_audio = retry_data
            best_sample_rate = retry_sample_rate
            best_duration = retry_duration

        if best_duration > upper_bound:
            recovery_kwargs = build_recovery_generation_kwargs(args.sentence, language)
            print(f"提示: 进入受限兜底参数: {recovery_kwargs}")
            recovery_audio, recovery_sample_rate = generate_once(
                model,
                text=args.sentence,
                language=language,
                speaker=speaker,
                instruct=instruct,
                generation_kwargs=recovery_kwargs,
            )
            recovery_data = normalize_audio(recovery_audio)
            recovery_duration = len(recovery_data) / recovery_sample_rate
            if recovery_duration < best_duration:
                best_audio = recovery_data
                best_sample_rate = recovery_sample_rate
                best_duration = recovery_duration

    sf.write(args.output, best_audio, best_sample_rate)
    print(f"已生成: {args.output} (时长: {best_duration:.2f}s)")


if __name__ == "__main__":
    main()
