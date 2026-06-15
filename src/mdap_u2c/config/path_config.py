from pathlib import Path


def find_project_root() -> Path:
    """从当前模块向上查找含 pyproject.toml 的项目根目录。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


class PathConfig:
    @staticmethod
    def get_root_dir() -> Path:
        return find_project_root()

    @staticmethod
    def get_runtime_dir():
        return PathConfig.get_root_dir() / "runtime"

    @staticmethod
    def get_temp_dir():
        return f"{PathConfig.get_runtime_dir()}/temp"

    @staticmethod
    def get_assets_dir():
        return f"{PathConfig.get_root_dir()}/assets"
