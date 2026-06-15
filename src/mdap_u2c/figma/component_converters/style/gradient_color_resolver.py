from typing import Dict, Any
import math
from .base import BaseConverter
from mdap_u2c.utils.style_value_utils import StyleValueUtils


class GradientColorResolver:
    """渐变色解析处理器"""
    _is_invisible = False           # 是否不可见(true表示不可见，false表示可见)
    _is_fully_opaque = False        # 是否完全不透明(true表示透明度1，之后的元素不可见; false表示透明度 < 1，后面的元素可见)

    def __init__(self, paint: Dict[str, Any], gradient_type: str):
        if not paint:
            return

        self._paint = paint
        self._gradient_type = gradient_type
        self._gradient_stops = paint.get("gradientStops", [])
        if all(item.get("color", {}).get("a", 1) == 0 for item in self._gradient_stops):
            self._is_invisible = True

        if all(item.get("color", {}).get("a", 1) == 1 for item in self._gradient_stops):
            self._is_fully_opaque = True

    def is_invisible(self) -> bool:
        """检测不可见(返回true表示不可见，false表示可见)"""
        return self._is_invisible

    def is_fully_opaque(self) -> bool:
        """检测完全不透明(true表示透明度1，之后的元素不可见; false表示透明度 < 1，后面的元素可见)"""
        return self._is_fully_opaque

    def get_value(self) -> str | None:
        """获取渐变样式值"""
        if not self._gradient_stops or len(self._gradient_stops) == 0:
            return None

        # 菱形渐变，CSS 不支持，使用多个线性渐变模拟
        if self._gradient_type == "GRADIENT_DIAMOND":
            return self._resolver_diamond_gradient()

        colors = []
        outer_opacity = self._paint.get("opacity", 1)
        positions = self._paint.get("gradientHandlePositions", [])
        for stop in self._gradient_stops:
            stop_color = stop.get("color", {})
            color = BaseConverter.convert_color(stop_color, outer_opacity * stop_color.get("a", 1))
            position = stop.get("position", 0) * 100
            colors.append(f"{color} {StyleValueUtils.format_number(position)}%")
        colors_str = ", ".join(colors)

        # 径向渐变
        if self._gradient_type == "GRADIENT_RADIAL":
            return f"radial-gradient({self._calculate_radial_params(positions)}, {colors_str})"

        # 锥形渐变
        if self._gradient_type == "GRADIENT_ANGULAR":
            return f"conic-gradient({self._calculate_conic_params(positions)}, {colors_str})"

        # 线性渐变
        return f"linear-gradient({self._calculate_angle(positions)}, {colors_str})"

    def _resolver_diamond_gradient(self):
        """处理菱形渐变(不支持角度变化，统一中心位置 50%)"""
        # 注意：菱形渐变的位置需要映射到 0-50% 范围（从中心到边缘）
        stop_parts = []
        outer_opacity = self._paint.get("opacity", 1)
        for stop in self._gradient_stops:
            stop_color = stop.get("color", {})
            color = BaseConverter.convert_color(stop_color, outer_opacity * stop_color.get("a", 1))
            # 位置从 0-1 映射到 0-50%（乘以 50 并四舍五入）
            position_pct = int(round(stop['position'] * 50))
            stop_parts.append(f"{color} {position_pct}%")
        stops_str = ", ".join(stop_parts)

        # 生成四个方向的线性渐变
        directions = [
            ("to bottom right", "bottom right"),
            ("to bottom left", "bottom left"),
            ("to top left", "top left"),
            ("to top right", "top right")
        ]

        gradients = []
        for direction, position in directions:
            gradients.append(f"linear-gradient({direction}, {stops_str}) {position} / 50% 50% no-repeat")

        return ", ".join(gradients)

    @classmethod
    def _calculate_conic_params(cls, positions: list):
        """
        处理锥形渐变参数
        语法：conic-gradient(from angle at position, color-stop1, color-stop2, ...);
        :param positions:
        :return:
        """
        x, y = cls._calculate_center_position(positions)

        return f"from {cls._calculate_angle(positions)} at {x} {y}"

    @classmethod
    def _calculate_radial_params(cls, positions: list):
        """
        处理径向渐变参数(形状[使用默认值即可]、大小、中心位置)
        注意：CSS不支持角度，所以对于 Figma 有发生角度旋转的，暂不支持
        """
        center = positions[0]
        horizontal_end = positions[1]
        vertical_end = positions[2]

        # 2. 计算水平半径（从中心到第二个向量的距离）
        dx_h = horizontal_end['x'] - center['x']  # 1.0 - 0.5 = 0.5
        dy_h = horizontal_end['y'] - center['y']  # 0.5 - 0.5 = 0
        radius_h = math.sqrt(dx_h ** 2 + dy_h ** 2)  # sqrt(0.25) = 0.5
        width = StyleValueUtils.format_number(radius_h * 100)  # 50%

        # 3. 计算垂直半径（从中心到第三个向量的距离）
        dx_v = vertical_end['x'] - center['x']  # 0.5 - 0.5 = 0
        dy_v = vertical_end['y'] - center['y']  # 1.0 - 0.5 = 0.5
        radius_v = math.sqrt(dx_v ** 2 + dy_v ** 2)  # sqrt(0.25) = 0.5
        height = StyleValueUtils.format_number(radius_v * 100)  # 50%

        x, y = cls._calculate_center_position(positions)

        return f"{height}% {width}% at {x} {y}"

    @classmethod
    def _calculate_center_position(cls, positions: list) -> tuple[str, str]:
        """计算中心位置"""
        center = positions[0]

        # 中心点位置
        x = StyleValueUtils.format_number(center['x'] * 100)  # 0.5 * 100 = 50%
        y = StyleValueUtils.format_number(center['y'] * 100)  # 0.5 * 100 = 50%

        return f"{x}%", f"{y}%"

    @classmethod
    def _calculate_angle(cls, positions: list):
        """计算角度"""
        start = positions[0]
        end = positions[1]

        dx = end['x'] - start['x']
        dy = end['y'] - start['y']

        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        return f"{StyleValueUtils.format_number((angle_deg + 90) % 360)}deg"
