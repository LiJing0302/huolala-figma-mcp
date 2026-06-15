"""
转换器基类
定义转换器的通用工具方法
"""
from typing import Dict, Any, Optional
from mdap_u2c.models.dsl_model import Style
from mdap_u2c.utils import StyleValueUtils


class BaseConverter:
    """转换器基类，提供通用的辅助方法"""
    @staticmethod
    def style_merge(target_style: Style, source_style: Style):
        """
        合并样式信息(把source_style的样式合并到target_style中)
        Args:
            target_style: 目标样式对象（会被修改）
            source_style: 源样式对象（提供要合并的样式）
        """
        if source_style is None:
            return

        if target_style is None:
            target_style = Style()
        
        for field_name in source_style.__struct_fields__:
            source_value = getattr(source_style, field_name, None)
            if source_value is not None:
                setattr(target_style, field_name, source_value)

    @staticmethod
    
    @staticmethod
    def convert_color(color: Dict[str, Any], opacity: Optional[float] = None) -> str:
        """
        转换颜色
        Figma 颜色格式: {r: 0-1, g: 0-1, b: 0-1, a: 0-1}
        输出格式: "rgba(r, g, b, a)"
        """
        r = int(round(color.get("r", 0) * 255))
        g = int(round(color.get("g", 0) * 255))
        b = int(round(color.get("b", 0) * 255))

        if opacity is not None:
            a = opacity
        else:
            a = color.get("a", 1)

        return f"rgba({r},{g},{b},{StyleValueUtils.format_number(a)})"

