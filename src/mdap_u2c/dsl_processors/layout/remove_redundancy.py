# 冗余涂层合并
import numpy
from mdap_u2c.enums import dsl_enum
from mdap_u2c.dsl_processors.layout import gen_tree, tree_rebuild, calc_list_layout, ai_type_def, tree_projection
from mdap_u2c.dsl_processors.layout.preset_layout_processor import is_flex_or_grid_container_two_more, \
    fix_preset_layout_on_container_remove, is_autolayout_elem
from mdap_u2c.dsl_processors.layout.parent_padding import get_parent_padding
from mdap_u2c.utils import component_style_utils
from mdap_u2c.utils.component_style_utils import is_transparent_container, is_transparent_control


def write_del_trans_node_flag(input_tree, flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_trans" not in json_dict:
        json_dict["del_trans"] = []
    json_dict["del_trans"].append(flag_id)


def write_del_cover_node_flag(input_tree, flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_cover" not in json_dict:
        json_dict["del_cover"] = []
    json_dict["del_cover"].append(flag_id)


def get_following_siblings_v2(tree, node):
    """
    获取当前节点同级的后续节点（简洁版本）
    """
    if node.identifier == tree.root:
        return []
    # 获取父节点的所有子节点
    parent_id = tree.parent(node.identifier).identifier
    siblings = tree.children(parent_id)
    # 使用列表切片获取后续节点
    try:
        current_index = [i for i, n in enumerate(siblings) if n.identifier == node.identifier][0]
        return siblings[current_index + 1:]
    except (IndexError, StopIteration):
        return []

def remove_container_only(input_tree, container_uid):
    if container_uid == input_tree.root:
        return []
    parent_uid = input_tree.parent(container_uid).data.uid
    container_node = input_tree.get_node(container_uid)
    # 删除前：若本容器带有分割线标记，则同步到父容器
    if container_node and container_node.data and getattr(container_node.data, "extra_dict", None):
        ed = container_node.data.extra_dict
        if ed.get("have_vertical_line") or ed.get("have_horizon_line"):
            parent_node = input_tree.get_node(parent_uid)
            if parent_node and parent_node.data:
                if ed.get("have_vertical_line"):
                    parent_node.data.extra_dict["have_vertical_line"] = 1
                if ed.get("have_horizon_line"):
                    parent_node.data.extra_dict["have_horizon_line"] = 1
    fix_preset_layout_on_container_remove(input_tree, container_uid)
    next_list = get_following_siblings_v2(input_tree, input_tree.get_node(container_uid))
    grand_son_list = input_tree.children(container_uid)
    for i, elem in enumerate(grand_son_list):
        input_tree.move_node(elem.data.uid, parent_uid)
    #保证层级调整后,顺便不变

    for i, elem in enumerate(next_list):
        input_tree.move_node(elem.data.uid, parent_uid)
    input_tree.remove_node(container_uid)

    return grand_son_list


def get_simular_container_list(input_tree, current_uid):
    children_list_original = input_tree.children(current_uid)
    result = calc_list_layout.judge_container_list(input_tree,input_tree.get_node(current_uid))
    maybe_list = list()

    if result == ai_type_def.LIST_TYPE.LOOP_CONTAINER.value:
        layout_type = tree_projection.calc_layout_type(input_tree.get_node(current_uid), children_list_original)
        for i,elem in enumerate(children_list_original):
            elem.data.extra_dict["list_elem"] = layout_type
            maybe_list.append(elem.data.uid)
        return maybe_list
    return []

def is_list_item(extra_dict):
    if "list_elem" not in extra_dict:
        return False
    if extra_dict["list_elem"] == ai_type_def.LAYOUT_TYPE.ROW.value or extra_dict["list_elem"] == ai_type_def.LAYOUT_TYPE.COLUMN.value:
        return True
    return False

def is_list_container(input_tree,current_uid):
    children_list = input_tree.children(current_uid)
    parent_node = input_tree.get_node(current_uid)
    if len(children_list) >=2 and "list_type" in parent_node.data.extra_dict and parent_node.data.extra_dict[
        "list_type"] == ai_type_def.LIST_TYPE.LOOP_CONTAINER.value :
        return True


def _is_no_brother_container(input_tree,current_uid):
    siblings = input_tree.siblings(current_uid)
    if siblings is None or len(siblings) == 0:
        return True
    return False

def is_reserve_container(input_tree, current_uid):
    current_node = input_tree.get_node(current_uid)
    if current_node.data.src.type != dsl_enum.ComponentType.CONTAINER:
        return False
    elif is_autolayout_elem(current_node) or (is_flex_or_grid_container_two_more(input_tree, current_node) and _is_no_brother_container(input_tree,current_uid)==False):
        return True
    elif is_list_container(input_tree, current_uid) and _is_no_brother_container(input_tree,current_uid)==False :
        return True
    elif is_list_item(current_node.data.extra_dict) :
        return True
    elif _is_two_elements_row_layout(input_tree, current_uid):
        return True
    elif _is_special_column_two_element(input_tree, current_uid):
        return True
    elif component_style_utils.is_redpoint_bubble(current_node.data):
        return True
    elif _is_overflow_hidden_with_over_edge(input_tree, current_node):
        return True
    elif _has_cross_control_with_valid_intersection(input_tree, current_node):
        return True
    return False

def _is_special_column_two_element(input_tree, current_uid):
    if _is_two_elements_column_with_wide_bottom(input_tree, current_uid):
          return True
    elif calc_list_layout.is_image_text_group(input_tree, current_uid):
        return True
    return False


def _is_two_elements_row_layout(input_tree, current_uid):
    """
    检查容器是否包含两个元素且为横向布局，且容器宽度>=300，且其中有一个控件居中
    
    Args:
        input_tree: 树结构
        current_uid: 当前节点的 uid
    
    Returns:
        bool: 如果满足所有条件返回 True
    """
    current_node = input_tree.get_node(current_uid)
    
    # 检查容器宽度是否 >= 300
    if current_node.data.width < 300:
        return False
    
    children_list = input_tree.children(current_uid)
    if len(children_list) != 2:
        return False
    
    # 计算布局类型
    layout_type = tree_projection.calc_layout_type(current_node, children_list)
    
    # 检查是否为横向布局（ROW）
    if layout_type != ai_type_def.LAYOUT_TYPE.ROW:
        return False
    
    # 检查是否有一个控件居中
    if not _has_centered_child(current_node, children_list):
        return False
    
    return True


def _is_two_elements_column_with_wide_bottom(input_tree, current_uid):
    """
    检查容器是否包含两个元素且为纵向布局，且下方元素非文本，宽/高 >= 4
    
    条件：
    1. 容器包含 2 个子元素
    2. 布局类型为纵向布局（COLUMN）
    3. 下方的元素不是文本类型（TEXT 或 CONTAINER_RICH）
    4. 下方元素的 宽度/高度 >= 4
    
    Args:
        input_tree: 树结构
        current_uid: 当前节点的 uid
    
    Returns:
        bool: 如果满足所有条件返回 True，表示该容器需要保留
    """
    current_node = input_tree.get_node(current_uid)
    children_list = input_tree.children(current_uid)
    
    # 检查是否有 2 个子元素
    if len(children_list) != 2:
        return False
    
    # 计算布局类型
    layout_type = tree_projection.calc_layout_type(current_node, children_list)
    
    # 检查是否为纵向布局（COLUMN）
    if layout_type != ai_type_def.LAYOUT_TYPE.COLUMN:
        return False
    
    # 按 y 坐标排序，找到下方的元素
    sorted_children = sorted(children_list, key=lambda c: c.data.y)
    bottom_child = sorted_children[-1]  # y 坐标最大的是下方元素
    
    # 检查下方元素是否为非文本类型
    bottom_type = bottom_child.data.src.type
    if bottom_type == dsl_enum.ComponentType.TEXT or bottom_type == dsl_enum.ComponentType.CONTAINER_RICH:
        return False
    
    # 检查下方元素的 宽/高 >= 4
    bottom_width = bottom_child.data.width
    bottom_height = bottom_child.data.height
    
    if bottom_height <= 0:
        return False
    
    width_height_ratio = bottom_width / bottom_height
    if width_height_ratio < 4 or bottom_height >=8:
        return False
    
    return True


def _has_centered_child(parent_node, children_list):
    """
    检查子元素中是否有一个是居中的
    
    Args:
        parent_node: 父容器节点
        children_list: 子元素列表
    
    Returns:
        bool: 如果有一个子元素居中返回 True
    """
    parent_x = parent_node.data.x
    parent_width = parent_node.data.width
    
    for child in children_list:
        child_x = child.data.x
        child_width = child.data.width
        
        # 计算子元素相对于父容器的左右边距
        left_margin = child_x - parent_x
        right_margin = (parent_x + parent_width) - (child_x + child_width)
        
        # 判断是否居中（左右边距差值 <= 2 像素）
        if abs(left_margin - right_margin) <= 2:
            return True
    
    return False


def _has_cross_control_with_valid_intersection(input_tree, current_node):
    """
    检查控件是否包含元素>=2 并且 cross_control 非空，且交叉区域的宽和高都>=2，
    且内部子元素和 cross_control 也发生交叉或者包含关系
    
    Args:
        input_tree: 树结构
        current_node: 当前节点
    
    Returns:
        bool: 如果满足条件返回 True
    """
    # 检查子元素数量是否 >= 2
    children_list = input_tree.children(current_node.data.uid)
    if len(children_list) < 2:
        return False
    
    # 检查 cross_control 是否非空
    cross_control = current_node.data.cross_control
    if cross_control is None or len(cross_control) == 0:
        return False
    
    # 检查是否存在至少一个交叉区域的宽和高都 >= 2，且内部子元素和 cross_control 也发生交叉或包含关系
    for cross_uid in cross_control:
        cross_node = input_tree.get_node(cross_uid)
        if cross_node is None:
            continue
        if component_style_utils.is_redpoint_bubble(cross_node.data):
            continue
        # 使用 judge_box3 计算交叉区域的宽和高
        _, col, row = gen_tree.judge_box3(current_node.data, cross_node.data)
        
        # 如果交叉区域的宽和高都 >= 2
        if col >= 2 and row >= 2:
            # 检查内部子元素是否和 cross_control 也发生交叉或包含关系
            if _children_intersect_with_cross_control(children_list, cross_node):
                return True
    
    return False


def _children_intersect_with_cross_control(children_list, cross_node):
    """
    检查子元素是否和 cross_control 发生交叉或包含关系
    
    Args:
        children_list: 子元素列表
        cross_node: 交叉控件节点
    
    Returns:
        bool: 如果存在至少一个子元素与 cross_node 发生交叉或包含关系返回 True
    """
    for child in children_list:
        # 使用 judge_box 判断交叉或包含关系
        # result > 0 表示发生了交叉或包含关系
        result = gen_tree.judge_box(child.data, cross_node.data)
        if result > 0:
            return True
    return False


def _is_overflow_hidden_with_over_edge(input_tree, current_node):
    """
    检查容器是否设置了 overflow: hidden 且有超出边界的内容。
    若当前节点 over_edge 长度为 1，且该节点为右边缘超出，则从该节点向下遍历找到
    「子元素数量不等于 1」的那一层；若该层为行布局且元素数量>=3，则设置 overflow: scroll。
    
    Args:
        input_tree: 树结构
        current_node: 当前节点
    
    Returns:
        bool: 如果满足条件返回 True
    """
    over_edge = current_node.data.over_edge
    if over_edge is None or len(over_edge) == 0:
        return False
    # 检查 style 是否存在
    if current_node.data.src.style is None:
        return False
    # 检查 overflow 是否为 hidden
    overflow = getattr(current_node.data.src.style, 'overflow', None)
    if overflow == 'hidden':
        return True
    children_list = input_tree.children(current_node.data.uid)
    for child in children_list:
        if child.data.src.type == dsl_enum.ComponentType.TEXT  or child.data.src.type == dsl_enum.ComponentType.CONTAINER_RICH :
            return True
    return False


def remove_transparent_control(input_tree, current_uid = None):
    if current_uid == None:
        current_uid = input_tree.root
    children_list = input_tree.children(current_uid)
    get_simular_container_list(input_tree, current_uid)
    current_node = input_tree.get_node(current_uid)

    if same_color_with_parent(input_tree,current_uid) and  is_reserve_container(input_tree,current_uid)==False :
        if current_node.data.src.type == dsl_enum.ComponentType.TEXT :
         input_tree.remove_node(current_uid)
         _write_same_color_with_parent_flag(input_tree,current_uid)
        else:
            grand_son_list =remove_container_only(input_tree, current_uid)
            _write_same_color_with_parent_flag(input_tree,current_uid)
            for i, grand_elem in enumerate(grand_son_list):
                remove_transparent_control(input_tree, grand_elem.data.uid)
        return

    if len(children_list) == 0 and is_transparent_container(current_node.data.src):
        input_tree.remove_node(current_uid)
    elif 1 <= len(children_list) <= 2  or _is_no_brother_container(input_tree,current_uid) : #=3的时候也有很多需要的容器,比如垂直的文本
        if len(children_list) == 1 and component_style_utils.is_redpoint_bubble(current_node.data) and is_transparent_container(current_node.data.src):
            grand_son_list = remove_container_only(input_tree, current_node.data.uid)
            write_del_trans_node_flag(input_tree, current_node.data.uid)
            grand_elem = grand_son_list[0]
            grand_elem.data.ai_type = current_node.data.ai_type
            remove_transparent_control(input_tree, grand_elem.data.uid)
        elif current_uid != input_tree.root and is_transparent_container(current_node.data.src)  and is_reserve_container(input_tree,current_uid)==False :
            grand_son_list = remove_container_only(input_tree, current_node.data.uid)
            write_del_trans_node_flag(input_tree, current_node.data.uid)
            for i, grand_elem in enumerate(grand_son_list):
                remove_transparent_control(input_tree, grand_elem.data.uid)
        else:
            for i, elem in enumerate(children_list):
                remove_transparent_control(input_tree, elem.data.uid)
    else:
        for i, elem in enumerate(children_list):
            remove_transparent_control(input_tree, elem.data.uid)

def _write_same_color_with_parent_flag(input_tree,flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_same_color" not in json_dict:
        json_dict["del_same_color"] = []
    json_dict["del_same_color"].append(flag_id)
    

def same_color_with_parent(input_tree,current_uid):

    current_node = input_tree.get_node(current_uid)
    parent_node = input_tree.parent(current_uid)
    if current_uid == input_tree.root:
        return False

    if current_node.data.src.type == dsl_enum.ComponentType.TEXT:
        #如果一个文本的颜色和父容器背景色一致,则返回TRUE
        text_color = current_node.data.src.style.color
        parent_bg_color = parent_node.data.src.style.background_color
        if text_color is not None and parent_bg_color is not None:
            return text_color == parent_bg_color
    elif   current_node.data.src.type == dsl_enum.ComponentType.CONTAINER:
        #如果一个容器的颜色和父容器背景色一致,则返回TRUE
        container_bg_color = current_node.data.src.style.background_color
        parent_bg_color = parent_node.data.src.style.background_color
        #当前容器和父容器大小完全一致,且
        if container_bg_color is not None and parent_bg_color is not None:
            # 判断背景色是否一致
            if container_bg_color == parent_bg_color:
                if current_node.data.src.style.border_color is None and current_node.data.src.style.background is None and current_node.data.src.style.box_shadow is None:
                    return True
    return False


# 去掉根节点背景图的圆角属性。仅当 top_bar_height > 0 或 is_translucent_top_bar 为 True 时执行。
# extra_dict 可来自 context.dsl.metadata.extra_dict 或 context_share_data 构造的 dict。
def remove_bg_radius(src, extra_dict=None):
    if extra_dict is None:
        extra_dict = {}
    top_bar_height = extra_dict.get("top_bar_height") or 0
    is_translucent = extra_dict.get("is_translucent_top_bar") in (True, "TRUE", "true")
    if not (top_bar_height > 0 or is_translucent):
        return
    src.style.border_radius = None
    src.style.border_top_left_radius = None
    src.style.border_top_right_radius = None
    src.style.border_bottom_right_radius = None
    src.style.border_bottom_left_radius = None


def _split_line_projection_size(width, height, current_node_data):
    """
    分割线投影时宽高至少取 1：若为分割线且宽度或高度 < 1，则投影用尺寸取 1。
    当分割线高度为 0 时，投影高度改为 2，且投影起始 y 坐标减 1（通过 y_offset=-1 表示）。
    返回 (proj_width, proj_height, y_offset) 用于投影区域计算，y_offset 非分割线或高度非 0 时为 0。
    """
    ai_type = getattr(current_node_data, "ai_type", None)
    if ai_type != ai_type_def.AI_TYPE.SPLIT_LINE.value:
        return width, height, 0
    proj_w = max(1, width) if width is not None else 1
    # 高度为 0 时：投影高度取 2，投影起始 y 坐标 -1
    if height is None or (isinstance(height, (int, float)) and height < 1):
        return proj_w, 2, -1
    proj_h = max(1, height)
    return proj_w, proj_h, 0


def generate_projection_map(projection_map, current_node_data, root_width, root_height, semi_translucent_map):
    # 创建投影图矩阵
    # 获取所有节点
    semi_translucent_flag = False
    result = is_transparent_control(current_node_data.src)
    if result == 1:
        return
    elif result == 2:  # 半透先记录下来
        semi_translucent_flag = True
    x = current_node_data.x
    y = current_node_data.y
    width = current_node_data.width
    height = current_node_data.height
    # 分割线且宽或高 < 1 时，投影最小宽高取 1；高度为 0 时投影高度为 2、起始 y 减 1
    width, height, y_offset = _split_line_projection_size(width, height, current_node_data)
    seq = current_node_data.seq
    if width > 0 and height > 0:
        # 确保坐标在有效范围内
        x_start = max(0, int(x))
        y_start = max(0, int(y + y_offset))
        x_end = min(int(root_width), int(x + width))
        y_end = min(int(root_height), int(y + height))
        # 批量赋值
        if x_start < x_end and y_start < y_end:
            # 检查是否存在圆角属性
            border_radii = component_style_utils.get_border_radii(current_node_data.src)
            border_radii = [component_style_utils.convert_str_to_int(radius, min(width, height)) for radius in border_radii]
            # 如果没有圆角或者圆角都为0，使用原来的快速填充方法
            if all(radius <= 0 for radius in border_radii):
                if semi_translucent_flag:
                    semi_translucent_map[y_start:y_end, x_start:x_end] = seq
                else:
                    projection_map[y_start:y_end, x_start:x_end] = seq
            else:
                # 处理圆角的情况，需要逐像素判断
                for py in range(y_start, y_end):
                    for px in range(x_start, x_end):
                        # 计算当前点相对于元素左上角的位置
                        local_x = px - x
                        local_y = py - y

                        # 判断当前点是否在带圆角的矩形区域内
                        if is_point_in_rounded_rect(local_x, local_y, width, height, border_radii):
                            if semi_translucent_flag:
                                semi_translucent_map[py, px] = seq
                            else:
                                projection_map[py, px] = seq


def is_point_in_rounded_rect(local_x, local_y, width, height, border_radii):
    """
    判断点是否在带圆角的矩形区域内
    local_x, local_y: 点相对于矩形左上角的坐标
    width, height: 矩形尺寸
    border_radii: (top_left, top_right, bottom_left, bottom_right) 圆角半径元组
    """
    top_left_r, top_right_r, bottom_left_r, bottom_right_r = border_radii

    # 如果点在矩形的直角区域，直接返回True
    if local_x >= top_left_r and local_x < width - top_right_r:
        return True
    if local_y >= top_left_r and local_y < height - bottom_left_r:
        return True

    # 如果点在四个圆角区域，需要进行圆角判断
    # 左上角圆角
    if local_x < top_left_r and local_y < top_left_r:
        return (local_x - top_left_r) ** 2 + (local_y - top_left_r) ** 2 <= top_left_r ** 2

    # 右上角圆角
    if local_x >= width - top_right_r and local_y < top_right_r:
        return (local_x - (width - top_right_r)) ** 2 + (local_y - top_right_r) ** 2 <= top_right_r ** 2

    # 左下角圆角
    if local_x < bottom_left_r and local_y >= height - bottom_left_r:
        return (local_x - bottom_left_r) ** 2 + (local_y - (height - bottom_left_r)) ** 2 <= bottom_left_r ** 2

    # 右下角圆角
    if local_x >= width - bottom_right_r and local_y >= height - bottom_right_r:
        return (local_x - (width - bottom_right_r)) ** 2 + (
                    local_y - (height - bottom_right_r)) ** 2 <= bottom_right_r ** 2

    return True

def get_min_seq_from_map_exclude_rounded_rect(projection_map, current_node):
    """
    计算投影矩阵中的最小seq值，如果current_node有圆角，则排除圆角区域的值。
    分割线投影时最小宽高取 1。
    
    Args:
        projection_map: 投影矩阵
        current_node: 当前节点
        
    Returns:
        int: 最小seq值，如果没有有效值返回-1
    """
    try:
        x = current_node.data.x
        y = current_node.data.y
        width = current_node.data.width
        height = current_node.data.height
        proj_width, proj_height, y_offset = _split_line_projection_size(width, height, current_node.data)

        if x < 0 or y < 0 or proj_width <= 0 or proj_height <= 0:
            return -1

        x_start = int(x)
        y_start = max(0, int(y + y_offset))
        x_end = int(x + proj_width)
        y_end = int(y + proj_height)

        # 获取对应区域的投影矩阵
        new_array = projection_map[y_start:y_end, x_start:x_end]
        if new_array.size == 0:
            return -1

        # 检查是否有圆角（分割线投影区域用 proj 尺寸）
        border_radii = component_style_utils.get_border_radii(current_node.data.src)

        # 如果没有圆角或者圆角都为0，使用原来的方法
        if all(radius <= 0 for radius in border_radii):
            return numpy.min(new_array)

        # 如果有圆角，需要排除圆角区域（用投影尺寸参与圆角判断）
        valid_values = []
        for local_y in range(new_array.shape[0]):
            for local_x in range(new_array.shape[1]):
                if is_point_in_rounded_rect(local_x, local_y, proj_width, proj_height, border_radii):
                    valid_values.append(new_array[local_y, local_x])

        if not valid_values:
            return -1
        return numpy.min(valid_values)

    except Exception as e:
        return -1

def get_min_seq_from_map(projection_map, current_node):
    x = current_node.data.x
    y = current_node.data.y
    width = current_node.data.width
    height = current_node.data.height
    # 分割线投影时最小宽高取 1；高度为 0 时投影高度为 2、起始 y 减 1
    proj_width, proj_height, y_offset = _split_line_projection_size(width, height, current_node.data)
    if x >= 0 and y >= 0 and proj_width > 0 and proj_height > 0:
        x_start = int(x)
        y_start = max(0, int(y + y_offset))
        x_end = int(x + proj_width)
        y_end = int(y + proj_height)
        new_array = projection_map[y_start:y_end, x_start:x_end]
        if new_array.size == 0:
            return -1
        return numpy.min(new_array)
    return -1


def write_maybe_overlap_flag(input_tree, current_uid):
    current_node = input_tree.get_node(current_uid)
    current_node.data.extra_dict["maybe_overlap"] = True

#当一个容器的子元素和它的大小宽高,圆角完全一致,且他的子元素颜色不透明,则返回true
def is_child_same_with_parent(input_tree,current_id):
    current_node = input_tree.get_node(current_id)
    # 只处理容器类型
    if current_node.data.src.type != dsl_enum.ComponentType.CONTAINER:
        return False
    
    # 获取子元素列表
    children_list = input_tree.children(current_id)
    # 必须只有一个子元素
    if len(children_list) != 1:
        return False
    
    child_node = children_list[0]
    
    # 比较宽高是否完全一致
    parent_width = current_node.data.width
    parent_height = current_node.data.height
    child_width = child_node.data.width
    child_height = child_node.data.height
    
    if abs(parent_width - child_width) > 0.01 or abs(parent_height - child_height) > 0.01:
        return False
    
    # 比较圆角是否完全一致
    parent_border_radii = component_style_utils.get_border_radii(current_node.data.src)
    child_border_radii = component_style_utils.get_border_radii(child_node.data.src)
    if parent_border_radii != child_border_radii:
        return False
    
    # 检查子元素的背景色是否不透明
    child_bg_color = child_node.data.src.style.background_color
    if child_bg_color is None:
        return False
    
    # 检查透明度，alpha >= 0.1 认为不透明（参考 is_transparent_container 的判断）
    child_alpha = component_style_utils.get_color_alpha(child_bg_color)
    if child_alpha < 0.1:
        return False
    
    return True
def _is_special_overlap_control(input_tree, current_node, projection_map=None):
    if current_node.data.uid == input_tree.root:
        return True
    elif component_style_utils.is_redpoint_bubble(current_node.data):
        return True
    # 当控件子元素>=2，且子元素可完全遮盖父控件，且子元素seq=min_seq时保留
    elif projection_map is not None:
        children_list = input_tree.children(current_node.data.uid)
        if len(children_list) >= 2:
            min_seq = get_min_seq_from_map(projection_map, current_node)
            if min_seq >= 0:
                parent_x = current_node.data.x
                parent_y = current_node.data.y
                parent_right = parent_x + current_node.data.width
                parent_bottom = parent_y + current_node.data.height
                child_min_x = min(c.data.x for c in children_list)
                child_min_y = min(c.data.y for c in children_list)
                child_max_right = max(c.data.x + c.data.width for c in children_list)
                child_max_bottom = max(c.data.y + c.data.height for c in children_list)
                # 子元素并集完全覆盖父控件
                if (child_min_x <= parent_x and child_min_y <= parent_y and
                        child_max_right >= parent_right and child_max_bottom >= parent_bottom):
                    # 子元素seq等于min_seq（至少有一个子元素在投影最上层）
                    if any(c.data.seq == min_seq for c in children_list):
                        return True
    return False

def remove_overlapped_control_by_projection_map(input_tree, current_uid, projection_map, semi_translucent_map):
    current_node = input_tree.get_node(current_uid)
    min_seq = get_min_seq_from_map(projection_map, current_node)

    if is_child_same_with_parent(input_tree,current_uid):
        grand_son_list = remove_container_only(input_tree, current_uid)
        write_del_cover_node_flag(input_tree,current_uid)
        for i, grand_elem in enumerate(grand_son_list):
            remove_transparent_control(input_tree, grand_elem.data.uid)
        return
    if  current_node.data.seq < min_seq and _is_special_overlap_control(input_tree, current_node, projection_map) is False :
        grandson_list = remove_container_only(input_tree, current_uid)
        write_del_cover_node_flag(input_tree, current_uid)
        for i, elem in enumerate(grandson_list):
            remove_overlapped_control_by_projection_map(input_tree, elem.data.uid, projection_map, semi_translucent_map)
    else:
        min_semi_seq = get_min_seq_from_map(semi_translucent_map, current_node)
        if current_node.data.seq < min_semi_seq:
            write_maybe_overlap_flag(input_tree, current_uid)
        children_list = input_tree.children(current_uid)
        for i, elem in enumerate(children_list):
            remove_overlapped_control_by_projection_map(input_tree, elem.data.uid, projection_map, semi_translucent_map)

def gen_projection_map(input_tree, current_id, projection_map):
    root_node = input_tree.get_node(input_tree.root)
    root_height = root_node.data.height
    root_width = root_node.data.width
    if current_id == input_tree.root:
        projection_map['projection_map'] = numpy.zeros((int(root_height), int(root_width)), dtype=numpy.int32)
        projection_map["semi_translucent_map"] = numpy.zeros((int(root_height), int(root_width)), dtype=numpy.int32)
    current_node = input_tree.get_node(current_id)

    generate_projection_map(projection_map['projection_map'], current_node.data, root_width, root_height,
                                        projection_map["semi_translucent_map"])
    children_list = input_tree.children(current_id)
    for i, elem in enumerate(children_list):
        gen_projection_map(input_tree, elem.data.uid, projection_map)


def remove_overlap_control(input_tree):
    projection_map = dict()
    gen_projection_map(input_tree, input_tree.root, projection_map)
    remove_overlapped_control_by_projection_map(input_tree, input_tree.root,
                                                            projection_map['projection_map'],
                                                            projection_map["semi_translucent_map"])
    return projection_map

