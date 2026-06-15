"""
布局相关常量

供 calc_layout_position、overlap_layout_processor、preset_layout_processor、
text_dimension_processor、container_width_processor、parent_padding 等模块共用。
设计稿尺寸等也集中在此，便于统一修改和维护。
"""
from typing import Optional

# 设计稿标准宽度（Figma 默认设计稿宽度，对应 iPhone 6/7/8 等机型）
FIGMA_DESIGN_WIDTH = 375

# 设计稿标准高度（Figma 默认设计稿高度，对应 iPhone 6/7/8 等机型）
FIGMA_DESIGN_HEIGHT = 812

# 边距阈值
ADJUST_WIDTH_MARGIN = 32.5


def get_adjust_width_min(design_width: Optional[float] = None) -> float:
    """
    宽度自适应的最小宽度阈值（动态计算）。
    设计稿宽度取 Metadata.width；未传入时使用 FIGMA_DESIGN_WIDTH。
    公式：min(设计稿宽度 * 0.8, 200)。 之前用的300，287
    """
    w = design_width if design_width is not None else FIGMA_DESIGN_WIDTH
    return min(float(w) * 0.8 - 13, 200)
