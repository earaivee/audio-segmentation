# 基于 Silero VAD 的批量音频按句子智能切分工具

import logging
import sys
from pathlib import Path
from typing import List, Optional

from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
import torchaudio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到控制台
        logging.FileHandler('segment.log', encoding='utf-8')  # 同时写入文件
    ]
)
logger = logging.getLogger(__name__)

INPUT_DIR = "./input"
OUTPUT_DIR = "./output"
SUPPORTED_FORMATS = (".wav", ".mp3")

# VAD 参数
VAD_CONFIG = {
    "threshold": 0.5,  # 语音阈值（0-1），环境噪音大时调高
    "min_silence_duration_ms": 500,  # 最小静音时长（毫秒），决定切分点
    "min_speech_duration_ms": 500,  # 最小语音片段时长（毫秒）
    "speech_pad_ms": 100,  # 片段前后保留时长（毫秒）
}

class AudioProcessingError(Exception):
    pass


def process_single_audio(audio_path: Path, model, output_folder: Path) -> int:
    try:
        # 读取音频
        audio = read_audio(str(audio_path))
        sr = 16000
        logger.debug(f"  音频时长: {len(audio) / sr:.2f}秒, 采样率: {sr}Hz")
    except Exception as e:
        raise AudioProcessingError(f"读取音频失败 {audio_path.name}: {e}") from e

    # 检测语音片段
    try:
        timestamps = get_speech_timestamps(
            audio,
            model,
            threshold=VAD_CONFIG["threshold"],
            sampling_rate=sr,
            min_speech_duration_ms=VAD_CONFIG["min_speech_duration_ms"],
            min_silence_duration_ms=VAD_CONFIG["min_silence_duration_ms"],
            speech_pad_ms=VAD_CONFIG["speech_pad_ms"],
            return_seconds=False
        )
    except Exception as e:
        raise AudioProcessingError(f"语音检测失败 {audio_path.name}: {e}") from e

    # 创建该音频的输出子目录
    audio_name = audio_path.stem
    audio_output_dir = output_folder / audio_name
    audio_output_dir.mkdir(parents=True, exist_ok=True)

    # 保存每个片段
    for i, seg in enumerate(timestamps):
        start = seg['start']
        end = seg['end']
        segment = audio[start:end]

        duration = (end - start) / sr
        output_path = audio_output_dir / f"{audio_name}_seg_{i:04d}.wav"

        # 添加 batch 维度（torchaudio.save 需要 [channels, samples]）
        if segment.dim() == 1:
            segment = segment.unsqueeze(0)

        try:
            torchaudio.save(str(output_path), segment.cpu(), sr)
            logger.debug(f"    保存: {output_path.name} ({duration:.2f}秒)")
        except Exception as e:
            raise AudioProcessingError(f"语音保存失败 {audio_path.name}: {e}") from e
    return 0


def get_audio_files(input_path: Path) -> List[Path]:
    audio_files = []
    for ext in SUPPORTED_FORMATS:
        audio_files.extend(input_path.glob(f"*{ext}"))
        audio_files.extend(input_path.glob(f"*{ext.upper()}"))
    # 去重并排序
    return sorted(set(audio_files))


def main():
    input_path = Path(INPUT_DIR)
    output_path = Path(OUTPUT_DIR)
    # 检查输入文件夹
    if not input_path.exists():
        logger.error(f"输入文件夹不存在: {INPUT_DIR}")
        sys.exit(1)

    if not input_path.is_dir():
        logger.error(f"输入路径不是文件夹: {INPUT_DIR}")
        sys.exit(1)

    # 获取音频文件列表
    audio_files = get_audio_files(input_path)

    if not audio_files:
        logger.warning(f"在 {INPUT_DIR} 中没有找到支持的音频文件")
        logger.info(f"支持的格式: {SUPPORTED_FORMATS}")
        sys.exit(0)

    logger.info("=" * 60)
    logger.info(f"批量音频切分工具启动")
    logger.info(f"输入目录: {INPUT_DIR}")
    logger.info(f"输出目录: {OUTPUT_DIR}")
    logger.info(f"找到 {len(audio_files)} 个音频文件")
    logger.info(f"VAD配置: threshold={VAD_CONFIG['threshold']}, "
                f"min_silence={VAD_CONFIG['min_silence_duration_ms']}ms")
    logger.info("=" * 60)

    # 加载模型
    try:
        logger.info("正在加载 Silero VAD 模型...")
        model = load_silero_vad()
        logger.info("模型加载完成")
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        sys.exit(1)

    # 处理每个音频
    total_segments = 0
    success_count = 0
    failed_files = []

    for audio_file in audio_files:
        logger.info(f"处理文件: {audio_file.name}, ")
        try:
            seg_count = process_single_audio(audio_file, model, output_path)
            if seg_count > 0:
                total_segments += seg_count
                success_count += 1
            elif seg_count == 0:
                # 没有检测到语音，也算处理成功（只是没有片段）
                success_count += 1
        except AudioProcessingError as e:
            logger.error(str(e))
            failed_files.append(audio_file.name)
        except Exception as e:
            logger.error(f"处理 {audio_file.name} 时发生未预期错误: {e}", exc_info=True)
            failed_files.append(audio_file.name)


if __name__ == "__main__":
    main()