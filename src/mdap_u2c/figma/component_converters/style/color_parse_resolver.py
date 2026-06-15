from enum import Enum
from typing import Dict, Any, Optional, List

import msgspec

from .base import BaseConverter
from .gradient_color_resolver import GradientColorResolver


class _ColorType(Enum):
    """颜色类型"""
    SOLID = "solid"
    IMAGE = "image"
    GRADIENT = "gradient"


class _ColorItem(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """单个颜色对象"""
    value: str              # 颜色值
    is_fully_opaque: bool   # 是否完全不透明
    type: _ColorType        # 颜色类型

    @staticmethod
    def of_solid(value: str, is_fully_opaque: bool):
        return _ColorItem(type=_ColorType.SOLID, value=value, is_fully_opaque=is_fully_opaque)

    @staticmethod
    def of_gradient(value: str, is_fully_opaque: bool):
        return _ColorItem(type=_ColorType.GRADIENT, value=value, is_fully_opaque=is_fully_opaque)


class ColorResult(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """颜色处理结果"""
    colors: list[str]               # 颜色列表
    is_only_one_solid_color: bool   # 是否只有一个纯色


class ColorParseResolver:
    """颜色解析处理器（主要处理以 Paint对象的属性，如：fills、strokes)"""
    _colors: List[_ColorItem]

    def __init__(self, paints: List[Dict[str, Any]]):
        self._colors = []
        self._paints = paints

    def get_values(self) -> Optional[ColorResult]:
        """获取值(返回颜色信息对象)"""
        if not self._paints or len(self._paints) == 0:
            return None

        self._handler_paint()
        color_len = len(self._colors)
        if color_len == 0:
            return None

        # 过滤完全不可见的颜色
        self._filter_not_visible_color()

        # 单个颜色
        if color_len == 1:
            first_color = self._colors[0]
            is_only_one_solid_color = first_color.type == _ColorType.SOLID
            return ColorResult(colors=[first_color.value], is_only_one_solid_color=is_only_one_solid_color)

        # 处理多个色值时，需要判断是否存在多个纯色对象（需要转化成渐变色，因为 CSS 不支持)
        colors = []
        max_len = len(self._colors) - 1
        for index, item in enumerate(self._colors):
            if index < max_len and item.type == _ColorType.SOLID:
                colors.append(f"linear-gradient(0deg, {item.value} 0%, {item.value} 100%)")
            else:
                colors.append(item.value)

        return ColorResult(colors=colors, is_only_one_solid_color=False)

    def _filter_not_visible_color(self):
        """过滤不透明之后的元素(因为不透明之后的颜色也看不见)"""
        for index, color in enumerate(self._colors):
            if color.is_fully_opaque:
                del self._colors[index + 1:]
                break

    @classmethod
    def _get_opacity_value(cls, paint: Dict[str, Any], outer_opacity: float):
        """
        获取透明度
        :param paint: Paint对象
        :param outer_opacity: 全局透明度，默认值 1
        :return:
        """
        if "opacity" in paint:
            return outer_opacity

        color = paint.get("color", {})
        return color.get("a", 1)

    def _handler_paint(self):
        paints = self._paints[::-1]
        for paint in paints:
            if not paint.get("visible", True):
                continue

            outer_opacity = paint.get("opacity", 1)
            if outer_opacity == 0:
                continue

            fill_type = paint.get("type")
            # 纯色处理
            if fill_type == "SOLID":
                self._do_solid_color(paint, outer_opacity)
                continue

            # 渐变色处理
            if fill_type in ["GRADIENT_LINEAR", "GRADIENT_RADIAL", "GRADIENT_ANGULAR", "GRADIENT_DIAMOND"]:
                self._do_gradient_color(paint, fill_type)
                continue

            # TODO 图片填充处理
            if fill_type == "IMAGE":
                continue

            # TODO 表情填充处理
            if fill_type == "EMOJI":
                continue

            # TODO 视频填充处理
            if fill_type == "VIDEO":
                continue

            # TODO 图形填充处理
            if fill_type == "PATTERN":
                continue

    def _do_gradient_color(self, paint: Dict[str, Any], fill_type: str):
        gradient = GradientColorResolver(paint, fill_type)
        if gradient.is_invisible():
            return

        if gradient.is_fully_opaque():
            self._colors.append(_ColorItem.of_gradient(gradient.get_value(), True))
        else:
            self._colors.append(_ColorItem.of_gradient(gradient.get_value(), False))

    def _do_solid_color(self, paint: Dict[str, Any], outer_opacity: float):
        opacity = self._get_opacity_value(paint, outer_opacity)
        self._colors.append(_ColorItem.of_solid(BaseConverter.convert_color(paint.get("color", {}), opacity), opacity == 1))

