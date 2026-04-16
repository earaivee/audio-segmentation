import torch
import torchaudio
from pathlib import Path
from typing import Dict, Any
from typing import List, Tuple
from silero_vad import get_speech_timestamps
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

def get_audio_duration(audio: torch.Tensor, sr: int) -> float:
    # 获取音频时长（秒） =  采样点数 / 采样率
    return len(audio) / sr

def analyze_audio(audio: torch.Tensor, sr: int,
                  clipping_threshold: float) -> Dict[str, Any]:
    # 分析音频特征  Returns: 包含峰值、RMS、时长的字典
    max_val = torch.abs(audio).max().item()
    rms = torch.sqrt(torch.mean(audio ** 2)).item()
    duration = get_audio_duration(audio, sr)
    return {
        "peak": max_val,
        "rms": rms,
        "duration": duration,
        "is_clipping": max_val > clipping_threshold
    }

def ensure_channels(audio: torch.Tensor) -> torch.Tensor:
    # 确保音频格式为 [channels, samples]
    if audio.dim() == 1:
        return audio.unsqueeze(0)  # [1, samples]
    return audio


def extract_segment( audio: torch.Tensor, start: int, end: int, sr: int,
                     normalizer=None, clipping_threshold: float = 0.99 ) -> Tuple[torch.Tensor, dict]:
    # 提取并处理单个片段
    segment = audio[start:end]
    original_stats = analyze_audio(segment, sr, clipping_threshold)
    # 音量归一化
    if normalizer:
        segment = normalizer.normalize(segment)
    normalized_stats = analyze_audio(segment, sr, clipping_threshold)

    return segment, {
        "duration_sec": (end - start) / sr,
        "original_rms": original_stats["rms"],
        "normalized_rms": normalized_stats["rms"]
    }

def save_segment(segment: torch.Tensor, output_path: Path, sr: int):
    # 保存音频片段
    segment = ensure_channels(segment)
    torchaudio.save(str(output_path), segment.cpu(), sr)

def split_segments(timestamps: List[Dict], audio: torch.Tensor, sr: int, vad_model,vad_config: dict,
                        max_duration: float , enabled_double_split: bool , factor: float ) -> List[Dict]:
    # 拆分过长的片段
    result = []

    for ts in timestamps:
        start = ts['start']
        end = ts['end']
        duration = (end - start) / sr

        logger.debug(f"片段: {start / sr:.2f}s - {end / sr:.2f}s (时长: {(end - start) / sr:.2f}s)")
        result.append(ts)

    return result

