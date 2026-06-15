"""
父容器 padding 获取工具

用于 margin 计算时减去父容器 padding，保证写入的 margin 为相对父内容区的有效值。
同时提供行/列布局容器的 padding 计算（_calc_row_container_padding、_calc_column_container_padding）。
供 container_width_processor、text_dimension_processor、calc_layout_position 等共用。
"""
from mdap_u2c.enums import dsl_enum
from mdap_u2c.dsl_processors.layout import ai_type_def
from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN, get_adjust_width_min

# 与 layout_constant 一致的容差，供本模块内 padding 计算使用
EPSILON = 2.1


def _parse_padding_to_float(value):
    """将 padding 值（可能为 str/int/float，如 '10px'）解析为 float。"""
    if value is None:
        return 0.0
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace("px", "").replace("pt", "").strip()
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0


def _adjust_padding_by_edge_elements(parent_node, filtered_children, padding_left, padding_right, padding_top, padding_bottom):
    """
    根据最左/最右/最上/最下元素修正 padding。
    若最左边元素到左边的间距<=padding_left，则修正 padding_left；同理修正 padding_right。
    若最上边元素到上边的间距<=padding_top，则修正 padding_top；同理修正 padding_bottom。
    """
    if not filtered_children:
        return padding_left, padding_right, padding_top, padding_bottom
    parent_x = parent_node.data.x
    parent_y = parent_node.data.y
    parent_right = parent_node.data.x + parent_node.data.width
    parent_bottom = parent_node.data.y + parent_node.data.height

    if padding_left > 0:
        leftmost_elem = min(filtered_children, key=lambda e: e.data.x)
        leftmost_dist = max(0, leftmost_elem.data.x - parent_x)
        if leftmost_dist <= padding_left:
            padding_left = leftmost_dist
    if padding_right > 0:
        rightmost_elem = max(filtered_children, key=lambda e: e.data.x + e.data.width)
        rightmost_dist = max(0, parent_right - (rightmost_elem.data.x + rightmost_elem.data.width))
        if rightmost_dist <= padding_right:
            padding_right = rightmost_dist
    if padding_top > 0:
        topmost_elem = min(filtered_children, key=lambda e: e.data.y)
        topmost_dist = max(0, topmost_elem.data.y - parent_y)
        if topmost_dist <= padding_top:
            padding_top = topmost_dist
    if padding_bottom > 0:
        bottommost_elem = max(filtered_children, key=lambda e: e.data.y + e.data.height)
        bottommost_dist = max(0, parent_bottom - (bottommost_elem.data.y + bottommost_elem.data.height))
        if bottommost_dist <= padding_bottom:
            padding_bottom = bottommost_dist
    return padding_left, padding_right, padding_top, padding_bottom


# 用于预处理阶段，控件树重排之前；design_width 为设计稿宽度（Metadata.width），未传则用默认值
def _get_original_padding(parent_node, design_width=None):
    padding_left = 0.0
    padding_right = 0.0
    padding_top = 0.0
    padding_bottom = 0.0
    if not (parent_node and parent_node.data and parent_node.data.src):
        return padding_left, padding_right, padding_top, padding_bottom
    src = parent_node.data.src
    adjust_min = get_adjust_width_min(design_width)

    if src.layout and src.layout.padding:
        p = src.layout.padding
        try:
            padding_left = float(p.left) if p.left is not None else 0.0
            padding_right = float(p.right) if p.right is not None else 0.0
            padding_top = float(p.top) if p.top is not None else 0.0
            padding_bottom = float(p.bottom) if p.bottom is not None else 0.0
            if parent_node.data.width < adjust_min:
                padding_left, padding_right = 0, 0
            if padding_left >= ADJUST_WIDTH_MARGIN:
                padding_left = 0
            if padding_right >= ADJUST_WIDTH_MARGIN:
                padding_right = 0
            if padding_top >= ADJUST_WIDTH_MARGIN:
                padding_top = 0
            if padding_bottom >= ADJUST_WIDTH_MARGIN:
                padding_bottom = 0
        except (ValueError, TypeError):
            padding_left = padding_right = padding_top = padding_bottom = 0.0
        return padding_left, padding_right, padding_top, padding_bottom
    return 0, 0, 0, 0

