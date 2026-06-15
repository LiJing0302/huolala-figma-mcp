"""
核心框架包
"""
from .cli import CliArgs
from .type import SingletonClass
from .logging import LoggingApplication

__all__ = [
    "CliArgs",
    "SingletonClass",
    "LoggingApplication",
]

