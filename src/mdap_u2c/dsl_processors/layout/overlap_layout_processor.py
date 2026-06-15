"""
重叠布局处理模块

该模块用于处理元素之间存在重叠的布局场景，当无法使用 flex 布局时，
优先尝试处理特定的重叠模式，无法处理时才回退到绝对布局。

重叠场景分类：
1. 背景覆盖模式：一个大元素作为背景，其他元素叠加在其上
2. 层叠模式：多个元素相互部分重叠
3. 无法处理的复杂重叠：使用绝对布局

作者: AI Assistant
日期: 2026-01-22
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from enum import IntEnum

from mdap_u2c.dsl_processors.layout import ai_type_def
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils.style_value_utils import StyleValueUtils
from mdap_u2c.dsl_processors.layout.container_width_processor import calc_no_width_layout, remove_control_width

from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN, get_adjust_width_min

_logger = logging.getLogger("overlap_layout_processor")

# 常量定义
OVERLAP_THRESHOLD = 0.8  # 重叠率阈值，超过此值认为是背景覆盖
EPSILON = 2.1  # 比较容差值


# ============================================================================
# 元素度量数据类
# ============================================================================

@dataclass
class ElementMetrics:
    """
    元素相对于父容器的度量信息
    
    Attributes:
        left_margin: 左边距 (元素左边到父容器左边的距离)
        right_margin: 右边距 (元素右边到父容器右边的距离)
        top_margin: 上边距 (元素顶部到父容器顶部的距离)
        bottom_margin: 下边距 (元素底部到父容器底部的距离)
        is_horizontal_center: 是否水平居中 (左右边距相等)
        is_vertical_center: 是否垂直居中 (上下边距相等)
    """
    left_margin: float
    right_margin: float
    top_margin: float
    bottom_margin: float
    is_horizontal_center: bool
    is_vertical_center: bool
    

def calc_element_metrics(elem_data, parent_data, epsilon: float = EPSILON) -> ElementMetrics:
    """
    计算元素相对于父容器的度量信息
    
    Args:
        elem_data: 子元素数据 (需要有 x, y, width, height 属性)
        parent_data: 父容器数据 (需要有 x, y, width, height 属性)
        epsilon: 比较容差值
    
    Returns:
        ElementMetrics: 包含边距和对齐信息的度量对象
    """
    # 计算四边边距
    left_margin = elem_data.x - parent_data.x
    right_margin = (parent_data.x + parent_data.width) - (elem_data.x + elem_data.width)
    top_margin = elem_data.y - parent_data.y
    bottom_margin = (parent_data.y + parent_data.height) - (elem_data.y + elem_data.height)
    
    # 判断是否居中
    is_horizontal_center = abs(left_margin - right_margin) <= epsilon
    is_vertical_center = abs(top_margin - bottom_margin) <= epsilon
    
    return ElementMetrics(
        left_margin=left_margin,
        right_margin=right_margin,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
        is_horizontal_center=is_horizontal_center,
        is_vertical_center=is_vertical_center,
    )


class OverlapType(IntEnum):
    """重叠类型枚举"""
    NONE = 0  # 无重叠
    COLUMN_CROSS_SMALL = 1  # 纵向交叉重叠（重叠区域小，使用负margin）
    COLUMN_CROSS_BIG = 2  # 纵向交叉重叠（重叠区域大，第一个元素绝对定位）
    COMPLEX_OVERLAP = 3  # 复杂重叠（无法简单处理）


# 常量：纵向重叠区域占父容器高度的阈值
COLUMN_CROSS_THRESHOLD = 0.3  # 30%


def _to_pt_str(value):
    """将值转换为 pt 字符串格式"""
    if value is None:
        return None
    return StyleValueUtils.format_value_with_unit(value)


def _flex_enum_to_str(value):
    """将 flex 枚举转换为字符串"""
    if value is None:
        return None
    if isinstance(value, (dsl_enum.FlexDirection, dsl_enum.JustifyContent,
                          dsl_enum.AlignItems, dsl_enum.FlexWrap,
                          dsl_enum.PositionType, dsl_enum.DisplayMode)):
        return value.value
    if isinstance(value, str):
        return value
    return str(value)


def _is_bottom_bar(elem) -> bool:
    """
    判断元素是否为底部栏
    
    Args:
        elem: 元素节点
    
    Returns:
        bool: 是底部栏返回 True
    """
    return elem.data.ai_type == ai_type_def.AI_TYPE.BOTTOM_BAR.value


def _calc_vertical_overlap_height(elem1_data, elem2_data) -> float:
    """
    计算两个元素在Y轴方向的重叠高度
    
    Args:
        elem1_data: 第一个元素的数据
        elem2_data: 第二个元素的数据

    Returns:
        float: 重叠高度，如果没有重叠返回 0
    """
    elem1_top = elem1_data.y
    elem1_bottom = elem1_data.y + elem1_data.height
    elem2_top = elem2_data.y
    elem2_bottom = elem2_data.y + elem2_data.height

    # 计算重叠区域
    overlap_top = max(elem1_top, elem2_top)
    overlap_bottom = min(elem1_bottom, elem2_bottom)

    if overlap_bottom <= overlap_top:
        return 0.0

    return overlap_bottom - overlap_top


def _detect_column_cross_overlap(children_list, parent_node) -> Tuple[OverlapType, Optional[int], Optional[int]]:
    """
    检测是否为纵向交叉重叠场景
    
    条件：
    1. 有且仅有两个控件
    2. 两个控件的 X 轴中心基本一致
    3. Y 轴有部分重叠
    4. 两个元素都不是底部栏
    
    Args:
        children_list: 子元素列表
        parent_node: 父节点
    
    Returns:
        Tuple[OverlapType, Optional[int], Optional[int]]: 
            (重叠类型, 上方元素索引, 下方元素索引)
    """
    if len(children_list) != 2:
        return OverlapType.NONE, None, None
    
    elem1 = children_list[0]
    elem2 = children_list[1]
    
    # 检查是否为底部栏
    if _is_bottom_bar(elem1) or _is_bottom_bar(elem2):
        return OverlapType.NONE, None, None
    
    # 检查 X 轴中心是否基本一致
    if elem2.data.y + elem2.data.height <= elem1.data.y + elem1.data.height:
        return OverlapType.COLUMN_CROSS_BIG, None, None
    # 计算 Y 轴重叠高度
    overlap_height = _calc_vertical_overlap_height(elem1.data, elem2.data)
    if overlap_height <= 0:
        return OverlapType.NONE, None, None
    
    # 确定上方和下方的元素索引（按 Y 坐标排序）
    if elem1.data.y <= elem2.data.y:
        top_index, bottom_index = 0, 1
    else:
        top_index, bottom_index = 1, 0
    
    # 计算重叠比例
    parent_height = parent_node.data.height
    if parent_height <= 0:
        return OverlapType.COLUMN_CROSS_BIG, None, None
    if min(elem1.data.height, elem2.data.height) == 0:
       return OverlapType.COLUMN_CROSS_BIG, None, None
    overlap_ratio = overlap_height / min(elem1.data.height, elem2.data.height)
    if overlap_ratio > 1:
       _logger.debug(f"纵向交叉重叠检测: 重叠高度={overlap_height}, 父容器高度={parent_height}, "
                  f"重叠比例={overlap_ratio:.2%}, 阈值={COLUMN_CROSS_THRESHOLD:.0%}")
    
    # 根据重叠比例判断类型
    if overlap_ratio <= COLUMN_CROSS_THRESHOLD and bottom_index > top_index:
        return OverlapType.COLUMN_CROSS_SMALL, top_index, bottom_index
    else:
        return OverlapType.COLUMN_CROSS_BIG, top_index, bottom_index


def detect_overlap_type(children_list, parent_node=None) -> Tuple[OverlapType, Optional[int], Optional[int]]:
    """
    检测重叠类型
    
    Args:
        children_list: 子元素列表
        parent_node: 父节点（用于计算重叠比例）
    
    Returns:
        Tuple[OverlapType, Optional[int], Optional[int]]: 
            (重叠类型, 上方元素索引, 下方元素索引)
    """
    if len(children_list) < 2:
        return OverlapType.NONE, None, None

    # 当子节点>=3 且面积最大的节点宽度>=父容器宽度*0.75 时，返回 COLUMN_CROSS_BIG
    if len(children_list) >= 3 and parent_node is not None and parent_node.data.width > 0:
        areas = [(i, elem.data.width * elem.data.height) for i, elem in enumerate(children_list)]
        max_idx = max(areas, key=lambda x: x[1])[0]
        max_elem = children_list[max_idx]
        if max_elem.data.width >= parent_node.data.width * 0.75:
            return OverlapType.COLUMN_CROSS_BIG, None, None
    
    # 优先检测纵向交叉重叠场景（仅 2 个子节点）
    if parent_node is not None:
        overlap_type, top_idx, bottom_idx = _detect_column_cross_overlap(children_list, parent_node)
        if overlap_type != OverlapType.NONE:
            return overlap_type, top_idx, bottom_idx
    
    return OverlapType.COMPLEX_OVERLAP, None, None


# ============================================================================
# 纵向交叉重叠布局处理函数
# ============================================================================

def _calc_column_cross_small_layout(input_tree, parent_node, children_list, top_index: int, bottom_index: int,
                                     context_share_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    处理纵向交叉重叠（小重叠）的布局
    
    策略：使用 flex 布局，第二个元素（下方元素）的 margin-top 设为负值
    
    Args:
        input_tree: 树结构
        parent_node: 父节点
        children_list: 子元素列表
        top_index: 上方元素的索引
        bottom_index: 下方元素的索引
        context_share_data: 上下文共享数据
    
    Returns:
        bool: 处理成功返回 True
    """
    top_elem = children_list[top_index]
    bottom_elem = children_list[bottom_index]
    # 设置父容器为纵向 flex 布局
    parent_node.data.src.style.flex_direction = _flex_enum_to_str(dsl_enum.FlexDirection.COLUMN)
    parent_node.data.src.style.align_items = _flex_enum_to_str(dsl_enum.AlignItems.CENTER)
    top_elem.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    # 计算上方元素的 margin-top
    top_metrics = calc_element_metrics(top_elem.data, parent_node.data)
    if top_metrics.top_margin > 0:
        top_elem.data.src.style.margin_top = _to_pt_str(top_metrics.top_margin)
    
    # 尝试去除上方元素的宽度
    if not calc_no_width_layout(input_tree, top_elem.data.uid, context_share_data):
        # 宽度未去除，计算上方元素的水平对齐
        if not top_metrics.is_horizontal_center:
            if top_metrics.left_margin < top_metrics.right_margin:
                top_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
                if top_metrics.left_margin > 0:
                    top_elem.data.src.style.margin_left = _to_pt_str(top_metrics.left_margin)
            else:
                top_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
                if top_metrics.right_margin > 0:
                    top_elem.data.src.style.margin_right = _to_pt_str(top_metrics.right_margin)
    
    bottom_elem.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    # 下方元素设置负的 margin-top
    # 计算重叠高度（负margin值）
    margin_top = bottom_elem.data.y -  (top_elem.data.y + top_elem.data.height - 1 )
    bottom_elem.data.src.style.margin_top = _to_pt_str(margin_top)
    
    # 尝试去除下方元素的宽度
    if not calc_no_width_layout(input_tree, bottom_elem.data.uid, context_share_data):
        # 宽度未去除，计算下方元素的水平对齐
        bottom_metrics = calc_element_metrics(bottom_elem.data, parent_node.data)
        if not bottom_metrics.is_horizontal_center:
            if bottom_metrics.left_margin < bottom_metrics.right_margin:
                bottom_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
                if bottom_metrics.left_margin > 0:
                    bottom_elem.data.src.style.margin_left = _to_pt_str(bottom_metrics.left_margin)
            else:
                bottom_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
                if bottom_metrics.right_margin > 0:
                    bottom_elem.data.src.style.margin_right = _to_pt_str(bottom_metrics.right_margin)
    
    _logger.info(f"应用纵向交叉小重叠布局: 父节点={parent_node.data.uid}, "
                 f"上方元素={top_elem.data.uid}, 下方元素={bottom_elem.data.uid}, "
                 f"负margin={margin_top}px")
    return True


