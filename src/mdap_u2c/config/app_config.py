import os

from mdap_u2c.core import CliArgs, SingletonClass
from mdap_u2c.config.env_config import get_env_config

_DEFAULT_APP_BASE_URL = "http://localhost:{PORT}"


class AppConfig(metaclass=SingletonClass):

    def __init__(self):
        cli_args = CliArgs.get_instance()
        self.CONFIG = get_env_config(port=cli_args.port)

    @staticmethod
    def get_instance():
        return AppConfig()

    @staticmethod
    def get_public_app_base_url() -> str:
        """对外可访问的服务根 URL（Skills 下载、ZIP 链接等），由 MDAP_APP_BASE_URL 配置。"""
        cfg = AppConfig.get_instance().CONFIG
        template = os.environ.get("MDAP_APP_BASE_URL", _DEFAULT_APP_BASE_URL).strip()
        if not template:
            template = _DEFAULT_APP_BASE_URL
        url = template.replace("{PORT}", str(cfg.PORT))
        return url.rstrip("/")

    def __str__(self):
        attrs = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        attrs_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
        return f"{self.__class__.__name__}({attrs_str})"

    def __repr__(self):
        return self.__str__()
