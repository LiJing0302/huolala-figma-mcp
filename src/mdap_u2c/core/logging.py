# coding=utf-8
import os
import logging
import queue
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from typing import Optional

from mdap_u2c.config.path_config import PathConfig


class CustomFormatter(logging.Formatter):
    def format(self, record):
        """将日志堆栈换行符转义为 \\n，避免多行日志被拆散。"""
        formatted = super().format(record)
        return formatted.replace('\n', '\\n')

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created)
        if datefmt:
            s = dt.strftime(datefmt)
            return s[:-3]
        else:
            t = dt.strftime("%Y-%m-%d %H:%M:%S")
            s = "%s,%03d" % (t, record.msecs)
            return s


class LoggingApplication:
    """日志配置管理类 - 使用异步队列处理日志，不阻塞主线程"""
    _initialized = False  # 标记是否已初始化
    _queue_listener: Optional[QueueListener] = None  # 队列监听器
    
    @staticmethod
    def get_log_dir() -> str:
        """日志目录：项目根目录 runtime/logs。"""
        log_dir = PathConfig.get_runtime_dir() / "logs"
        os.makedirs(log_dir, exist_ok=True)
        return str(log_dir)
    
    @classmethod
    def _get_log_file_path(cls, file_name: str = "sys") -> str:
        log_dir = cls.get_log_dir()
        return f"{log_dir}/{file_name}.log"
    
    @classmethod
    def init(cls, file_name: str = "sys", log_level: Optional[str] = None):
        if cls._initialized:
            return

        formatter = CustomFormatter(
            datefmt='%Y-%m-%d %H:%M:%S.%f',
            fmt="###|||%(asctime)s|||%(levelname)s|||-|||-|||%(processName)s(%(threadName)s)|||-|||-|||%(name)s--->%(message)s"
        )

        # 设置根记录器和级别，同时情况已有处理器
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.handlers.clear()

        # 文件日志处理器
        file_handler = TimedRotatingFileHandler(
            filename=cls._get_log_file_path(file_name),
            when='D',          # 按天滚动
            interval=1,        # 每1天
            backupCount=10,    # 保留10天
            encoding='utf-8'
        )
        file_handler.suffix = "%Y-%m-%d.log"
        file_handler.setFormatter(formatter)

        # 控制台日志处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # 创建日志队列（使用无界对象）
        log_queue = queue.Queue(-1)
        root_logger.addHandler(QueueHandler(log_queue))

        cls._queue_listener = QueueListener(log_queue, file_handler, console_handler)
        cls._queue_listener.start()

        # 屏蔽框架内部的正常日志
        logging.getLogger("mcp").setLevel(logging.WARNING)

        cls._initialized = True
    
    @classmethod
    def shutdown(cls):
        """关闭日志系统，确保所有日志都被写入"""
        if cls._queue_listener is not None:
            cls._queue_listener.stop()
            cls._queue_listener = None
        cls._initialized = False

    @classmethod
    def is_initialized(cls) -> bool:
        """检查日志系统是否已初始化"""
        return cls._initialized


