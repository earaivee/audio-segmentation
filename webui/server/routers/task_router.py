# webui/server/routers/task_router.py
"""任务执行 API"""

from fastapi import APIRouter, HTTPException
from webui.server.routers.config_router import get_config
from webui.server.services.task_service import task_service

router = APIRouter()


@router.get("/status")
async def get_task_status():
    # 获取任务状态
    return {
        "status": task_service.status,
        "progress": task_service.progress,
        "message": task_service.message,
        "logs": task_service.logs[-50:],  # 返回最后50条日志
    }


@router.post("/run")
async def run_task():
    # 启动任务
    if task_service.is_running():
        raise HTTPException(status_code=400, detail="任务正在运行中")
    
    config = get_config()
    success = task_service.start(config)
    
    if not success:
        raise HTTPException(status_code=400, detail="任务启动失败")
    
    return {"message": "任务已启动"}


@router.post("/stop")
async def stop_task():
    # 停止任务
    if not task_service.is_running():
        raise HTTPException(status_code=400, detail="任务未运行")
    
    task_service.stop()
    return {"message": "任务已停止"}
