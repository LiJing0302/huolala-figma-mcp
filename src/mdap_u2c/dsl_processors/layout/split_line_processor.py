"""
分割线布局处理模块

将分割线转换为 border-bottom 样式或使用绝对定位

投影前横向分割线处理（have_horizon_line）：
- 3.1 分割线与容器左右边距为 0、到容器下边距为 0 -> 直接转 border-bottom
- 3.2 左右边距不为 0，且分割线左<=其他左、右<=其他右、分割线 y>=其他 y -> 创建包装器包裹余下元素并设 border-bottom
"""

import logging
from typing import Callable

from mdap_u2c.models.dsl_model import Position
from mdap_u2c.dsl_processors.layout import ai_type_def, gen_tree
from mdap_u2c.dsl_processors.layout.parent_padding import get_parent_padding, calc_row_container_padding
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models.dsl_model import ContainerComponent, ContainerComponentProps, Style,Layout

_logger = logging.getLogger(__name__)

_MARGIN_ZERO_EPS = 2.0
_BOTTOM_ZERO_THRESHOLD = 2.0


def _to_pt_str(value) -> str:
    """将数值转换为 pt 字符串格式"""
    if isinstance(value, (int, float)):
        return f"{value}px"
    return str(value)


def calc_split_line_layout(input_tree, parent_node, elem, 
                           absolute_layout_callback: Callable) -> bool:

    if parent_node.data.layout_type == ai_type_def.LAYOUT_TYPE.ROW.value and elem.data.width <= elem.data.height :
        return False
    children_list = [elem]
    absolute_layout_callback(input_tree, parent_node, children_list)
    return True


def _is_bottom_split_line(elem_data, parent_data, threshold: float = 2.0) -> bool:
    """
    判断分割线是否在父容器底部
    
    条件：
    1. 是横向分割线（宽度 > 高度 * 3）
    2. 分割线宽度与父容器宽度接近（差值 < 2px）
    3. 分割线底部边缘与父容器底部边缘的距离 <= threshold
    
    Args:
        elem_data: 分割线元素数据
        parent_data: 父容器数据
        threshold: 底部判断阈值（像素）
    
    Returns:
        bool: 是底部分割线返回 True
    """
    # 判断是否为横向分割线
    if elem_data.width <= elem_data.height * 3:
        return False

    # 计算分割线底部与父容器底部的距离
    elem_bottom = elem_data.y + elem_data.height
    parent_bottom = parent_data.y + parent_data.height
    bottom_gap = abs(parent_bottom - elem_bottom)
    
    return bottom_gap <= threshold


def _convert_split_line_to_border_bottom(input_tree,parent_node, elem):
    """
    将分割线转换为父容器的 border-bottom 样式
    
    使用 border_bottom 简写属性，格式为 "width style color"
    
    Args:
        parent_node: 父容器节点
        elem: 分割线元素节点
    """
    elem_style = elem.data.src.style
    parent_style = parent_node.data.src.style
    
    # 获取分割线的颜色（优先使用边框颜色，其次使用背景颜色）
    border_color = None
    if elem_style.border_color is not None:
        border_color = elem_style.border_color
    elif elem_style.background_color is not None:
        border_color = elem_style.background_color
    else:
        border_color = "rgba(235,239,245,1)"  # 默认颜色
    
    # 获取分割线的高度作为边框宽度
    border_width = elem.data.height
    if border_width <= 0:
        # 如果高度为0，尝试使用边框宽度
        if elem_style.border_width is not None:
            border_width = elem_style.border_width
        else:
            border_width = 0.5  # 默认边框宽度
    #最后一个元素不设置底部边框线
    if not _is_last_elem_in_parent(input_tree,input_tree.parent(parent_node.data.uid)):
       # 使用 border-bottom 简写属性（格式：width style color）
      parent_style.border_bottom = f"{_to_pt_str(border_width)} solid {border_color}"
    
    _logger.debug(f"分割线转换为 border-bottom: 父容器={parent_node.data.uid}, "
                  f"border-bottom={parent_style.border_bottom}")

def _is_last_elem_in_parent(input_tree, elem):
    siblings = input_tree.siblings(elem.data.uid)
    for sibling in siblings:
        if sibling.data.ai_type != ai_type_def.AI_TYPE.SPLIT_LINE.value and  sibling.data.y > elem.data.y:
            return False
    return True


def _split_overflow_crop(elem_data,split_right_margin):
    if split_right_margin < 0:
        elem_data.width = elem_data.width - abs(split_right_margin)

