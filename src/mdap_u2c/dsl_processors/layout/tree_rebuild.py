import json
import copy

import treelib
import logging

from mdap_u2c.dsl_processors.layout.calc_layout_position import flex_enum_to_str
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models.dsl_model import ImageComponent, ContainerComponent
from mdap_u2c.utils import StyleValueUtils
from treelib import Tree, Node
import functools

from mdap_u2c.constant import FIGMA_DESIGN_WIDTH
from mdap_u2c.dsl_processors.layout import find_special_control, tree_projection, calc_layout_position, \
    gen_tree, child_over_parent_process, ai_type_def
from mdap_u2c.dsl_processors.layout import remove_redundancy
from mdap_u2c.models.dsl_model import Style
_logger = logging.getLogger("tree_rebuild")


def beyond_screen_judge(json_dict,share_tree_info):
    root_height = share_tree_info.root_height
    root_width = share_tree_info.root_width
    current_id = json_dict['id']
    current_y = json_dict['props']['attrs']['y']
    current_height = json_dict['props']['style']['height']
    top_out = 0
    bottom_out = 0

    if current_y < 0:
        json_dict['id'] = current_id
        top_out = 1

    if current_y + current_height > root_height:
        json_dict['id'] = current_id
        bottom_out = 1
    find_children = 'children' in json_dict
    if find_children:
        children_list = json_dict['children']
        for i, elem in enumerate(children_list):
            temp_top_out, temp_bottom_out = beyond_screen_judge(elem, share_tree_info)
            if temp_top_out == 1:
                top_out = 1
            if temp_bottom_out == 1:
                bottom_out = 1
    return top_out, bottom_out

def _is_horizontal_split_line(data):
    """
    判断是否是宽度远大于高度的水平分割线
    条件：ai_type 为 SPLIT_LINE 且 宽度 > 高度 * 3
    """
    if data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
        if data.height <=2  and data.width >=200:
            return True
    return False


def compare_x(elem1, elem2):
    if isinstance(elem1, Node):
        a1 = elem1.data
        a2 = elem2.data
    else:
        a1 = elem1
        a2 = elem2
    w1 = float(getattr(a1, "width", 0) or 0)
    w2 = float(getattr(a2, "width", 0) or 0)
    x1 = float(getattr(a1, "x", 0) or 0)
    x2 = float(getattr(a2, "x", 0) or 0)
    rx1 = x1 + max(w1 - 1, 0)
    rx2 = x2 + max(w2 - 1, 0)
    x_overlap = max(x1, x2) <= min(rx1, rx2)
    if (w1 == 0 or w2 == 0) and x_overlap:
        return 0
    result = gen_tree.judge_box(a1, a2)

    if result > 0:
        return 0
    else:
        # 当其中一个元素是宽度远大于高度的水平分割线时，改成比较 y 坐标
        if _is_horizontal_split_line(a1) or _is_horizontal_split_line(a2):
            if a1.y > a2.y:
                return 1
            elif a1.y < a2.y:
                return -1
            else:
                return 0
        
        if a1.x > a2.x:
            return 1
        elif a1.x < a2.x:
            return -1
        else:
            return 0


def compare_y(elem1, elem2):
    a1, a2 = elem1.data, elem2.data
    h1 = float(getattr(a1, "height", 0) or 0)
    h2 = float(getattr(a2, "height", 0) or 0)
    y1 = float(getattr(a1, "y", 0) or 0)
    y2 = float(getattr(a2, "y", 0) or 0)
    ry1 = y1 + max(h1 - 1, 0)
    ry2 = y2 + max(h2 - 1, 0)
    y_overlap = max(y1, y2) <= min(ry1, ry2)
    if (h1 == 0 or h2 == 0) and y_overlap:
        return 0
    result = gen_tree.judge_box(a1, a2)
    if result > 0:
        return 0
    else:
        if a1.y > a2.y:
            return 1
        elif a1.y < a2.y:
            return -1
        else:
            return 0


