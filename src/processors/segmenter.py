# src/processors/segmenter.py

from pathlib import Path
from typing import List, Tuple
import torch
from silero_vad import get_speech_timestamps

from ..config.settings import VADConfig
from src.utils.audio_utils import extract_segment, save_segment, split_segments
from .normalizer import AudioNormalizer
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

class AudioSegmenter:
    # 音频切分器

    def __init__(self, vad_config: VADConfig, normalizer: AudioNormalizer):
        self.vad_config = vad_config
        self.normalizer = normalizer

    def detect_speech_segments(self, audio: torch.Tensor, sr: int, model) -> List[dict]:
        # 检测语音片段
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
        # 提取并处理单个片段
        return extract_segment(audio, start, end, sr,
            normalizer=self.normalizer,
            clipping_threshold=self.normalizer.config.clipping_threshold
        )

    def apply_duration_limit(self, timestamps: List[dict], audio: torch.Tensor, sr: int, model,
                             min_second: int, max_second: int, enabled_double_split: bool, factor) -> List[dict]:
        if not timestamps:
            return []

        # 1. 拆分过长的片段
        split_result = split_segments(timestamps, audio, sr, model, vad_config, max_second, enabled_double_split, factor)
        # 3. 返回
        return split_result

    def save_segment(self, segment: torch.Tensor, output_path: Path, sr: int):
        # 保存片段
        save_segment(segment, output_path, sr)