# webui/server/config/settings.py
"""应用配置 dataclass — 默认值从 models.py 的 Pydantic 模型继承，保证单一数据源。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Optional

from ..models import (
    VADConfigModel,
    NormalizeConfigModel,
    FasterWhisperConfigModel,
    TrainingExportConfigModel,
    SettingConfigModel,
)


@dataclass
class VADConfig:
    # Silero VAD 语音活动检测配置
    threshold: float = VADConfigModel.model_fields["threshold"].default
    min_silence_duration_ms: int = VADConfigModel.model_fields["min_silence_duration_ms"].default
    min_speech_duration_ms: int = VADConfigModel.model_fields["min_speech_duration_ms"].default
    speech_pad_ms: int = VADConfigModel.model_fields["speech_pad_ms"].default

    def to_dict(self):
        return {
            "threshold": self.threshold,
            "min_silence_duration_ms": self.min_silence_duration_ms,
            "min_speech_duration_ms": self.min_speech_duration_ms,
            "speech_pad_ms": self.speech_pad_ms,
        }


@dataclass
class NormalizeConfig:
    # 音频归一化配置
    enabled: bool = NormalizeConfigModel.model_fields["enabled"].default
    method: str = NormalizeConfigModel.model_fields["method"].default
    target_rms: float = NormalizeConfigModel.model_fields["target_rms"].default
    target_peak: float = NormalizeConfigModel.model_fields["target_peak"].default
    clipping_threshold: float = NormalizeConfigModel.model_fields["clipping_threshold"].default

    def __post_init__(self):
        assert self.method in ["peak", "rms"], f"Unknown method: {self.method}"
        assert 0 < self.target_rms < 1, "target_rms must be between 0 and 1"
        assert 0 < self.target_peak <= 1, "target_peak must be between 0 and 1"
        assert 0 < self.clipping_threshold <= 1, "clipping_threshold must be between 0 and 1"


@dataclass
class FasterWhisperConfig:
    # Faster-whisper ASR 配置
    enabled: bool = FasterWhisperConfigModel.model_fields["enabled"].default
    model_size: str = FasterWhisperConfigModel.model_fields["model_size"].default
    model_path: Optional[str] = FasterWhisperConfigModel.model_fields["model_path"].default
    device: str = FasterWhisperConfigModel.model_fields["device"].default
    compute_type: str = FasterWhisperConfigModel.model_fields["compute_type"].default
    language: str = FasterWhisperConfigModel.model_fields["language"].default
    beam_size: int = FasterWhisperConfigModel.model_fields["beam_size"].default

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "model_size": self.model_size,
            "model_path": self.model_path,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "beam_size": self.beam_size,
        }


@dataclass
class TrainingExportConfig:
    # 训练数据导出配置
    enabled: bool = TrainingExportConfigModel.model_fields["enabled"].default
    format_type: str = TrainingExportConfigModel.model_fields["format_type"].default
    speaker: str = TrainingExportConfigModel.model_fields["speaker"].default
    language: str = TrainingExportConfigModel.model_fields["language"].default
    output_path: Path = Path(TrainingExportConfigModel.model_fields["output_path"].default)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "format_type": self.format_type,
            "speaker": self.speaker,
            "language": self.language,
            "output_path": str(self.output_path),
        }


@dataclass
class SettingConfig:
    # 应用主配置类，聚合所有子配置
    input_dir: Path = Path(SettingConfigModel.model_fields["input_dir"].default)
    output_dir: Path = Path(SettingConfigModel.model_fields["output_dir"].default)
    supported_formats: Tuple[str, ...] = tuple(SettingConfigModel.model_fields["supported_formats"].default)
    vad: VADConfig = field(default_factory=VADConfig)
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    faster_whisper: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)
    sovits: TrainingExportConfig = field(default_factory=TrainingExportConfig)

    def __post_init__(self):
        self.input_dir = Path(self.input_dir)
        self.output_dir = Path(self.output_dir)
