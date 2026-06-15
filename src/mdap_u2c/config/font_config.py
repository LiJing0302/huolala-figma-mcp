"""
配置需要导出的字体列表。

字体文件放在 assets/fonts/ 下；仓库默认不包含字体文件（版权原因），
用户可按映射表自行放置，存在时才会被打包进 ZIP。
"""
from pathlib import Path

from mdap_u2c.config.path_config import PathConfig


class FontConfig:
    _FONT_MAP: dict[str, str] = {
      
    }

    @classmethod
    def get_font_file(cls, font_name):
        # 需要兼容 SFProDisplay 倾斜字体
        if font_name.startswith("SFProDisplay-"):
            font_name = font_name.replace("Italic", "")

        filename = cls._FONT_MAP.get(font_name)
        if not filename:
            return None

        font_path = Path(PathConfig.get_assets_dir()) / "fonts" / filename
        return filename if font_path.is_file() else None
