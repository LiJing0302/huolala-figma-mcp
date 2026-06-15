from calendar import c
import functools
import logging
import re
import unicodedata
from collections import Counter
from typing import Optional, Dict, Any

import numpy
from PIL import Image
from dns.rdatatype import DS

from mdap_u2c.constant import FIGMA_DESIGN_HEIGHT
from mdap_u2c.dsl_processors.layout import tree_projection, ai_type_def, calc_list_layout, tree_rebuild, gen_tree
from mdap_u2c.enums import dsl_enum, common_enum
from mdap_u2c.utils import component_style_utils
from mdap_u2c.utils import StyleValueUtils

# 导入重叠布局处理模块
from mdap_u2c.dsl_processors.layout.overlap_layout_processor import (
    calc_overlap_layout,
    _calc_absolute_layout,
    calc_element_metrics,
    ElementMetrics,
)
from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN, get_adjust_width_min

# 导入分割线处理模块
from mdap_u2c.dsl_processors.layout.split_line_processor import (
    calc_split_line_layout,
)

# 从拆分模块导入文本宽高处理相关函数
from mdap_u2c.dsl_processors.layout.text_dimension_processor import (
    _parse_font_size,
    _parse_px_value,
    _count_text_characters,
    _is_text_multiline,
    _collect_rich_text_content,
    _get_text_position_relative_to_parent,
    _is_row_uniform_for_text,
    _calc_text_row_count_by_image,
    _crop_text_region,
    _is_column_uniform,
    _calc_text_display_x_range,
    _parse_line_height,
    _is_web_platform,
    remove_text_height as _remove_text_height,
    remove_text_width_in_row,
)

# 从拆分模块导入容器宽度处理相关函数
from mdap_u2c.dsl_processors.layout.container_width_processor import (
    remove_text_width_in_column,
    remove_control_width as _remove_control_width,
    calc_no_width_layout as _calc_no_width_layout,
    replace_width_height_by_100_percent,
    _has_no_sibling_on_left_right,
    _has_no_sibling_on_right,
    _has_no_sibling_on_left,
)
from mdap_u2c.dsl_processors.layout.parent_padding import (
    get_parent_padding as _get_parent_padding,
    has_layout_padding as _has_layout_padding,
    calc_row_container_padding as _calc_row_container_padding,
    calc_column_container_padding as _calc_column_container_padding,
)

SPACE_BETWEEN_MAX_VAR = 0.7  #2/3
MIN_EDGE_GAP = 32
LEFT_RIGHT_THROLD = 20

EPSILON = 2.1
VERTICAL_EPSILON = 1.1
_logger = logging.getLogger("calc_layout_position")


def calc_first_last_metrics(tree_children_list, parent_data, epsilon: float = EPSILON) -> tuple:
    """
    计算第一个和最后一个子元素的边距
    
    Args:
        tree_children_list: 子元素列表
        parent_data: 父容器数据
        epsilon: 比较容差值
    
    Returns:
        tuple: (left_offset, right_offset, is_equal)
            - left_offset: 第一个元素的左边距
            - right_offset: 最后一个元素的右边距
            - is_equal: 左右边距是否相等
    """
    first_elem = tree_children_list[0].data
    last_elem = tree_children_list[-1].data
    
    left_offset = first_elem.x - parent_data.x
    right_offset = (parent_data.x + parent_data.width) - (last_elem.x + last_elem.width)
    is_equal = abs(left_offset - right_offset) <= epsilon
    
    return left_offset, right_offset, is_equal

# 辅助函数：确保 margin 对象存在
def _ensure_margin(component):
    """确保组件的 margin 对象存在"""

    return component.style


# 辅助函数：确保值为 float 类型（转换 numpy 类型）
def _to_pt_str(value):
    """将值转换为 Python float 类型，处理 numpy 类型"""
    if value is None:
        return None
    return StyleValueUtils.format_value_with_unit(value)


def flex_enum_to_str(value):
    """
    将 flex-direction、justify-content、align-items 的枚举值转成字符串
    
    Args:
        value: 枚举值或字符串，可以是以下类型：
            - dsl_enum.FlexDirection
            - dsl_enum.JustifyContent
            - dsl_enum.AlignItems
            - dsl_enum.FlexWrap
            - 字符串
            - None
    
    Returns:
        str: 转换后的字符串值，如果输入为 None 则返回 None
    """
    if value is None:
        return None
    
    # 如果是枚举类型，获取其 value
    if isinstance(value, (dsl_enum.FlexDirection, dsl_enum.JustifyContent, 
                          dsl_enum.AlignItems, dsl_enum.FlexWrap,dsl_enum.PositionType ,dsl_enum.DisplayMode)):
        return value.value
    
    # 如果已经是字符串，直接返回
    if isinstance(value, str):
        return value
    
    # 其他情况，尝试转换为字符串
    return str(value)


def _set_relative_for_elem_overlap_with_bg_image(filter_children_list, bg_image_list):
    """
    若 filter_children_list 中的元素与 bg_image_list 中的元素发生重叠，
    且该元素的 position 为 None，则将 position 设置为 relative。
    用于确保与背景图重叠的内容能正确显示在背景图之上。
    """
    if not bg_image_list:
        return
    for elem in filter_children_list:
        for bg_elem in bg_image_list:
            result = gen_tree.judge_box(elem.data, bg_elem.data)
            if result != 0:
                if getattr(elem.data.src.style, "position", None) is None:
                    elem.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
                break


def _set_relative_for_flex_elem_overlap_with_non_flex(parent_node, filter_children_list, non_flex_elem_list):
    """
    在 parent_node.data.src.children 对应的节点中，找到与 non_flex_elem_list 局部重叠且非包含的元素，
    若其 position 为 None 则设为 relative。
    """
    if not non_flex_elem_list:
        return
    style_children = getattr(parent_node.data.src, "children", None) or []
    style_children_ids = {getattr(c, "id", None) for c in style_children if getattr(c, "id", None) is not None}
    flex_elem_list = [e for e in filter_children_list if getattr(e.data.src, "id", None) in style_children_ids]
    for flex_elem in flex_elem_list:
        for non_flex_elem in non_flex_elem_list:
            result = gen_tree.judge_box(flex_elem.data, non_flex_elem.data)
            if result > 0 and result not in (2, 3):
                if getattr(flex_elem.data.src.style, "position", None) is None:
                    flex_elem.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
                break


def calc_flex_relative_layout(input_tree, parent_node, children_list, context_share_data: Optional[Dict[str, Any]] = None):
    # 导入预设布局处理模块（延迟导入避免循环依赖）
    from mdap_u2c.dsl_processors.layout import preset_layout_processor
    if component_style_utils.is_rich_text_container(parent_node.data.src):
        return
    filter_children_list = list()
    red_point_bubble_list = list()
    bg_image_list = list()
    for i, elem in enumerate(children_list):
        if (getattr(elem.data, 'extra_dict', None) or {}).get('bg_image') == 1:
            bg_image_list.append(elem)
            continue
        if component_style_utils.is_redpoint_bubble(elem.data):
            red_point_bubble_list.append(elem)
            parent_node.data.ai_type = ai_type_def.AI_TYPE.RED_POINT_BUBBLE_CONTAINER.value
        elif elem.data.ai_type == ai_type_def.AI_TYPE.BOTTOM_BAR.value:
            continue
        elif  elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            if calc_split_line_layout(input_tree, parent_node, elem, _calc_absolute_layout):
                continue
            else:
                filter_children_list.append(elem)
        else:
            filter_children_list.append(elem)

    if bg_image_list:
        _calc_absolute_layout(input_tree, parent_node, bg_image_list)
        _set_relative_for_elem_overlap_with_bg_image(filter_children_list, bg_image_list)
    non_flex_elem_list = preset_layout_processor.get_non_flex_elem_list(parent_node, filter_children_list)
    if non_flex_elem_list:
        _calc_absolute_layout(input_tree, parent_node, non_flex_elem_list)
        _set_relative_for_flex_elem_overlap_with_non_flex(parent_node, filter_children_list, non_flex_elem_list)
        flex_children_list = [e for e in filter_children_list if e not in non_flex_elem_list]
        filter_children_list = flex_children_list

    # 检查是否有预设的grid 布局，且没有重计算标志，如果有则直接应用而不重新计算
    if preset_layout_processor.process_preset_grid_layout(input_tree, parent_node,
                                      filter_children_list) and "need_re_calc" not in parent_node.data.extra_dict:
            return
    result = _calc_flex_layout(input_tree, parent_node, filter_children_list, context_share_data)

    if result is False:
        # 当无法使用 flex 布局时，优先尝试重叠布局处理
        # 重叠布局函数会先判断重叠场景，无法处理时会自动调用绝对布局
        calc_overlap_layout(
            input_tree, 
            parent_node, 
            filter_children_list,
            context_share_data=context_share_data
        )
        _logger.warning(f"{parent_node.data.uid}无法计算flex布局,尝试重叠布局或定位")

    _calc_redpoint_relative_layout(input_tree, red_point_bubble_list)  # 处理红点布局算法


