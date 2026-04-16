# webui/server/routers/audio_router.py
"""音频文件管理 API"""

import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import List, Optional
from webui.server.models import (
    MergeRequest, SplitRequest, TranscribeRequest,
    UpdateTextRequest, ExportListRequest, AudioFileInfo,
    RenameRequest, MoveRequest, SplitAtTimesRequest
)
from webui.server.routers.config_router import get_config
from webui.server.services.audio_service import (
    list_audio_files, list_audio_tree, merge_audio_files, split_audio_file,
    transcribe_single, update_audio_text, delete_audio_file,
    export_training_list, rename_audio_file, move_audio_file,
    list_folders, split_audio_at_times, list_source_files
)

router = APIRouter()


@router.get("/list")
async def get_audio_list():
    """获取输出目录的音频文件列表（平铺）"""
    config = get_config()
    files = list_audio_files(config.output_dir, config.supported_formats)
    return {"files": files, "total": len(files)}


@router.get("/tree")
async def get_audio_tree():
    """获取输出目录的音频文件树形结构（按文件夹分组）"""
    config = get_config()
    tree = list_audio_tree(config.output_dir, config.supported_formats)
    total_files = sum(item["children_count"] for item in tree)
    return {"tree": tree, "total_folders": len(tree), "total_files": total_files}


@router.get("/play")
async def play_audio(path: str):
    """音频文件流式播放"""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        str(file_path),
        media_type="audio/wav",
        filename=file_path.name,
    )


@router.delete("/{filename}")
async def remove_audio(filename: str, dir: str = ""):
    """删除单个音频片段"""
    config = get_config()
    if dir:
        filepath = config.output_dir / dir / filename
    else:
        # 搜索文件
        found = list(config.output_dir.glob(f"**/{filename}"))
        if not found:
            raise HTTPException(status_code=404, detail="文件不存在")
        filepath = found[0]

    delete_audio_file(str(filepath), output_dir=config.output_dir)
    return {"message": f"已删除: {filename}"}


@router.post("/merge")
async def merge_audio(req: MergeRequest):
    """合并多个音频片段，自动命名保存在源文件所在目录"""
    if len(req.filepaths) < 2:
        raise HTTPException(status_code=400, detail="至少需要两个文件才能合并")

    from pathlib import Path as _P
    # 自动命名: stem1_stem2_merge.wav，保存在第一个文件所在目录
    first = _P(req.filepaths[0])
    second = _P(req.filepaths[1])
    output_name = f"{first.stem}_{second.stem}_merge.wav"
    output_path = str(first.parent / output_name)

    try:
        result = merge_audio_files(req.filepaths, output_path)
        return {"message": "合并完成", "output": result, "output_name": output_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并失败: {e}")


@router.post("/split")
async def split_audio(req: SplitRequest):
    """手动切分单个音频"""
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
    """对单个音频进行 ASR 识别"""
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
    """修改识别文本"""
    config = get_config()
    try:
        update_audio_text(req.filepath, req.text, output_dir=config.output_dir)
        return {"message": "文本已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")


@router.post("/export-list")
async def export_list(req: ExportListRequest):
    """重新生成 GPT-SoVITS 训练列表"""
    config = get_config()

    if req.items:
        items = req.items
    else:
        # 使用当前输出目录中的所有文件
        files = list_audio_files(config.output_dir, config.supported_formats)
        items = files

    try:
        output_path = export_training_list(config, items)
        return {"message": "训练列表已生成", "output_path": output_path, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")


@router.get("/output-list")
async def get_output_list():
    """获取 output.list 推理文本文件内容"""
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
    """重命名音频文件"""
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
    """移动音频文件到目标文件夹"""
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
    """获取输出目录下所有文件夹列表"""
    config = get_config()
    folders = list_folders(config.output_dir)
    return {"folders": folders}


@router.get("/sources")
async def get_source_files():
    """获取输入目录的原始源文件列表"""
    config = get_config()
    groups = list_source_files(config.input_dir)
    total_files = sum(g["count"] for g in groups)
    return {"groups": groups, "total_files": total_files, "total_folders": len(groups), "input_dir": str(config.input_dir)}


@router.post("/import-source")
async def import_source_files(
    files: List[UploadFile] = File(...),
    subfolder: Optional[str] = Form(default=""),
):
    """导入源音频文件到输入目录"""
    config = get_config()
    target_dir = config.input_dir
    if subfolder:
        target_dir = target_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = target_dir / f.filename
        # 避免覆盖同名文件，自动加序号
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
    """按用户指定的时间点切分音频"""
    if not Path(req.filepath).exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        output_files = split_audio_at_times(req.filepath, req.times)
        return {"message": f"切分完成，共 {len(output_files)} 个片段", "files": output_files}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切分失败: {e}")

