# webui/server/services/task_service.py
"""任务执行服务 - 封装 AudioSegmentationApp 在后台线程中运行"""

import gc
import logging
import threading
import asyncio
from pathlib import Path
from typing import Optional, List, Set

from silero_vad import load_silero_vad, read_audio
from src.config.settings import SettingConfig
from src.processors.normalizer import AudioNormalizer
from src.processors.segmenter import AudioSegmenter
from src.utils.asr_utils import batch_transcribe, load_asr_model
from src.utils.file_utils import get_audio_files, get_unique_files, get_file_count, rename_folder
from src.utils.time_utils import get_timestamp
from src.config.errors import FileError, AudioError


class WebSocketLogHandler(logging.Handler):

    def __init__(self):
        super().__init__()
        self.connections: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task_service = None  # 引用 TaskService 实例

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_task_service(self, ts):
        self._task_service = ts

    def emit(self, record):
        msg = self.format(record)
        # 缓存日志到 TaskService
        if self._task_service:
            self._task_service.add_log(msg)
        if self._loop and self.connections:
            for ws in list(self.connections):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"type": "log", "message": msg}),
                        self._loop
                    )
                except Exception:
                    self.connections.discard(ws)


# 全局日志 handler
ws_log_handler = WebSocketLogHandler()
ws_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))


