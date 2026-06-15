from typing import Dict, Any, Optional

import math


class FigmaCheckUtils:
    """Figma 检查工具"""

    @staticmethod
    def is_vertical_horizontal_rotation(rotation: Optional[float] = None) -> bool:
        """检查节点是否为垂直水平旋转"""
        _, reversed_degrees, _ = FigmaCheckUtils._calculation_rotation_angle(rotation if rotation else 0)

        return reversed_degrees in (0, 90, 180, -90, -180)

    @staticmethod
    def has_image_fill(node: Dict[str, Any]) -> bool:
        """检查节点是否有图片填充"""
        fills = node.get("fills", [])
        if not fills:
            return False

        for fill in fills:
            if fill.get("type") == "IMAGE" and fill.get("visible", True):
                return True
        return False

    @staticmethod
    def _calculation_rotation_angle(radians: float) -> (float, float, float):
        """
        计算旋转角度并保留两位小数
        :param radians: 弧度
        :return: 角度(角度, 角度翻转(figma使用该值), 实际角度(0 - 360))
        """
        degrees = round(radians * (180 / math.pi), 2)
        reversed_degrees = round(-degrees, 2)
        positive_degrees = round((reversed_degrees + 360) % 360, 2)

        return degrees, reversed_degrees, positive_degrees
