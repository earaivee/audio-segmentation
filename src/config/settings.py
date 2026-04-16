import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple
from typing import Optional, Any

@dataclass
class VADConfig:
    # VAD 参数配置
    # 语音检测敏感度
    threshold: float = 0.50
    # 最小静音间隔
    min_silence_duration_ms: int = 720
    # 最小语音片段时长
    min_speech_duration_ms: int = 600
    # speech_pad_ms
    speech_pad_ms: int = 200

    def to_dict(self):
        return {
            "threshold": self.threshold,
            "min_silence_duration_ms": self.min_silence_duration_ms,
            "min_speech_duration_ms": self.min_speech_duration_ms,
            "speech_pad_ms": self.speech_pad_ms,
        }

@dataclass
class NormalizeConfig:
    # 音量归一化配置
    enabled: bool = True
    # rms 基于平均响度调整 peak 基于最大峰值调整
    method: str = "rms"  # 'peak', 'rms'
    # Root Mean Square（均方根），代表音频的平均响度
    target_rms: float = 0.15
    # 目标峰值 音频的最大振幅上限
    target_peak: float = 0.95
    # 削波的检测阈值
    clipping_threshold : float = 0.99

    def __post_init__(self):
        assert self.method in ["peak", "rms"], f"Unknown method: {self.method}"
        assert 0 < self.target_rms < 1, "target_rms must be between 0 and 1"
        assert 0 < self.target_peak <= 1, "target_peak must be between 0 and 1"
        assert 0 < self.clipping_threshold  <= 1, "clipping_threshold must be between 0 and 1"

@dataclass
class FasterWhisperConfig:
    # Faster-Whisper 语音识别配置
    # 是否启用
    enabled: bool = True
    # 模型选择 (tiny, base, small, medium, large)
    model: str = "medium"
    # 设备 (cpu, cuda)
    device: str = "cpu"
    # 量化类型 (int8, float16, float32)
    compute_type: str = "int8"
    # CPU 线程数
    cpu_threads: int = os.cpu_count() // 2 or 4
    # 语言 (zh, en, None=自动检测)
    language: Optional[str] = "zh"
    # 识别任务 (transcribe, translate)
    task: str = "transcribe"
    # 初始提示（提高特定词准确率）
    initial_prompt: Optional[str] = None
    # 自动保存文本
    enables_auto_save: bool = True
    output_dir: Optional[Path] = Path("./resources/asr")

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "cpu_threads": self.cpu_threads,
            "language": self.language,
            "task": self.task,
            "initial_prompt": self.initial_prompt,
            "enables_auto_save": self.enables_auto_save,
            "output_dir": str(self.output_dir),
        }

@dataclass
class GptSovitsConfig:
    # GPT-SoVITS 训练列表配置
    enabled: bool = True
    # 说话人名称
    speaker: str = "default"
    # 语言 (zh, en, ja)
    language: str = "zh"
    # 输出文件路径
    output_path: Path = Path("./resources/output/output.list")

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "speaker": self.speaker,
            "language": self.language,
            "output_path": str(self.output_path),
        }

@dataclass
class SettingConfig:
    # 应用主配置
    input_dir: Path = Path("./resources/input")
    output_dir: Path = Path("./resources/output")
    supported_formats: Tuple[str, ...] = (".wav", ".mp3")
    vad: VADConfig = field(default_factory=VADConfig)
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    whisper: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)
    sovits: GptSovitsConfig = field(default_factory=GptSovitsConfig)

    def __post_init__(self):
        self.input_dir = Path(self.input_dir)
        self.output_dir = Path(self.output_dir)