def compare_x_y(elem1, elem2):
    if isinstance(elem1, treelib.Node):
        elem1 = elem1.data
        elem2 = elem2.data
    w1 = float(getattr(elem1, "width", 0) or 0)
    h1 = float(getattr(elem1, "height", 0) or 0)
    w2 = float(getattr(elem2, "width", 0) or 0)
    h2 = float(getattr(elem2, "height", 0) or 0)
    x1, y1 = float(getattr(elem1, "x", 0)), float(getattr(elem1, "y", 0))
    x2, y2 = float(getattr(elem2, "x", 0)), float(getattr(elem2, "y", 0))

    # 坐标区间重叠：x、y 方向区间均有重叠（宽/高为 0 时退化为点）
    rx1 = x1 + max(w1 - 1, 0)
    ry1 = y1 + max(h1 - 1, 0)
    rx2 = x2 + max(w2 - 1, 0)
    ry2 = y2 + max(h2 - 1, 0)
    x_overlap = max(x1, x2) <= min(rx1, rx2)
    y_overlap = max(y1, y2) <= min(ry1, ry2)
    intervals_overlap = x_overlap and y_overlap

    if (w1 == 0 or h1 == 0 or w2 == 0 or h2 == 0) and intervals_overlap:
        return 0

    result, col, row = gen_tree.judge_box3(elem1, elem2)
    if result > 0.1 or (0 < result <= 0.1 and max(col, row) >= 1):
        return 0
    else:
        y1 = int(elem1.y) >> 3
        y2 = int(elem2.y) >> 3

        if abs(elem1.x + y1 * 100) > abs(elem2.x + y2 * 100):
            return 1
        elif abs(elem1.x + y1 * 100) < abs(elem2.x + y2 * 100):
            return -1
        else:
            return 0


def sort_tree_by_split(children_list, parent_value):
    if  parent_value.layout_type != None:
        if parent_value.layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value:
            children_list.sort(key=functools.cmp_to_key(compare_y))
        elif parent_value.layout_type == ai_type_def.LAYOUT_TYPE.ROW.value:
            children_list.sort(key=functools.cmp_to_key(compare_x))
        else:
            children_list.sort(key=functools.cmp_to_key(compare_x_y))
    else:
        children_list.sort(key=functools.cmp_to_key(compare_x_y))


def change_image_type(current_node_data):
    uid = current_node_data.uid
    _logger.warning(f"图片包含子节点,改成容器{uid}")
    new_container = ContainerComponent(id=uid, style=current_node_data.src.style, layout=current_node_data.src.layout, props=None)
    new_container.figma = current_node_data.src.figma
    new_container.style.background_image = current_node_data.src.figma.node_id
    container_style_process(new_container)
    current_node_data.src = new_container


def change_text_container(current_node_data, child_list):
    old_id = current_node_data.uid
    new_text_id = old_id + 'Child'
    _logger.warning(f"文字包含子节点,改成容器{old_id}")

    old_text_container = copy.deepcopy(current_node_data.src)
    old_text_container.children = list()

    new_container = ContainerComponent(id=old_id, style=current_node_data.src.style, layout=current_node_data.src.layout,
                                       props=None)

    new_container.style = Style()
    new_container.style.margin_left = current_node_data.src.style.margin_left
    new_container.style.margin_right = current_node_data.src.style.margin_right
    new_container.style.margin_top = current_node_data.src.style.margin_top
    new_container.style.margin_bottom = current_node_data.src.style.margin_bottom
    new_container.style.width = _to_pt_str(current_node_data.src.style.width)
    new_container.style.height = current_node_data.src.style.height
    new_container.style.align_self = current_node_data.src.style.align_self
    new_container.style.align_items = current_node_data.src.style.align_items
    new_container.style.justify_content = current_node_data.src.style.align_self
    new_container.style.flex_direction = current_node_data.src.style.flex_direction
    new_container.style.top = current_node_data.src.style.top
    new_container.style.left = current_node_data.src.style.left
    new_container.style.right = current_node_data.src.style.right
    new_container.style.bottom = current_node_data.src.style.bottom
    new_container.style.display = current_node_data.src.style.display
    new_container.style.position = current_node_data.src.style.position

    new_container.type = "container"
    old_text_container.id = new_text_id
    old_text_container.style.position = calc_layout_position.flex_enum_to_str(dsl_enum.PositionType.ABSOLUTE)
    old_text_container.style.margin_left = None
    old_text_container.style.margin_right = None
    old_text_container.style.margin_top = None
    old_text_container.style.margin_bottom = None

    if new_container.style.position is None:
        new_container.style.position = flex_enum_to_str(dsl_enum.PositionType.RELATIVE)

    child_list.insert(0, old_text_container)
    new_container.children = child_list
    current_node_data.src = new_container

