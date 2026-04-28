# webui/server/services/audio_service.py
"""音频操作服务 - 合并/删除/切分/单次识别"""

import torch
import torchaudio
import json
import soundfile as sf
import os
import subprocess
from pathlib import Path
from typing import List, Optional
import logging

from pydub import AudioSegment
from silero_vad import load_silero_vad, read_audio
from ..config.settings import SettingConfig
from .normalizer import AudioNormalizer
from .segmenter import AudioSegmenter
from ..utils.asr_utils import transcribe_audio, load_faster_whisper_model
from ..utils.audio_utils import get_audio_duration

logger = logging.getLogger("audio_service")


def _get_texts_json_path(output_dir: Path) -> Path:
    # 获取 texts.json 数据库文件路径
    return output_dir / "texts.json"


def load_texts_db(output_dir: Path) -> dict:
    # 从 output_dir 加载 texts.json 数据库
    db_path = _get_texts_json_path(output_dir)
    db: dict = {}
    if db_path.exists():
        try:
            db = json.loads(db_path.read_text(encoding="utf-8"))
        except Exception:
            db = {}
    return db


def save_texts_db(output_dir: Path, db: dict):
    # 保存 texts.json 数据库到 output_dir
    db_path = _get_texts_json_path(output_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def get_text_for_audio(output_dir: Path, audio_stem: str) -> str:
    # 从文本数据库中获取指定音频的识别文本
    db = load_texts_db(output_dir)
    if audio_stem in db:
        return db[audio_stem]
    return ""


def set_text_for_audio(output_dir: Path, audio_stem: str, text: str):
    # 保存指定音频的识别文本到数据库
    db = load_texts_db(output_dir)
    db[audio_stem] = text
    save_texts_db(output_dir, db)


def remove_text_for_audio(output_dir: Path, audio_stem: str):
    # 从文本数据库中删除指定音频的识别文本
    db = load_texts_db(output_dir)
    if audio_stem in db:
        del db[audio_stem]
        save_texts_db(output_dir, db)


def bulk_set_texts(output_dir: Path, results: dict):
    # 批量更新文本数据库
    db = load_texts_db(output_dir)
    db.update(results)
    save_texts_db(output_dir, db)


def get_audio_info(filepath: Path, texts_db: dict = None) -> dict:
    # 获取单个音频文件的基本信息（时长、文件路径、文本等）
    try:
        audio = read_audio(str(filepath))
        sr = 16000
        duration = get_audio_duration(audio, sr)

        text = ""
        if texts_db is not None and filepath.stem in texts_db:
            text = texts_db[filepath.stem]

        return {
            "filename": filepath.name,
            "filepath": str(filepath.resolve()),
            "duration_sec": round(duration, 2),
            "text": text,
            "parent_dir": filepath.parent.name,
        }
    except Exception as e:
        return {
            "filename": filepath.name,
            "filepath": str(filepath.resolve()),
            "duration_sec": 0.0,
            "text": "",
            "parent_dir": filepath.parent.name,
            "error": str(e),
        }


def list_audio_files(output_dir: Path, supported_formats: tuple) -> List[dict]:
    # 列出输出目录下的所有音频文件信息（去重、排序）
    output_dir.mkdir(parents=True, exist_ok=True)

    if not output_dir.exists():
        return []

    audio_files = []
    for ext in supported_formats:
        audio_files.extend(output_dir.glob(f"**/*{ext}"))
        audio_files.extend(output_dir.glob(f"**/*{ext.upper()}"))

    seen = set()
    unique = []
    for f in sorted(audio_files):
        key = f.name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return [get_audio_info(f) for f in unique]


def list_audio_tree(output_dir: Path, supported_formats: tuple) -> List[dict]:
    # 按文件夹分组列出音频文件树形结构
    output_dir.mkdir(parents=True, exist_ok=True)

    if not output_dir.exists():
        return []

    audio_files = []
    for ext in supported_formats:
        audio_files.extend(output_dir.glob(f"**/*{ext}"))
        audio_files.extend(output_dir.glob(f"**/*{ext.upper()}"))

    seen = set()
    unique = []
    for f in sorted(audio_files):
        key = str(f.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)

    from collections import OrderedDict
    groups: OrderedDict[str, list] = OrderedDict()
    for f in unique:
        parent = f.parent.name
        if f.parent.resolve() == output_dir.resolve():
            parent = "_root_"
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(f)

    texts_db = load_texts_db(output_dir)

    tree = []
    for folder_name, folder_files in groups.items():
        children = []
        total_duration = 0.0
        for f in folder_files:
            info = get_audio_info(f, texts_db=texts_db)
            seg_name = f.stem
            if seg_name.startswith(folder_name):
                seg_name = seg_name[len(folder_name):].lstrip("_")
            info["seg_name"] = seg_name or f.stem
            info["key"] = str(f.resolve())
            if folder_name == "_root_":
                info["parent_dir"] = ""
            children.append(info)
            total_duration += info.get("duration_sec", 0.0)

        display_name = folder_name if folder_name != "_root_" else "未分组文件"
        tree.append({
            "key": f"folder:{folder_name}",
            "folder": display_name,
            "children_count": len(children),
            "total_duration_sec": round(total_duration, 2),
            "is_folder": True,
            "children": children,
        })

    return tree


def merge_audio_files(filepaths: List[str], output_path: str) -> str:
    # 合并多个音频文件为一个 WAV 文件
    sr = 16000
    segments = []
    for fp in filepaths:
        audio = read_audio(fp)
        segments.append(audio)

    merged = torch.cat(segments, dim=0)
    merged_2d = merged.unsqueeze(0) if merged.dim() == 1 else merged
    torchaudio.save(output_path, merged_2d.cpu(), sr)
    return output_path


def split_audio_file(filepath: str, config: SettingConfig) -> List[str]:
    # 使用 VAD 自动检测语音片段并切分音频
    audio = read_audio(filepath)
    sr = 16000
    audio_path = Path(filepath)

    vad_model = load_silero_vad()
    normalizer = AudioNormalizer(config.normalize)
    segmenter = AudioSegmenter(config.vad, normalizer)

    timestamps = segmenter.detect_speech_segments(audio, sr, vad_model)
    if not timestamps:
        return []

    output_dir = audio_path.parent
    output_files = []
    for i, ts in enumerate(timestamps, 1):
        segment, info = segmenter.extract_and_process_segment(
            audio, ts['start'], ts['end'], sr
        )
        output_path = output_dir / f"{audio_path.stem}_split_{i:04d}.wav"
        segmenter.save_segment(segment, output_path, sr)
        output_files.append(str(output_path))

    del vad_model
    return output_files


def transcribe_single(filepath: str, config: SettingConfig) -> str:
    # 对单个音频文件执行 ASR 语音识别
    try:
        fw_model = load_faster_whisper_model(config.faster_whisper)
        if fw_model is None:
            logger.warning("faster-whisper 模型未启用")
            return ""

        text = transcribe_audio(fw_model, config.faster_whisper, Path(filepath))
        set_text_for_audio(config.output_dir, Path(filepath).stem, text)

        del fw_model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

        return text
    except Exception as e:
        logger.error(f"ASR 识别失败: {e}", exc_info=True)
        raise


def update_audio_text(filepath: str, text: str, output_dir: Path = None):
    # 手动更新指定音频文件的识别文本
    audio_path = Path(filepath)
    if output_dir is None:
        output_dir = audio_path.parent.parent
    set_text_for_audio(output_dir, audio_path.stem, text)


def delete_audio_file(filepath: str, output_dir: Path = None):
    # 删除音频文件及其关联的文本文件和识别文本数据库记录
    audio_path = Path(filepath)
    if output_dir is None:
        output_dir = audio_path.parent.parent
    if audio_path.exists():
        audio_path.unlink()
    remove_text_for_audio(output_dir, audio_path.stem)


def export_training_list(config: SettingConfig, audio_items: List[dict]) -> str:
    # 导出训练列表文件，支持多种 TTS/VC 模型格式
    lines = []
    fmt = config.sovits.format_type
    speaker = config.sovits.speaker
    language = config.sovits.language

    for item in audio_items:
        filepath = item.get("filepath", "")
        text = item.get("text", "")
        if not filepath or not text:
            continue

        if fmt == "gpt_sovits":
            line = f"{filepath}|{speaker}|{language}|{text}"
        elif fmt == "vits":
            line = f"{filepath}|{speaker}|{text}"
        elif fmt == "bert_vits2":
            line = f"{filepath}|{speaker}|{language}|{text}"
        elif fmt == "rvc":
            line = f"{filepath}|{text}"
        elif fmt == "rvc_wav_only":
            line = filepath
        elif fmt == "index_tts":
            line = f"{filepath}|{text}"
        elif fmt == "fish_speech":
            line = f"{filepath}\t{text}"
        else:
            line = f"{filepath}|{speaker}|{language}|{text}"
        lines.append(line)

    if lines:
        output_path = Path(config.sovits.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")

    return str(config.sovits.output_path)


def rename_audio_file(filepath: str, new_name: str) -> str:
    # 重命名音频文件（同时处理同名 .txt 文件）
    audio_path = Path(filepath)
    if not audio_path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    ext = audio_path.suffix
    if not new_name.endswith(ext):
        new_name = new_name + ext

    new_path = audio_path.parent / new_name
    if new_path.exists() and new_path != audio_path:
        raise FileExistsError(f"目标文件已存在: {new_name}")

    audio_path.rename(new_path)

    return str(new_path.resolve())


def move_audio_file(filepath: str, target_folder: str, output_dir: Path) -> str:
    # 将音频文件移动到输出目录下的指定文件夹
    audio_path = Path(filepath)
    if not audio_path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    if not target_folder or target_folder == "_root_":
        target_dir = output_dir
    else:
        target_dir = output_dir / target_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    new_path = target_dir / audio_path.name
    if new_path.exists():
        raise FileExistsError(f"目标文件夹已存在同名文件: {audio_path.name}")

    import shutil
    shutil.move(str(audio_path), str(new_path))

    return str(new_path.resolve())


def list_folders(output_dir: Path) -> List[str]:
    # 获取输出目录下的所有子文件夹名称列表
    if not output_dir.exists():
        return []
    folders = [d.name for d in sorted(output_dir.iterdir()) if d.is_dir()]
    return folders


def list_source_files(input_dir: Path) -> List[dict]:
    # 列出输入目录中所有支持的音视频文件（按文件夹分组）
    if not input_dir.exists():
        return []

    all_formats = ('.wav', '.mp3', '.flac', '.ogg', '.mp4', '.mkv', '.avi', '.webm', '.m4a')
    all_files = []
    for f in sorted(input_dir.rglob('*')):
        if f.is_file() and f.suffix.lower() in all_formats:
            try:
                size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                rel = f.relative_to(input_dir)
                folder = str(rel.parent) if str(rel.parent) != '.' else ''
                all_files.append({
                    "filename": f.name,
                    "filepath": str(f.resolve()),
                    "size_mb": size_mb,
                    "ext": f.suffix.lower(),
                    "folder": folder,
                })
            except Exception:
                pass

    from collections import OrderedDict
    groups: OrderedDict[str, list] = OrderedDict()
    for item in all_files:
        folder = item["folder"]
        if folder not in groups:
            groups[folder] = []
        groups[folder].append(item)

    result = []
    for folder_name, folder_files in groups.items():
        total_size = round(sum(f["size_mb"] for f in folder_files), 2)
        result.append({
            "folder": folder_name or "根目录",
            "folder_raw": folder_name,
            "files": folder_files,
            "count": len(folder_files),
            "total_size_mb": total_size,
        })
    return result


def list_directory(path: str) -> dict:
    # 浏览文件系统目录，列出子文件夹和驱动器
    import os
    p = Path(path) if path else Path.home()
    if not p.exists():
        p = Path.home()

    dirs = []
    try:
        for item in sorted(p.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                dirs.append({
                    "name": item.name,
                    "path": str(item.resolve()),
                })
    except PermissionError:
        pass

    drives = []
    if os.name == 'nt':
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                drives.append({"name": drive, "path": drive})

    return {
        "current": str(p.resolve()),
        "parent": str(p.parent.resolve()) if p.parent != p else None,
        "dirs": dirs,
        "drives": drives,
    }


def split_audio_at_times(filepath: str, times: List[float]) -> List[str]:
    # 在指定时间点手动切分音频文件
    audio = read_audio(filepath)
    sr = 16000
    audio_path = Path(filepath)
    total_duration = len(audio) / sr

    times = sorted(set(t for t in times if 0 < t < total_duration))
    if not times:
        raise ValueError("没有有效的切分时间点")

    boundaries = [0.0] + times + [total_duration]

    output_dir = audio_path.parent
    output_files = []
    for i in range(len(boundaries) - 1):
        start_sample = int(boundaries[i] * sr)
        end_sample = int(boundaries[i + 1] * sr)
        segment = audio[start_sample:end_sample]

        if len(segment) == 0:
            continue

        output_path = output_dir / f"{audio_path.stem}_split_{i + 1}.wav"
        segment_2d = segment.unsqueeze(0) if segment.dim() == 1 else segment
        torchaudio.save(str(output_path), segment_2d.cpu(), sr)
        output_files.append(str(output_path))

    return output_files


# 视频/音频转 WAV
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.webm', '.m4a', '.flac', '.ogg', '.mp3', '.wav'}


def convert_audio(filepath: str, output_format: str = "wav", output_dir: Optional[Path] = None) -> str:
    """
    将视频或音频文件转换为指定格式（wav/mp3/flac/ogg/aac/m4a）。
    使用 ffmpeg 直接转换（不依赖 pydub / ffprobe）。
    """
    SUPPORTED_FORMATS = {"wav", "mp3", "flac", "ogg", "aac", "m4a"}
    fmt = output_format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的格式: {output_format}，支持的格式: {', '.join(sorted(SUPPORTED_FORMATS))}")

    src_path = Path(filepath)
    if not src_path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    ext = src_path.suffix.lower()
    if ext == f'.{fmt}':
        return str(src_path)

    if output_dir is None:
        output_dir = src_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{src_path.stem}.{fmt}"

    # 定位 imageio_ffmpeg 自带的 ffmpeg 可执行文件
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("未找到 ffmpeg，请安装 ffmpeg 或安装 imageio-ffmpeg 包")

    # ffmpeg 参数构建
    cmd = [ffmpeg_exe, "-i", str(src_path), "-y"]

    if fmt == "wav":
        cmd.extend(["-ar", "16000", "-ac", "1"])
    elif fmt == "mp3":
        cmd.extend(["-b:a", "192k"])
    elif fmt == "aac":
        cmd.extend(["-b:a", "192k", "-f", "adts"])
    elif fmt == "m4a":
        cmd.extend(["-b:a", "192k", "-c:a", "aac"])

    cmd.append(str(out_path))

    logger.info(f"正在转换: {src_path.name} -> {out_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ffmpeg 转换失败: {result.stderr}")
        raise RuntimeError(f"ffmpeg 转换失败: {result.stderr[:500]}")

    logger.info(f"转换完成: {out_path}")
    return str(out_path)


def convert_to_wav(filepath: str, output_dir: Optional[Path] = None) -> str:
    """兼容旧接口，内部调用 convert_audio。"""
    return convert_audio(filepath, "wav", output_dir)