def change_bottombar_coordinate(child_data, parent_value):
    child_data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.ABSOLUTE)
    child_data.src.style.bottom = 0
    if parent_value.src.style.position is None:
        parent_value.src.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    child_data.src.style.width = "100%"
    child_data.extra_dict["edit_width"] = 1
    child_data.src.style.border_bottom_right_radius = None
    child_data.src.style.border_bottom_left_radius = None

def _calc_redpoint_relative_layout(input_tree, redpoint_bubble_list):
    for i, elem in enumerate(redpoint_bubble_list):
        nearest_control = input_tree.parent(elem.data.uid) #取父容器做为基准
        if nearest_control.data.src.style.position is None:
            nearest_control.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
        elem.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.ABSOLUTE)
        elem.data.src.style.top = _to_pt_str(elem.data.y - nearest_control.data.y)
        
        # 检查 nearest_control 排除红点气泡后是否为纵向布局
        if _is_column_layout_without_redpoint(input_tree, nearest_control):
            # 使用相对容器中心+固定偏移量的方式定位
            # 计算红点右边缘相对于容器中心的偏移量
            elem_right_edge = elem.data.x + elem.data.width - nearest_control.data.x
            container_center = nearest_control.data.width / 2
            offset_from_center = elem_right_edge - container_center
            elem.data.src.style.right = f"calc(50% - {_to_pt_str(offset_from_center)})"
        else:
            elem.data.src.style.right = _to_pt_str(nearest_control.data.x + nearest_control.data.width - elem.data.x - elem.data.width)


def _is_column_layout_without_redpoint(input_tree, parent_node):
    """
    检查容器排除红点气泡后是否为纵向布局
    
    Args:
        input_tree: 树结构
        parent_node: 父容器节点
    
    Returns:
        bool: 如果排除红点气泡后为纵向布局返回 True
    """
    children_list = input_tree.children(parent_node.data.uid)
    
    # 排除红点气泡
    non_redpoint_children = [
        child for child in children_list 
        if not component_style_utils.is_redpoint_bubble(child.data)
    ]
    
    # 如果排除后没有子元素或只有一个子元素，不认为是纵向布局
    if len(non_redpoint_children) < 2:
        return False
    
    # 计算布局类型
    layout_type = tree_projection.calc_layout_type(parent_node, non_redpoint_children)
    
    return layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value


# 返回横向列表对齐方式
# ROW_ALIGNMENT_TYPE.LEFT_TO_RIGHT: 从左到右对齐
# ROW_ALIGNMENT_TYPE.RIGHT_TO_LEFT: 从右到左对齐
# ROW_ALIGNMENT_TYPE.SPACE_BETWEEN: 分散对齐
# ROW_ALIGNMENT_TYPE.INVALID: 无效/未知对齐类型

def _get_row_alignment_type(input_tree, parent_node, tree_children_list):
    if len(tree_children_list) <= 1:
        return ai_type_def.ROW_ALIGNMENT_TYPE.INVALID, 0
    elif len(tree_children_list) == 3:
        tmp_layout_type,tmp_index = _left_center_right_layout_calc(input_tree, parent_node, tree_children_list)
        if tmp_layout_type is not None:
            return tmp_layout_type,tmp_index
    first_node = input_tree.get_node(tree_children_list[0].data.uid)
    last_node = input_tree.get_node(tree_children_list[-1].data.uid)
    second_node = input_tree.get_node(tree_children_list[1].data.uid)
    left_gap = first_node.data.x - parent_node.data.x
    right_gap = (parent_node.data.x + parent_node.data.width) - (last_node.data.x + last_node.data.width)
    max_index = 1
    max_space = (second_node.data.x - first_node.data.x - first_node.data.width)
    for i in range(1, len(tree_children_list)):
        current_node = input_tree.get_node(tree_children_list[i].data.uid)
        last_node = input_tree.get_node(tree_children_list[i - 1].data.uid)
        current_space = current_node.data.x - last_node.data.x - last_node.data.width
        if current_space > max_space:
            max_space = current_space
            max_index = i
    if max_space > left_gap and max_space > right_gap and left_gap <= MIN_EDGE_GAP and right_gap <= MIN_EDGE_GAP and max_space > MIN_EDGE_GAP * 1.5:
        return ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN, max_index
    elif first_node.data.x + first_node.data.width/2 > parent_node.data.x + parent_node.data.width/2:
        return ai_type_def.ROW_ALIGNMENT_TYPE.RIGHT_TO_LEFT, max_index
    else:
        return ai_type_def.ROW_ALIGNMENT_TYPE.LEFT_TO_RIGHT, 0
    return ai_type_def.ROW_ALIGNMENT_TYPE.INVALID, 0

# 返回纵向列表对齐方式
# COLUMN_ALIGNMENT_TYPE.TOP_TO_BOTTOM: 从上到下对齐
# COLUMN_ALIGNMENT_TYPE.SPACE_BETWEEN: 分散对齐
# COLUMN_ALIGNMENT_TYPE.INVALID: 无效/未知对齐类型

def _get_column_alignment_type(input_tree, parent_node, tree_children_list):
    """
    判断列布局的垂直对齐类型
    
    条件：
    1. 子元素数量 > 1
    2. 原始高度在 600-1000 之间
    3. 分散对齐条件：
       - max_v_space > top_gap and max_v_space > bottom_gap
       - max_index 的控件中心点位置低于父容器中心点
       - max_v_space > 100
    
    Returns:
        tuple: (对齐类型, 分界点索引)
    """
    if len(tree_children_list) <= 1:
        return ai_type_def.COLUMN_ALIGNMENT_TYPE.INVALID, 0
    
    # 获取原始高度，检查是否在 600-FIGMA_DESIGN_HEIGHT 范围内
    try:
        root_node_data = input_tree.get_node(input_tree.root).data
        origin_height = root_node_data.extra_dict.get("origin_height", 0)
        if not (600 <= origin_height <= 1000):
            return ai_type_def.COLUMN_ALIGNMENT_TYPE.TOP_TO_BOTTOM, 0
    except (AttributeError, KeyError):
        return ai_type_def.COLUMN_ALIGNMENT_TYPE.TOP_TO_BOTTOM, 0
    
    first_node = input_tree.get_node(tree_children_list[0].data.uid)
    last_node = input_tree.get_node(tree_children_list[-1].data.uid)
    second_node = input_tree.get_node(tree_children_list[1].data.uid)
    
    # 计算上下边距
    top_gap = first_node.data.y - parent_node.data.y
    bottom_gap = (parent_node.data.y + parent_node.data.height) - (last_node.data.y + last_node.data.height)
    
    # 计算元素之间的最大垂直间距
    max_index = 1
    max_v_space = (second_node.data.y - first_node.data.y - first_node.data.height)
    for i in range(1, len(tree_children_list)):
        current_node = input_tree.get_node(tree_children_list[i].data.uid)
        prev_node = input_tree.get_node(tree_children_list[i - 1].data.uid)
        current_space = current_node.data.y - prev_node.data.y - prev_node.data.height
        if current_space > max_v_space:
            max_v_space = current_space
            max_index = i
    
    # 判断是否为垂直分散对齐
    # 条件1: 最大间距比顶部和底部大
    # 条件2: max_index 的控件中心点位置低于父容器中心点
    # 条件3: max_v_space > 100
    max_index_node = input_tree.get_node(tree_children_list[max_index].data.uid)
    max_index_node_center = max_index_node.data.y + max_index_node.data.height / 2
    parent_center = parent_node.data.y + parent_node.data.height / 2
    
    if (max_v_space > top_gap and max_v_space > bottom_gap and 
        max_index_node_center > parent_center and 
        max_v_space > 100):
        return ai_type_def.COLUMN_ALIGNMENT_TYPE.SPACE_BETWEEN, max_index
    else:
        return ai_type_def.COLUMN_ALIGNMENT_TYPE.TOP_TO_BOTTOM, 0