def process_horizontal_split_line_before_projection(input_tree, parent_uid) -> bool:
    """
    投影前处理横向分割线（当父容器有 have_horizon_line 时调用）。

    - 3.1 分割线与容器左右边距为 0、到容器下边距为 0 -> 直接在父容器设 border-bottom，隐藏分割线。
    - 3.2 左右边距不为 0，且 分割线左<=其他左、右<=其他右、分割线 y>=其他 y -> 创建与分割线同宽、父容器同高的容器包裹余下元素，在该容器上设 border-bottom。

    Returns:
        True 表示已处理（已转 border-bottom 并隐藏分割线），调用方可跳过本次投影；False 表示未处理。
    """
    parent_node = input_tree.get_node(parent_uid)
    if not parent_node or not parent_node.data:
        return False
    parent_data = parent_node.data
    children_list = input_tree.children(parent_uid)
    if not children_list:
        return False
    if parent_node.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
        return False
    # 找到底部的横向分割线（仅取一个）
    split_elem = None
    for n in children_list:
        if getattr(n.data, "ai_type", None) != ai_type_def.AI_TYPE.SPLIT_LINE.value:
            continue
        if not _is_bottom_split_line(n.data, parent_data, _BOTTOM_ZERO_THRESHOLD):
            continue
        split_elem = n
        break
    if not split_elem:
        return False

    elem_data = split_elem.data
    split_left_margin = elem_data.x - parent_data.x
    split_right_margin = (parent_data.x + parent_data.width) - (elem_data.x + elem_data.width)
    if split_right_margin < 0:
        _split_overflow_crop(elem_data,split_right_margin)
        split_left_margin = 0
    elem_bottom = elem_data.y + elem_data.height
    parent_bottom = parent_data.y + parent_data.height
    bottom_gap = abs(parent_bottom - elem_bottom)


    left_right_zero = (
        abs(split_left_margin) <= _MARGIN_ZERO_EPS and abs(split_right_margin) <= _MARGIN_ZERO_EPS
    )
    bottom_zero = bottom_gap <= _BOTTOM_ZERO_THRESHOLD

    # 3.1 左右边距为 0 且到下边距为 0 -> 直接父容器 border-bottom
    if left_right_zero and bottom_zero:
        _convert_split_line_to_border_bottom(input_tree,parent_node, split_elem)
        split_elem.data.src.style.display = "none"
        _logger.debug(f"投影前横向分割线 3.1: parent={parent_uid}, 直接 border-bottom" + (" (最底端跳过)"  ""))
        return True

    # 3.2 左右边距不为 0，且 分割线左<=其他左、右<=其他右、分割线 y>=其他 y
    other_nodes = [n for n in children_list if n.data.uid != split_elem.data.uid]
    if not other_nodes:
        _convert_split_line_to_border_bottom(input_tree,parent_node, split_elem)
        split_elem.data.src.style.display = "none"
        input_tree.remove_node(split_elem.data.uid)
        return True

    split_y_ge_others = all(elem_data.y >= n.data.y for n in other_nodes)
    if not split_y_ge_others:
        return False

    other_left_margins = [n.data.x - parent_data.x for n in other_nodes]
    other_right_margins = [
        (parent_data.x + parent_data.width) - (n.data.x + n.data.width) for n in other_nodes
    ]
    min_other_left = min(other_left_margins)
    min_other_right = min(other_right_margins)
    if not (
        split_left_margin <= min_other_left + _MARGIN_ZERO_EPS
        and split_right_margin <= min_other_right + _MARGIN_ZERO_EPS
    ):
        return False

    # 创建与分割线同宽、父容器同高的容器包裹余下元素，设 border-bottom
    wrapper_uid =  "_split_bottom_wrapper_" +  str(elem_data.uid)
    if input_tree.contains(wrapper_uid):
        _logger.debug(f"投影前横向分割线 3.2: 包装器已存在，跳过 parent={parent_uid}, wrapper={wrapper_uid}")
        return True
    container1 = gen_tree.UIControl(
        elem_data.x, parent_data.y, elem_data.width, parent_data.height, wrapper_uid
    )
    container1.src = ContainerComponent(
        id=wrapper_uid,
        style=Style(),
        layout=None,
        props=ContainerComponentProps(),
    )
    container1.extra_dict["split_bottom_wrapper"] = 1
    container1.seq = parent_data.seq + 0.1
    container1.layout_type = parent_data.layout_type
    container1.src.layout = parent_node.data.src.layout

    input_tree.create_node(container1.uid, container1.uid, parent=parent_uid, data=container1)
    for other in other_nodes:
        input_tree.move_node(other.data.uid, container1.uid)
    wrapper_node = input_tree.get_node(container1.uid)
    _convert_split_line_to_border_bottom(input_tree,wrapper_node, split_elem)
    split_elem.data.src.style.display = "none"
    input_tree.remove_node(split_elem.data.uid)

    _logger.debug(f"投影前横向分割线 3.2: parent={parent_uid}, wrapper={wrapper_uid}")
    return True
