# webui/server/routers/audio_router.py

import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from typing import List, Optional

from ..models import (
    MergeRequest, SplitRequest, TranscribeRequest,
    UpdateTextRequest, ExportListRequest, AudioFileInfo,
    RenameRequest, MoveRequest, SplitAtTimesRequest,
    ConvertRequest,
)
from .config_router import get_config
from ..services.audio_service import (
    list_audio_files, list_audio_tree, merge_audio_files, split_audio_file,
    transcribe_single, update_audio_text, delete_audio_file,
    export_training_list, rename_audio_file, move_audio_file,
    list_folders, split_audio_at_times, list_source_files,
    convert_to_wav, convert_audio,
)

router = APIRouter()


@router.get("/list")
async def get_audio_list():
    # 获取输出目录中的音频文件列表（扁平）
    config = get_config()
    files = list_audio_files(config.output_dir, config.supported_formats)
    return {"files": files, "total": len(files)}


@router.get("/tree")
async def get_audio_tree():
    # 获取输出目录中的音频文件树形结构（按文件夹分组）
    config = get_config()
    tree = list_audio_tree(config.output_dir, config.supported_formats)
    total_files = sum(item["children_count"] for item in tree)
    return {"tree": tree, "total_folders": len(tree), "total_files": total_files}


@router.get("/play")
async def play_audio(path: str):
    # 播放指定路径的音频文件
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        str(file_path),
        media_type="audio/wav",
        filename=file_path.name,
    )


@router.delete("/remove-source")
async def remove_source_file(filepath: str):
    # 删除输入目录中的源文件（含安全校验）
    config = get_config()
    source_path = Path(filepath)
    try:
        source_path.resolve().relative_to(config.input_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不能删除输出目录外的文件")

    if not source_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        source_path.unlink()
        return {"message": f"已删除源文件: {source_path.name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.delete("/{filename}")
async def delete_audio_file_route(filename: str, dir: str = ""):
    # 删除输出目录中的音频文件及其文本数据库记录
    config = get_config()
    if dir and dir != "_root_":
        file_path = config.output_dir / dir / filename
    else:
        file_path = config.output_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    try:
        delete_audio_file(str(file_path), output_dir=config.output_dir)
        return {"message": f"已删除文件: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.post("/merge")
async def merge_audio(req: MergeRequest):
    # 合并多个音频文件为一个 WAV 文件
    if len(req.filepaths) < 2:
        raise HTTPException(status_code=400, detail="至少需要两个文件才能合并")

    first = Path(req.filepaths[0])
    second = Path(req.filepaths[1])
    output_name = f"{first.stem}_{second.stem}_merge.wav"
    output_path = str(first.parent / output_name)

    try:
        result = merge_audio_files(req.filepaths, output_path)
        return {"message": "合并完成", "output": result, "output_name": output_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并失败: {e}")


@router.post("/split")
async def split_audio(req: SplitRequest):
    # 使用 VAD 自动检测语音片段并切分音频
    if not Path(req.filepath).exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    config = get_config()
    try:
        output_files = split_audio_file(req.filepath, config)
        return {"message": f"切分完成，共 {len(output_files)} 个片段", "files": output_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切分失败: {e}")


@router.post("/transcribe")
async def transcribe_audio_single(req: TranscribeRequest):
    # 使用 ASR 模型对单个音频文件进行语音识别
    if not Path(req.filepath).exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    config = get_config()
    try:
        text = transcribe_single(req.filepath, config)
        return {"text": text, "filepath": req.filepath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"识别失败: {e}")


@router.put("/text")
async def update_text(req: UpdateTextRequest):
    # 手动更新指定音频文件的识别文本
    config = get_config()
    try:
        update_audio_text(req.filepath, req.text, output_dir=config.output_dir)
        return {"message": "文本已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")


@router.post("/export-list")
async def export_list(req: ExportListRequest):
    # 导出训练列表文件（GPT-SoVITS 格式）
    config = get_config()

    if req.items:
        items = req.items
    else:
        files = list_audio_files(config.output_dir, config.supported_formats)
        items = files

    try:
        output_path = export_training_list(config, items)
        return {"message": "训练列表已生成", "output_path": output_path, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")


@router.get("/output-list")
async def get_output_list():
    # 读取已生成的训练列表文件内容
    config = get_config()
    list_path = config.sovits.output_path

    if not Path(list_path).exists():
        return {"content": "", "exists": False, "path": str(list_path)}

    try:
        content = Path(list_path).read_text(encoding="utf-8")
        return {"content": content, "exists": True, "path": str(list_path), "lines": content.count("\n") if content else 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")


@router.put("/rename")
async def rename_audio(req: RenameRequest):
    # 重命名音频文件（同时处理同名 .txt 文件）
    try:
        new_path = rename_audio_file(req.filepath, req.new_name)
        return {"message": "重命名成功", "new_path": new_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")


@router.put("/move")
async def move_audio(req: MoveRequest):
    # 将音频文件移动到输出目录下的指定文件夹
    config = get_config()
    try:
        new_path = move_audio_file(req.filepath, req.target_folder, config.output_dir)
        return {"message": "移动成功", "new_path": new_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移动失败: {e}")


@router.get("/folders")
async def get_folders():
    # 获取输出目录下的所有子文件夹列表
    config = get_config()
    folders = list_folders(config.output_dir)
    return {"folders": folders}


@router.get("/sources")
async def get_source_files():
    # 获取输入目录中的所有源文件（按文件夹分组）
    config = get_config()
    groups = list_source_files(config.input_dir)
    total_files = sum(g["count"] for g in groups)
    return {"groups": groups, "total_files": total_files, "total_folders": len(groups), "input_dir": str(config.input_dir)}


@router.post("/import-source")
async def import_source_files(
    files: List[UploadFile] = File(...),
    subfolder: Optional[str] = Form(default=""),
):
    # 上传导入源音频/视频文件到输入目录
    config = get_config()
    target_dir = config.input_dir
    if subfolder:
        target_dir = target_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = target_dir / f.filename
        if dest.exists():
            stem = dest.stem
            ext = dest.suffix
            i = 1
            while dest.exists():
                dest = target_dir / f"{stem}_{i}{ext}"
                i += 1
        with open(str(dest), "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved.append({"filename": dest.name, "filepath": str(dest.resolve())})

    return {"message": f"已导入 {len(saved)} 个文件", "files": saved}


@router.post("/split-at-times")
async def split_at_times(req: SplitAtTimesRequest):
    # 在指定时间点手动切分音频文件
    if not Path(req.filepath).exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        output_files = split_audio_at_times(req.filepath, req.times)
        return {"message": f"切分完成，共 {len(output_files)} 个片段", "files": output_files}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切分失败: {e}")


@router.post("/convert-to-wav")
async def convert_audio_to_wav(filepath: str):
    # 兼容旧接口，将视频或音频文件转换为 WAV 格式
    try:
        wav_path = convert_to_wav(filepath)
        return {"message": "转换完成", "wav_path": wav_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换失败: {e}")


@router.post("/convert")
async def convert_audio_route(req: ConvertRequest):
    # 将音频文件转换为指定格式（wav / mp3 / flac / ogg / aac / m4a）
    try:
        out_path = convert_audio(req.filepath, req.output_format)
        return {"message": f"已转换为 {req.output_format.upper()} 格式", "output_path": out_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换失败: {e}")