def _left_center_right_layout_calc(input_tree, parent_node, tree_children_list):
        left_offset, right_offset, is_equal = calc_first_last_metrics(
            tree_children_list, parent_node.data, epsilon=1.1)
        
        if not is_equal:
            return None, 0
        
        # 检查控件横向间距是否 >= 3
        first_elem = tree_children_list[0].data
        middle_elem = tree_children_list[1].data
        last_elem = tree_children_list[2].data
        
        gap1 = middle_elem.x - (first_elem.x + first_elem.width)  # 第一个和第二个之间的间距
        gap2 = last_elem.x - (middle_elem.x + middle_elem.width)  # 第二个和第三个之间的间距
        
        if gap1 < 3 or gap2 < 3:
            return None, 0
        
        # 计算中间元素的中心偏移
        middle_center = middle_elem.x + middle_elem.width / 2
        parent_center = parent_node.data.x + parent_node.data.width / 2
        center_offset = middle_center - parent_center
        
        if abs(center_offset) <= EPSILON:
            return ai_type_def.ROW_ALIGNMENT_TYPE.LEFT_CENTER_RIGHT, 1
        elif center_offset > EPSILON:
            return ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN, 1
        else:
            return ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN, 2


# ============================================================================
# 非规则布局策略函数
# ============================================================================

def _check_all_children_vertical_center(tree_children_list, parent_center):
    """
    检查所有子元素是否垂直居中
    
    Returns:
        bool: 所有子元素都垂直居中返回 True
    """
    for elem in tree_children_list:
        child_center = elem.data.y + elem.data.height / 2
        if abs(child_center - parent_center) > VERTICAL_EPSILON:
            return False
    return True


def _calc_unregular_row_vertical_align(parent_node, tree_children_list):
    """
    计算非规则行布局的垂直对齐方式
    """
    parent_center = parent_node.data.y + parent_node.data.height / 2
    
    if _check_all_children_vertical_center(tree_children_list, parent_center):
        parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.CENTER)
    else:
        parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)


def _calc_left_center_right_margin(parent_node, tree_children_list):
    """
    计算左中右布局的边距
    """
    # 如果 layout 中已有 padding，直接使用，不重新计算（padding 不能为负）
    left_offset, right_offset, _ = calc_first_last_metrics(
            tree_children_list, parent_node.data)
    parent_node.data.src.style.padding_left = _to_pt_str(max(0, left_offset))
    parent_node.data.src.style.padding_right = _to_pt_str(max(0, right_offset))

    tree_children_list[1].data.src.style.margin_right = "auto"
    tree_children_list[1].data.src.style.margin_left = "auto"


def _calc_left_to_right_margin(elem, prev_elem, parent_node, index):
    """
    计算从左往右布局的边距
    """
    current_style = _ensure_margin(elem.data.src)
    padding_left, _, _, _ = _get_parent_padding(parent_node)
    
    if index == 0:
        metrics = calc_element_metrics(elem.data, parent_node.data)
        # 减去父容器的 padding_left
        effective_margin = metrics.left_margin - padding_left
        current_style.margin_left = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None
    else:
        margin_left = elem.data.x - prev_elem.data.x - prev_elem.data.width
        current_style.margin_left = _to_pt_str(margin_left) if abs(margin_left) >=0.1 else None


def _calc_right_to_left_margin(elem, next_elem, parent_node, index, total_count):
    """
    计算从右往左布局的边距
    """
    current_style = _ensure_margin(elem.data.src)
    _, padding_right, _, _ = _get_parent_padding(parent_node)
    
    if index == total_count - 1:
        metrics = calc_element_metrics(elem.data, parent_node.data)
        # 减去父容器的 padding_right
        effective_margin = metrics.right_margin - padding_right
        current_style.margin_right = _to_pt_str(effective_margin) if abs(effective_margin)>= 0.1 else None
    else:
        margin_right = next_elem.data.x - elem.data.x - elem.data.width
        current_style.margin_right = _to_pt_str(margin_right)


def _calc_unregular_row_horizontal_margins(input_tree, parent_node, tree_children_list):
    """
    计算非规则行布局的水平边距
    """
    align_type, justified_start_index = _get_row_alignment_type(
        input_tree, parent_node, tree_children_list)
    if align_type == ai_type_def.ROW_ALIGNMENT_TYPE.RIGHT_TO_LEFT:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_END)
    else:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)
    # 左中右布局特殊处理
    if align_type == ai_type_def.ROW_ALIGNMENT_TYPE.LEFT_CENTER_RIGHT:
        _calc_left_center_right_margin(parent_node, tree_children_list)
        # 尝试去除符合条件的文本宽度
        for elem in tree_children_list:
            remove_text_width_in_row(input_tree, elem.data.uid)

        return
    
    # 处理每个子元素的边距
    total_count = len(tree_children_list)
    for i, elem in enumerate(tree_children_list):
        prev_elem = tree_children_list[i - 1] if i > 0 else None
        next_elem = tree_children_list[i + 1] if i < total_count - 1 else None
        
        # SPACE_BETWEEN 分界点设置 auto
        if align_type == ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN and i == justified_start_index:
            current_style = _ensure_margin(elem.data.src)
            current_style.margin_left = "auto"
        
        # 从左往右布局
        is_left_to_right = (
            align_type == ai_type_def.ROW_ALIGNMENT_TYPE.LEFT_TO_RIGHT or 
            (align_type == ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN and i < justified_start_index)
        )
        if is_left_to_right:
            _calc_left_to_right_margin(elem, prev_elem, parent_node, i)
        
        # 从右往左布局
        is_right_to_left = (
            align_type == ai_type_def.ROW_ALIGNMENT_TYPE.RIGHT_TO_LEFT or 
            (align_type == ai_type_def.ROW_ALIGNMENT_TYPE.SPACE_BETWEEN and i >= justified_start_index)
        )
        if is_right_to_left:
            _calc_right_to_left_margin(elem, next_elem, parent_node, i, total_count)
    
    # 尝试去除符合条件的文本宽度
    for elem in tree_children_list:
        remove_text_width_in_row(input_tree, elem.data.uid)


def _calc_unregular_row_vertical_margins(parent_node, tree_children_list):
    """
    计算非规则行布局的垂直边距（当不居中时）
    """
    align_items = parent_node.data.src.style.align_items

    if align_items == flex_enum_to_str(dsl_enum.AlignItems.FLEX_START):
        _, _, padding_top, _ = _get_parent_padding(parent_node)

        for elem in tree_children_list:
            metrics = calc_element_metrics(elem.data, parent_node.data)
            current_style = _ensure_margin(elem.data.src)
            # 减去父容器的 padding_top
            effective_margin = metrics.top_margin - padding_top
            current_style.margin_top = _to_pt_str(effective_margin) if abs(effective_margin) >=0.1 else None

    elif align_items == flex_enum_to_str(dsl_enum.AlignItems.FLEX_END):
        _, _, _, padding_bottom = _get_parent_padding(parent_node)

        for elem in tree_children_list:
            metrics = calc_element_metrics(elem.data, parent_node.data)
            current_style = _ensure_margin(elem.data.src)
            # 减去父容器的 padding_bottom
            effective_margin =  metrics.bottom_margin - padding_bottom
            current_style.margin_bottom = _to_pt_str(effective_margin) if abs(effective_margin)>=0.1 else None


