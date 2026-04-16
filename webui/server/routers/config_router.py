# webui/server/routers/config_router.py
"""配置管理 API"""

from fastapi import APIRouter
from src.config.settings import (
    SettingConfig, VADConfig, NormalizeConfig,
    FasterWhisperConfig, GptSovitsConfig
)
from webui.server.models import (
    SettingConfigModel, VADConfigModel, NormalizeConfigModel,
    FasterWhisperConfigModel, GptSovitsConfigModel
)
from pathlib import Path

from webui.server.services.audio_service import list_directory

router = APIRouter()

# 全局配置单例
_config = SettingConfig()


def get_config() -> SettingConfig:
    return _config


def _config_to_model(config: SettingConfig) -> SettingConfigModel:
    # 将 dataclass 配置转为 Pydantic 模型
    return SettingConfigModel(
        input_dir=str(config.input_dir),
        output_dir=str(config.output_dir),
        supported_formats=list(config.supported_formats),
        vad=VADConfigModel(**config.vad.to_dict()),
        normalize=NormalizeConfigModel(
            enabled=config.normalize.enabled,
            method=config.normalize.method,
            target_rms=config.normalize.target_rms,
            target_peak=config.normalize.target_peak,
            clipping_threshold=config.normalize.clipping_threshold,
        ),
        whisper=FasterWhisperConfigModel(**config.whisper.to_dict()),
        sovits=GptSovitsConfigModel(
            enabled=config.sovits.enabled,
            speaker=config.sovits.speaker,
            language=config.sovits.language,
            output_path=str(config.sovits.output_path),
        ),
    )


def _apply_model_to_config(model: SettingConfigModel, config: SettingConfig):
    # 将 Pydantic 模型写回 dataclass 配置
    config.input_dir = Path(model.input_dir)
    config.output_dir = Path(model.output_dir)
    config.supported_formats = tuple(model.supported_formats)

    # VAD
    config.vad.threshold = model.vad.threshold
    config.vad.min_silence_duration_ms = model.vad.min_silence_duration_ms
    config.vad.min_speech_duration_ms = model.vad.min_speech_duration_ms
    config.vad.speech_pad_ms = model.vad.speech_pad_ms

    # Normalize
    config.normalize.enabled = model.normalize.enabled
    config.normalize.method = model.normalize.method
    config.normalize.target_rms = model.normalize.target_rms
    config.normalize.target_peak = model.normalize.target_peak
    config.normalize.clipping_threshold = model.normalize.clipping_threshold

    # Whisper
    config.whisper.enabled = model.whisper.enabled
    config.whisper.model = model.whisper.model
    config.whisper.device = model.whisper.device
    config.whisper.compute_type = model.whisper.compute_type
    config.whisper.cpu_threads = model.whisper.cpu_threads
    config.whisper.language = model.whisper.language
    config.whisper.task = model.whisper.task
    config.whisper.initial_prompt = model.whisper.initial_prompt

    # SoVITS
    config.sovits.enabled = model.sovits.enabled
    config.sovits.speaker = model.sovits.speaker
    config.sovits.language = model.sovits.language
    config.sovits.output_path = Path(model.sovits.output_path)


@router.get("", response_model=SettingConfigModel)
async def get_all_config():
    # 获取当前所有配置
    return _config_to_model(_config)


@router.put("")
async def update_all_config(model: SettingConfigModel):
    # 更新所有配置
    _apply_model_to_config(model, _config)
    return {"message": "配置已更新", "config": _config_to_model(_config)}


@router.patch("/{section}")
async def update_section_config(section: str, data: dict):
    # 更新单个配置段
    if section == "vad":
        for k, v in data.items():
            if hasattr(_config.vad, k):
                setattr(_config.vad, k, v)
    elif section == "normalize":
        for k, v in data.items():
            if hasattr(_config.normalize, k):
                setattr(_config.normalize, k, v)
    elif section == "whisper":
        for k, v in data.items():
            if hasattr(_config.whisper, k):
                setattr(_config.whisper, k, v)
    elif section == "sovits":
        for k, v in data.items():
            if k == "output_path":
                v = Path(v)
            if hasattr(_config.sovits, k):
                setattr(_config.sovits, k, v)
    else:
        return {"error": f"未知的配置段: {section}"}

    return {"message": f"{section} 配置已更新", "config": _config_to_model(_config)}


@router.get("/browse-dirs")
async def browse_dirs(path: str = ""):
    # 浏览文件系统目录
    return list_directory(path)
