import sys
from pathlib import Path

from loguru import logger

LOG_FORMAT = (
    "<level>{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}</level>"
)
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}"


def setup_logging(log_file: Path | str = "twitter_monitor.log"):
    logger.remove()

    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format=FILE_FORMAT,
        colorize=False,
    )

    logger.add(
        sys.stderr,
        level="INFO",
        format=LOG_FORMAT,
        colorize=True,
    )

    return logger
