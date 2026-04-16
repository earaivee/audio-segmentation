# 音频智能切分工具 - WebUI 启动入口
import uvicorn
import sys
from pathlib import Path

def main():
    # 启动 WebUI
    # 添加项目根目录到 Python 路径
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    print("正在启动 WebUI 服务器...")
    print("访问地址: http://localhost:8000")
    print("启动WebUI --npm run dev --prefix webui/client")

    # 启动 FastAPI 服务器
    uvicorn.run(
        "src.app:create_app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()