"""
配置模块

定义应用配置值和设置项
注意：框架层的初始化代码（如 CLI、日志）已移至 core/ 包
"""

from .app_config import AppConfig

__all__ = [
    "AppConfig",
]
