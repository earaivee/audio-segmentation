# webui/server/config/errors.py

from dataclasses import dataclass
from typing import Optional


@dataclass
class BasesError(Exception):
    # 自定义异常基类
    def __init__(self, message: Optional[str] = None):
        self.message = message or self.default_message
        super().__init__(self.message)

    @property
    def default_message(self) -> str:
        return "发生错误"


class AudioError(BasesError):
    # 音频处理失败异常
    @property
    def default_message(self) -> str:
        return "音频处理失败"


class FileError(BasesError):
    # 文件操作失败异常
    @property
    def default_message(self) -> str:
        return "文件操作失败"


class AsrError(BasesError):
    # 音频识别失败异常
    @property
    def default_message(self) -> str:
        return "音频识别失败"


class CaseError(BasesError):
    # 异常的条件分支异常
    @property
    def default_message(self) -> str:
        return "异常的条件分支"


class NotEnableError(BasesError):
    # 功能未启用异常
    @property
    def default_message(self) -> str:
        return "未启用相应的功能"