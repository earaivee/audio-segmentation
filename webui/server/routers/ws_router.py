# webui/server/routers/ws_router.py
"""WebSocket 实时推送路由"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.task_service import ws_log_handler, task_service

router = APIRouter()


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    # WebSocket 端点：实时推送任务日志和进度
    await websocket.accept()
    ws_log_handler.connections.add(websocket)

    loop = asyncio.get_event_loop()
    ws_log_handler.set_loop(loop)

    try:
        if task_service.logs:
            await websocket.send_json({
                "type": "history",
                "logs": task_service.logs,
            })
        await websocket.send_json({
            "type": "progress",
            "progress": task_service.progress,
            "message": task_service.message,
            "status": task_service.status,
        })
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_log_handler.connections.discard(websocket)