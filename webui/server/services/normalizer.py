# webui/server/services/normalizer.py

import torch

from ..config.errors import CaseError
from ..config.settings import NormalizeConfig
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class AudioNormalizer:
    # 音频音量归一化处理类

    def __init__(self, config: NormalizeConfig):
        # 初始化归一化器，加载配置
        self.config = config

    def normalize_peak(self, audio: torch.Tensor) -> torch.Tensor:
        # 峰值归一化：将音频最大振幅调整到目标峰值
        max_val = torch.abs(audio).max()
        if max_val > 1e-6:
            audio = audio / max_val * self.config.target_peak
        return audio

    def normalize_rms(self, audio: torch.Tensor) -> torch.Tensor:
        # RMS 归一化：将音频均方根调整到目标 RMS 值
        rms = torch.sqrt(torch.mean(audio ** 2))
        if rms > 1e-6:
            audio = audio / rms * self.config.target_rms
        return audio

    def normalize(self, audio: torch.Tensor) -> torch.Tensor:
        # 根据配置的归一化方法对音频进行归一化
        if not self.config.enabled:
            return audio
        if self.config.method == "peak":
            return self.normalize_peak(audio)
        elif self.config.method == "rms":
            return self.normalize_rms(audio)
        else:
            raise CaseError()