#兼容代码。不支持图片和文本控件当容器
def image_text_to_container(parent_data, child_list):
    if parent_data.src.type == dsl_enum.ComponentType.IMAGE:
        change_image_type(parent_data)
    elif parent_data.src.type == dsl_enum.ComponentType.TEXT:
        change_text_container(parent_data, child_list)

def container_style_process(src):
    if src.style.background_image is not None :
        src.style.background_size = "cover"
        if src.style.background_position is None:
           src.style.background_position = "center"

def image_style_process(src):
    src.style.object_fit = "cover"

def _to_pt_str(value):
    """将值转换为 Python float 类型，处理 numpy 类型"""
    if value is None:
        return None
    return StyleValueUtils.format_value_with_unit(value)


def _spacing_value_is_non_zero(val):
    """判断 margin/padding 值是否非 0。None、0、0px 等视为 0；auto、calc() 等视为非 0"""
    if val is None:
        return False
    s = str(val).strip()
    if s == "auto":
        return True
    try:
        num = float(s.replace("px", "").replace("pt", "").replace("%", "").strip())
        return num != 0
    except (ValueError, TypeError):
        return True  # calc() 等复杂表达式视为非 0


def _to_shorthand_part(val):
    """将单个方向的值转为简写中的部分，None 或 0 返回 '0'"""
    if val is None:
        return "0"
    s = str(val).strip()
    if s == "auto":
        return "auto"
    try:
        num = float(s.replace("px", "").replace("pt", "").replace("%", "").strip())
        if num == 0:
            return "0"
        return s
    except (ValueError, TypeError):
        return s


def _to_padding_shorthand_part(val):
    """将 padding 值转为简写部分，负值视为 0（CSS padding 不能为负）"""
    if val is None:
        return "0"
    s = str(val).strip()
    try:
        num = float(s.replace("px", "").replace("pt", "").replace("%", "").strip())
        if num <= 0:
            return "0"
        return s
    except (ValueError, TypeError):
        return s


def _convert_margin_padding_to_shorthand(style):
    """
    若 margin-top/right/bottom/left 或 padding-top/right/bottom/left 中有非 0 值，
    则改为 Margin/Padding 简写形式（top right bottom left），并清空分写属性。
    """
    if style is None:
        return
    # Margin 简写
    mt, mr, mb, ml = style.margin_top, style.margin_right, style.margin_bottom, style.margin_left
    if any(_spacing_value_is_non_zero(v) for v in (mt, mr, mb, ml)):
        style.margin = " ".join(
            _to_shorthand_part(v) for v in (mt, mr, mb, ml)
        )
        style.margin_top = None
        style.margin_right = None
        style.margin_bottom = None
        style.margin_left = None
    # Padding 简写（padding 不能为负，使用 _to_padding_shorthand_part 将负值转为 0）
    pt, pr, pb, pl = style.padding_top, style.padding_right, style.padding_bottom, style.padding_left
    if any(_spacing_value_is_non_zero(v) for v in (pt, pr, pb, pl)):
        style.padding = " ".join(
            _to_padding_shorthand_part(v) for v in (pt, pr, pb, pl)
        )
        style.padding_top = None
        style.padding_right = None
        style.padding_bottom = None
        style.padding_left = None


def write_display_flex(parent_data):
    if parent_data.src.style.display == "grid":
        return
    if parent_data.src.style.flex_direction is not  None or parent_data.src.style.justify_content is not  None or parent_data.src.style.align_items is not  None or parent_data.src.style.align_self is not None:
        parent_data.src.style.display = "flex"