class TaskService:
    
    def __init__(self):
        self.status = "idle"  # idle, running, completed, error
        self.progress = 0.0
        self.message = ""
        self.logs: List[str] = []  # 缓存日志历史
        self._max_logs = 1000
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def is_running(self) -> bool:
        return self.status == "running"

    def start(self, config: SettingConfig):
        if self.is_running():
            return False
        self._stop_event.clear()
        self.status = "running"
        self.progress = 0.0
        self.message = "任务启动中..."
        self.logs = []  # 新任务清空日志
        self._thread = threading.Thread(target=self._run, args=(config,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if self.is_running():
            self._stop_event.set()
            self.status = "idle"
            self.message = "任务已停止"

    def add_log(self, msg: str):
        """添加日志到缓存"""
        self.logs.append(msg)
        if len(self.logs) > self._max_logs:
            self.logs = self.logs[-self._max_logs:]

    def _broadcast_progress(self, progress: float, message: str = ""):
        """广播进度到 WebSocket"""
        self.progress = progress
        if message:
            self.message = message
        if ws_log_handler._loop and ws_log_handler.connections:
            for ws in list(ws_log_handler.connections):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({
                            "type": "progress",
                            "progress": progress,
                            "message": message,
                            "status": self.status,
                        }),
                        ws_log_handler._loop
                    )
                except Exception:
                    ws_log_handler.connections.discard(ws)

    def _run(self, config: SettingConfig):
        """后台线程执行任务"""
        logger = logging.getLogger("task_service")
        logger.addHandler(ws_log_handler)
        logger.setLevel(logging.INFO)

        try:
            # 创建输出目录
            config.output_dir.mkdir(parents=True, exist_ok=True)
            if not config.input_dir.exists():
                config.input_dir.mkdir(parents=True, exist_ok=True)

            if get_file_count(config.output_dir, config.supported_formats) > 0:
                timestamp = get_timestamp()
                new_name = f"{config.output_dir.stem}_bak_{timestamp}"
                rename_folder(config.output_dir, new_name)
                logger.info(f"输出目录已存在，备份目录为: {new_name}")

            # 获取音频文件
            audio_files = get_unique_files(
                get_audio_files(config.input_dir, config.supported_formats)
            )
            if not audio_files:
                raise FileError(f"{config.input_dir} 无音频源文件")

            total = len(audio_files)
            logger.info(f"共找到 {total} 个音频文件")

            # 加载模型
            self._broadcast_progress(0.0, "正在加载 Silero VAD 模型...")
            logger.info("正在加载 Silero VAD 模型...")
            vad_model = load_silero_vad()

            self._broadcast_progress(0.05, "正在加载 ASR 模型...")
            logger.info("正在加载 ASR 模型...")
            asr_model = load_asr_model(config.whisper)

            self._broadcast_progress(0.1, "模型加载完成，准备开始处理...")
            logger.info("模型加载完成")

            normalizer = AudioNormalizer(config.normalize)
            segmenter = AudioSegmenter(config.vad, normalizer)

            # 切分 (10% - 20%)
            for idx, audio_file in enumerate(audio_files):
                if self._stop_event.is_set():
                    logger.info("任务被用户停止")
                    self.status = "idle"
                    return

                # 切分进度: 10% -> 20%
                progress = 0.1 + ((idx + 1) / total) * 0.1
                self._broadcast_progress(progress, f"正在切分: {audio_file.name} ({idx + 1}/{total})")
                logger.info(f"正在处理: {audio_file.name}")

                audio = read_audio(str(audio_file))
                sr = 16000
                timestamps = segmenter.detect_speech_segments(audio, sr, vad_model)
                if not timestamps:
                    logger.warning(f"未检测到文件 {audio_file.name} 的语音")
                    continue

                # 时长限制已停用，由前端筛选替代
                # timestamps = segmenter.apply_duration_limit(
                #     timestamps, audio, sr, vad_model,
                #     config.segmenter.enabled_double_split, config.segmenter.factor
                # )

                output_dir = config.output_dir / audio_file.stem
                output_dir.mkdir(parents=True, exist_ok=True)

                for i, ts in enumerate(timestamps, 1):
                    segment, info = segmenter.extract_and_process_segment(
                        audio, ts['start'], ts['end'], sr
                    )
                    output_path = output_dir / f"{audio_file.stem}_seg_{i:04d}.wav"
                    segmenter.save_segment(segment, output_path, sr)

                logger.info(f"音频 {audio_file.name} 已切分完成, 片段数: {len(timestamps)}")

            # ASR (20% - 95%)
            if config.whisper.enabled and asr_model is not None:
                self._broadcast_progress(0.2, "正在进行音频识别...")
                logger.info("正在进行音频识别...")
                output_audio_files = get_audio_files(config.output_dir, config.supported_formats)
                asr_total = len(output_audio_files)

                from src.utils.asr_utils import transcribe_audio
                from webui.server.services.audio_service import set_text_for_audio, export_training_list

                for idx, audio_path in enumerate(output_audio_files):
                    if self._stop_event.is_set():
                        logger.info("任务被用户停止")
                        self.status = "idle"
                        return
                    # ASR进度: 20% -> 95%
                    progress = 0.2 + ((idx + 1) / max(asr_total, 1)) * 0.75
                    self._broadcast_progress(progress, f"识别中: {audio_path.name} ({idx + 1}/{asr_total})")
                    text = transcribe_audio(asr_model, config.whisper, audio_path)

                    # 每识别一条就立即写入 texts.json
                    set_text_for_audio(config.output_dir, audio_path.stem, text)

                    logger.info(f"识别完成: {audio_path.name} -> {text}")

                # 生成 GPT-SoVITS 列表
                self._broadcast_progress(0.95, "正在生成训练列表...")
                logger.info("正在生成训练列表...")
                from webui.server.services.audio_service import load_texts_db
                texts_db = load_texts_db(config.output_dir)
                audio_items = [{"filepath": str(f), "text": texts_db.get(f.stem, "")} for f in output_audio_files]
                export_training_list(config, audio_items)

            self._broadcast_progress(1.0, "任务完成")
            logger.info("全部任务完成!")
            self.status = "completed"

            # 清理
            del vad_model
            if asr_model:
                del asr_model
            gc.collect()

        except Exception as e:
            logger.error(f"任务执行出错: {e}")
            self.status = "error"
            self.message = str(e)
            self._broadcast_progress(self.progress, f"错误: {e}")
        finally:
            logger.removeHandler(ws_log_handler)


# 全局任务服务单例
task_service = TaskService()
ws_log_handler.set_task_service(task_service)
