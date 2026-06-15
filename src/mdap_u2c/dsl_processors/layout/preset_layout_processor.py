# 预设布局处理模块
# 处理设计稿中已经计算好的 flex/grid 布局，直接复用而不重新计算

import logging

import numpy as np

from mdap_u2c.models.dsl_model import Spacing
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import StyleValueUtils
from mdap_u2c.dsl_processors.layout import ai_type_def
from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN
from mdap_u2c.dsl_processors.layout.parent_padding import get_parent_padding

GAP_VALIDATE_TOLERANCE = 2.0
# 负 gap 特殊处理：当 gap 在此区间内且所有内部间距均满足时，直接返回空非 flex 列表并写入 style
NEGATIVE_GAP_MIN = -24
NEGATIVE_GAP_MAX = 0

_logger = logging.getLogger("preset_layout_processor")


def _to_pt_str(value):
    """将值转换为带单位的字符串，处理 numpy 类型"""
    if value is None:
        return None
    return StyleValueUtils.format_value_with_unit(value)


def _flex_enum_to_str(value):
    """
    将 flex-direction、justify-content、align-items 的枚举值转成字符串
    """
    if value is None:
        return None
    
    # 如果是枚举类型，获取其 value
    if isinstance(value, (dsl_enum.FlexDirection, dsl_enum.JustifyContent, 
                          dsl_enum.AlignItems, dsl_enum.FlexWrap, dsl_enum.PositionType, dsl_enum.DisplayMode)):
        return value.value
    
    # 如果已经是字符串，直接返回
    if isinstance(value, str):
        return value
    
    # 其他情况，尝试转换为字符串
    return str(value)


def _rects_overlap(elem_a, elem_b):
    """判断两个元素矩形是否重叠。"""
    ax1, ay1 = float(elem_a.data.x), float(elem_a.data.y)
    ax2, ay2 = ax1 + float(elem_a.data.width), ay1 + float(elem_a.data.height)
    bx1, by1 = float(elem_b.data.x), float(elem_b.data.y)
    bx2, by2 = bx1 + float(elem_b.data.width), by1 + float(elem_b.data.height)
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def _has_any_overlap(elem_list):
    """判断列表中是否存在任意一对重叠元素。"""
    for i in range(len(elem_list)):
        for j in range(i + 1, len(elem_list)):
            if _rects_overlap(elem_list[i], elem_list[j]):
                return True
    return False


def _variance_x_center(elem_list):
    """计算元素列表的 x_center 方差。x_center = x + width/2。"""
    if len(elem_list) <= 1:
        return 0.0
    centers = [float(e.data.x) + float(e.data.width) / 2 for e in elem_list]
    return float(np.var(centers))


def _variance_y_center(elem_list):
    """计算元素列表的 y_center 方差。y_center = y + height/2。"""
    if len(elem_list) <= 1:
        return 0.0
    centers = [float(e.data.y) + float(e.data.height) / 2 for e in elem_list]
    return float(np.var(centers))


def _is_horizontal_center(elem, parent_node, epsilon=2.0):
    """判断元素相对父容器是否左右间距相等（水平居中）。"""
    px = float(parent_node.data.x)
    pw = float(parent_node.data.width)
    ex = float(elem.data.x)
    ew = float(elem.data.width)
    left_margin = ex - px
    right_margin = (px + pw) - (ex + ew)
    return abs(left_margin - right_margin) <= epsilon


