"""从项目根目录加载 .env 到 os.environ（不覆盖已存在的系统环境变量）。"""
from __future__ import annotations

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)
_loaded = False


def _find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    env_file = _find_project_root() / ".env"
    if not env_file.is_file():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        _logger.debug("Loaded environment from %s", env_file)
    except ImportError:
        _logger.warning("python-dotenv 未安装，跳过 .env 加载")
