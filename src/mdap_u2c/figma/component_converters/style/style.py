"""
样式转换器
负责将 Figma 节点的通用样式信息转换为 DSL Style 对象
"""
from typing import Dict, Any

from mdap_u2c.models import dsl_model
from mdap_u2c.enums import dsl_enum, figma_enum
from .base import BaseConverter
from mdap_u2c.utils import StyleValueUtils
from .color_parse_resolver import ColorParseResolver


class StyleConverter(BaseConverter):
    """样式转换器"""
    _component_type: dsl_enum.ComponentType
    _node_type: str
    _node: Dict[str, Any]
    _style: dsl_model.Style

    def set_data(self, component_type: dsl_enum.ComponentType, node: Dict[str, Any]):
        self._style = dsl_model.Style()
        self._component_type = component_type
        self._node = node
        self._node_type = node.get("type")
        return self

    def get_common_style(self) -> dsl_model.Style:
        if self._component_type == dsl_enum.ComponentType.IMAGE:
            return self._style

        if self._component_type == dsl_enum.ComponentType.CONTAINER:
            self._handle_background_style()     # 背景色和渐变
            self._handle_border_style()         # 边框
            self._handle_border_radius()        # 圆角

        self._handle_shadow_style()             # 阴影
        self._handle_other_style()              # 其他效果

        return self._style

    def _handle_background_style(self):
        """从填充中提取背景信息"""
        color_info = ColorParseResolver(self._node.get("fills", [])).get_values()
        if not color_info:
            return

        if color_info.is_only_one_solid_color:
            self._style.background_color = color_info.colors[0]
            return

        self._style.background = ", ".join(color_info.colors)

    def _handle_border_style(self):
        strokes = self._node.get("strokes", [])
        if not strokes:
            return

        color_info = ColorParseResolver(self._node.get("strokes", [])).get_values()
        if not color_info:
            return

        if color_info.is_only_one_solid_color:
            self._style.border_color = color_info.colors[0]
        else:
            # 多个颜色兼容问题 设置边框颜色标识
            color_value = ", ".join(color_info.colors)
            self._style.border_color = f"background_{color_value}"

        # 处理描边宽度
        stroke_weight = self._node.get("strokeWeight")
        if stroke_weight is not None:
            stroke_weight = StyleValueUtils.format_value_with_unit(stroke_weight)
        else:
            # 如果没有 strokeWeight，默认使用 1
            stroke_weight = StyleValueUtils.format_value_with_unit(1)

        stroke_align = self._node.get("strokeAlign", "INSIDE")
        if stroke_align == "OUTSIDE":
            self._style.border_width = stroke_weight
        elif stroke_align == "CENTER":
            self._style.border_width = stroke_weight
        else:
            self._style.border_width = stroke_weight

        # 处理虚线样式
        stroke_dashes = self._node.get("strokeDashes", [])
        if stroke_dashes:
            self._style.border_style = "dashed"
        else:
            self._style.border_style = "solid"

        self._style.box_sizing = "border-box"

    def _handle_shadow_style(self):
        """提取阴影效果"""
        shadows = []
        effects = self._node.get("effects", [])
        for effect in effects:
            if not effect.get("visible", True):
                continue

            effect_type = effect.get("type")
            offset_x = effect.get("offset", {}).get("x", 0)
            offset_y = effect.get("offset", {}).get("y", 0)
            radius = effect.get("radius", 0)
            color = self.convert_color(effect.get("color", {}), effect.get("opacity"))
            if effect_type == "DROP_SHADOW":
                shadows.append(f"{StyleValueUtils.format_value_with_unit(offset_x)} {StyleValueUtils.format_value_with_unit(offset_y)} {StyleValueUtils.format_value_with_unit(radius)} {color}")

            elif effect_type == "INNER_SHADOW":
                shadows.append(f"inset {StyleValueUtils.format_value_with_unit(offset_x)} {StyleValueUtils.format_value_with_unit(offset_y)} {StyleValueUtils.format_value_with_unit(radius)} {color}")

        self._style.box_shadow = ", ".join(shadows) if shadows else None

    def _handle_border_radius(self):
        """处理圆角（包括统一圆角和独立圆角）"""
        if self._component_type == dsl_enum.ComponentType.CONTAINER and self._node_type == figma_enum.FigmaNodeType.EllipseNode:
            self._style.border_radius = "50%"
            return

        # 统一圆角
        corner_radius = self._node.get("cornerRadius")
        if corner_radius is not None:
            self._style.border_radius = StyleValueUtils.format_value_with_unit(corner_radius)
            return

        rectangle_corner_radii = self._node.get("rectangleCornerRadii", [])
        if not rectangle_corner_radii:
            return

        # 判断rectangle_corner_radii四个角是否都为0
        if all(radius == 0 for radius in rectangle_corner_radii):
            return

        self._style.border_top_left_radius = StyleValueUtils.format_value_with_unit(rectangle_corner_radii[0])
        self._style.border_top_right_radius = StyleValueUtils.format_value_with_unit(rectangle_corner_radii[1])
        self._style.border_bottom_right_radius = StyleValueUtils.format_value_with_unit(rectangle_corner_radii[2])
        self._style.border_bottom_left_radius = StyleValueUtils.format_value_with_unit(rectangle_corner_radii[3])


    def _handle_other_style(self):
        """处理其他效果（如模糊等），这些效果在 DSL 模型中没有直接对应，但可以记录在 extensions 中"""

        # 透明度
        opacity = self._node.get("opacity", 1.0)
        self._style.opacity = StyleValueUtils.format_number(opacity)

        # 溢出裁剪
        if self._node.get("clipsContent"):
            self._style.overflow = "hidden"

