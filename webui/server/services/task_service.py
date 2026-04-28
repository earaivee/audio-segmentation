# webui/server/services/task_service.py
"""任务执行服务 - 封装 AudioSegmentationApp 在后台线程中运行"""

import gc
import logging
import threading
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Set

from silero_vad import load_silero_vad, read_audio
from ..config.settings import SettingConfig
from ..models import TaskStage
from .normalizer import AudioNormalizer
from .segmenter import AudioSegmenter
from ..utils.asr_utils import batch_transcribe, load_faster_whisper_model, transcribe_audio
from ..utils.file_utils import get_audio_files, get_unique_files, get_file_count, rename_folder
from ..utils.time_utils import get_timestamp
from ..config.errors import FileError, AudioError
from .audio_service import set_text_for_audio, load_texts_db, export_training_list


class WebSocketLogHandler(logging.Handler):
    # 将日志实时推送到 WebSocket 连接的处理器

    def __init__(self):
        super().__init__()
        self.connections: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task_service = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        # 设置事件循环引用
        self._loop = loop

    def set_task_service(self, ts):
        # 设置任务服务引用
        self._task_service = ts

    def emit(self, record):
        # 发送日志消息到 WebSocket 和任务服务缓存
        msg = self.format(record)
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


ws_log_handler = WebSocketLogHandler()
ws_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))


