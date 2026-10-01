"""日志工具：统一日志格式，同时输出到控制台和文件
全项目统一用 `from app.utils.logger import logger`，不要各自 print。"""
import logging
import sys
from pathlib import Path

from app.config import settings, PROJECT_ROOT

# 日志目录（启动时自动创建，parents=True 表示父目录不存在也一并建）
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式：时间 | 级别 | 模块名 | 内容
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "smart_agent") -> logging.Logger:
    """获取配置好的 logger（单例模式，重复调用不会重复添加 handler）"""
    logger = logging.getLogger(name)

    # 避免重复添加 handler——否则同一行日志会被打印 N 遍
    if logger.handlers:
        return logger

    # getattr(logging, "INFO") 等价于 logging.INFO；第二个参数是默认值
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    # 文件输出（按天命名）
    from datetime import datetime
    log_file = LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    return logger


# 模块级单例：import 本模块时就建好，全项目直接 `from app.utils.logger import logger`
logger = get_logger()