def _collect_non_flex_by_overlap(remaining_list, layout_type, non_flex_elem_list, already_ids):
    """
    若存在相互重叠的元素，迭代剔除：纵向布局取剔除后余下元素 x_center 方差最小，横向取 y_center 方差最小。
    被剔除的元素加入 non_flex_elem_list（并写入 already_ids 去重），直到剩余元素都不重叠。

    特殊情况：当存在重叠且 remaining 仅 2 个元素、一个为图片一个为容器时，将图片加入 non_flex_elem_list。
    """
    remaining = list(remaining_list)
    while _has_any_overlap(remaining):
        if len(remaining) <= 1:
            break
        # 特殊情况：2 个元素且一个为图片、一个为容器时，将图片加入 non_flex
        if len(remaining) == 2:
            a, b = remaining[0], remaining[1]
            type_a = getattr(a.data.src, "type", None) if getattr(a.data, "src", None) else None
            type_b = getattr(b.data.src, "type", None) if getattr(b.data, "src", None) else None
            if type_a == dsl_enum.ComponentType.IMAGE and type_b == dsl_enum.ComponentType.CONTAINER:
                uid = getattr(a.data, "uid", id(a))
                if uid not in already_ids:
                    already_ids.add(uid)
                    non_flex_elem_list.append(a)
                break
            if type_a == dsl_enum.ComponentType.CONTAINER and type_b == dsl_enum.ComponentType.IMAGE:
                uid = getattr(b.data, "uid", id(b))
                if uid not in already_ids:
                    already_ids.add(uid)
                    non_flex_elem_list.append(b)
                break
        if layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value:
            best_remove_idx = -1
            best_variance = float('inf')
            for i in range(len(remaining)):
                candidate = [remaining[j] for j in range(len(remaining)) if j != i]
                v = _variance_x_center(candidate)
                if v < best_variance:
                    best_variance = v
                    best_remove_idx = i
            if best_remove_idx < 0:
                break
            removed = remaining.pop(best_remove_idx)
            uid = getattr(removed.data, "uid", id(removed))
            if uid not in already_ids:
                already_ids.add(uid)
                non_flex_elem_list.append(removed)
        else:
            best_remove_idx = -1
            best_variance = float('inf')
            for i in range(len(remaining)):
                candidate = [remaining[j] for j in range(len(remaining)) if j != i]
                v = _variance_y_center(candidate)
                if v < best_variance:
                    best_variance = v
                    best_remove_idx = i
            if best_remove_idx < 0:
                break
            removed = remaining.pop(best_remove_idx)
            uid = getattr(removed.data, "uid", id(removed))
            if uid not in already_ids:
                already_ids.add(uid)
                non_flex_elem_list.append(removed)


def _try_negative_gap_return_empty(parent_node, filter_children_list, layout_type):
    """
    gap 为负数时的特殊处理：行布局检查 column_gap，列布局检查 row_gap。
    若 -24 < gap < 0 且所有相邻子元素间距都在该范围内，则设置 style.column_gap/row_gap 并返回 True（调用方应直接返回 []）。
    否则返回 False。
    """
    if not filter_children_list or len(filter_children_list) < 2:
        return False
    layout = getattr(parent_node.data.src, "layout", None)
    if not layout or not layout.flexbox:
        return False
    style = getattr(parent_node.data.src, "style", None)
    if style is None:
        return False
    flexbox = layout.flexbox

    def _gap_in_range(g):
        if g is None:
            return False
        try:
            v = float(g)
            return NEGATIVE_GAP_MIN < v < NEGATIVE_GAP_MAX
        except (TypeError, ValueError):
            return False

    if layout_type == ai_type_def.LAYOUT_TYPE.ROW.value:
        cg = getattr(flexbox, "column_gap", None)
        if not _gap_in_range(cg):
            return False
        # 按 x 排序，检查相邻元素水平间距是否都在 (-24, 0)
        ordered = sorted(filter_children_list, key=lambda e: float(e.data.x))
        for i in range(len(ordered) - 1):
            curr = ordered[i].data
            next_ = ordered[i + 1].data
            gap_val = float(next_.x) - (float(curr.x) + float(curr.width))
            if abs (gap_val - cg) >=0.1:
                return False
        parent_node.data.extra_dict["negative_gap"] = 1
        return True

    if layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value:
        rg = getattr(flexbox, "row_gap", None)
        if not _gap_in_range(rg):
            return False
        # 按 y 排序，检查相邻元素纵向间距是否都在 (-24, 0)
        ordered = sorted(filter_children_list, key=lambda e: float(e.data.y))
        for i in range(len(ordered) - 1):
            curr = ordered[i].data
            next_ = ordered[i + 1].data
            gap_val = float(next_.y) - (float(curr.y) + float(curr.height))
            if  abs (gap_val - rg) >=0.1:
                return False
        parent_node.data.extra_dict["negative_gap"] = 1
        return True

    return False


