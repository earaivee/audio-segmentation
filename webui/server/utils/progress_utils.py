# webui/server/progress_utils.py

from alive_progress import alive_bar


def progressBar(total):
    # 创建标准进度条（用于 CLI 模式）
    return alive_bar(
        total=total,
        manual=False,
        force_tty=True,
        stats=True,
        elapsed=True,
    )


def customProgressBar(total, manual=False, force_tty=True, status=True, elapsed=False):
    # 创建自定义进度条（支持手动模式和统计信息开关）
    return alive_bar(
        total=total,
        manual=manual,
        force_tty=force_tty,
        stats=status,
        elapsed=elapsed,
    )