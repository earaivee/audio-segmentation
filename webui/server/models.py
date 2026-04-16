# webui/server/models.py
"""Pydantic 模型 - 映射 src/config/settings.py 中的配置类"""

from pydantic import BaseModel, Field
from typing import Optional, Tuple
from pathlib import Path


class VADConfigModel(BaseModel):
    threshold: float = 0.50
    min_silence_duration_ms: int = 720
    min_speech_duration_ms: int = 600
    speech_pad_ms: int = 200


class NormalizeConfigModel(BaseModel):
    enabled: bool = True
    method: str = "rms"
    target_rms: float = 0.15
    target_peak: float = 0.95
    clipping_threshold: float = 0.99


class FasterWhisperConfigModel(BaseModel):
    enabled: bool = True
    model: str = "medium"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 4
    language: Optional[str] = "zh"
    task: str = "transcribe"
    initial_prompt: Optional[str] = None


class GptSovitsConfigModel(BaseModel):
    enabled: bool = True
    speaker: str = "output"
    language: str = "ZH"
    output_path: str = "./resources/output.list"


class SettingConfigModel(BaseModel):
    input_dir: str = "./resources/input"
    output_dir: str = "./resources/output"
    supported_formats: list[str] = [".wav", ".mp3"]
    vad: VADConfigModel = Field(default_factory=VADConfigModel)
    normalize: NormalizeConfigModel = Field(default_factory=NormalizeConfigModel)
    whisper: FasterWhisperConfigModel = Field(default_factory=FasterWhisperConfigModel)
    sovits: GptSovitsConfigModel = Field(default_factory=GptSovitsConfigModel)


# --- 请求/响应模型 ---

class TaskStatusResponse(BaseModel):
    status: str  # idle, running, completed, error
    progress: float = 0.0
    message: str = ""


class AudioFileInfo(BaseModel):
    filename: str
    filepath: str
    duration_sec: float = 0.0
    text: str = ""
    parent_dir: str = ""


class MergeRequest(BaseModel):
    filepaths: list[str]
    output_filename: str = ""


class SplitRequest(BaseModel):
    filepath: str


class TranscribeRequest(BaseModel):
    filepath: str


class UpdateTextRequest(BaseModel):
    filepath: str
    text: str


class ExportListRequest(BaseModel):
    items: list[dict] = []


class RenameRequest(BaseModel):
    filepath: str
    new_name: str


class MoveRequest(BaseModel):
    filepath: str
    target_folder: str


class SplitAtTimesRequest(BaseModel):
    filepath: str
    times: list[float]