def get_non_flex_elem_list(parent_node, filter_children_list):
    """
    返回应采用绝对定位的非 flex 元素列表。
    0. gap 为负数且 -24 < gap < 0、且内部相邻元素间距均满足时，直接返回 [] 并设置 style.column_gap/row_gap。
    1. 行布局且 2 个元素：若一个左右间距相等、另一个不相等，则将间距不等的设为非 flex。
    2. 扫描是否有相互重叠的元素；若有则迭代剔除：纵向布局取剔除后余下元素 x_center 方差最小，
       横向布局取 y_center 方差最小，被剔除的加入非 flex，直到剩余元素都不重叠。
    """
    if len(filter_children_list) <= 1:
        return []
    if not (parent_node and parent_node.data and parent_node.data.src and parent_node.data.src.layout):
        return []
    if not is_preset_flex_or_grid_layout(parent_node.data):
        return []
    layout = parent_node.data.src.layout
    if layout.flexbox is None:
        return []
    layout_type = parent_node.data.layout_type
    if layout_type not in (ai_type_def.LAYOUT_TYPE.ROW.value, ai_type_def.LAYOUT_TYPE.COLUMN.value):
        return []

    # 负 gap 特殊处理：满足条件则直接返回空并写入 style
    if _try_negative_gap_return_empty(parent_node, filter_children_list, layout_type):
        return []

    non_flex_elem_list = []
    already_ids = set()

    def _add_non_flex(elem):
        uid = getattr(elem.data, "uid", id(elem))
        if uid not in already_ids:
            already_ids.add(uid)
            non_flex_elem_list.append(elem)

    # 1. 行布局且 2 个元素：一个左右间距相等、另一个不相等 -> 间距不等的设为非 flex
    if layout_type == ai_type_def.LAYOUT_TYPE.ROW.value and len(filter_children_list) == 2:
        a, b = filter_children_list[0], filter_children_list[1]
        ca, cb = _is_horizontal_center(a, parent_node), _is_horizontal_center(b, parent_node)
        if ca != cb:
            if not ca:
                _add_non_flex(a)
            else:
                _add_non_flex(b)
            return non_flex_elem_list
    # 2. 重叠扫描：从“当前视为 flex 的候选”中剔除重叠项，使余下方差最小，直到无重叠
    flex_candidates = [e for e in filter_children_list if getattr(e.data, "uid", id(e)) not in already_ids]
    _collect_non_flex_by_overlap(flex_candidates, layout_type, non_flex_elem_list, already_ids)

    return non_flex_elem_list


def _get_container_margin_floats(container_node, parent_node):
    """
    根据容器与父节点的 x、y 坐标及父容器的 padding 计算 margin 四向数值 (top, right, bottom, left)。
    margin = 容器外边与父容器内容区（父区域减去 padding）的间距。
    """
    m_top = m_right = m_bottom = m_left = 0.0
    if not (container_node and container_node.data and parent_node and parent_node.data):
        return m_top, m_right, m_bottom, m_left
    padding_left, padding_right, padding_top, padding_bottom = get_parent_padding(parent_node)
    try:
        parent_x = float(parent_node.data.x)
        parent_y = float(parent_node.data.y)
        parent_w = float(parent_node.data.width)
        parent_h = float(parent_node.data.height)
        cont_x = float(container_node.data.x)
        cont_y = float(container_node.data.y)
        cont_w = float(container_node.data.width)
        cont_h = float(container_node.data.height)
    except (TypeError, ValueError, AttributeError):
        return m_top, m_right, m_bottom, m_left
    m_left = cont_x - (parent_x + padding_left)
    m_top = cont_y - (parent_y + padding_top)
    m_right = (parent_x + parent_w - padding_right) - (cont_x + cont_w)
    m_bottom = (parent_y + parent_h - padding_bottom) - (cont_y + cont_h)
    return m_top, m_right, m_bottom, m_left


