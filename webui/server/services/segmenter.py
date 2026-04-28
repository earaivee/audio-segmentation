# webui/server/services/segmenter.py

from pathlib import Path
from typing import List, Tuple
import torch
from silero_vad import get_speech_timestamps

from ..config.settings import VADConfig
from ..utils.audio_utils import extract_segment, save_segment, split_segments
from ..utils.logger import setup_logger
from .normalizer import AudioNormalizer

logger = setup_logger(__name__)


class AudioSegmenter:
    # 音频 VAD 语音检测与切分类

    def __init__(self, vad_config: VADConfig, normalizer: AudioNormalizer):
        # 初始化切分器，配置 VAD 参数和归一化器
        self.vad_config = vad_config
        self.normalizer = normalizer

    def detect_speech_segments(self, audio: torch.Tensor, sr: int, model) -> List[dict]:
        # 使用 Silero VAD 检测音频中的语音片段，返回时间戳列表
        timestamps = get_speech_timestamps(
            audio,
            model,
            threshold=self.vad_config.threshold,
            sampling_rate=sr,
            min_speech_duration_ms=self.vad_config.min_speech_duration_ms,
            min_silence_duration_ms=self.vad_config.min_silence_duration_ms,
            speech_pad_ms=self.vad_config.speech_pad_ms,
            return_seconds=False
        )
        return timestamps

    def extract_and_process_segment(self, audio: torch.Tensor, start: int, end: int, sr: int) -> Tuple[torch.Tensor, dict]:
        # 提取并处理指定范围的音频片段（含归一化），返回片段和统计信息
        return extract_segment(audio, start, end, sr,
            normalizer=self.normalizer,
            clipping_threshold=self.normalizer.config.clipping_threshold
        )

    def apply_duration_limit(self, timestamps: List[dict], audio: torch.Tensor, sr: int, model,
                             min_second: int, max_second: int, enabled_double_split: bool, factor) -> List[dict]:
        # 对检测到的语音片段应用时长限制过滤
        if not timestamps:
            return []

        split_result = split_segments(timestamps, audio, sr, model, self.vad_config, max_second, enabled_double_split, factor)
        return split_result

    def save_segment(self, segment: torch.Tensor, output_path: Path, sr: int):
        # 保存音频片段到文件
        save_segment(segment, output_path, sr)