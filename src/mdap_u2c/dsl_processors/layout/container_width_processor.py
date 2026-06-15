"""
容器宽度去除处理模块

负责容器宽度自适应、文本宽度去除等相关功能
"""
import functools
import logging
from typing import Optional, Dict, Any

from mdap_u2c.constant import FIGMA_DESIGN_WIDTH, FIGMA_DESIGN_HEIGHT
from mdap_u2c.dsl_processors.layout import ai_type_def, tree_rebuild
from mdap_u2c.dsl_processors.layout.parent_padding import get_parent_padding as _get_parent_padding
from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN, get_adjust_width_min
from mdap_u2c.dsl_processors.layout.text_dimension_processor import (
    _parse_px_value,
    _is_text_multiline,
    _get_text_position_relative_to_parent,
    _calc_text_display_x_range,
    _crop_text_region,
    remove_text_width_in_column,
    _has_no_sibling_on_left_right,
    _has_no_sibling_on_right,
    _has_no_sibling_on_left,
    EPSILON,
)
from mdap_u2c.enums import dsl_enum

_logger = logging.getLogger("container_width_processor")


def _to_pt_str(value):
    """将数值转换为像素字符串"""
    if value is None:
        return None
    return f"{round(value, 1)}px"


def flex_enum_to_str(enum_value):
    """将枚举值转换为字符串"""
    if hasattr(enum_value, 'value'):
        return enum_value.value
    return enum_value


# ============================================================================
# 元素度量计算
# ============================================================================

def calc_element_metrics(elem_data, parent_data):
    """
    计算元素相对于父容器的度量信息
    
    Args:
        elem_data: 元素数据
        parent_data: 父容器数据
    
    Returns:
        度量对象，包含 left_margin, right_margin, top_margin, bottom_margin, is_horizontal_center
    """
    class Metrics:
        def __init__(self):
            self.left_margin = 0
            self.right_margin = 0
            self.top_margin = 0
            self.bottom_margin = 0
            self.is_horizontal_center = False
    
    metrics = Metrics()
    
    parent_x = parent_data.x
    parent_y = parent_data.y
    parent_width = parent_data.width
    parent_height = parent_data.height
    parent_right = parent_x + parent_width
    parent_bottom = parent_y + parent_height
    
    elem_x = elem_data.x
    elem_y = elem_data.y
    elem_width = elem_data.width
    elem_height = elem_data.height
    elem_right = elem_x + elem_width
    elem_bottom = elem_y + elem_height
    
    metrics.left_margin = elem_x - parent_x
    metrics.right_margin = parent_right - elem_right
    metrics.top_margin = elem_y - parent_y
    metrics.bottom_margin = parent_bottom - elem_bottom
    metrics.is_horizontal_center = abs(metrics.left_margin - metrics.right_margin) <= EPSILON
    
    return metrics


