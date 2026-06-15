from typing import Dict, Any, Optional, List, Union
from mdap_u2c.models import dsl_model
from mdap_u2c.enums import dsl_enum
from mdap_u2c.figma.check import NodeBoxUtils
from mdap_u2c.utils import StyleValueUtils


class TextStyleConverter:
    """文本样式转换器"""

    @classmethod
    def get_style_with_node(cls, style: dsl_model.Style, node: Dict[str, Any], parent_component: Optional[dsl_model.AbstractComponent] = None) -> dsl_model.Style:
        figma_style = node.get("style", {})
        font_size = cls._resolve_font_size(figma_style.get("fontSize"))
        cls.get_style_with_style(style, figma_style)
        cls._resolve_text_overflow(style, figma_style, font_size, node)
        style.color = cls._resolve_text_color(node.get("fills", []))

        return style

    @classmethod
    def get_style_with_style(cls, style: dsl_model.Style, figma_style: Dict[str, Any]) -> dsl_model.Style:
        font_size = cls._resolve_font_size(figma_style.get("fontSize"))
        style.font_size = StyleValueUtils.format_value_with_unit(font_size)

        style.line_height = cls._resolve_line_height(figma_style, font_size)
        style.font_weight = cls._resolve_font_weight(figma_style.get("fontWeight"))
        style.font_family = cls._resolve_font_family(figma_style.get("fontPostScriptName"), figma_style.get("fontFamily"))
        style.letter_spacing = cls._resolve_letter_spacing(figma_style.get("letterSpacing"))
        style.text_decoration = cls._resolve_text_decoration(figma_style.get("textDecoration"))
        style.color = cls._resolve_text_color(figma_style.get("fills"))
        style.text_align = cls._resolve_text_align(figma_style.get("textAlignHorizontal"))
        style.vertical_align = cls._resolve_vertical_align(figma_style.get("textAlignVertical"))
        style.text_indent = cls._resolve_text_indent(figma_style.get("paragraphIndent"))

        italic = figma_style.get("italic", False)
        if italic:
            style.font_style = "italic"

        return style

    @staticmethod
    def _resolve_text_overflow(style: dsl_model.Style, figma_style: Dict[str, Any], font_size: float, node: Dict[str, Any]):
        # 处理是否需要换行和溢出显示...支持
        if figma_style.get("textTruncation", "DISABLED") != "ENDING":
            return

        max_lines = figma_style.get("maxLines", None)
        box_width = NodeBoxUtils.get_node_width_use_bounding(node.get("absoluteBoundingBox"))
        render_height = NodeBoxUtils.get_node_height_use_bounding(node.get("absoluteRenderBounds"))
        width_value = StyleValueUtils.format_value_with_unit(box_width)
        line_render = int(render_height / font_size)
        show_line = 1
        if max_lines and max_lines > 1:
            show_line = max_lines
        elif line_render > 1:
            show_line = line_render

        if show_line > 1:
            style.display = "-webkit-box"
            style.max_width = width_value
            style.overflow = "hidden"
            style.text_overflow = "ellipsis"
            style.white_space = "normal"
            style.webkit_line_clamp = show_line
            style.webkit_box_orient = "vertical"
        else:
            style.display = "inline-block"
            style.max_width = width_value
            style.text_overflow = "ellipsis"
            style.overflow = "hidden"
            style.white_space = "nowrap"

    @staticmethod
    def _resolve_text_indent(paragraph_indent: Optional[int]) -> Optional[str]:
        if paragraph_indent:
            return StyleValueUtils.format_value_with_unit(paragraph_indent)

    @staticmethod
    def _resolve_letter_spacing(letter_spacing: Optional[float]) -> Optional[str]:
        if letter_spacing:
            return StyleValueUtils.format_value_with_unit(letter_spacing)

    @staticmethod
    def _resolve_font_weight(font_weight: Optional[int]) -> Optional[int]:
        if font_weight:
            return int(font_weight)

    @staticmethod
    def _resolve_font_size(value: Optional[float]) -> Optional[float]:
        if not value:
            return

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if value.is_integer():
                return int(value)

            return float(f"{value:.2f}")

    @staticmethod
    def _resolve_font_family(font_post_script_name: Optional[str], font_family: Optional[str]) -> Optional[str]:
        if font_post_script_name:
            return font_post_script_name
        elif font_family:
            return font_family

    @staticmethod
    def _resolve_line_height(text_style: Dict[str, Any], font_size: float) -> Optional[Union[str, float]]:
        """转换行高"""
        unit = text_style.get("lineHeightUnit")
        px_value = text_style.get("lineHeightPx", None)
        if unit == "PIXELS" and px_value:
            return StyleValueUtils.format_value_with_unit(px_value)
        elif unit == "FONT_SIZE_%":
            value = text_style.get("lineHeightPercentFontSize", None)
            if value:
                return StyleValueUtils.format_value_with_unit(value, dsl_enum.StyleUnit.PERCENT)
        elif unit == "INTRINSIC_%" and px_value and font_size:
            return float(f"{(px_value / font_size):.2f}")

    @staticmethod
    def _resolve_text_align(value: Optional[str]) -> Optional[str]:
        """映射文本对齐方式"""
        if not value:
            return None

        if value == "LEFT":
            return None

        align_map = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFIED": "justify"}
        return align_map.get(value)

    @staticmethod
    def _resolve_vertical_align(value: Optional[str]) -> Optional[str]:
        """垂直对齐方式"""
        if not value:
            return None

        if value == "TOP":
            return None

        align_map = {"TOP": "top", "CENTER": "middle", "BOTTOM": "bottom"}
        return align_map.get(value)

    @staticmethod
    def _resolve_text_decoration(figma_decoration: Optional[str]) -> Optional[str]:
        """映射文本装饰"""
        if not figma_decoration or figma_decoration == "NONE":
            return None
        decoration_map = {"UNDERLINE": "underline", "STRIKETHROUGH": "line-through"}
        return decoration_map.get(figma_decoration)

    @staticmethod
    def _resolve_text_color(fills: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """文本颜色转化：优先取可见的纯色(SOLID)，其次支持线性渐变(GRADIENT_LINEAR)。"""
        if not fills:
            return None

        from .base import BaseConverter
        from .gradient_color_resolver import GradientColorResolver

        fills = fills[::-1]
        for fill in fills:
            if not fill.get("visible", True):
                continue
            fill_type = fill.get("type")
            if fill_type == "SOLID":
                return BaseConverter.convert_color(fill.get("color", {}), fill.get("opacity"))
            if fill_type == "GRADIENT_LINEAR":
                gradient = GradientColorResolver(fill, "GRADIENT_LINEAR")
                if not gradient.is_invisible():
                    value = gradient.get_value()
                    if value:
                        return value
        return None