def fix_preset_layout_on_container_remove(input_tree, container_uid):
    """
    容器删除前，对预设 flex/grid 布局做修复：
    1. 若被删容器是 is_preset_flex_or_grid_layout 且无其他兄弟节点，
       将其 padding 加到父容器的 padding 上；若该容器 margin 非空，则将 margin 也叠加到父容器 padding。
    2. 若被删容器的父容器是 is_preset_flex_or_grid_layout，
       将父容器的 layout.flexbox / layout.gridbox 置空，便于后续重新计算布局。
    """
    if container_uid == input_tree.root:
        return
    parent_node = input_tree.parent(container_uid)
    parent_uid = parent_node.data.uid
    container_node = input_tree.get_node(container_uid)
    siblings = input_tree.children(parent_uid)

    # 1. 被删容器是预设 flex/grid 且为唯一子节点时，将其 padding（及 margin 若非空）合并到父容器
    if  len(siblings) == 1:
        c_top = c_right = c_bottom = c_left = 0.0
        cont_layout = container_node.data.src.layout
        if cont_layout and cont_layout.padding:
            cp = cont_layout.padding
            c_top = (float(cp.top) if cp.top is not None else 0.0)
            c_right = (float(cp.right) if cp.right is not None else 0.0)
            c_bottom = (float(cp.bottom) if cp.bottom is not None else 0.0)
            c_left = (float(cp.left) if cp.left is not None else 0.0)
        m_top, m_right, m_bottom, m_left = _get_container_margin_floats(container_node, parent_node)
        total_top = total_right = total_bottom = total_left = 0
        if m_top <= ADJUST_WIDTH_MARGIN:
            total_top = c_top + m_top
        if m_right <= ADJUST_WIDTH_MARGIN:
            total_right = c_right + m_right
        if m_bottom <= ADJUST_WIDTH_MARGIN:
            total_bottom = c_bottom + m_bottom
        if m_left <= ADJUST_WIDTH_MARGIN:
            total_left = c_left + m_left
        if total_top != 0 or total_right != 0 or total_bottom != 0 or total_left != 0:
            parent_src = parent_node.data.src
            if parent_src.layout is not None:
                parent_layout = parent_src.layout
                if parent_layout.padding is None:
                    parent_layout.padding = Spacing(
                        top=total_top, right=total_right, bottom=total_bottom, left=total_left
                    )
                else:
                    pp = parent_layout.padding
                    parent_layout.padding = Spacing(
                        top=(pp.top if pp.top is not None else 0) + total_top,
                        right=(pp.right if pp.right is not None else 0) + total_right,
                        bottom=(pp.bottom if pp.bottom is not None else 0) + total_bottom,
                        left=(pp.left if pp.left is not None else 0) + total_left,
                    )

    # 2. 父容器是预设 flex/grid 时，清空 flexbox/gridbox 以便后续重算
    if is_preset_flex_or_grid_layout(parent_node.data):
        parent_src = parent_node.data.src
        if parent_src.layout is not None:
            parent_src.layout.flexbox = None
            parent_src.layout.gridbox = None

def is_autolayout_elem(current_node):
    if "autolayout_child" in current_node.data.extra_dict:
        return True
def is_flex_or_grid_container_two_more(input_tree, current_node):
    """
    若 layout 的 display 为预设的 flex 或 grid，且 flexbox/gridbox 中有容器相关属性，且子元素数量>=2，
    则标记该容器及其子节点的 extra_dict["autolayout"] = 1，并返回 True 表示应保留该容器。
    """

    children_list = input_tree.children(current_node.data.uid)
    if len(children_list) < 2:
        return False
    if not is_preset_flex_or_grid_layout(current_node.data):
        return False
    if len(children_list) >= 3:
      for child in children_list:
         child.data.extra_dict["autolayout_child"] = 1
    return True


def is_preset_flex_or_grid_layout(node_data):
    """
    判断容器是否有预设的 flex/grid 布局
    
    条件：
    1. display 为 flex 或 grid
    2. 至少有一个容器相关属性：direction, align_items, row_gap, wrap, 
       justify_content, grid_template_columns, grid_template_rows, padding
    
    Args:
        node_data: 节点数据
    
    Returns:
        bool: 如果有预设的 flex/grid 布局返回 True
    """
    if node_data.src.layout is None:
        return False
    
    layout = node_data.src.layout
    display = layout.display
    
    # 检查 display 是否为 flex 或 grid
    if display != dsl_enum.DisplayMode.FLEX and display != dsl_enum.DisplayMode.GRID:
        return False
    
    # 检查是否有相关的布局属性
    if display == dsl_enum.DisplayMode.FLEX and layout.flexbox is not None:
        flexbox = layout.flexbox
        # 检查容器相关属性
        if (flexbox.direction is not None or 
            flexbox.align_items is not None or 
            flexbox.justify_items is not None or
            flexbox.row_gap is not None or 
            flexbox.column_gap is not None or
            flexbox.wrap is not None or 
            flexbox.align_content is not None or
            flexbox.justify_content is not None):
            return True
    
    if display == dsl_enum.DisplayMode.GRID and layout.gridbox is not None:
        gridbox = layout.gridbox
        # 检查容器相关属性
        if (gridbox.grid_template_columns is not None or 
            gridbox.grid_template_rows is not None or
            gridbox.row_gap is not None or
            gridbox.column_gap is not None):
            return True
    
    # 检查 padding
    if layout.padding is not None:
        padding = layout.padding
        if (padding.top is not None or padding.bottom is not None or
            padding.left is not None or padding.right is not None):
            return True
    
    return False