def get_parent_padding(node):
    """
    从 style 字段获取 padding 值。

    优先读取 style.padding_left/right/top/bottom，若分写属性均有值则使用；
    否则解析 style.padding 简写（格式 "top right bottom left"）。

    Args:
        node: 节点，需包含 node.data.src.style

    Returns:
        tuple: (padding_left, padding_right, padding_top, padding_bottom)，均为 float
    """
    padding_left = 0.0
    padding_right = 0.0
    padding_top = 0.0
    padding_bottom = 0.0
    if not (node and node.data and node.data.src):
        return padding_left, padding_right, padding_top, padding_bottom
    style = getattr(node.data.src, "style", None)
    if not style:
        return padding_left, padding_right, padding_top, padding_bottom

    # 优先使用分写属性
    pl = getattr(style, "padding_left", None)
    pr = getattr(style, "padding_right", None)
    pt = getattr(style, "padding_top", None)
    pb = getattr(style, "padding_bottom", None)
    if any(v is not None and str(v).strip() for v in (pl, pr, pt, pb)):
        padding_left = _parse_padding_to_float(pl)
        padding_right = _parse_padding_to_float(pr)
        padding_top = _parse_padding_to_float(pt)
        padding_bottom = _parse_padding_to_float(pb)
        return padding_left, padding_right, padding_top, padding_bottom

    # 使用简写 padding
    padding_shorthand = getattr(style, "padding", None)
    if padding_shorthand and str(padding_shorthand).strip():
        padding_top, padding_right, padding_bottom, padding_left = _parse_padding_shorthand(padding_shorthand)

    return padding_left, padding_right, padding_top, padding_bottom

def _parse_padding_shorthand(shorthand) -> tuple:
    """
    解析 CSS padding 简写，格式 "top right bottom left"。
    支持 1/2/3/4 值形式，返回 (padding_top, padding_right, padding_bottom, padding_left)。
    """
    if not shorthand or not str(shorthand).strip():
        return 0.0, 0.0, 0.0, 0.0
    parts = [p.strip() for p in str(shorthand).split()]
    if not parts:
        return 0.0, 0.0, 0.0, 0.0
    parsed = [_parse_padding_to_float(p) for p in parts]
    if len(parsed) == 1:
        v = parsed[0]
        return v, v, v, v
    if len(parsed) == 2:
        t_b, l_r = parsed[0], parsed[1]
        return t_b, l_r, t_b, l_r
    if len(parsed) == 3:
        t, l_r, b = parsed[0], parsed[1], parsed[2]
        return t, l_r, b, l_r
    # 4 values: top right bottom left

def has_layout_padding(parent_node):
    """
    检查父容器是否在 layout.padding 中已有 padding 值

    Args:
        parent_node: 父容器节点

    Returns:
        bool: 如果 layout.padding 存在且至少有一个方向有值，返回 True
    """
    if not (parent_node and parent_node.data and parent_node.data.src):
        return False
    layout = parent_node.data.src.layout
    if not (layout and layout.padding):
        return False
    p = layout.padding
    return (p.left or p.right or p.top or p.bottom) > 0

def calc_row_container_padding(parent_node, filtered_children, design_width=None):
    """
    计算行布局容器的 padding（四个方向：left, right, top, bottom）
    design_width 为设计稿宽度（Metadata.width），未传则用默认值。

    逻辑：
    1. 如果 layout 中已有 padding，直接使用，不重新计算
    2. 否则计算所有子控件到父容器的最小上间距 smallest_top_bottom_margin
    3. 计算左右 padding：第一个元素的 left_margin 和最后一个元素的 right_margin
    4. 如果 smallest_top_bottom_margin <= ADJUST_WIDTH_MARGIN 且 > 0，则设置上下 padding

    Args:
        parent_node: 父容器节点
        filtered_children: 过滤后的子元素列表
        design_width: 设计稿根节点宽度（Metadata.width），可选

    Returns:
        tuple: (padding_left, padding_right, padding_top, padding_bottom, should_set_padding)
    """
    adjust_min = get_adjust_width_min(design_width)
    if has_layout_padding(parent_node):
        padding_left, padding_right, padding_top, padding_bottom = _get_original_padding(parent_node, design_width)

        if padding_left >= ADJUST_WIDTH_MARGIN:
            padding_left = 0
        if padding_right >= ADJUST_WIDTH_MARGIN:
            padding_right = 0
        if padding_top >= ADJUST_WIDTH_MARGIN:
            padding_top = 0
        if padding_bottom >= ADJUST_WIDTH_MARGIN:
            padding_bottom = 0
        # 容器宽度 < 阈值时，左右 padding 强制为 0
        if parent_node.data.width < adjust_min:
            padding_left, padding_right, padding_top, padding_bottom = 0,0,0,0 #大模型转码时，只有padding_top和padding_bottom，会自动脑补
        else:
            padding_left, padding_right, padding_top, padding_bottom = _adjust_padding_by_edge_elements(
                parent_node, filtered_children, padding_left, padding_right, padding_top, padding_bottom
            )
        return padding_left, padding_right, padding_top, padding_bottom, True
    return 0, 0, 0, 0, False

