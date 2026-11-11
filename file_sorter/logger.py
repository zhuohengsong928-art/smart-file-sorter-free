"""日志模块：双通道日志，完整记录运行轨迹。

特性：
  - 控制台输出：WARNING 及以上级别，醒目着色
  - 文件日志：DEBUG 级别，完整操作记录 → logs/sorter_YYYYMMDD_HHMMSS.log
  - 自动创建日志目录
  - 结构化格式：[时间] [级别] [模块] 消息
  - 模块级 logger 获取函数，各模块零配置使用
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 日志格式
CONSOLE_FMT = "%(asctime)s  %(levelname)-7s  %(message)s"
CONSOLE_DATE = "%H:%M:%S"

FILE_FMT = "%(asctime)s  %(levelname)-7s  [%(module)s]  %(message)s"
FILE_DATE = "%Y-%m-%d %H:%M:%S"

# 包级 logger
_logger: Optional[logging.Logger] = None
_log_file_path: Optional[str] = None


def init_logger(
    log_dir: Optional[str] = None,
    verbose: bool = False,
) -> logging.Logger:
    """初始化日志系统（全局单次调用）。

    Args:
        log_dir: 日志文件目录，默认当前目录下的 logs/
        verbose: True 时控制台也输出 DEBUG 级别
    """
    global _logger, _log_file_path

    if _logger is not None:
        return _logger

    _logger = logging.getLogger("file_sorter")
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    # === 控制台 handler ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_level = logging.DEBUG if verbose else logging.INFO
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FMT, CONSOLE_DATE))

    class ConsoleColorFormatter(logging.Formatter):
        """控制台着色：WARNING=黄 ERROR=红。"""

        COLORS = {
            logging.WARNING: "\033[33m",
            logging.ERROR: "\033[31m",
            logging.CRITICAL: "\033[1;31m",
        }
        RESET = "\033[0m"

        def format(self, record):
            msg = super().format(record)
            color = self.COLORS.get(record.levelno)
            if color:
                msg = f"{color}{msg}{self.RESET}"
            # 处理 Windows GBK 终端 emoji 编码问题
            return msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

    console_handler.setFormatter(ConsoleColorFormatter(CONSOLE_FMT, CONSOLE_DATE))
    _logger.addHandler(console_handler)

    # === 文件 handler ===
    if log_dir is None:
        log_dir = str(Path.cwd() / "logs")
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file_path = os.path.join(log_dir, f"sorter_{timestamp}.log")

    file_handler = logging.FileHandler(_log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FMT, FILE_DATE))
    _logger.addHandler(file_handler)

    _logger.debug("日志系统初始化完成")
    _logger.debug("日志文件: %s", _log_file_path)

    return _logger


def get_logger() -> logging.Logger:
    """获取模块级 logger（各模块调用此函数）。"""
    global _logger
    if _logger is None:
        # fallback：未显式初始化时自动初始化
        return init_logger()
    return _logger


def get_log_file_path() -> Optional[str]:
    """返回当前日志文件的完整路径。"""
    return _log_file_path