def _calc_unregular_row_layout(input_tree, parent_node, tree_children_list):
    """
    非规则行布局策略
    """
    # 设置基本 flex 属性
    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.ROW)

    # 1. 计算垂直对齐方式
    _calc_unregular_row_vertical_align(parent_node, tree_children_list)

    # 2. 计算水平间距
    _calc_unregular_row_horizontal_margins(input_tree, parent_node, tree_children_list)
    
    # 3. 计算垂直边距（当不居中时）
    _calc_unregular_row_vertical_margins(parent_node, tree_children_list)
    
    return True


def _filter_redpoint_children(tree_children_list):
    """
    过滤掉红点和气泡元素
    """
    return [
        elem for elem in tree_children_list
        if elem.data.ai_type not in [
            ai_type_def.AI_TYPE.BUBBLE.value,
            ai_type_def.AI_TYPE.RED_POINT.value
        ]
    ]


def _calc_column_vertical_margins(elem, prev_elem, parent_node, index, align_type=None, justified_start_index=0, total_count=0, next_elem=None):
    """
    计算列布局的垂直边距
    
    Args:
        elem: 当前元素
        prev_elem: 前一个元素
        parent_node: 父节点
        index: 当前元素索引
        align_type: 对齐类型（可选）
        justified_start_index: 分散对齐的分界点索引（可选）
        total_count: 总元素数量（可选）
        next_elem: 下一个元素（可选）
    """
    current_style = _ensure_margin(elem.data.src)
    _, _, padding_top, padding_bottom = _get_parent_padding(parent_node)
    
    # 分散对齐时，分界点及之后的元素特殊处理
    if align_type == ai_type_def.COLUMN_ALIGNMENT_TYPE.SPACE_BETWEEN and index >= justified_start_index:
        # 在分界点设置 margin_top = "auto"
        if index == justified_start_index:
            current_style.margin_top = "auto"
        
        # 计算 margin_bottom：最后一个元素计算到父容器底部的间距，其他元素计算与下一个元素的间距
        if index == total_count - 1:
            metrics = calc_element_metrics(elem.data, parent_node.data)
            # 减去父容器的 padding_bottom
            effective_margin =  metrics.bottom_margin - padding_bottom
            current_style.margin_bottom = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None
        elif next_elem is not None:
            margin_bottom = next_elem.data.y - elem.data.y - elem.data.height
            current_style.margin_bottom = _to_pt_str(margin_bottom)
        return
    
    # 默认从上到下布局
    if index == 0:
        metrics = calc_element_metrics(elem.data, parent_node.data)
        # 减去父容器的 padding_top
        effective_margin = metrics.top_margin - padding_top
        current_style.margin_top = _to_pt_str(effective_margin) if abs(effective_margin) >=0.1  else None
    else:
        margin_top = elem.data.y - prev_elem.data.y - prev_elem.data.height
        current_style.margin_top = _to_pt_str(margin_top) if margin_top > 0 else None


def _calc_column_horizontal_align(elem, parent_node):
    """
    计算列布局中单个元素的水平对齐方式
    
    Returns:
        str or None: 'left', 'right', 或 None (居中)
    """
    parent_center = parent_node.data.x + parent_node.data.width / 2
    elem_center = elem.data.x + elem.data.width / 2
    offset = elem_center - parent_center
    if abs(offset) <= 2:
        return None
    elif offset >= LEFT_RIGHT_THROLD:
        return 'right'
    return 'left'
def _calc_row_gap(parent_node, filtered_children):
      row_gap_value = parent_node.data.src.style.row_gap
      if row_gap_value is not None:
        return row_gap_value
      if len(filtered_children) >= 2:
            gaps = []
            for i in range(1, len(filtered_children)):
                prev_elem = filtered_children[i - 1]
                curr_elem = filtered_children[i]
                gap = curr_elem.data.y - (prev_elem.data.y + prev_elem.data.height)
                gaps.append(gap)
            if gaps:
                gap_min, gap_max = min(gaps), max(gaps)
                # 纵向间距差距 <= 1 则视为相等，计算 row_gap（取均值）
                if gap_max - gap_min <= 1 and gap_min > 0:
                    row_gap_value = sum(gaps) / len(gaps)
                    _logger.debug(f"列布局纵向间距差距<=1，计算得到 row_gap: {row_gap_value}px")
                    return row_gap_value
      return None


def _calc_unregular_column_layout(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    """
    非规则列布局策略
    
    优化：
    1. 计算所有子控件到父容器的最小左间距
    2. 找出所有左右间距相等的子控件，取最小边距
    3. 满足条件时设置父容器 padding，子元素 margin 减去 padding
    4. 处理 row_gap：不从 layout 取，仅当容器纵向间距差距 <= 1 时计算 row_gap
    """
    # 设置基本 flex 属性
    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.COLUMN)
    parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)
    parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.CENTER)

    # 过滤红点元素
    filtered_children = _filter_redpoint_children(tree_children_list)

    # 计算并设置父容器的 padding；设计稿宽度从根节点取（等同 Metadata.width）
    root = input_tree.get_node(input_tree.root) if input_tree else None
    design_width = float(root.data.width) if root and root.data else None
    padding_left, padding_right, padding_top, padding_bottom, should_set_padding = _calc_column_container_padding(parent_node, filtered_children, design_width)
    if should_set_padding:
        # 如果 layout 中已有 padding，直接使用，不重新设置
            if padding_top > 0:
                parent_node.data.src.style.padding_top = _to_pt_str(padding_top)
            if padding_right > 0:
                parent_node.data.src.style.padding_right = _to_pt_str(padding_right)
            if padding_bottom > 0:
                parent_node.data.src.style.padding_bottom = _to_pt_str(padding_bottom)
            if padding_left > 0:
                parent_node.data.src.style.padding_left = _to_pt_str(padding_left)
            _logger.debug(f"列布局设置 padding: top={padding_top}, right={padding_right}, bottom={padding_bottom}, left={padding_left}px")
    
    # 不从 layout 取 row_gap，仅当容器纵向间距差距 <= 1 时计算 row_gap
    row_gap_value = _calc_row_gap(parent_node, filtered_children)
    parent_node.data.src.style.row_gap = _to_pt_str(row_gap_value)
    # 获取垂直对齐类型
    align_type, justified_start_index = _get_column_alignment_type(
        input_tree, parent_node, filtered_children)
    
    total_count = len(filtered_children)
    
    # 处理每个子元素
    for i, elem in enumerate(filtered_children):
        prev_elem = filtered_children[i - 1] if i > 0 else None
        next_elem = filtered_children[i + 1] if i < total_count - 1 else None
        
        # 如果有 row_gap，则不需要计算控件之间的 margin 值
        if row_gap_value is None or row_gap_value == 0:
            # 1. 计算垂直边距（支持分散对齐）
            _calc_column_vertical_margins(
                elem, prev_elem, parent_node, i,
                align_type=align_type,
                justified_start_index=justified_start_index,
                total_count=total_count,
                next_elem=next_elem
            )
        else:
            # 如果有 row_gap，只计算第一个元素的 margin_top（相对于父容器顶部）
            if i == 0:
                metrics = calc_element_metrics(elem.data, parent_node.data)
                current_style = _ensure_margin(elem.data.src)
                # 减去父容器的 padding_top
                effective_margin = metrics.top_margin - padding_top
                current_style.margin_top = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None
        
        # 2. 尝试自适应宽度布局,内部已经完成了有效的margin_left 和margin_right 计算
        if _calc_no_width_layout(input_tree, elem.data.uid, context_share_data):
            # 如果父容器设置了 padding，需要修正 _calc_no_width_layout 设置的 margin
                current_style = elem.data.src.style
                if current_style is not None:
                    # 修正 width 中的 calc 值
                    if current_style.width is not None and 'calc' in str(current_style.width):
                        # 原来的 width 是 calc(100% - 32px)，现在父容器有 padding
                        # 需要修正为 calc(100% - 0px) 或 100%
                        metrics = calc_element_metrics(elem.data, parent_node.data)
                        total_margin = metrics.left_margin + metrics.right_margin
                        new_total = total_margin - padding_left - padding_right
                        if new_total <= 0:
                            current_style.width = "100%"
                        else:
                            current_style.width = f"calc(100% - {new_total}px)"
        else:
            # 3. 计算水平对齐
            align_direction = _calc_column_horizontal_align(elem, parent_node)
            current_style = _ensure_margin(elem.data.src)
            metrics = calc_element_metrics(elem.data, parent_node.data)

            # 如果父容器设置了 padding，计算 margin 时需要减去 padding
            # 使用之前计算好的 padding 值
            effective_left_margin = max(0, metrics.left_margin - padding_left)
            effective_right_margin = max(0, metrics.right_margin - padding_right)

            if align_direction == 'right':
                    current_style.align_self = flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
                    if effective_right_margin > 0:
                        current_style.margin_right = _to_pt_str(effective_right_margin)
            elif align_direction == 'left':
                current_style.align_self = flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
                if effective_left_margin > 0:
                    current_style.margin_left = _to_pt_str(effective_left_margin)
    
    return True


