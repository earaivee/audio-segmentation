# src/app.py
# 音频智能切分 - 核心应用类（CLI 模式 / 被 WebUI task_service 引用）
import gc

from silero_vad import load_silero_vad, read_audio
from pathlib import Path
from src.utils.progress_utils import progressBar
from src.config.settings import SettingConfig
from src.processors.normalizer import AudioNormalizer
from src.processors.segmenter import AudioSegmenter
from src.utils.asr_utils import batch_transcribe, load_asr_model
from src.utils.logger import setup_logger
from src.utils.file_utils import get_audio_files, get_unique_files, get_file_count, rename_folder
from src.config.errors import FileError, AudioError
from src.utils.time_utils import get_timestamp
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path as _Path
import uvicorn

logger = setup_logger(__name__)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(
        title="音频智能切分工具",
        description="基于 Silero VAD 的音频智能切分与 ASR 识别系统",
        version="1.0.0"
    )
    
    # 导入路由
    from webui.server.routers import audio_router, config_router, ws_router, task_router
    
    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 在生产环境中应该指定具体的域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(config_router.router, prefix="/api/config", tags=["配置管理"])
    app.include_router(audio_router.router, prefix="/api/audio", tags=["音频管理"])
    app.include_router(task_router.router, prefix="/api/task", tags=["任务管理"])
    app.include_router(ws_router.router, tags=["WebSocket"])
    
    # 静态文件服务（前端构建产物）
    client_dist = _Path(__file__).parent.parent / "webui" / "client" / "dist"
    if client_dist.exists():
        app.mount("/", StaticFiles(directory=str(client_dist), html=True), name="static")
    
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "音频智能切分服务运行中"}
    
    return app


class AudioSegmentationApp:

    def __init__(self, config: SettingConfig = None):
        self.config = config or SettingConfig()
        self.whisper = config.whisper
        self.normalizer = AudioNormalizer(self.config.normalize)
        self.segmenter = AudioSegmenter(self.config.vad, self.normalizer)
        self.model = None
        self.asr = None

    def setup(self):
        # 初始化设置  创建输出目录
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        # 加载 VAD 模型
        logger.info("正在加载 Silero VAD 模型...")
        self.model = load_silero_vad()
        logger.info("正在加载 ASR 模型...")
        self.asr = load_asr_model(self.whisper)
        logger.info("模型加载完成")
        logger.info("正在启动主程序...")

    def close(self):
        # 关闭资源
        del self.model
        del self.asr
        gc.collect()

    def process_file(self, audio_path: Path) -> tuple:
        # 处理单个文件
        audio = read_audio(str(audio_path))
        # 采样率（Sample Rate）
        sr = 16000
        # 检测语音片段
        timestamps = self.segmenter.detect_speech_segments(audio, sr, self.model)
        if not timestamps:
            raise AudioError(f"未检测到文件 {audio_path.name} 的语音")

        # 创建输出目录
        output_dir = self.config.output_dir / audio_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        segments_info = []
        for i, ts in enumerate(timestamps, 1):
            segment, info = self.segmenter.extract_and_process_segment(
                audio, ts['start'], ts['end'], sr
            )
            output_path = output_dir / f"{audio_path.stem}_seg_{i:04d}.wav"
            self.segmenter.save_segment(segment, output_path, sr)
            segments_info.append({
                "index": i,
                "file_name": output_path.name,
                "duration_sec": info["duration_sec"],
                "original_rms": info["original_rms"],
                "normalized_rms": info["normalized_rms"]
            })
        return len(timestamps), segments_info

    def run(self):
        logger.info("audio segment program run is successful!")
        # 运行主流程
        if not self.config.input_dir.exists():
            self.config.input_dir.mkdir(parents=True, exist_ok=True)

        if get_file_count(self.config.output_dir, self.config.supported_formats ) > 0:
            timestamp = get_timestamp()
            new_name = f"{self.config.output_dir.stem}_bak_{timestamp}"
            rename_folder(self.config.output_dir, new_name)
            logger.info(f"输出目录已存在，备份目录为: {new_name}")

        # 获取所有文件
        audio_files = get_unique_files(get_audio_files(self.config.input_dir, self.config.supported_formats ))

        if not audio_files:
            raise FileError(f"{self.config.input_dir} 无音频源文件")

        # 初始化
        self.setup()

        # run
        with progressBar(len(audio_files)) as progress:
            for idx, audio_file in enumerate(audio_files, 1):
                try:
                    segment_count, segments = self.process_file(audio_file)
                except Exception as e:
                    raise AudioError()
                progress()
                print(f"音频 {audio_file.name} 已切分完成, 片段数: {segment_count}")

        # 音频识别 + 生成 GPT-SoVITS 训练列表
        if self.whisper.enabled and self.asr is not None:
            logger.info("正在进行音频识别......")
            output_audio_files = get_audio_files(self.config.output_dir, self.config.supported_formats)
            transcribe_results = batch_transcribe(self.asr, self.config.whisper, output_audio_files)
            # 生成 GPT-SoVITS 训练列表
            generate_sovits_list(self.config.sovits, transcribe_results, output_audio_files)
