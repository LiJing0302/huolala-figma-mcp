import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BaseConfig:
    APP_ID: str = "huolala-figma-mcp"
    HOST: str = "0.0.0.0"
    PORT: int = 10001

    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "runtime/logs"


def get_env_config(port: Optional[int]) -> BaseConfig:
    config = BaseConfig()
    config.PORT = port or config.PORT
    _override_from_env(config)
    return config


def _override_from_env(config: BaseConfig) -> None:
    port = os.getenv("PORT")
    if port:
        try:
            config.PORT = int(port)
        except ValueError:
            pass

    log_level = os.getenv("LOG_LEVEL")
    if log_level:
        config.LOG_LEVEL = log_level


__all__ = [
    "BaseConfig",
    "get_env_config",
]