def _calc_one_elem_flex_layout(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.COLUMN)
    _remove_text_height(input_tree, tree_children_list[0].data.uid, context_share_data)
    child_elem = tree_children_list[0]
    # 优先检查是否可以通过设置父容器的 padding 来替代子元素的 margin
    # 条件：子元素左右边距相等且在合理范围内；设计稿宽度从根节点取（等同 Metadata.width）
    root = input_tree.get_node(input_tree.root) if input_tree else None
    design_width = float(root.data.width) if root and root.data else None
    padding_left, padding_right, padding_top, padding_bottom,should_set_padding = _calc_column_container_padding(parent_node,tree_children_list, design_width)
    if should_set_padding:
        # 如果 layout 中已有 padding，直接使用，不重新设置
            if padding_top > 0:
                parent_node.data.src.style.padding_top = _to_pt_str(padding_top)
            if padding_right > 0:
                parent_node.data.src.style.padding_right = _to_pt_str(padding_right)
            if padding_bottom > 0:
                parent_node.data.src.style.padding_bottom = _to_pt_str(padding_bottom)
            if padding_left > 0:
                parent_node.data.src.style.padding_left = _to_pt_str(padding_left)
            _logger.debug(f"列布局设置 padding: top={padding_top}, right={padding_right}, bottom={padding_bottom}, left={padding_left}px")
    if _calc_no_width_layout(input_tree, child_elem.data.uid, context_share_data) == False:
        if abs(child_elem.data.x + child_elem.data.width / 2 - parent_node.data.x - parent_node.data.width / 2) <= 1 and abs(
            child_elem.data.x - parent_node.data.x) > 0:
            parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.CENTER)
        elif child_elem.data.x + child_elem.data.width / 2 < parent_node.data.x + parent_node.data.width / 2:
            parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
            margin_left = child_elem.data.x - parent_node.data.x
            effective_margin = margin_left - padding_left
            child_elem.data.src.style.margin_left = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None
        else:
            parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
            margin_right = parent_node.data.x + parent_node.data.width - child_elem.data.x - child_elem.data.width
            effective_margin = margin_right - padding_right
            child_elem.data.src.style.margin_right = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None

    margin_bottom = parent_node.data.y + parent_node.data.height - child_elem.data.y - child_elem.data.height
    margin_top = child_elem.data.y - parent_node.data.y

    if abs(child_elem.data.y + child_elem.data.height / 2 - parent_node.data.y - parent_node.data.height / 2) <= 1 and abs(
        child_elem.data.y - parent_node.data.y) > 0:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.CENTER)
    elif abs(margin_bottom) <= abs(margin_top):  # 有子节点超出父节点的情况
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_END)
        effective_margin = margin_bottom - padding_bottom
        child_elem.data.src.style.margin_bottom = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None
    else:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)
        effective_margin =  margin_top - padding_top
        child_elem.data.src.style.margin_top = _to_pt_str(effective_margin) if abs(effective_margin) >= 0.1 else None

# ============================================================================
# 布局策略函数
# ============================================================================

def _set_vertical_align(parent_node, tree_children_list, y_list, height_list):

    _calc_unregular_row_vertical_align(parent_node, tree_children_list)
    # 计算垂直边距（当不居中时）
    _calc_unregular_row_vertical_margins(parent_node, tree_children_list)

def _get_vision_x_bounds(input_tree, node_uid, node_data):
    """
    计算节点在视觉上的左右 x 边界（用于计算两元素视觉间距）。
    若是透明容器：vision_x_left 为内部元素 x 最小值，vision_x_right 为内部元素 (x+width-1) 的最大值；
    否则使用节点自身的 x 与 x+width-1。
    Returns:
        (vision_x_left, vision_x_right)
    """
    if node_data.src and component_style_utils.is_transparent_container(node_data.src):
        children = input_tree.children(node_uid)
        if not children:
            return node_data.x, node_data.x + node_data.width - 1
        xs = [c.data.x for c in children]
        rights = [c.data.x + c.data.width - 1 for c in children]
        return min(xs), max(rights)
    return node_data.x, node_data.x + node_data.width - 1

