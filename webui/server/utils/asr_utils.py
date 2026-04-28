# webui/server/asr_utils.py

from pathlib import Path

from ..config.settings import FasterWhisperConfig
from ..config.errors import AsrError
from .logger import setup_logger
from .progress_utils import progressBar

logger = setup_logger(__name__)

_fw_model = None  # faster-whisper 模型缓存


def load_faster_whisper_model(config: FasterWhisperConfig):
    # 加载 faster-whisper 模型，支持本地路径或模型名
    global _fw_model

    if not config.enabled:
        return None

    if _fw_model is not None:
        return _fw_model

    try:
        from faster_whisper import WhisperModel

        model_source = config.model_path if (
            config.model_path and Path(config.model_path).exists()
        ) else config.model_size

        _fw_model = WhisperModel(
            model_source,
            device=config.device,
            compute_type=config.compute_type,
            download_root="./models",
        )
        logger.info(
            f"Faster-whisper 模型加载成功 (source={model_source}, device={config.device})"
        )
        return _fw_model
    except Exception as e:
        raise AsrError(f"Faster-whisper 模型加载失败: {e}")


def transcribe_audio(model, config: FasterWhisperConfig, audio_path: Path):
    # 对单个音频文件执行 faster-whisper 识别
    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=config.language,
            beam_size=config.beam_size,
        )
        text = " ".join(seg.text for seg in segments).strip()
        # 繁体转简体
        if config.language == "zh":
            import opencc
            converter = opencc.OpenCC("t2s")
            text = converter.convert(text)
        logger.info(
            f"Faster-whisper 识别完成, language={info.language}, "
            f"confidence={info.language_probability:.2f}"
        )
        return text
    except Exception as e:
        raise AsrError(f"Faster-whisper 识别失败: {e}")


def batch_transcribe(model, config: FasterWhisperConfig, audio_paths: list):
    # 批量对多个音频文件执行语音识别，返回文件名到文本的映射
    results = {}

    with progressBar(len(audio_paths)) as progress:
        for index, audio_path in enumerate(audio_paths):
            text = transcribe_audio(model, config, audio_path)
            progress()
            progress.text(f" #{index + 1} ")
            print(f"文本识别： {text}")
            results[audio_path.stem] = text
    return results