def _calc_column_container_padding_by_margin(parent_node,filtered_children):
    parent_x = parent_node.data.x
    parent_y = parent_node.data.y
    parent_width = parent_node.data.width
    parent_height = parent_node.data.height
    parent_right = parent_x + parent_width
    parent_bottom = parent_y + parent_height

    # 1. 找出所有左右间距差值 <= EPSILON 的子控件，取最小边距
    smallest_margin = float("inf")
    for elem in filtered_children:
        elem_x = elem.data.x
        elem_width = elem.data.width
        elem_right = elem_x + elem_width
        left_margin = elem_x - parent_x
        right_margin = parent_right - elem_right
        if abs(left_margin - right_margin) <= EPSILON:
            small_margin = min(left_margin, right_margin)
            if small_margin < smallest_margin:
                smallest_margin = small_margin

    # 2. 计算上下 padding
    first_elem = filtered_children[0]
    last_elem = filtered_children[-1]
    padding_top = first_elem.data.y - parent_y
    padding_bottom = parent_bottom - (last_elem.data.y + last_elem.data.height)
    padding_top = max(0, padding_top)
    padding_bottom = max(0, padding_bottom)

    # 4. 判断是否需要设置左右 padding
    if smallest_margin <= ADJUST_WIDTH_MARGIN and smallest_margin > 0:
        padding_left = smallest_margin
        padding_right = smallest_margin
    else:
        padding_left, padding_right = 0, 0
    return padding_left, padding_right, padding_top, padding_bottom


def calc_column_container_padding(parent_node, filtered_children, design_width=None):
    """
    计算列布局容器的 padding（四个方向：left, right, top, bottom）
    design_width 为设计稿宽度（Metadata.width），未传则用默认值。

    逻辑：
    1. 如果 layout 中已有 padding，直接使用，不重新计算
    2. 否则找出所有左右间距差值 <= EPSILON 的子控件，取最小边距 smallest_margin
    3. 计算上下 padding：第一个元素的 top_margin 和最后一个元素的 bottom_margin
    4. 如果 smallest_margin <= ADJUST_WIDTH_MARGIN 且 > 0，则设置左右 padding

    Args:
        parent_node: 父容器节点
        filtered_children: 过滤后的子元素列表
        design_width: 设计稿根节点宽度（Metadata.width），可选

    Returns:
        tuple: (padding_left, padding_right, padding_top, padding_bottom, should_set_padding)
    """
    adjust_min = get_adjust_width_min(design_width)
    if has_layout_padding(parent_node):
        padding_left, padding_right, padding_top, padding_bottom = _get_original_padding(parent_node, design_width)
    else:
        padding_left, padding_right, padding_top, padding_bottom = _calc_column_container_padding_by_margin(parent_node, filtered_children)
    if padding_left >= ADJUST_WIDTH_MARGIN:
        padding_left = 0
    if padding_right >= ADJUST_WIDTH_MARGIN:
         padding_right = 0
    if padding_top >= ADJUST_WIDTH_MARGIN:
        padding_top = 0
    if padding_bottom >= ADJUST_WIDTH_MARGIN:
        padding_bottom = 0
        # 容器宽度 < 阈值时，左右 padding 强制为 0
    if parent_node.data.width < adjust_min:
        padding_left, padding_right = 0, 0
    else:
        padding_left, padding_right, padding_top, padding_bottom = _adjust_padding_by_edge_elements(
            parent_node, filtered_children, padding_left, padding_right, padding_top, padding_bottom
        )
        return padding_left, padding_right, padding_top, padding_bottom, True
    if not filtered_children:
        return 0, 0, 0, 0, False
    return padding_left, padding_right, padding_top, padding_bottom, True

