# 音频智能切分工具 - WebUI 启动入口
import os

# 解决 numpy/torch 的 OpenMP 运行时冲突
if "KMP_DUPLICATE_LIB_OK" not in os.environ:
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import uvicorn

def main():
    # 启动 WebUI
    print("正在启动 WebUI 服务器...")
    print("访问地址: http://localhost:8000")

    # 启动 FastAPI 服务器
    uvicorn.run(
        "webui.server.app:create_app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()