def _calc_row_two_children_layout(input_tree, parent_node, tree_children_list, y_list, height_list):
    """
    计算只有2个子元素的行布局
    
    Returns:
        True: 成功计算布局
        False: 需要使用非规则布局
    """
    # 计算两个元素的度量信息
    first_metrics = calc_element_metrics(tree_children_list[0].data, parent_node.data)
    second_metrics = calc_element_metrics(tree_children_list[1].data, parent_node.data)
    
    # 检查是否存在一个居中元素和一个非居中元素
    first_center = first_metrics.is_horizontal_center
    second_center = second_metrics.is_horizontal_center
    
    # 当一个元素居中，另一个元素不居中时，采用混合布局
    if first_center != second_center:
        return _calc_center_with_absolute_layout(
            input_tree, parent_node, tree_children_list, 
            first_metrics, second_metrics, first_center, y_list, height_list
        )
    
    left_offset, right_offset, is_equal = calc_first_last_metrics(
        tree_children_list, parent_node.data)
    # 视觉间距：透明容器用内部元素边界，否则用节点自身边界
    v_left_0, v_right_0 = _get_vision_x_bounds(
        input_tree, tree_children_list[0].data.uid, tree_children_list[0].data)
    v_left_1, v_right_1 = _get_vision_x_bounds(
        input_tree, tree_children_list[1].data.uid, tree_children_list[1].data)
    vision_space_gap = v_left_1 - v_right_0

    # 左右间距相等且两元素视觉间距>=3时使用space-between；设计稿宽度从根节点取（等同 Metadata.width）
    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.ROW)
    root = input_tree.get_node(input_tree.root) if input_tree else None
    design_width = float(root.data.width) if root and root.data else None
    adjust_min = get_adjust_width_min(design_width)
    use_space_between = (
        vision_space_gap >= 3 and parent_node.data.width > adjust_min
        and tree_children_list[0].data.x + tree_children_list[0].data.width / 2 < parent_node.data.x + parent_node.data.width / 2
        and tree_children_list[1].data.x + tree_children_list[1].data.width / 2 > parent_node.data.x + parent_node.data.width / 2
    )
    # 特殊 case：左边是小图片(<=18)、右边是文本/富文本、两者间距<=8 时，不使用 SPACE_BETWEEN
    first_elem = tree_children_list[0].data
    second_elem = tree_children_list[1].data
    first_src = getattr(first_elem, 'src', None)
    second_src = getattr(second_elem, 'src', None)
    if use_space_between and first_src and second_src:
        second_type = getattr(second_src, 'type', None)
        is_small_image_left = (
             first_elem.width <= 18
        )
        is_text_right = second_type in (
            dsl_enum.ComponentType.TEXT.value,
            dsl_enum.ComponentType.CONTAINER_RICH.value,
        )
        if is_small_image_left and is_text_right and vision_space_gap <= 8:
            use_space_between = False

    if use_space_between:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.SPACE_BETWEEN)
        # 设置左右边距（需要减去父容器的 padding）
        if left_offset != 0 or right_offset != 0:
            padding_left, padding_right, _, _ = _get_parent_padding(parent_node)
            margin0 = _ensure_margin(tree_children_list[0].data.src)
            # 减去父容器的 padding_left
            effective_left_margin = max(0, left_offset - padding_left)
            margin0.margin_left = _to_pt_str(effective_left_margin) if effective_left_margin > 0 else None

            margin_last = _ensure_margin(tree_children_list[-1].data.src)
            # 减去父容器的 padding_right
            effective_right_margin = max(0, right_offset - padding_right)
            margin_last.margin_right = _to_pt_str(effective_right_margin) if effective_right_margin > 0 else None
    else:
        first_center_x = tree_children_list[0].data.x + tree_children_list[0].data.width / 2
        parent_center_x = parent_node.data.x + parent_node.data.width / 2

        if first_center_x > parent_center_x :
            parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_END)
            _calc_right_to_left_margin(tree_children_list[0], tree_children_list[1], parent_node, 0, 2)
            _calc_right_to_left_margin(tree_children_list[1], None, parent_node, 1, 2)
        else:
            parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)
            _calc_left_to_right_margin(tree_children_list[0], None, parent_node, 0)
            _calc_left_to_right_margin(tree_children_list[1], tree_children_list[0], parent_node, 1)

    # 设置垂直对齐
    _set_vertical_align(parent_node, tree_children_list, y_list, height_list)
    return True


def _calc_center_with_absolute_layout(input_tree, parent_node, tree_children_list, 
                                       first_metrics, second_metrics, first_is_center,
                                       y_list, height_list):
    """
    处理一个元素居中、另一个元素居左或居右的混合布局
    
    居中元素使用 flex 布局始终居中，非居中元素使用绝对布局
    
    Args:
        input_tree: 树结构
        parent_node: 父节点
        tree_children_list: 子元素列表
        first_metrics: 第一个元素的度量信息
        second_metrics: 第二个元素的度量信息
        first_is_center: 第一个元素是否居中
        y_list: y坐标列表
        height_list: 高度列表
    
    Returns:
        True: 成功计算布局
    """
    # 确定居中元素和非居中元素
    if first_is_center:
        absolute_elem = tree_children_list[1]
        absolute_metrics = second_metrics
    else:
        absolute_elem = tree_children_list[0]
        absolute_metrics = first_metrics
    
    # 父容器设置为 relative 和 flex 居中
    if  parent_node.data.src.style.position is None:
        parent_node.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)
    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.ROW)
    parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.CENTER)
    
    # 设置垂直对齐
    _set_vertical_align(parent_node, tree_children_list, y_list, height_list)
    
    # 非居中元素使用绝对布局
    absolute_elem.data.src.style.position = flex_enum_to_str(dsl_enum.PositionType.ABSOLUTE)
    
    # 获取父容器的 padding，绝对定位需要考虑 padding
    padding_left, padding_right, padding_top, _ = _get_parent_padding(parent_node)
    
    # 减去父容器的 padding_top
    effective_top_margin = max(0, absolute_metrics.top_margin - padding_top)
    absolute_elem.data.src.style.top = _to_pt_str(effective_top_margin) if effective_top_margin > 0 else None
    
    # 判断非居中元素是居左还是居右
    if absolute_metrics.left_margin < absolute_metrics.right_margin:
        # 居左，减去父容器的 padding_left
        absolute_elem.data.src.style.left = _to_pt_str(absolute_metrics.left_margin)
    else:
        absolute_elem.data.src.style.right = _to_pt_str( absolute_metrics.right_margin)
    
    return True


def _is_row_table_like(tree_children_list, margin_x_list):
    """
    判断一行连续元素是否为表格形态。
    条件：元素横向 margin 都相等且 <= 1，且每个元素有边框或背景色。
    """
    if not margin_x_list or len(tree_children_list) < 2:
        return False
    # 横向 margin 都 <= 1 且相等（方差为 0 或极小）
    if numpy.max(margin_x_list) > 2 or numpy.min(margin_x_list) < 0.5:
        return False

    # 每个元素有边框或背景色
    for elem in tree_children_list:
        src = getattr(elem.data, "src", None)
        if not src:
            return False
        style = getattr(src, "style", None)
        if not style:
            return False
        has_border = component_style_utils.have_border(src)
        has_bg = bool(getattr(style, "background_color", None))
        if not (has_border or has_bg):
            return False
    return True


def _calc_row_uniform_spacing(parent_node, tree_children_list, margin_x_list):
    """
    计算均匀间距的行布局 (space-around 或 space-between)
    """
    left_offset, right_offset, is_equal = calc_first_last_metrics(
        tree_children_list, parent_node.data)
    
    # 判断使用 space-around 还是 space-between
    if is_equal and abs(left_offset * 2 - margin_x_list[0]) <= 1:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.SPACE_AROUND)
    else:
        parent_node.data.src.style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.SPACE_BETWEEN)
        if left_offset != 0 or right_offset != 0:
            # 减去父容器的 padding，margin 为相对父内容区的有效值
            padding_left, padding_right, _, _ = _get_parent_padding(parent_node)
            margin0 = _ensure_margin(tree_children_list[0].data.src)
            effective_left_margin = max(0, left_offset - padding_left)
            margin0.margin_left = _to_pt_str(effective_left_margin) if effective_left_margin > 0 else None
            margin_last = _ensure_margin(tree_children_list[-1].data.src)
            effective_right_margin = max(0, right_offset - padding_right)
            margin_last.margin_right = _to_pt_str(effective_right_margin) if effective_right_margin > 0 else None

def _calc_split_line_container_layout(input_tree, parent_node, tree_children_list):
    """
    处理包含分割线的容器布局
    
    当内部有分割线时：
    1. 父容器宽度设置为自适应，左右间距固定
    2. 内部非分割线的元素宽度等分
    """
    # 分离分割线和非分割线元素
    split_line_elements = []
    non_line_elements = []
    
    for elem in tree_children_list:
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            split_line_elements.append(elem)
        else:
            non_line_elements.append(elem)
    # 设置父容器为 flex 行布局
    parent_style = parent_node.data.src.style
    parent_style.align_items = flex_enum_to_str(dsl_enum.AlignItems.CENTER)
    parent_style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)

    parent_style.width = "100%"
    parent_node.data.extra_dict["edit_width"] = 1


    _calc_unregular_row_vertical_align(parent_node, tree_children_list)
    #  计算垂直边距（当不居中时）
    _calc_unregular_row_vertical_margins(parent_node, tree_children_list)

    # 计算非分割线元素的等分宽度百分比
    if len(non_line_elements) > 0:
        width_percent = round(100 / len(non_line_elements), 2)
        
        for elem in non_line_elements:
            elem.data.src.style.width = f"{width_percent}%"
            elem.data.extra_dict["edit_width"] = 1
    
    # 分割线使用固定宽度
    for elem in split_line_elements:
        elem.data.src.style.width = _to_pt_str(elem.data.width)


