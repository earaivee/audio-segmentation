# webui/server/file_utils.py

from pathlib import Path
from typing import List, Tuple

from .logger import setup_logger
from ..config.errors import FileError

logger = setup_logger(__name__)


def get_file_count(input_dir: Path, supported_formats: Tuple[str, ...]) -> int:
    # 统计指定目录中支持的音频文件数量（去重）
    audio_files = set()
    for ext in supported_formats:
        for f in input_dir.glob(f"**/*{ext}"):
            audio_files.add(f)
        for f in input_dir.glob(f"**/*{ext.upper()}"):
            audio_files.add(f)
    return len(audio_files)


def get_audio_files(input_dir: Path, supported_formats: Tuple[str, ...]) -> List[Path]:
    # 获取指定目录中所有支持的音频文件路径列表（已排序）
    audio_files = set()
    for ext in supported_formats:
        for f in input_dir.glob(f"**/*{ext}"):
            audio_files.add(f)
        for f in input_dir.glob(f"**/*{ext.upper()}"):
            audio_files.add(f)
    return sorted(list(audio_files))


def get_unique_files(audio_files: List[Path]) -> List[Path]:
    # 对音频文件列表按名称去重（忽略大小写），返回唯一文件列表
    unique = {}
    for f in audio_files:
        unique[f.name.lower()] = f
    return sorted(unique.values())


def rename_folder(old_path: Path, new_name: str) -> Path:
    # 重命名文件夹
    new_path = old_path.parent / new_name
    try:
        old_path.rename(new_path)
    except Exception as e:
        raise FileError(f"文件夹重命名失败: {e}")
    return new_path


def rename_file(old_path: Path, new_name: str) -> Path:
    # 重命名文件（保留原扩展名）
    new_path = old_path.parent / f"{new_name}{old_path.suffix}"
    try:
        old_path.rename(new_path)
    except Exception as e:
        raise FileError(f"文件重命名失败: {e}")
    return new_path