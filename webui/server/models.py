# webui/server/models.py
"""Pydantic 模型 - 用于 API 请求/响应的数据校验与序列化
也是所有配置的单一数据源，settings.py 中的 dataclass 默认值从此处获取。
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Tuple
from pathlib import Path


class VADConfigModel(BaseModel):
    """Silero VAD 语音活动检测参数"""

    threshold: float = 0.52
    # VAD 语音检测灵敏度阈值，范围 0~1。值越低越敏感，容易切出短片段；值越高越严格，只保留确信的语音

    min_silence_duration_ms: int = 900
    # 片段之间最小静音时长（毫秒）。低于此值视为连续语音的一部分，不会在此处断开

    min_speech_duration_ms: int = 500
    # 最小语音片段时长（毫秒）。短于此值的片段会被丢弃，用于过滤误检测的噪声或杂音

    speech_pad_ms: int = 300
    # 在每个语音片段前后自动填充的静音时长（毫秒），使切出的音频片段不会在语音起始或结尾处被截断


class NormalizeConfigModel(BaseModel):
    """音频音量归一化参数"""

    enabled: bool = True
    # 是否启用音量归一化

    method: str = "rms"
    # 归一化方式：
    #   "rms"  - 基于均方根（RMS），按平均响度统一音量
    #   "peak" - 基于峰值，将所有片段的最高振幅对齐到同一水平

    target_rms: float = 0.15
    # RMS 归一化的目标均方根值（method="rms" 时生效）。值越大整体音量越大，推荐范围 0.10 ~ 0.30

    target_peak: float = 0.95
    # 峰值归一化的目标峰值（method="peak" 时生效）。通常设为 0.90 ~ 1.0，留一点余量避免削波失真

    clipping_threshold: float = 0.99
    # 削波（爆音）判定阈值，超过此值视为过载失真。用于分析音频时标记是否存在削波


class FasterWhisperConfigModel(BaseModel):
    """Faster-whisper 语音识别（ASR）参数"""

    enabled: bool = True
    # 是否启用 faster-whisper 语音识别

    model_size: str = "medium"
    # Whisper 模型规格：tiny / base / small / medium / large-v3。越大越准确但速度越慢、显存占用越高

    model_path: str = "./models/faster-whisper-medium"
    # 本地已下载的模型路径，优先使用此路径。若路径不存在或为空，则根据 model_size 自动下载

    device: str = "cpu"
    # 推理设备："cpu" 或 "cuda"。CUDA 可大幅提升速度，但需要 GPU 和对应驱动

    compute_type: str = "int8"
    # 计算精度："int8"（量化，速度快/精度略低）或 "float16"（GPU）/ "float32"。int8 适合 CPU，float16 适合 CUDA GPU

    language: str = "zh"
    # 识别语言代码："zh"（中文）、"en"（英文）、"ja"（日文）等。设为 None 可自动检测，但指定语言准确率更高

    beam_size: int = 5
    # 束搜索宽度。越大识别越准确但速度越慢，推荐 3~5，过小可能遗漏最优解码路径


class TrainingExportFormat(str, Enum):
    """训练列表导出格式枚举"""
    GPT_SOVITS = "gpt_sovits"        # {wav_path}|{speaker}|{language}|{text}
    VITS = "vits"                    # {wav_path}|{speaker}|{text}
    BERT_VITS2 = "bert_vits2"        # {wav_path}|{speaker}|{language}|{text}
    RVC = "rvc"                      # {wav_path}|{text}
    RVC_WAV_ONLY = "rvc_wav_only"    # {wav_path}
    INDEX_TTS = "index_tts"          # {wav_path}|{text}
    FISH_SPEECH = "fish_speech"      # {wav_path}\t{text}


class TrainingExportConfigModel(BaseModel):
    """训练数据导出参数，支持多种 TTS/VC 模型格式"""

    enabled: bool = True
    # 是否启用训练列表导出功能

    format_type: str = TrainingExportFormat.GPT_SOVITS.value
    # 导出格式：gpt_sovits / vits / bert_vits2 / rvc / rvc_wav_only / fish_speech

    speaker: str = "output"
    # 说话人名称，仅在格式需要 speaker 字段时生效（GPT-SoVITS / VITS / Bert-VITS2）

    language: str = "ZH"
    # 语言标签，仅在格式需要 language 字段时生效（GPT-SoVITS / Bert-VITS2）

    output_path: str = "./resources/output.list"
    # 训练列表文件的输出路径


class SettingConfigModel(BaseModel):
    """主配置类，聚合所有子配置"""

    input_dir: str = "./resources/input"
    # 源音频/视频输入目录，存放待处理的原始文件

    output_dir: str = "./resources/output"
    # 处理结果输出目录，存放切分后的片段和识别文本

    supported_formats: list[str] = [".wav", ".mp3"]
    # 系统支持的音频文件格式扩展名列表

    vad: VADConfigModel = Field(default_factory=VADConfigModel)
    # VAD 语音活动检测子配置

    normalize: NormalizeConfigModel = Field(default_factory=NormalizeConfigModel)
    # 音频音量归一化子配置

    faster_whisper: FasterWhisperConfigModel = Field(default_factory=FasterWhisperConfigModel)
    # faster-whisper 语音识别子配置

    sovits: TrainingExportConfigModel = Field(default_factory=TrainingExportConfigModel)
    # 训练数据导出子配置（支持 GPT-SoVITS / VITS / Bert-VITS2 / RVC / Fish Speech）


# --- 请求/响应模型 ---

class TaskStage(str, Enum):
    """任务执行阶段枚举"""

    PREPARING = "preparing"
    # 准备阶段：检查配置、加载模型、创建目录
    SEGMENTING = "segmenting"
    # 正在按 VAD 切分音频为独立语音片段
    TRANSCRIBING = "transcribing"
    # 正在使用 ASR 对切分后的片段进行语音识别
    INFERRING = "inferring"
    # 推理阶段（暂未实现）
    COMPLETED = "completed"
    # 全部任务执行完毕
    ERROR = "error"
    # 任务执行过程中发生错误


class TaskStatusResponse(BaseModel):
    """后台任务状态响应模型"""

    status: str
    # 任务运行状态："idle"（空闲）、"running"（运行中）、"completed"（已完成）、"error"（出错）

    stage: str = TaskStage.PREPARING.value
    # 当前执行阶段，对应 TaskStage 枚举值

    progress: float = 0.0
    # 任务进度，范围 0.0 ~ 100.0

    message: str = ""
    # 附加信息，用于显示给用户的状态提示或错误描述


class AudioFileInfo(BaseModel):
    """音频文件信息响应模型"""

    filename: str
    # 文件名（含扩展名）

    filepath: str
    # 文件绝对路径

    duration_sec: float = 0.0
    # 音频时长（秒）

    text: str = ""
    # ASR 语音识别结果文本

    parent_dir: str = ""
    # 所属子目录名称（相对于 output_dir）


class MergeRequest(BaseModel):
    """合并音频请求模型"""

    filepaths: list[str]
    # 待合并的音频文件路径列表

    output_filename: str = ""
    # 输出文件名（为空时自动生成）


class SplitRequest(BaseModel):
    """VAD 自动切分请求模型"""

    filepath: str
    # 待切分的音频文件路径


class TranscribeRequest(BaseModel):
    """语音识别请求模型"""

    filepath: str
    # 待识别的音频文件路径


class UpdateTextRequest(BaseModel):
    """手动更新识别文本请求模型"""

    filepath: str
    # 音频文件路径

    text: str
    # 更新后的识别文本内容


class ExportListRequest(BaseModel):
    """导出 GPT-SoVITS 训练列表请求模型"""

    items: list[dict] = []
    # 要导出的音频文件信息列表（空时使用全部文件）


class RenameRequest(BaseModel):
    """重命名文件请求模型"""

    filepath: str
    # 当前文件路径

    new_name: str
    # 新文件名（不含路径）


class MoveRequest(BaseModel):
    """移动文件请求模型"""

    filepath: str
    # 待移动的文件路径

    target_folder: str
    # 目标文件夹名称（相对于 output_dir）


class ConvertRequest(BaseModel):
    """音频格式转换请求模型"""

    filepath: str
    # 待转换的文件路径

    output_format: str = "wav"
    # 目标格式：wav / mp3 / flac / ogg / aac / m4a


class SplitAtTimesRequest(BaseModel):
    """按指定时间点手动切分请求模型"""

    filepath: str
    # 待切分的音频文件路径

    times: list[float]
    # 切分时间点列表（单位：秒）