def _calc_row_layout_fixed_column_gap(input_tree, parent_node, tree_children_list):
    """
    column_gap 固定时的行布局：根据固定 gap 计算水平坐标（首尾 margin），设置 flex 与垂直对齐。
    调用前需保证 parent_node.data.src.style.column_gap 已设置且可解析为数值。

    Returns:
        True: 已按固定 gap 完成布局
    """
    style = getattr(parent_node.data.src, "style", None)
    column_gap_str = getattr(style, "column_gap", None) if style else None
    if not style or column_gap_str is None or len(tree_children_list) < 2:
        return False
    gap_val = _parse_px_value(column_gap_str, 0.0)

    parent_node.data.src.style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.ROW)
    _calc_unregular_row_vertical_align(parent_node, tree_children_list)

    padding_left, padding_right, _, _ = _get_parent_padding(parent_node)
    left_offset, right_offset, _ = calc_first_last_metrics(tree_children_list, parent_node.data)
    effective_left  = float(left_offset) - float(padding_left)
    effective_right = float(right_offset) - float(padding_right)

    first_style = _ensure_margin(tree_children_list[0].data.src)
    first_style.margin_left = _to_pt_str(effective_left) if effective_left >= 0.1 else None
    last_style = _ensure_margin(tree_children_list[-1].data.src)
    last_style.margin_right = _to_pt_str(effective_right) if effective_right >= 0.1 else None

    _calc_unregular_row_vertical_margins(parent_node, tree_children_list)
    for elem in tree_children_list:
        remove_text_width_in_row(input_tree, elem.data.uid)
    return True