def _apply_preset_container_layout(node_data):
    """
    将 layout 中的 flexbox/gridbox 属性复制到容器的 style
    
    Args:
        node_data: 节点数据
    """
    layout = node_data.src.layout
    style = node_data.src.style
    display = layout.display
    
    # 设置 display
    style.display = _flex_enum_to_str(display)
    
    # 应用 flexbox 属性
    if display == dsl_enum.DisplayMode.FLEX and layout.flexbox is not None:
        flexbox = layout.flexbox
        if flexbox.direction is not None:
            style.flex_direction = _flex_enum_to_str(flexbox.direction)
        if flexbox.align_items is not None:
            style.align_items = _flex_enum_to_str(flexbox.align_items)
        if flexbox.justify_items is not None:
            style.justify_items = _flex_enum_to_str(flexbox.justify_items)
        if flexbox.row_gap is not None:
            style.row_gap = _to_pt_str(flexbox.row_gap)
        if flexbox.column_gap is not None:
            style.column_gap = _to_pt_str(flexbox.column_gap)
        if flexbox.wrap is not None:
            style.flex_wrap = _flex_enum_to_str(flexbox.wrap)
        if flexbox.align_content is not None:
            style.align_content = _flex_enum_to_str(flexbox.align_content)
        if flexbox.justify_content is not None:
            style.justify_content = _flex_enum_to_str(flexbox.justify_content)
    # 应用 gridbox 属性
    if display == dsl_enum.DisplayMode.GRID and layout.gridbox is not None:
        gridbox = layout.gridbox
        if gridbox.grid_template_columns is not None:
            style.grid_template_columns = gridbox.grid_template_columns
        if gridbox.grid_template_rows is not None:
            style.grid_template_rows = gridbox.grid_template_rows
        if gridbox.row_gap is not None:
            style.row_gap = _to_pt_str(gridbox.row_gap)
        if gridbox.column_gap is not None:
            style.column_gap = _to_pt_str(gridbox.column_gap)
    
    # 应用 padding 属性
    if layout.padding is not None:
        padding = layout.padding
        if padding.top is not None:
            style.padding_top = _to_pt_str(padding.top)
        if padding.bottom is not None:
            style.padding_bottom = _to_pt_str(padding.bottom)
        if padding.left is not None:
            style.padding_left = _to_pt_str(padding.left)
        if padding.right is not None:
            style.padding_right = _to_pt_str(padding.right)


def _apply_preset_child_layout(child_node, parent_display):
    """
    为子元素应用 flexbox/gridbox 中的布局位置属性
    
    Args:
        child_node: 子节点
        parent_display: 父容器的 display 类型
    """
    child_data = child_node.data
    if child_data.src.layout is None:
        return
    
    layout = child_data.src.layout
    style = child_data.src.style
    
    # 应用 flexbox 子元素属性
    if parent_display == dsl_enum.DisplayMode.FLEX and layout.flexbox is not None:
        flexbox = layout.flexbox
        if flexbox.flex_grow is not None:
            # flex_grow 是数字，不需要单位
            style.flex_grow = str(int(flexbox.flex_grow)) if flexbox.flex_grow == int(flexbox.flex_grow) else str(flexbox.flex_grow)
        if flexbox.flex_shrink is not None:
            style.flex_shrink = str(int(flexbox.flex_shrink)) if flexbox.flex_shrink == int(flexbox.flex_shrink) else str(flexbox.flex_shrink)
        if flexbox.flex_basis is not None:
            style.flex_basis = _to_pt_str(flexbox.flex_basis)
        if flexbox.align_self is not None:
            style.align_self = flexbox.align_self
    
    # 应用 gridbox 子元素属性
    if parent_display == dsl_enum.DisplayMode.GRID and layout.gridbox is not None:
        gridbox = layout.gridbox
        if gridbox.grid_row is not None:
            style.grid_row = gridbox.grid_row
        if gridbox.grid_column is not None:
            style.grid_column = gridbox.grid_column