def write_width_height(parent_data,context_share_data):
    figma_width = context_share_data["figma_width"]
    figma_height = context_share_data["figma_height"]
    calc_layout_position.replace_width_height_by_100_percent(parent_data, figma_width, figma_height)
    parent_width = float(round(parent_data.width, 1))
    parent_height = float(round(parent_data.height, 1))
    if "edit_width" not in parent_data.extra_dict:
        if parent_width > 0 :
            parent_data.src.style.width = _to_pt_str(parent_width)
        elif parent_data.src.layout is not None and  parent_data.src.layout.size.width is not None:
            parent_data.src.style.width = _to_pt_str(parent_data.src.layout.size.width)
    if "edit_height" not in parent_data.extra_dict:
        if parent_height > 0:
            parent_data.src.style.height = _to_pt_str(parent_height)
        elif parent_data.src.layout is not None and parent_data.src.layout.size.height is not  None:
            parent_data.src.style.height = _to_pt_str(parent_data.src.layout.size.height)

def tree_to_dsl(input_tree, current_uid,context_share_data):
    parent_data = input_tree.get_node(current_uid).data
    if current_uid == input_tree.root:
        extra_dict = {
            "top_bar_height": context_share_data.get("top_bar_height"),
            "is_translucent_top_bar": context_share_data.get("is_translucent_top_bar"),
        }
        remove_redundancy.remove_bg_radius(parent_data.src, extra_dict)
    elif parent_data.src.type == dsl_enum.ComponentType.CONTAINER:
        container_style_process(parent_data.src)
    elif parent_data.src.type == dsl_enum.ComponentType.IMAGE:
        image_style_process(parent_data.src)
    if parent_data.src.style.display == "none":
        return None
    children_list = input_tree.children(current_uid)
    sort_tree_by_split(children_list, parent_data)
    if "debug" in context_share_data and context_share_data["debug"] == 1:
        parent_data.src.id = current_uid
    write_width_height(parent_data,context_share_data)
    if len(children_list) != 0:
        child_list = list()
        calc_layout_position.calc_flex_relative_layout(input_tree, input_tree.get_node(current_uid), children_list, context_share_data)
        parent_data = input_tree.get_node(current_uid).data
        write_display_flex(parent_data)
        parent_data.src.children = list()
        for i, elem in enumerate(children_list):
            sub_component = tree_to_dsl(input_tree, elem.data.uid,context_share_data)
            if sub_component is None:
                continue
            sub_component.parent_id = parent_data.src.id
            child_list.append(sub_component)
        if len(child_list) > 0:
            image_text_to_container(parent_data, child_list)
            parent_data.src.children = child_list
    elif parent_data.src.type != dsl_enum.ComponentType.CONTAINER_RICH:
        # 子节点被移走后（如 bg_image 处理），需清空 src.children，避免输出 stale 的 component_copy.children
        parent_data.src.children = list()
    # 若 margin/padding 分写值非 0，则改为 Margin/Padding 简写
    _convert_margin_padding_to_shorthand(parent_data.src.style)
    return parent_data.src


def tree_to_json(input_tree, current_uid):
    parent_data = input_tree.get_node(current_uid).data
    json_dict = parent_data.jsonformat()
    if parent_data.src.type == dsl_enum.ComponentType.TEXT:
        json_dict["text"] = parent_data.src.props.text
    parent_value = parent_data.src
    json_dict["origin_id"] = parent_value.id
    if parent_value.figma is not None:
        json_dict["figma_id"] = parent_value.figma.node_id
    children_list = input_tree.children(current_uid)
    sort_tree_by_split(children_list, parent_data)  # 列表排序
    if len(children_list) != 0:
        json_list = list()

        for i, elem in enumerate(children_list):
            sub_json = tree_to_json(input_tree, elem.data.uid)
            if sub_json is None:
                continue
            json_list.append(sub_json)
        if len(json_list) > 0:
            json_dict["children"] = json_list
    return json_dict


if __name__ == '__main__':
    with open('./test.json') as f:
        json_data = json.load(f)