def _calc_row_layout_strategy(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    """
    ROW 布局策略
    
    Returns:
        True: 成功计算布局
        False: 无法计算布局
    """
    # 收集子元素的位置信息
    y_list = []
    height_list = []
    width_list = []
    margin_x_list = []
    # 过滤红点元素
    filtered_children = _filter_redpoint_children(tree_children_list)

    # 计算并设置父容器的 padding（四个方向）；设计稿宽度从根节点取（等同 Metadata.width）
    root = input_tree.get_node(input_tree.root) if input_tree else None
    design_width = float(root.data.width) if root and root.data else None
    padding_left, padding_right, padding_top, padding_bottom, should_set_padding = _calc_row_container_padding(
        parent_node, filtered_children, design_width)
    if should_set_padding:
        if padding_top > 0:
            parent_node.data.src.style.padding_top = _to_pt_str(padding_top)
        if padding_right > 0:
            parent_node.data.src.style.padding_right = _to_pt_str(padding_right)
        if padding_bottom > 0:
            parent_node.data.src.style.padding_bottom = _to_pt_str(padding_bottom)
        if padding_left > 0:
            parent_node.data.src.style.padding_left = _to_pt_str(padding_left)
        _logger.debug(
            f"两子元素行布局设置 padding: top={padding_top}, right={padding_right}, bottom={padding_bottom}, left={padding_left}px")


    if  parent_node.data.extra_dict.get("list_type") == ai_type_def.LIST_TYPE.VERTICAL_SPLIT_LIST.value:
        _calc_split_line_container_layout(input_tree, parent_node, tree_children_list)
        return True

    for i, elem in enumerate(tree_children_list):

        y_list.append(elem.data.y)
        width_list.append(elem.data.width)
        height_list.append(elem.data.height)
        
        if i >= 1:
            margin_x = (tree_children_list[i].data.x - 
                       tree_children_list[i - 1].data.x - tree_children_list[i - 1].data.width + 1)
            margin_x_list.append(margin_x)

    # 2个子元素特殊处理
    if len(tree_children_list) == 2:
        if _calc_row_two_children_layout(input_tree, parent_node, tree_children_list, y_list, height_list):
            for elem in tree_children_list:
                remove_text_width_in_row(input_tree, elem.data.uid)
            return True

    # style.column_gap 已设置时，使用固定 gap 的行布局坐标计算
    if getattr(parent_node.data.src.style, "column_gap", None) is not None:
        if _calc_row_layout_fixed_column_gap(input_tree, parent_node, tree_children_list):
            return True

    var_margin = numpy.var(margin_x_list)
    margin_mean = numpy.mean(margin_x_list)
    margin_min = numpy.min(margin_x_list)
    
    # 计算是否满足 uniform spacing 的条件
    can_use_uniform_spacing = False
    if var_margin <= SPACE_BETWEEN_MAX_VAR :
        if len(tree_children_list) == 2:
            # 2个元素时：最右边元素的中心距离 > 父容器中心距离
            last_elem = tree_children_list[-1]
            last_elem_center = last_elem.data.x + last_elem.data.width / 2
            parent_center = parent_node.data.x + parent_node.data.width / 2
            can_use_uniform_spacing = last_elem_center > parent_center
        elif len(tree_children_list) >= 3:
            # >= 3个元素时：最左边元素左边距和最右边元素右边距差值 <= 3
            left_offset, right_offset, _ = calc_first_last_metrics(tree_children_list, parent_node.data)
            can_use_uniform_spacing = abs(left_offset - right_offset) <= 3
    
    is_table = _is_row_table_like(tree_children_list, margin_x_list)
    if (can_use_uniform_spacing or parent_node.data.ai_type == ai_type_def.AI_TYPE.BOTTOM_BAR.value)  and not is_table:
        # 设置垂直对齐
        _set_vertical_align(parent_node, tree_children_list, y_list, height_list)
        # 计算横坐标布局
        #  计算水平边距间距均匀情况且间距>1dp 才用space-around和space-between
        return _calc_row_uniform_spacing(parent_node, tree_children_list, margin_x_list)

    return _calc_unregular_row_layout(input_tree, parent_node, tree_children_list)

def _calc_column_layout_strategy(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    """
    COLUMN 布局策略
    纵向分布不用 space-between，移动端都是上往下流式布局
    
    Returns:
        True: 成功计算布局
        False: 无法计算布局
    """
    return _calc_unregular_column_layout(input_tree, parent_node, tree_children_list, context_share_data)


def _calc_row_gaps_mode(tree_children_list, row_cnt):
    """
    计算每行元素纵向间距的众数
    
    Returns:
        float: row-gap 的众数
    """
    if row_cnt <= 0 or len(tree_children_list) <= row_cnt:
        return 0
    
    row_gaps = []
    for i in range(row_cnt, len(tree_children_list)):
        gap = (tree_children_list[i].data.y - 
               tree_children_list[i - row_cnt].data.y - 
               tree_children_list[i - row_cnt].data.height)
        row_gaps.append(round(gap, 1))
    
    if not row_gaps:
        return 0
    
    # 计算众数
    gap_counter = Counter(row_gaps)
    mode_gap = gap_counter.most_common(1)[0][0] if gap_counter else row_gaps[0]
    return mode_gap


def _calc_grid_layout_strategy(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    """
    GRID 布局策略
    
    Returns:
        True: 成功计算布局
        False: 无法计算布局
    """
    # 收集子元素信息
    y_list = []
    width_list = []
    height_list = []
    row_cnt = 0  # 每行元素数量 (column_cnt)
    
    for i, elem in enumerate(tree_children_list):
        # 检测换行位置
        if i > 0 and row_cnt == 0 and tree_children_list[i].data.x < tree_children_list[i - 1].data.x:
            row_cnt = i
        
        y_list.append(elem.data.y)
        width_list.append(elem.data.width)
        height_list.append(elem.data.height)
    
    # 判断是否为列表
    calc_list_layout.judge_list(input_tree, parent_node, width_list, height_list)
    
    # 检测高度异常且发生重叠的元素，对其使用绝对布局
    # 找出最常见的高度（众数）作为"正常"高度
    height_counter = Counter([round(h, 1) for h in height_list])
    normal_height = height_counter.most_common(1)[0][0] if height_counter else height_list[0]
    
    # 找出高度异常的元素索引
    abnormal_indices = []
    for i, elem in enumerate(tree_children_list):
        if abs(round(elem.data.height, 1) - normal_height) > 2:
            abnormal_indices.append(i)
    
    # 检查高度异常的元素是否与其他元素重叠
    absolute_layout_elements = []
    normal_layout_elements = []
    
    for i, elem in enumerate(tree_children_list):
        if i in abnormal_indices:
            # 检查是否与其他元素重叠
            is_overlapping = False
            for j, other_elem in enumerate(tree_children_list):
                if i != j:
                    # 检查两个元素是否在垂直方向上重叠
                    elem_top = elem.data.y
                    elem_bottom = elem.data.y + elem.data.height
                    other_top = other_elem.data.y
                    other_bottom = other_elem.data.y + other_elem.data.height
                    
                    # 检查两个元素是否在水平方向上重叠
                    elem_left = elem.data.x
                    elem_right = elem.data.x + elem.data.width
                    other_left = other_elem.data.x
                    other_right = other_elem.data.x + other_elem.data.width
                    
                    horizontal_overlap = not (elem_right <= other_left or elem_left >= other_right)
                    vertical_overlap = not (elem_bottom <= other_top or elem_top >= other_bottom)
                    
                    if horizontal_overlap and vertical_overlap:
                        is_overlapping = True
                        break
            
            if is_overlapping:
                absolute_layout_elements.append(elem)
            else:
                normal_layout_elements.append(elem)
        else:
            normal_layout_elements.append(elem)
    
    # 对重叠的异常高度元素使用绝对布局
    if absolute_layout_elements:
        _calc_absolute_layout(input_tree, parent_node, absolute_layout_elements)
    
    # 如果没有正常布局的元素，直接返回
    if not normal_layout_elements:
        return True
    
    # 使用正常布局元素继续处理
    tree_children_list = normal_layout_elements
    
    # 重新计算 row_cnt（因为可能有元素被移到绝对布局）
    row_cnt = 0
    height_list = []
    for i, elem in enumerate(tree_children_list):
        if i > 0 and row_cnt == 0 and tree_children_list[i].data.x < tree_children_list[i - 1].data.x:
            row_cnt = i
        height_list.append(elem.data.height)

    if row_cnt == 0:
        _logger.warning('行计数为0')
        return True
    
    # 如果 layout 中已有 padding，直接使用
    if _has_layout_padding(parent_node):
        padding_left, padding_right, padding_top, _ = _get_parent_padding(parent_node)
        left_padding = padding_left
        right_padding = padding_right
        top_padding = padding_top
    else:
        # 计算左右 padding
        left_padding = tree_children_list[0].data.x - parent_node.data.x
        last_elem_in_first_row = tree_children_list[row_cnt - 1]
        right_padding = (parent_node.data.x + parent_node.data.width) - (last_elem_in_first_row.data.x + last_elem_in_first_row.data.width)
        
        # 设置 top padding
        top_padding = tree_children_list[0].data.y - parent_node.data.y
    
    # 计算 row-gap 的众数
    row_gap_mode = _calc_row_gaps_mode(tree_children_list, row_cnt)
    
    # 计算 column-gap（第一行元素之间的间距众数）
    column_gap_mode = 0
    if row_cnt > 1:
        first_row_gaps = []
        for i in range(1, row_cnt):
            gap = tree_children_list[i].data.x - (tree_children_list[i-1].data.x + tree_children_list[i-1].data.width)
            first_row_gaps.append(round(gap, 1))
        if first_row_gaps:
            column_gap_mode = Counter(first_row_gaps).most_common(1)[0][0]

    # 设置容器 padding
    parent_style = parent_node.data.src.style
    if left_padding > 0:
        parent_style.padding_left = _to_pt_str(left_padding)
    if right_padding > 0:
        parent_style.padding_right = _to_pt_str(right_padding)
    if top_padding > 0:
        parent_style.padding_top = _to_pt_str(top_padding)
    
    # 判断第一个子元素是否为透明容器
    first_elem = tree_children_list[0]
    is_transparent = component_style_utils.is_transparent_container(first_elem.data.src)
    
    # 判断是否使用固定宽度：row_gap <= 2 且 column_gap <= 2
    use_fixed_width = row_gap_mode <= 2 and column_gap_mode <= 2
    
    # 判断是否满足 grid 布局条件：
    # 1. 非透明容器
    # 2. 左右间距相等
    # 3. 中间间距 >= 3
    is_left_right_equal = abs(left_padding - right_padding) <= EPSILON
    use_grid_layout = (not is_transparent) and is_left_right_equal and column_gap_mode >= 3
    
    if use_grid_layout:
        # 使用 display: grid 布局
        parent_style.display = flex_enum_to_str(dsl_enum.DisplayMode.GRID)
        # 获取第一个元素的宽度作为固定列宽
        first_elem_width = tree_children_list[0].data.width
        # 设置 grid-template-columns: 固定 N 列，每列固定宽度
        parent_style.grid_template_columns = f"repeat({row_cnt}, {_to_pt_str(first_elem_width)})"
        # 设置 justify-content: space-between，列之间间距自适应
        parent_style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.SPACE_BETWEEN)
        # 设置 row-gap
        if row_gap_mode > 0:
            parent_style.row_gap = _to_pt_str(row_gap_mode)
        return True

    # 使用 flex-wrap 布局
    parent_style.flex_direction = flex_enum_to_str(dsl_enum.FlexDirection.ROW)
    parent_style.flex_wrap = flex_enum_to_str(dsl_enum.FlexWrap.WRAP)

    # 设置 row-gap
    if row_gap_mode > 0:
        parent_style.row_gap = _to_pt_str(row_gap_mode)
    # 设置 column-gap
    if column_gap_mode > 0:
        parent_style.column_gap = _to_pt_str(column_gap_mode)
    parent_style.justify_content = flex_enum_to_str(dsl_enum.JustifyContent.FLEX_START)

    if is_transparent:
        if not use_fixed_width:
            parent_style.column_gap = None
            # 元素宽度用百分比表示 (1/column_cnt)
            width_percent = round(100 / row_cnt, 0)
            for elem in tree_children_list:
                elem.data.src.style.width = f"{width_percent}%"
                elem.data.extra_dict["edit_width"] = 1
    return True


# 布局策略映射表
_LAYOUT_STRATEGIES = {
    ai_type_def.LAYOUT_TYPE.ROW.value: _calc_row_layout_strategy,
    ai_type_def.LAYOUT_TYPE.COLUMN.value: _calc_column_layout_strategy,
    ai_type_def.LAYOUT_TYPE.GRID.value: _calc_grid_layout_strategy,
}


def _calc_flex_layout(input_tree, parent_node, tree_children_list, context_share_data: Optional[Dict[str, Any]] = None):
    """
    计算 flex 布局 (使用策略模式)
    
    Args:
        input_tree: 输入树
        parent_node: 父节点
        tree_children_list: 子节点列表
        context_share_data: 上下文共享数据（包含 pil_image、image_scale、code_type 等）
    
    Returns:
        True: 成功计算布局
        False: 无法计算布局
    """
    # 空列表不处理
    if len(tree_children_list) <= 0:
        return False
    
    # 单元素特殊处理
    if len(tree_children_list) == 1:
        _calc_one_elem_flex_layout(input_tree, parent_node, tree_children_list, context_share_data)
        return True
    
    # 多元素情况下，尝试对所有文本节点进行高度去除
    # 不再局限于容器只包含一个文本的情况
    for elem in tree_children_list:
        if elem.data.src.type == dsl_enum.ComponentType.TEXT or elem.data.src.type == dsl_enum.ComponentType.CONTAINER_RICH:
            _remove_text_height(input_tree, elem.data.uid, context_share_data)
    
    # 无布局类型时标记为 MESS
    if parent_node.data.layout_type is None:
        parent_node.data.layout_type = ai_type_def.LAYOUT_TYPE.MESS.value
        return False
    
    layout_type = parent_node.data.layout_type

    # 使用策略模式分发布局计算
    strategy = _LAYOUT_STRATEGIES.get(layout_type)
    if strategy:
        return strategy(input_tree, parent_node, tree_children_list, context_share_data)
    return False
