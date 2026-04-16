# webui/server/services/audio_service.py
"""音频操作服务 - 合并/删除/切分/单次识别"""

import torch
import torchaudio
import json
import soundfile as sf
from pathlib import Path
from typing import List, Optional
import logging

from silero_vad import load_silero_vad, read_audio
from src.config.settings import SettingConfig
from src.processors.normalizer import AudioNormalizer
from src.processors.segmenter import AudioSegmenter
from src.utils.asr_utils import transcribe_audio, load_asr_model
from src.utils.audio_utils import get_audio_duration

logger = logging.getLogger("audio_service")

# ====== 统一文本存储 (texts.json) ======

def _get_texts_json_path(output_dir: Path) -> Path:
    """获取 texts.json 的路径"""
    return output_dir / "texts.json"


def load_texts_db(output_dir: Path) -> dict:
    """加载统一文本存储，兼容旧的单独 .txt 文件"""
    db_path = _get_texts_json_path(output_dir)
    db: dict = {}
    if db_path.exists():
        try:
            db = json.loads(db_path.read_text(encoding="utf-8"))
        except Exception:
            db = {}
    return db


def save_texts_db(output_dir: Path, db: dict):
    """保存统一文本存储"""
    db_path = _get_texts_json_path(output_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def get_text_for_audio(output_dir: Path, audio_stem: str) -> str:
    """获取音频对应的识别文本，优先从 texts.json 读，兼容旧 .txt 文件"""
    db = load_texts_db(output_dir)
    if audio_stem in db:
        return db[audio_stem]
    return ""


def set_text_for_audio(output_dir: Path, audio_stem: str, text: str):
    """设置音频对应的识别文本"""
    db = load_texts_db(output_dir)
    db[audio_stem] = text
    save_texts_db(output_dir, db)


def remove_text_for_audio(output_dir: Path, audio_stem: str):
    """删除音频对应的识别文本"""
    db = load_texts_db(output_dir)
    if audio_stem in db:
        del db[audio_stem]
        save_texts_db(output_dir, db)


def bulk_set_texts(output_dir: Path, results: dict):
    """批量设置识别文本"""
    db = load_texts_db(output_dir)
    db.update(results)
    save_texts_db(output_dir, db)


def get_audio_info(filepath: Path, texts_db: dict = None) -> dict:
    """获取音频文件信息"""
    try:
        audio = read_audio(str(filepath))
        sr = 16000
        duration = get_audio_duration(audio, sr)

        # 从 texts_db 中读取文本
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
    """获取输出目录下所有音频文件的信息（平铺列表）"""
    # 确保目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not output_dir.exists():
        return []

    audio_files = []
    for ext in supported_formats:
        audio_files.extend(output_dir.glob(f"**/*{ext}"))
        audio_files.extend(output_dir.glob(f"**/*{ext.upper()}"))

    # 去重并排序
    seen = set()
    unique = []
    for f in sorted(audio_files):
        key = f.name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return [get_audio_info(f) for f in unique]


def list_audio_tree(output_dir: Path, supported_formats: tuple) -> List[dict]:
    """获取输出目录下所有音频文件，按文件夹分组为树形结构"""
    # 确保目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not output_dir.exists():
        return []

    audio_files = []
    for ext in supported_formats:
        audio_files.extend(output_dir.glob(f"**/*{ext}"))
        audio_files.extend(output_dir.glob(f"**/*{ext.upper()}"))

    # 去重并排序
    seen = set()
    unique = []
    for f in sorted(audio_files):
        key = str(f.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)

    # 按父目录分组
    from collections import OrderedDict
    groups: OrderedDict[str, list] = OrderedDict()
    for f in unique:
        parent = f.parent.name
        # 如果文件直接在 output_dir 下，归入 "未分组"
        if f.parent.resolve() == output_dir.resolve():
            parent = "_root_"
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(f)

    # 加载 texts.json
    texts_db = load_texts_db(output_dir)

    tree = []
    for folder_name, folder_files in groups.items():
        children = []
        total_duration = 0.0
        for f in folder_files:
            info = get_audio_info(f, texts_db=texts_db)
            # 为子节点添加简短名称（去掉文件夹前缀）
            seg_name = f.stem
            if seg_name.startswith(folder_name):
                seg_name = seg_name[len(folder_name):].lstrip("_")
            info["seg_name"] = seg_name or f.stem
            info["key"] = str(f.resolve())
            # 根目录文件的 parent_dir 设为空字符串，避免删除/移动时路径错误
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
    """合并多个音频文件"""
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
    """切分单个音频文件"""
    audio = read_audio(filepath)
    sr = 16000
    audio_path = Path(filepath)

    vad_model = load_silero_vad()
    normalizer = AudioNormalizer(config.normalize)
    segmenter = AudioSegmenter(config.vad, normalizer)

    timestamps = segmenter.detect_speech_segments(audio, sr, vad_model)
    if not timestamps:
        return []

    # 时长限制已停用
    # timestamps = segmenter.apply_duration_limit(
    #     timestamps, audio, sr, vad_model,
    #     config.segmenter.enabled_double_split, config.segmenter.factor
    # )

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
    """对单个音频进行 ASR 识别，结果写入 texts.json"""
    try:
        asr_model = load_asr_model(config.whisper)
        if asr_model is None:
            logger.warning("ASR 模型未启用或加载失败")
            return ""

        text = transcribe_audio(asr_model, config.whisper, Path(filepath))
        # 写入 texts.json
        set_text_for_audio(config.output_dir, Path(filepath).stem, text)

        # 清理模型释放内存
        del asr_model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

        return text
    except Exception as e:
        logger.error(f"ASR 识别失败: {e}", exc_info=True)
        raise


def update_audio_text(filepath: str, text: str, output_dir: Path = None):
    """更新音频对应的识别文本（存入 texts.json）"""
    audio_path = Path(filepath)
    if output_dir is None:
        # 默认使用音频父目录的父目录作为 output_dir
        output_dir = audio_path.parent.parent
    set_text_for_audio(output_dir, audio_path.stem, text)


def delete_audio_file(filepath: str, output_dir: Path = None):
    """删除音频文件及其文本记录"""
    audio_path = Path(filepath)
    if output_dir is None:
        output_dir = audio_path.parent.parent
    if audio_path.exists():
        audio_path.unlink()
    # 从 texts.json 中删除
    remove_text_for_audio(output_dir, audio_path.stem)
    # 兼容清理旧 .txt 文件
    txt_path = audio_path.parent / f"{audio_path.stem}.txt"
    if txt_path.exists():
        txt_path.unlink()


def export_training_list(config: SettingConfig, audio_items: List[dict]) -> str:
    """根据给定的音频项列表重新生成 GPT-SoVITS 训练列表"""
    lines = []
    for item in audio_items:
        filepath = item.get("filepath", "")
        text = item.get("text", "")
        if filepath and text:
            line = f"{filepath}|{config.sovits.speaker}|{config.sovits.language}|{text}"
            lines.append(line)

    if lines:
        output_path = Path(config.sovits.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")

    return str(config.sovits.output_path)


def rename_audio_file(filepath: str, new_name: str) -> str:
    """重命名音频文件及其文本文件，返回新路径"""
    audio_path = Path(filepath)
    if not audio_path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    # 确保新名称有正确扩展名
    ext = audio_path.suffix
    if not new_name.endswith(ext):
        new_name = new_name + ext

    new_path = audio_path.parent / new_name
    if new_path.exists() and new_path != audio_path:
        raise FileExistsError(f"目标文件已存在: {new_name}")

    # 重命名音频文件
    audio_path.rename(new_path)

    # 重命名对应的文本文件
    txt_path = audio_path.parent / f"{audio_path.stem}.txt"
    if txt_path.exists():
        new_txt_path = new_path.parent / f"{new_path.stem}.txt"
        txt_path.rename(new_txt_path)

    return str(new_path.resolve())


def move_audio_file(filepath: str, target_folder: str, output_dir: Path) -> str:
    """移动音频文件及其文本文件到目标文件夹，返回新路径"""
    audio_path = Path(filepath)
    if not audio_path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    # 空字符串或 _root_ 表示移动到根目录
    if not target_folder or target_folder == "_root_":
        target_dir = output_dir
    else:
        target_dir = output_dir / target_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    new_path = target_dir / audio_path.name
    if new_path.exists():
        raise FileExistsError(f"目标文件夹已存在同名文件: {audio_path.name}")

    # 移动音频文件
    import shutil
    shutil.move(str(audio_path), str(new_path))

    # 移动对应的文本文件
    txt_path = audio_path.parent / f"{audio_path.stem}.txt"
    if txt_path.exists():
        new_txt_path = target_dir / f"{audio_path.stem}.txt"
        shutil.move(str(txt_path), str(new_txt_path))

    return str(new_path.resolve())


def list_folders(output_dir: Path) -> List[str]:
    """列出输出目录下所有子文件夹名称"""
    if not output_dir.exists():
        return []
    folders = [d.name for d in sorted(output_dir.iterdir()) if d.is_dir()]
    return folders


def list_source_files(input_dir: Path) -> List[dict]:
    """列出输入目录下的原始源文件（递归扫描子目录，按文件夹分组）"""
    if not input_dir.exists():
        return []

    # 支持音频和视频格式
    all_formats = ('.wav', '.mp3', '.flac', '.ogg', '.mp4', '.mkv', '.avi', '.webm', '.m4a')
    all_files = []
    for f in sorted(input_dir.rglob('*')):
        if f.is_file() and f.suffix.lower() in all_formats:
            try:
                size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                # 相对于 input_dir 的路径
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

    # 按文件夹分组
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
    """浏览指定目录，返回子目录列表"""
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

    # Windows 驱动器列表
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
    """按用户指定的时间点切分音频，纯按时间裁剪不使用 VAD"""
    audio = read_audio(filepath)
    sr = 16000
    audio_path = Path(filepath)
    total_duration = len(audio) / sr

    # 排序并去重时间点，过滤无效值
    times = sorted(set(t for t in times if 0 < t < total_duration))
    if not times:
        raise ValueError("没有有效的切分时间点")

    # 构建区间: [0, t1], [t1, t2], ..., [tn, end]
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