def _calc_column_cross_big_layout(input_tree, parent_node, children_list,
                                   context_share_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    处理纵向交叉重叠（大重叠）的布局
    
    策略：
    - 当 len(children_list) >= 3：面积最大的节点用 flex 布局，剩余元素用绝对定位。
    - 当 len(children_list) == 2：面积大的用 flex 布局，面积小的用绝对定位（原有逻辑）。
    
    Args:
        input_tree: 树结构
        parent_node: 父节点
        children_list: 子元素列表
        context_share_data: 上下文共享数据
    
    Returns:
        bool: 处理成功返回 True
    """
    if len(children_list) < 2:
        return False

    if len(children_list) >= 3:
        # 面积最大的节点用 flex 布局，其余用绝对定位
        areas = [(i, elem.data.width * elem.data.height) for i, elem in enumerate(children_list)]
        max_idx = max(areas, key=lambda x: x[1])[0]
        flex_elem = children_list[max_idx]
        absolute_list = [elem for i, elem in enumerate(children_list) if i != max_idx]
    else:
        # 原有两子节点逻辑
        first_elem = children_list[0]
        second_elem = children_list[1]

        first_type = getattr(first_elem.data.src, "type", None)
        second_type = getattr(second_elem.data.src, "type", None)
        is_first_image = first_type == dsl_enum.ComponentType.IMAGE
        is_second_image = second_type == dsl_enum.ComponentType.IMAGE
        is_first_container = first_type == dsl_enum.ComponentType.CONTAINER
        is_second_container = second_type == dsl_enum.ComponentType.CONTAINER

        # 特殊条件：一个为图片、一个为容器时，图片绝对定位，容器 flex 布局
        if (is_first_image and is_second_container):
            flex_elem, absolute_elem = second_elem, first_elem
        elif (is_first_container and is_second_image):
            flex_elem, absolute_elem = first_elem, second_elem
        else:
            first_area = first_elem.data.width * first_elem.data.height
            second_area = second_elem.data.width * second_elem.data.height
            if first_area >= second_area:
                flex_elem, absolute_elem = first_elem, second_elem
            else:
                flex_elem, absolute_elem = second_elem, first_elem
        absolute_list = [absolute_elem]

    # 父容器设置为相对定位和纵向 flex 布局
    if parent_node.data.src.style.position is None:
        parent_node.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    parent_node.data.src.style.flex_direction = _flex_enum_to_str(dsl_enum.FlexDirection.COLUMN)
    parent_node.data.src.style.align_items = _flex_enum_to_str(dsl_enum.AlignItems.CENTER)

    # 非面积最大元素使用绝对定位
    _calc_absolute_layout(input_tree, parent_node, absolute_list)

    # 面积最大的元素使用正常流布局，计算 margin-top
    flex_metrics = calc_element_metrics(flex_elem.data, parent_node.data)
    flex_elem.data.src.style.margin_top = _to_pt_str(flex_metrics.top_margin)
    if not calc_no_width_layout(input_tree, flex_elem.data.uid, context_share_data):
        if not flex_metrics.is_horizontal_center:
            if flex_metrics.left_margin < flex_metrics.right_margin:
                flex_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
                if flex_metrics.left_margin > 0:
                    flex_elem.data.src.style.margin_left = _to_pt_str(flex_metrics.left_margin)
            else:
                flex_elem.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
                if flex_metrics.right_margin > 0:
                    flex_elem.data.src.style.margin_right = _to_pt_str(flex_metrics.right_margin)
    if flex_elem.data.src.style.position is None:
        flex_elem.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    #_logger.info(f"应用纵向交叉大重叠布局: 父节点={parent_node.data.uid}, "
    #             f"面积大(flex)={flex_elem.data.uid}, 绝对定位数量={len(absolute_list)}")
    return True


# ============================================================================
# 绝对布局处理函数
# ============================================================================

def _calc_absolute_layout(input_tree, parent_node, children_list):
    """
    对于一些交叉重叠情况，无法计算 flex 布局，只能用绝对定位
    
    Args:
        input_tree: 树结构
        parent_node: 父节点
        children_list: 子元素列表
    """
    if parent_node.data.src.style.position is None:
        parent_node.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    absolute_list = children_list
    need_z_index = False
    
    for i, elem in enumerate(absolute_list):
        elem.data.src.style.position = _flex_enum_to_str(dsl_enum.PositionType.ABSOLUTE)
        
        # 设置 z_index
        if need_z_index:
            elem.data.src.style.z_index = int(elem.data.seq)

        # 使用度量函数计算边距
        metrics = calc_element_metrics(elem.data, parent_node.data)
        
        # 垂直方向定位：底部间距小于顶部间距时使用 bottom，否则使用 top
        if metrics.bottom_margin < metrics.top_margin:
            elem.data.src.style.bottom = _to_pt_str(metrics.bottom_margin)
        else:
            elem.data.src.style.top = _to_pt_str(metrics.top_margin)
        
        # 分割线类型且宽度 > 300 时，宽度自适应，左右间距固定
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value and elem.data.width > 300:
            # 宽度自适应，左右间距固定
            if metrics.left_margin > 0.1 or metrics.right_margin > 0.1:
                elem.data.src.style.width = f"calc(100% - {round(metrics.left_margin + metrics.right_margin, 1)}px)"
            else:
                elem.data.src.style.width = "100%"
            if metrics.left_margin > 0.1:
                elem.data.src.style.left = _to_pt_str(metrics.left_margin)
            if metrics.right_margin > 0.1:
                elem.data.src.style.right = _to_pt_str(metrics.right_margin)
            elem.data.extra_dict["edit_width"] = 1
        elif metrics.is_horizontal_center:
            # 左右边距相等，采用居中对齐；设计稿宽度从根节点取（等同 Metadata.width）
            root = input_tree.get_node(input_tree.root) if input_tree else None
            design_width = float(root.data.width) if root and root.data else None
            adjust_min = get_adjust_width_min(design_width)
            if metrics.left_margin <= ADJUST_WIDTH_MARGIN and elem.data.width >= adjust_min:
                # 边距满足条件时，宽度自适应
                if metrics.left_margin > 0:
                    elem.data.src.style.width = f"calc(100% - {round(metrics.left_margin * 2, 1)}px)"
                    elem.data.src.style.left = _to_pt_str(metrics.left_margin)
                    elem.data.src.style.right = _to_pt_str(metrics.right_margin)
                else:
                    elem.data.src.style.width = "100%"
                elem.data.extra_dict["edit_width"] = 1
            else:
                # 条件不满足时（小元素居中，如图标），使用 left: 50% + transform 实现居中
                elem.data.src.style.left = "50%"
                elem.data.src.style.transform = "translateX(-50%)"
        elif metrics.right_margin < metrics.left_margin:
            # 右边间距大于左边间距，采用右间距偏移的方式
            elem.data.src.style.right = _to_pt_str(metrics.right_margin)
        else:
            # 默认使用左偏移
            elem.data.src.style.left = _to_pt_str(metrics.left_margin)


def calc_overlap_layout(input_tree, parent_node, children_list, 
                        context_share_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    计算重叠布局
    
    此函数是重叠布局处理的主入口，会根据重叠类型选择合适的处理策略。
    如果无法处理，则调用绝对布局函数。
    
    Args:
        input_tree: 树结构
        parent_node: 父节点
        children_list: 子元素列表
        context_share_data: 上下文共享数据
    
    Returns:
        bool: 处理成功返回 True
    """
    if len(children_list) <= 0:
        return True
    
    if len(children_list) == 1:
        # 单元素不存在重叠，直接使用绝对布局
        _calc_absolute_layout(input_tree, parent_node, children_list)
        return True
    
    # 检测重叠类型（传入 parent_node 用于计算重叠比例）
    overlap_type, top_index, bottom_index = detect_overlap_type(children_list, parent_node)
    
    _logger.debug(f"重叠类型检测结果: {overlap_type.name}, 父节点={parent_node.data.uid}, 子元素数量={len(children_list)}")
    
    # 根据重叠类型选择处理策略
    if overlap_type == OverlapType.COLUMN_CROSS_SMALL:
        # 纵向交叉小重叠：使用 flex 布局，第二个元素 margin 设为负值
        if _calc_column_cross_small_layout(input_tree, parent_node, children_list, top_index, bottom_index, context_share_data):
            return True
        # 处理失败，回退到绝对布局
        _logger.warning(f"纵向交叉小重叠布局处理失败，使用绝对布局: {parent_node.data.uid}")
        _calc_absolute_layout(input_tree, parent_node, children_list)
        return True
    
    elif overlap_type == OverlapType.COLUMN_CROSS_BIG:
        # 纵向交叉大重叠：面积大的用 flex 布局，面积小的用绝对定位
        if _calc_column_cross_big_layout(input_tree, parent_node, children_list, context_share_data):
            return True
        # 处理失败，回退到绝对布局
        _logger.warning(f"纵向交叉大重叠布局处理失败，使用绝对布局: {parent_node.data.uid}")
        _calc_absolute_layout(input_tree, parent_node, children_list)
        return True
    
    else:
        # 复杂重叠或无法识别的场景，直接使用绝对布局
        _logger.warning(f"复杂重叠场景，使用绝对布局: {parent_node.data.uid}")
        _calc_absolute_layout(input_tree, parent_node, children_list)
        return True

