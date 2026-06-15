import copy
import logging
from typing import Optional

from mdap_u2c.constant import FIGMA_DESIGN_WIDTH
from mdap_u2c.dsl_processors.layout import gen_tree, child_over_parent_process,ai_type_def
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import component_style_utils

from mdap_u2c.models.dsl_model import AbstractComponent

_logger = logging.getLogger("tree_rebuild")

class TreeExtraInfo(object):
    def __init__(self):
        self.root_width = 0
        self.root_height = 0
        self.seq = [0.0]


def write_over_screen_flag(componet: AbstractComponent, value):
    if componet.extensions is None:
        componet.extensions = dict()
        componet.extensions["over_screen"] = value

def beyond_screen_process(component: AbstractComponent, share_tree_info):
    root_width = share_tree_info.root_width
    root_height = share_tree_info.root_height
    current_id = component.id
    if component.layout is None: #部分节点例如复文本没有layout信息
        return
    origin_x = component.layout.position.x
    origin_y = component.layout.position.y
    origin_width = component.layout.size.width
    origin_height = component.layout.size.height

    crop_x1 = 0
    crop_y1 = 0
    crop_x2 = origin_width
    crop_y2 = origin_height

    new_x = origin_x
    new_y = origin_y
    new_width = origin_width
    new_height = origin_height
    if origin_x + origin_width <= 0 or origin_y + origin_height <= 0 or origin_x >= root_width:
        _logger.warning(current_id + 'out of range')
        return True
    if origin_y >= root_height:
        _logger.warning(current_id + 'out of range')
        return True
    new_width = origin_width
    new_height = origin_height
    if origin_x < 0:
        crop_x1 = -1 * origin_x
        new_width = origin_width + origin_x
        new_x = 0
    if origin_y < 0:
        crop_y1 = -1 * origin_y
        new_height = origin_height + origin_y
        new_y = 0
    if new_x + new_width > root_width:
        crop_x2 = root_width - component.layout.position.x
        new_width = root_width - new_x
    if new_y + new_height > root_height:
        write_over_screen_flag(component, "bottom")

    component.layout.size.width = new_width
    component.layout.size.height = new_height
    component.layout.position.x = new_x
    component.layout.position.y = new_y
    return False


def _should_use_child_as_root(parent: AbstractComponent, child: AbstractComponent) -> bool:
    """
    判断是否应该用子节点作为根结点。
    条件：根结点只有一个子节点，且子节点和父容器大小宽高一样，且存在背景色，且背景色不透明，
    且子节点存在圆角属性，且节点宽度=375。
    """
    if parent.layout is None or child.layout is None:
        return False
    if child.style is None:
        return False
    parent_width = parent.layout.size.width
    parent_height = parent.layout.size.height
    child_width = child.layout.size.width
    child_height = child.layout.size.height
    # 子节点和父容器大小宽高一样
    if int(child_width) != int(parent_width) or int(child_height) != int(parent_height):
        return False
    # 存在背景色且不透明
    bg_color = child.style.background_color
    if bg_color is None:
        return False
    if component_style_utils.get_color_alpha(bg_color) < 0.02:
        return False
    # 子节点存在圆角属性
    if child.style.border_radius is not None and child_width != FIGMA_DESIGN_WIDTH:
        return False
    return True


def _parse_opacity_value(opacity) -> float:
    """解析 style.opacity，返回 0~1 的浮点数，无效时返回 1.0。"""
    if opacity is None:
        return 1.0
    if isinstance(opacity, (int, float)):
        return float(opacity)
    if isinstance(opacity, str):
        try:
            return float(opacity)
        except (ValueError, TypeError):
            pass
    return 1.0


def _apply_opacity_to_color(color_str: Optional[str], opacity: float) -> str:
    """
    将 opacity 乘入颜色，得到等效的 rgba 字符串。
    若 color_str 为 None 或非 rgba/rgb 格式，则视为透明底，返回 rgba(0,0,0,opacity)。
    """
    if opacity is None or opacity >= 1.0:
        return color_str or "rgba(0,0,0,0)"
    if not color_str or not isinstance(color_str, str):
        return f"rgba(0,0,0,{opacity})"
    s = color_str.strip().lower()
    start = s.find("(")
    end = s.find(")")
    if start == -1 or end == -1:
        return f"rgba(0,0,0,{opacity})"
    values = s[start + 1:end].split(",")
    values = [v.strip() for v in values]
    if len(values) == 4 and s.startswith("rgba"):
        try:
            r, g, b, a = float(values[0]), float(values[1]), float(values[2]), float(values[3])
            new_a = a * opacity
            return f"rgba({int(r)},{int(g)},{int(b)},{new_a})"
        except (ValueError, TypeError):
            pass
    if len(values) == 3 and s.startswith("rgb"):
        try:
            r, g, b = float(values[0]), float(values[1]), float(values[2])
            return f"rgba({int(r)},{int(g)},{int(b)},{opacity})"
        except (ValueError, TypeError):
            pass
    return f"rgba(0,0,0,{opacity})"


def _bake_empty_container_opacity_to_background(component: AbstractComponent) -> None:
    """
    递归处理：类型为 container、opacity < 1 且没有子节点的容器，
    将 opacity 烘焙到 background_color，并去掉 opacity 属性。
    """
    if component.type != dsl_enum.ComponentType.CONTAINER.value:
        # 递归子节点
        for child in getattr(component, "children", []) or []:
            _bake_empty_container_opacity_to_background(child)
        return
    children = getattr(component, "children", []) or []
    for child in children:
        _bake_empty_container_opacity_to_background(child)
    if len(children) != 0:
        return
    style = getattr(component, "style", None)
    if style is None:
        return
    opacity = getattr(style, "opacity", None)
    op_val = _parse_opacity_value(opacity)
    if op_val >= 1.0:
        return
    new_bg = _apply_opacity_to_color(getattr(style, "background_color", None), op_val)
    style.background_color = new_bg
    style.opacity = None


def _find_best_root(component: AbstractComponent, basic_tree_info) -> AbstractComponent:
    """
    递归查找最佳根结点。
    若当前根满足"单子节点、同尺寸、有背景色且不透明、有圆角、宽度375"，
    则用子节点作为根继续递归查找。
    """
    if len(component.children) != 1:
        return component
    child = component.children[0]
    if not _should_use_child_as_root(component, child):
        return component
    # 更新根尺寸信息
    basic_tree_info.root_width = child.layout.size.width
    basic_tree_info.root_height = child.layout.size.height
    return _find_best_root(child, basic_tree_info)


def dsl_to_tree(component: AbstractComponent, tree, parent_name, basic_tree_info):
    # 根结点层级：先对整树做「无子节点 container 的 opacity 烘焙到 background_color」再查找最佳根
    if parent_name is None:
        _bake_empty_container_opacity_to_background(component)
        component = _find_best_root(component, basic_tree_info)
    current_seq = basic_tree_info.seq[0]
    basic_tree_info.seq[0] += 1.0
    if beyond_screen_process(component, basic_tree_info):
        return
    if component.layout is None:
        current_x = current_y =  current_width  = current_height = 0
    else :
        current_x = component.layout.position.x
        current_y = component.layout.position.y
        current_width = component.layout.size.width
        current_height = component.layout.size.height
    current_id = str(component.type) +str(int(current_seq)) +'(' + str(int(current_x)) +'_' +str(int(current_y))+'_' +str(int(current_width))+'_' +str(int(current_height))+str(')') +component.id
    ui_elem = gen_tree.UIControl(current_x, current_y, current_width, current_height, current_id)
    ui_elem.seq = current_seq
    if component_style_utils.regconize_split_line(current_width,current_height):
        ui_elem.ai_type = ai_type_def.AI_TYPE.SPLIT_LINE.value

    need_add_children_flag = False
    if len(component.children) == 0 or component_style_utils.is_rich_text_container(component):
        ui_elem.src = component
    else:
        component_copy = copy.deepcopy(component)
        ui_elem.src = component_copy
        need_add_children_flag = True

    if parent_name is None:
        tree.create_node(tag=ui_elem.uid, identifier=ui_elem.uid, data=ui_elem)
    else:
        child_over_parent_process.mark_over_parent_node(tree, parent_name, current_x, current_y, current_width,
                                                        current_height, current_id)
        gen_tree.gen_sub_tree(ui_elem, tree, parent_name)

    if need_add_children_flag:
        children_list = component.children
        for i, elem in enumerate(children_list):
            dsl_to_tree(elem, tree, current_id, basic_tree_info)
    return