def _is_table_container(input_tree, current_uid,current_node):
    # 如果当前节点是网格布局，且内部控件的横向和纵向间距 <= 2，则不自适应宽度
    if current_node.data.layout_type == ai_type_def.LAYOUT_TYPE.GRID.value:
        children = input_tree.children(current_uid)
        children.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))  # 从小到大排序.极端情况下纵向切分，其他情况横向切分

        if len(children) >= 2:
            # 计算横向间距（column_gap）
            column_gap = 0
            for i in range(1, len(children)):
                if children[i].data.x > children[i - 1].data.x:
                    gap = children[i].data.x - (children[i - 1].data.x + children[i - 1].data.width)
                    column_gap = gap
                    break
            # 计算纵向间距（row_gap）
            row_gap = 0
            for i in range(1, len(children)):
                if children[i].data.y > children[i - 1].data.y + children[i - 1].data.height:
                    gap = children[i].data.y - (children[i - 1].data.y + children[i - 1].data.height)
                    row_gap = gap
                    break
            # 如果横向和纵向间距都 <= 2，则不自适应宽度
            if column_gap <= 2 and row_gap <= 2:
                return True

    # 如果当前节点是横向布局，排除掉表格布局， 则不自适应宽度
    if current_node.data.layout_type == ai_type_def.LAYOUT_TYPE.ROW.value and len(
            input_tree.children(current_uid)) >= 2:
        children = input_tree.children(current_uid)
        # 每个子元素都是容器且 background_color 或 border_color 非空 -> 视为表格容器
        all_container_with_style = True
        children.sort(key=functools.cmp_to_key(tree_rebuild.compare_x))  # 从小到大排序.极端情况下纵向切分，其他情况横向切分
        row_gap_small = True
        for i,child in enumerate(children):
            if not (child.data.src and child.data.src.type == dsl_enum.ComponentType.CONTAINER.value):
                all_container_with_style = False
                break
            style = child.data.src.style if child.data.src else None
            if not style or not (style.background_color or style.border_color):
                all_container_with_style = False
                break
            gap = children[i].data.x - (children[i - 1].data.x + children[i - 1].data.width)
            if gap >= 3:
                row_gap_small = False
                break
        if all_container_with_style and row_gap_small:

            return True


    # 如果当前节点是纵向布局，行间距 <= 3，且每行元素的子元素横向间距 <= 3，则不自适应宽度，有2个富文本纵向叠加的case，需要宽度自适应
    '''
    if current_node.data.layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value and len(input_tree.children(current_uid)) >= 2:
        children = input_tree.children(current_uid)
        children.sort(key=functools.cmp_to_key(tree_rebuild.compare_y))  # 从小到大排序.极端情况下纵向切分，其他情况横向切分

        if len(children) >= 2:
            # 检查行间距（相邻子元素的纵向间距）
            row_gap_small = True
            for i in range(1, len(children)):
                row_gap = children[i].data.y - (children[i-1].data.y + children[i-1].data.height)
                if row_gap >= 3:
                    row_gap_small = False
                    break

            # 检查每行元素的子元素横向间距
            child_column_gap_small = True
            if row_gap_small:
                for child in children:
                    child_children = input_tree.children(child.data.uid)
                    if len(child_children) >= 2:
                        # 检查横向间距
                        for j in range(1, len(child_children)):
                            if child_children[j].data.x > child_children[j-1].data.x:
                                gap = child_children[j].data.x - (child_children[j-1].data.x + child_children[j-1].data.width)
                                if gap >= 3:
                                    child_column_gap_small = False
                                    break
                        if child_column_gap_small:
                            break

            # 如果行间距 <= 3 且子元素横向间距 <= 3，则不自适应宽度
            if row_gap_small and child_column_gap_small:
                return TRUE
    '''
    return False
# ============================================================================
# 容器宽度去除函数
# ============================================================================

def remove_control_width(input_tree, current_uid):
    """
    当控件类型为容器、文本或富文本容器时，且距离父容器的左右间距相等且间距<=32，则设置style.width=None
    
    条件：
    1. 控件类型为 container、text 或 container_rich
    2. 距离父容器的左右间距<=16（使用容差值比较）
    3. 间距 <= 32
    4. 如果是网格布局且内部控件的横向和纵向间距<=2，则不自适应
    5. 满足条件时，设置 style.width = None
    
    返回值：
    - True: 成功修改了宽度
    - False: 未修改宽度
    """
    current_node = input_tree.get_node(current_uid)
    if current_node is None:
        return False
    current_width = current_node.data.width
    root = input_tree.get_node(input_tree.root) if input_tree else None
    design_width = float(root.data.width) if root and root.data else None
    adjust_min_local = get_adjust_width_min(design_width)   # 部分页面使用更小阈值
    if current_width < adjust_min_local:
        return False
    # 检查节点类型是否为容器、文本或富文本容器
    component_type = current_node.data.src.type
    if component_type not in [
        dsl_enum.ComponentType.IMAGE.value, #某些图片包含节点，需要拉伸
        dsl_enum.ComponentType.CONTAINER.value
    ]:
        return False
    
    # 检查是否有 style 对象
    if current_node.data.src.style is None:
        return False
    
    if _is_table_container(input_tree, current_uid,current_node):
        return False
    # 获取父节点
    parent_node = input_tree.parent(current_uid)
    if parent_node is None:
        return False
    have_brother = len(input_tree.siblings(current_uid)) > 0

    # 使用度量函数计算边距
    metrics = calc_element_metrics(current_node.data, parent_node.data)
    # 减去父容器的 padding，得到相对于内容区的有效 margin（CSS 中 100% 与 margin 均相对父容器内容框）
    padding_left, padding_right, _, _ = _get_parent_padding(parent_node)
    effective_left_margin = max(0.0, float(metrics.left_margin) - float(padding_left))
    effective_right_margin = max(0.0, float(metrics.right_margin) - float(padding_right))
    if effective_left_margin <= ADJUST_WIDTH_MARGIN and abs(effective_left_margin - effective_right_margin) <= ADJUST_WIDTH_MARGIN/2:
        # 满足条件，设置 width，并设置 extra_dict["edit_width"] = 0
        total_effective = round(effective_left_margin + effective_right_margin,1)
        if total_effective <= 0.1:
            current_node.data.src.style.width = "100%"
        else:
            current_node.data.src.style.width = f"calc(100% - {total_effective}px)"
            if effective_left_margin >0.1:
                current_node.data.src.style.margin_left = _to_pt_str(effective_left_margin)
            if effective_right_margin >0.1:
                current_node.data.src.style.margin_right = _to_pt_str(effective_right_margin)
        if have_brother is False:
            parent_node.data.src.style.align_items = flex_enum_to_str(dsl_enum.AlignItems.CENTER)
        elif parent_node.data.src.style.align_items != flex_enum_to_str(dsl_enum.AlignItems.CENTER):
            current_node.data.src.style.align_self = flex_enum_to_str(dsl_enum.AlignItems.CENTER)
        current_node.data.extra_dict["edit_width"] = 0
        return True
    
    return False