def get_layout_type_from_display_mode(node_data):
    """
    根据 DisplayMode 获取控件布局方式
    
    根据节点的 display 模式和 flex_direction 判断布局方式：
    - GRID -> 网格布局 (GRID)
    - FLEX + direction=row/row-reverse -> 横向布局 (ROW)
    - FLEX + direction=column/column-reverse -> 纵向布局 (COLUMN)
    - 其他情况返回 None
    
    Args:
        node_data: 节点数据
    
    Returns:
        int: 布局类型，对应 ai_type_def.LAYOUT_TYPE 的值
            - ai_type_def.LAYOUT_TYPE.GRID.value: 网格布局
            - ai_type_def.LAYOUT_TYPE.ROW.value: 横向布局
            - ai_type_def.LAYOUT_TYPE.COLUMN.value: 纵向布局
            - None: 无法确定布局类型
    """
    if node_data.src.layout is None:
        return None
    
    layout = node_data.src.layout
    display = layout.display
    
    # GRID 模式 -> 网格布局
    if display == dsl_enum.DisplayMode.GRID:
        return ai_type_def.LAYOUT_TYPE.GRID.value
    
    # FLEX 模式 -> 根据 flex_direction 判断
    if display == dsl_enum.DisplayMode.FLEX:
        if layout.flexbox is not None and layout.flexbox.direction is not None:
            direction = layout.flexbox.direction
            # 如果是枚举类型，获取其 value
            if isinstance(direction, dsl_enum.FlexDirection):
                direction_str = direction.value
            elif isinstance(direction, str):
                direction_str = direction
            else:
                direction_str = str(direction)
            wrap = layout.flexbox.wrap
            # 判断横向或纵向 有些列布局，设计稿用行布局+折行表示，所以加过滤
            if direction_str in (dsl_enum.FlexDirection.ROW.value, dsl_enum.FlexDirection.ROW_REVERSE.value) and wrap != dsl_enum.FlexWrap.WRAP.value:
                return ai_type_def.LAYOUT_TYPE.ROW.value
            elif direction_str in (dsl_enum.FlexDirection.COLUMN.value, dsl_enum.FlexDirection.COLUMN_REVERSE.value):
                return ai_type_def.LAYOUT_TYPE.COLUMN.value
    
    return None


def process_preset_grid_layout(input_tree, parent_node, children_list):
    """
    处理预设的 flex/grid 布局
    
    只有 grid 布局容器才完全保留预设布局，flex 布局会继续重新计算。
    
    对于 grid 布局容器：
    1. 容器相关属性（grid_template_columns, grid_template_rows, row_gap, column_gap, padding）
       不再重新计算，直接复用现成字段并修改 style 字段
    2. 容器内部元素不再重新计算布局相关字段，直接采用 gridbox 中
       相关布局位置的字段（grid_row, grid_column）
    
    Args:
        input_tree: 输入树
        parent_node: 父节点
        children_list: 子节点列表
    
    Returns:
        bool: 如果处理了预设布局返回 True，否则返回 False
    """
    parent_data = parent_node.data
    
    # 检查是否有预设布局
    if not is_preset_flex_or_grid_layout(parent_data):
        return False
    
    # 检查 layout 是否存在
    if parent_data.src.layout is None:
        return False
    
    layout = parent_data.src.layout
    display = layout.display
    
    # 只有 grid 布局才完全保留预设布局
    if display != dsl_enum.DisplayMode.GRID:
        return False
    
    # 检查 grid 布局是否有相关属性
    if layout.gridbox is None:
        return False
    
    gridbox = layout.gridbox
    # 检查是否有 grid 相关的容器属性
    has_grid_attrs = (
        gridbox.grid_template_columns is not None or 
        gridbox.grid_template_rows is not None or
        gridbox.row_gap is not None or
        gridbox.column_gap is not None
    )
    
    if not has_grid_attrs:
        return False
    
    _logger.info(f"使用预设的 grid 布局: {parent_data.uid}")
    
    # 应用容器布局属性到 style
    _apply_preset_container_layout(parent_data)
    
    # 获取父容器的 display 类型
    parent_display = parent_data.src.layout.display
    
    # 为子元素应用布局属性
    for child in children_list:
        _apply_preset_child_layout(child, parent_display)
    
    return True