class TaskService:

    def __init__(self):
        # 初始化任务服务，设置状态和运行标记
        self.status = "idle"
        self.stage = TaskStage.PREPARING.value
        self.progress = 0.0
        self.message = ""
        self.logs: List[str] = []
        self._max_logs = 1000
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def is_running(self) -> bool:
        # 检查任务是否正在运行
        return self.status == "running"

    def start(self, config: SettingConfig):
        # 启动后台任务线程，执行音频切分全流程
        if self.is_running():
            return False
        self._stop_event.clear()
        self.status = "running"
        self.stage = TaskStage.PREPARING.value
        self.progress = 0.0
        self.message = "任务启动中..."
        self.logs = []
        self._thread = threading.Thread(target=self._run, args=(config,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        # 请求停止当前运行中的任务
        if self.is_running():
            self._stop_event.set()
            self.stage = TaskStage.ERROR.value
            self.status = "idle"
            self.message = "任务已停止"

    def _set_stage(self, stage: TaskStage):
        # 设置当前任务阶段
        self.stage = stage.value

    def add_log(self, msg: str):
        # 添加日志到缓存列表，超限时自动裁剪
        self.logs.append(msg)
        if len(self.logs) > self._max_logs:
            self.logs = self.logs[-self._max_logs:]

    def _broadcast_progress(self, progress: float, message: str = ""):
        # 通过 WebSocket 广播进度更新（含当前阶段）
        self.progress = progress
        if message:
            self.message = message
        if ws_log_handler._loop and ws_log_handler.connections:
            for ws in list(ws_log_handler.connections):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({
                            "type": "progress",
                            "stage": self.stage,
                            "progress": progress,
                            "message": message,
                            "status": self.status,
                        }),
                        ws_log_handler._loop
                    )
                except Exception:
                    ws_log_handler.connections.discard(ws)

    def _smooth_progress(self, target: float, message: str = "", step: float = 1.0, delay: float = 0.3):
        # 平滑过渡到目标进度，每次增加 step%，间隔 delay 秒
        while self.progress < target:
            next_val = min(self.progress + step, target)
            self._broadcast_progress(round(next_val, 1), message)
            if next_val >= target:
                break
            time.sleep(delay)

    def _run(self, config: SettingConfig):
        # 后台线程执行体：加载模型、遍历文件切分、ASR 识别、生成训练列表
        logger = logging.getLogger("task_service")
        logger.addHandler(ws_log_handler)
        logger.setLevel(logging.INFO)

        try:
            config.output_dir.mkdir(parents=True, exist_ok=True)
            if not config.input_dir.exists():
                config.input_dir.mkdir(parents=True, exist_ok=True)

            if get_file_count(config.output_dir, config.supported_formats) > 0:
                timestamp = get_timestamp()
                new_name = f"{config.output_dir.stem}_bak_{timestamp}"
                rename_folder(config.output_dir, new_name)
                logger.info(f"输出目录已存在，备份目录为: {new_name}")

            audio_files = get_unique_files(
                get_audio_files(config.input_dir, config.supported_formats)
            )
            if not audio_files:
                raise FileError(f"{config.input_dir} 无音频源文件")

            total = len(audio_files)
            logger.info(f"共找到 {total} 个音频文件")

            # ===== 阶段 1: 准备阶段 (0-25%) =====
            self._set_stage(TaskStage.PREPARING)

            self._smooth_progress(8.0, "正在初始化环境...")
            logger.info("正在初始化环境...")

            self._smooth_progress(15.0, "正在加载 Silero VAD 模型...")
            logger.info("正在加载 Silero VAD 模型...")
            vad_model = load_silero_vad()

            self._smooth_progress(22.0, "正在加载 ASR 模型...")
            logger.info("正在加载 ASR 模型...")
            fw_model = load_faster_whisper_model(config.faster_whisper)

            self._smooth_progress(25.0, "初始化完成，准备切分音频...")
            logger.info("模型加载完成")

            normalizer = AudioNormalizer(config.normalize)
            segmenter = AudioSegmenter(config.vad, normalizer)

            # ===== 阶段 2: 切分音频 (25-50%) =====
            self._set_stage(TaskStage.SEGMENTING)

            # 先做一次 VAD 检测，统计总片段数用于进度计算
            all_segments = []  # [(audio_file, audio, sr, timestamps), ...]
            total_segments = 0
            for idx, audio_file in enumerate(audio_files):
                if self._stop_event.is_set():
                    logger.info("任务被用户停止")
                    self.status = "idle"
                    return

                file_progress = 25.0 + (idx / total) * 12.5
                self._smooth_progress(file_progress, f"[VAD检测 {idx + 1}/{total}] {audio_file.name}")
                logger.info(f"正在检测: {audio_file.name}")

                audio = read_audio(str(audio_file))
                sr = 16000
                timestamps = segmenter.detect_speech_segments(audio, sr, vad_model)
                if not timestamps:
                    logger.warning(f"未检测到文件 {audio_file.name} 的语音")
                    all_segments.append((audio_file, audio, sr, []))
                    continue

                all_segments.append((audio_file, audio, sr, timestamps))
                total_segments += len(timestamps)

            seg_processed = 0
            for audio_file, audio, sr, timestamps in all_segments:
                if self._stop_event.is_set():
                    logger.info("任务被用户停止")
                    self.status = "idle"
                    return

                if not timestamps:
                    continue

                output_dir = config.output_dir / audio_file.stem
                output_dir.mkdir(parents=True, exist_ok=True)

                for i, ts in enumerate(timestamps):
                    seg_processed += 1
                    overall_progress = 37.5 + (seg_processed / total_segments) * 12.5
                    self._smooth_progress(
                        overall_progress,
                        f"[切分 {seg_processed}/{total_segments}] {audio_file.name} 片段 {i + 1}/{len(timestamps)}"
                    )

                    segment, info = segmenter.extract_and_process_segment(
                        audio, ts['start'], ts['end'], sr
                    )
                    output_path = output_dir / f"{audio_file.stem}_seg_{i + 1:04d}.wav"
                    segmenter.save_segment(segment, output_path, sr)

                logger.info(f"音频 {audio_file.name} 已切分完成, 片段数: {len(timestamps)}")

            self._smooth_progress(50.0, "切分完成，开始识别...")

            # ===== 阶段 3: 识别音频 (50-75%) =====
            self._set_stage(TaskStage.TRANSCRIBING)
            if config.faster_whisper.enabled and fw_model is not None:
                output_audio_files = get_audio_files(config.output_dir, config.supported_formats)
                asr_total = len(output_audio_files)
                logger.info(f"共 {asr_total} 个音频片段需要识别")

                for idx, audio_path in enumerate(output_audio_files):
                    if self._stop_event.is_set():
                        logger.info("任务被用户停止")
                        self.status = "idle"
                        return

                    asr_progress = 53.0 + ((idx + 1) / asr_total) * 19.0
                    self._smooth_progress(
                        asr_progress,
                        f"[识别 {idx + 1}/{asr_total}] {audio_path.name}"
                    )
                    logger.info(f"正在识别: {audio_path.name}")

                    text = transcribe_audio(fw_model, config.faster_whisper, audio_path)
                    set_text_for_audio(config.output_dir, audio_path.stem, text)
                    logger.info(f"识别完成: {audio_path.name}")

                self._smooth_progress(73.0, "正在生成训练列表...")
                logger.info("正在生成训练列表...")
                texts_db = load_texts_db(config.output_dir)
                audio_items = [{"filepath": str(f), "text": texts_db.get(f.stem, "")} for f in output_audio_files]
                export_training_list(config, audio_items)
                self._smooth_progress(75.0, "训练列表生成完成")

            # ===== 阶段 4: 推理阶段 (75-100%) =====
            self._set_stage(TaskStage.INFERRING)
            self._smooth_progress(85.0, "推理阶段（待实现）...")
            logger.info("推理阶段（待实现）")

            self._set_stage(TaskStage.COMPLETED)
            self._smooth_progress(100.0, "任务全部完成!")
            logger.info("全部任务完成!")
            self.status = "completed"

            del vad_model
            if fw_model:
                del fw_model
            gc.collect()

        except Exception as e:
            logger.error(f"任务执行出错: {e}")
            self._set_stage(TaskStage.ERROR)
            self.status = "error"
            self.message = str(e)
            self._broadcast_progress(self.progress, f"错误: {e}")
        finally:
            logger.removeHandler(ws_log_handler)


task_service = TaskService()
ws_log_handler.set_task_service(task_service)