def calc_no_width_layout(input_tree, current_uid, context_share_data: Optional[Dict[str, Any]] = None):
    """
    移除节点宽度并计算 margin_left 和 margin_right
    
    如果 remove_text_width_in_column 或 remove_control_width 成功移除了宽度，
    则计算并设置当前节点的 margin_left 和 margin_right
    
    返回值：
    - True: 成功移除了宽度并设置了 margin
    - False: 未移除宽度
    """
    # 尝试移除文本宽度
    if remove_text_width_in_column(input_tree, current_uid, context_share_data):
        # 计算当前节点的 margin_left, margin_right
        return True
    # 尝试移除控件宽度
    elif remove_control_width(input_tree, current_uid):
        # 计算当前节点的 margin_left, margin_right
        return True
    return False


def replace_width_height_by_100_percent(current_node_data, origin_width, origin_height):
    """
    如果 origin_width == FIGMA_DESIGN_WIDTH 且 origin_height == FIGMA_DESIGN_HEIGHT，则将匹配的宽度或高度替换为 100%
    
    条件：
    1. origin_width == FIGMA_DESIGN_WIDTH 且 origin_height == FIGMA_DESIGN_HEIGHT
    2. 如果控件宽度为 FIGMA_DESIGN_WIDTH，则设置 style.width = "100%"，extra_dict["edit_width"] = 1
    3. 如果控件高度为 FIGMA_DESIGN_HEIGHT，则设置 style.height = "100%"，extra_dict["edit_height"] = 1
    
    返回值：
    - True: 成功修改了宽度或高度
    - False: 未修改
    """
    # 检查 origin_width 和 origin_height 是否满足条件
    if origin_width != FIGMA_DESIGN_WIDTH or origin_height <= 600:
        return False

    
    # 检查是否有 style 对象
    if current_node_data.src.style is None:
        return False
    
    # 使用小的容差值进行浮点数比较
    modified = False
    # 检查宽度是否为设计稿标准宽度
    if abs(current_node_data.width - FIGMA_DESIGN_WIDTH) <= EPSILON:
        current_node_data.src.style.width = "100%"
        current_node_data.extra_dict["edit_width"] = 1
        modified = True
    
    # 检查高度是否为设计稿标准高度
    if abs(current_node_data.height - FIGMA_DESIGN_HEIGHT) <= EPSILON:
        current_node_data.src.style.height = "100vh"
        current_node_data.extra_dict["edit_height"] = 1
        modified = True
    
    return modified


# 保持向后兼容的别名
_remove_control_width = remove_control_width
_calc_no_width_layout = calc_no_width_layout
