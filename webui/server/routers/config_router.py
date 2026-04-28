# webui/server/routers/config_router.py
"""配置管理 API"""

from fastapi import APIRouter
from ..config.settings import (
    SettingConfig, VADConfig, NormalizeConfig,
    TrainingExportConfig, FasterWhisperConfig
)
from ..models import (
    SettingConfigModel, VADConfigModel, NormalizeConfigModel,
    TrainingExportConfigModel, FasterWhisperConfigModel
)
from pathlib import Path

from ..services.audio_service import list_directory

router = APIRouter()

_config = SettingConfig()


def get_config() -> SettingConfig:
    # 获取全局配置单例
    return _config


def _config_to_model(config: SettingConfig) -> SettingConfigModel:
    # 将 SettingConfig 转换为 Pydantic 模型
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
        faster_whisper=FasterWhisperConfigModel(
            enabled=config.faster_whisper.enabled,
            model_size=config.faster_whisper.model_size,
            model_path=config.faster_whisper.model_path or "",
            device=config.faster_whisper.device,
            compute_type=config.faster_whisper.compute_type,
            language=config.faster_whisper.language,
            beam_size=config.faster_whisper.beam_size,
        ),
        sovits=TrainingExportConfigModel(
            enabled=config.sovits.enabled,
            format_type=config.sovits.format_type,
            speaker=config.sovits.speaker,
            language=config.sovits.language,
            output_path=str(config.sovits.output_path),
        ),
    )


def _apply_model_to_config(model: SettingConfigModel, config: SettingConfig):
    # 将 Pydantic 模型的值应用到 SettingConfig
    config.input_dir = Path(model.input_dir)
    config.output_dir = Path(model.output_dir)
    config.supported_formats = tuple(model.supported_formats)

    config.vad.threshold = model.vad.threshold
    config.vad.min_silence_duration_ms = model.vad.min_silence_duration_ms
    config.vad.min_speech_duration_ms = model.vad.min_speech_duration_ms
    config.vad.speech_pad_ms = model.vad.speech_pad_ms

    config.normalize.enabled = model.normalize.enabled
    config.normalize.method = model.normalize.method
    config.normalize.target_rms = model.normalize.target_rms
    config.normalize.target_peak = model.normalize.target_peak
    config.normalize.clipping_threshold = model.normalize.clipping_threshold

    config.faster_whisper.enabled = model.faster_whisper.enabled
    config.faster_whisper.model_size = model.faster_whisper.model_size
    config.faster_whisper.model_path = model.faster_whisper.model_path
    config.faster_whisper.device = model.faster_whisper.device
    config.faster_whisper.compute_type = model.faster_whisper.compute_type
    config.faster_whisper.language = model.faster_whisper.language
    config.faster_whisper.beam_size = model.faster_whisper.beam_size

    config.sovits.enabled = model.sovits.enabled
    config.sovits.format_type = model.sovits.format_type
    config.sovits.speaker = model.sovits.speaker
    config.sovits.language = model.sovits.language
    config.sovits.output_path = Path(model.sovits.output_path)


@router.get("", response_model=SettingConfigModel)
async def get_all_config():
    # 获取全部配置
    return _config_to_model(_config)


@router.put("")
async def update_all_config(model: SettingConfigModel):
    # 更新全部配置
    _apply_model_to_config(model, _config)
    return {"message": "配置已更新", "config": _config_to_model(_config)}


@router.patch("/{section}")
async def update_section_config(section: str, data: dict):
    # 更新指定配置段（vad/normalize/whisper/sovits）
    if section == "vad":
        for k, v in data.items():
            if hasattr(_config.vad, k):
                setattr(_config.vad, k, v)
    elif section == "normalize":
        for k, v in data.items():
            if hasattr(_config.normalize, k):
                setattr(_config.normalize, k, v)
    elif section == "faster_whisper":
        for k, v in data.items():
            if hasattr(_config.faster_whisper, k):
                setattr(_config.faster_whisper, k, v)
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
    # 浏览文件系统目录（用于界面选择路径）
    return list_directory(path)
