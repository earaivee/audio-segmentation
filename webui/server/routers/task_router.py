# webui/server/routers/task_router.py
"""任务执行 API"""

from fastapi import APIRouter, HTTPException
from .config_router import get_config
from ..services.task_service import task_service

router = APIRouter()


@router.get("/status")
async def get_task_status():
    # 获取后台任务的当前状态、阶段、进度和日志
    return {
        "status": task_service.status,
        "stage": task_service.stage,
        "progress": task_service.progress,
        "message": task_service.message,
        "logs": task_service.logs[-50:],
    }


@router.post("/run")
async def run_task():
    # 启动后台音频切分任务
    if task_service.is_running():
        raise HTTPException(status_code=400, detail="任务正在运行中")

    config = get_config()
    success = task_service.start(config)

    if not success:
        raise HTTPException(status_code=400, detail="任务启动失败")

    return {"message": "任务已启动"}


@router.post("/stop")
async def stop_task():
    # 停止当前运行中的后台任务
    if not task_service.is_running():
        raise HTTPException(status_code=400, detail="任务未运行")

    task_service.stop()
    return {"message": "任务已停止"}