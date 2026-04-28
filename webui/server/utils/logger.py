# webui/server/logger.py

import logging
import sys


def setup_logger(name: str = __name__, log_file: str = "webui/server/segment.log") -> logging.Logger:
    # 配置并返回指定名称的日志记录器（控制台 + 文件输出）
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger