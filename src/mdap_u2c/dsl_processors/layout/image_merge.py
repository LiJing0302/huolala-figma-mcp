import os
import logging
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image
from mdap_u2c.constant import FIGMA_DESIGN_WIDTH
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models.dsl_model import Style, Layout, ImageComponentProps, AbstractComponent
from mdap_u2c.utils import component_style_utils

from mdap_u2c.models.dsl_model import ImageComponent
from mdap_u2c.services.del_same_img import _bgra_to_bgr_composite
from mdap_u2c.utils.component_style_utils import is_text, have_border, is_small_or_square_container, is_rich_text_container

TEXT_CONTAINER = "text_container"
ICON_CONTAINER_PROPORTION_THRESHOLD = 0.45
# 小/方形容器合并为图时：子元素纵向投影（投到 x 轴）后，相邻块之间的横向间隙上限
SMALL_CONTAINER_PROJECTION_MAX_H_GAP = 7
# 纵向投影时：子元素相对父元素的宽高占比均 ≥ 该阈值则视为「与父几乎同尺寸」，可剔除不参与投影
NEAR_PARENT_PROJECTION_EXCLUDE_RATIO = 0.95
# 区域图像灰度纵向扫描：相邻行灰度差超过该阈值视为「颜色突变」
GRAY_VERTICAL_MUTATION_THRESHOLD = 8
_logger = logging.getLogger("image_merge")


def is_text_container(elem,context_share_data):
    if elem.extensions is not None and TEXT_CONTAINER in elem.extensions:
        return True
    children_list = elem.children
    for son_elem in children_list:
        if is_text(son_elem) or is_rich_text_container(son_elem) :
            if  son_elem.type == dsl_enum.ComponentType.TEXT and  len(son_elem.props.text)==1  :
                if  son_elem.props.text.isdigit() and int(elem.layout.size.width) <= 16 and int(elem.layout.size.height) <= 16:
                    # 检查 elem 和兄弟节点是否有交叉重叠
                    if _has_overlap_with_siblings(elem, context_share_data):
                        return False
                if son_elem.layout is None:
                    continue
                if len(children_list)>=2 and  int(son_elem.layout.size.width)<= 24 and  abs(son_elem.layout.size.height -son_elem.layout.size.width )<=2 :#零碎元素多
                   return False
            mark_parent_node(elem, TEXT_CONTAINER,context_share_data)
            return True
        if is_text_container(son_elem,context_share_data):
            return True
    return False


def _has_overlap_with_siblings(elem, context_share_data):
    """
    检查元素是否与兄弟节点有交叉重叠
    
    Args:
        elem: 当前元素
        context_share_data: 上下文共享数据
    
    Returns:
        bool: 如果与任一兄弟节点有交叉重叠返回 True
    """
    # 获取父节点
    if elem.parent_id is None or "dsl_map" not in context_share_data:
        return False
    
    parent = context_share_data["dsl_map"].get(elem.parent_id)
    if parent is None or not hasattr(parent, 'children') or parent.children is None:
        return False
    
    # 获取 elem 的边界
    elem_x = elem.layout.position.x
    elem_y = elem.layout.position.y
    elem_width = elem.layout.size.width
    elem_height = elem.layout.size.height
    
    # 遍历兄弟节点检查是否有重叠
    for sibling in parent.children:
        if sibling.id == elem.id:
            continue
        if sibling.layout is None:
            continue
        
        sibling_x = sibling.layout.position.x
        sibling_y = sibling.layout.position.y
        sibling_width = sibling.layout.size.width
        sibling_height = sibling.layout.size.height
        
        # 判断两个矩形是否重叠
        if _rectangles_overlap(elem_x, elem_y, elem_width, elem_height,
                               sibling_x, sibling_y, sibling_width, sibling_height):
            return True
    
    return False


def _rectangles_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
    """
    判断两个矩形是否有交叉重叠

    Args:
        x1, y1, w1, h1: 第一个矩形的位置和尺寸
        x2, y2, w2, h2: 第二个矩形的位置和尺寸

    Returns:
        bool: 如果两个矩形有重叠返回 True
    """
    # 两个矩形不重叠的条件取反
    # 不重叠：x1 >= x2 + w2 或 x2 >= x1 + w1 或 y1 >= y2 + h2 或 y2 >= y1 + h1
    # 重叠：以上条件都不满足
    return not (x1 >= x2 + w2 or x2 >= x1 + w1 or y1 >= y2 + h2 or y2 >= y1 + h1)


def is_icon_container_proportion_below_threshold(container: AbstractComponent) -> bool:
    """
    占比判断：计算容器内子元素在水平方向上的并集宽度，若并集宽/容器宽 <= ICON_CONTAINER_PROPORTION_THRESHOLD 则返回 True。

    Args:
        container: 容器组件

    Returns:
        True 表示并集宽度占比不超过阈值（可视为图标类小占比容器），否则 False
    """
    if container.layout is None:
        return False
    container_width = container.layout.size.width
    if container_width <= 0:
        return False
    children_list = container.children or []
    if len(children_list) == 0:
        return False
    min_left = None
    max_right = None
    for child in children_list:
        if child.layout is None:
            continue
        left = child.layout.position.x
        right = child.layout.position.x + child.layout.size.width
        if min_left is None:
            min_left, max_right = left, right
        else:
            min_left = min(min_left, left)
            max_right = max(max_right, right)
    if min_left is None or max_right is None:
        return False
    union_width = max_right - min_left
    return (union_width / container_width) <= ICON_CONTAINER_PROPORTION_THRESHOLD


# 反向遍历标记
def mark_parent_node(component, key,context_share_data):
    if component.extensions is None:
        component.extensions = dict()
    component.extensions[key] = True
    if component.parent_id is not None:
        grand_parent_node = context_share_data["dsl_map"][component.parent_id]
        if grand_parent_node is not None:
            mark_parent_node(grand_parent_node, key,context_share_data)

#将dsl装成map,存放到context_share_data["dsl_map"]中
def dsl_to_map(component, context_share_data):
    """
    将 DSL 组件树转换为 map，以 component.id 作为 key
    
    递归遍历组件树，将每个组件存储到 context_share_data["dsl_map"] 中
    
    Args:
        component: DSL 组件（AbstractComponent 或其子类）
        context_share_data: 上下文共享数据字典，需要包含 "dsl_map" 键
    """
    if component is None:
        return
    
    # 确保 dsl_map 存在
    if "dsl_map" not in context_share_data:
        context_share_data["dsl_map"] = {}
    # 以 component.id 作为 key 存储组件
    context_share_data["dsl_map"][component.id] = component
    
    # 递归处理子组件
    if hasattr(component, 'children') and component.children:
        for child in component.children:
            dsl_to_map(child, context_share_data)


def calc_component_vertical_projection_list(
    parent_item, exclude_near_parent_size_children: bool = False
):
    """
    计算子元素在父容器内的纵向投影（投到 x 轴上的覆盖区间）。

    Args:
        parent_item: 父组件
        exclude_near_parent_size_children: 为 True 时，不参与投影的子元素：宽、高相对父容器
            均 ≥ NEAR_PARENT_PROJECTION_EXCLUDE_RATIO（默认 0.95）的视为与父几乎同尺寸，予以剔除。
    """
    parent_x = parent_item.layout.position.x
    parent_width = int(parent_item.layout.size.width)
    parent_height = float(parent_item.layout.size.height)
    parent_wf = float(parent_item.layout.size.width)
    vertical_array = np.zeros(parent_width)
    input_list = parent_item.children
    child_over_parent = False
    for i, elem in enumerate(input_list):
        if exclude_near_parent_size_children and parent_wf > 0 and parent_height > 0:
            cw = float(elem.layout.size.width)
            ch = float(elem.layout.size.height)
            if (
                cw / parent_wf >= NEAR_PARENT_PROJECTION_EXCLUDE_RATIO
                and ch / parent_height >= NEAR_PARENT_PROJECTION_EXCLUDE_RATIO
            ):
                continue
        child_x = elem.layout.position.x  # get_control_assume_x(elem)  #
        child_width = elem.layout.size.width  # get_control_assume_width(elem)
        if child_width > 1 :
           x_left = child_x - parent_x
           x_right = child_x + child_width - parent_x - 1
           if x_left < 0:
               x_left = 0
               child_over_parent = True
           if x_right > parent_width - 1:
               x_right = parent_width - 1
               child_over_parent = True
           vertical_array[int(x_left):int(x_right)] = 1 # 留一个像素空缺，解决两个紧紧挨着的控件无法分割问题
        elif elem.layout.size.height >= 2:
            x_left = child_x - parent_x
            vertical_array[int(x_left)] = 1
    split_line_list = list()
    for i in range(parent_width - 1):
        if vertical_array[i] == 1 and vertical_array[i + 1] != 1:
            split_line_list.append(i + 1)
    return split_line_list, child_over_parent, vertical_array


def _crop_parent_region_grayscale_design_coords(
    parent_item, context_share_data: Dict[str, Any]
) -> Optional[np.ndarray]:
    """
    截取父容器在设计稿坐标系下的图像数组 (H×W 或 H×W×C)，与 layout 宽高一致。
    无 pil_image 或区域无效时返回 None。
    """
    pil_image = context_share_data.get("pil_image")
    if pil_image is None or parent_item.layout is None:
        return None
    image_scale =1
    x = int(parent_item.layout.position.x * image_scale)
    y = int(parent_item.layout.position.y * image_scale)
    width = int(parent_item.layout.size.width * image_scale)
    height = int(parent_item.layout.size.height * image_scale)
    left = max(0, x)
    upper = max(0, y)
    right = min(pil_image.width, x + width)
    lower = min(pil_image.height, y + height)
    if right <= left or lower <= upper:
        return None
    cropped = pil_image.crop((left, upper, right, lower))
    parent_w = int(parent_item.layout.size.width)
    parent_h = int(parent_item.layout.size.height)
    if parent_w <= 0 or parent_h <= 0:
        return None
    if cropped.size != (parent_w, parent_h):
        cropped = cropped.resize((parent_w, parent_h), Image.Resampling.BILINEAR)
    if "A" in cropped.getbands():
        cropped = cropped.convert("RGBA")
    elif cropped.mode != "RGB" and cropped.mode != "L":
        cropped = cropped.convert("RGB")
    return np.asarray(cropped)


def _save_vertical_mutation_gray_png(gray_2d: np.ndarray, component_id: str) -> None:
    """
    将参与纵向突变投影的灰度图写入当前工作目录下子目录，便于调试。
    """
    try:
        debug_dir = os.path.join(os.getcwd(), "vertical_mutation_gray_debug")
        os.makedirs(debug_dir, exist_ok=True)
        safe_id = component_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        file_path = os.path.join(debug_dir, f"{safe_id}.png")
        Image.fromarray(gray_2d, mode="L").save(file_path, "PNG")
        _logger.info(f"纵向突变投影灰度调试图已保存: {file_path}")
    except Exception as e:
        _logger.warning(f"保存纵向突变投影灰度图失败: {component_id}, {e}")


def _vertical_array_from_gray_vertical_mutation(
    gray: np.ndarray, debug_parent_id: None
) -> np.ndarray:
    """
    对灰度图按列做纵向扫描：从上往下检查相邻像素灰度差，
    只要某一列首次出现差值 > GRAY_VERTICAL_MUTATION_THRESHOLD，
    该列投影记为 1 并立即结束该列扫描；否则保持 0。
    debug_parent_id 非空时，将最终用于统计的灰度图写入当前目录下 vertical_mutation_gray_debug/。
    """
    if gray.size == 0:
        return np.array([])
    # 透明图先按 alpha 合成到底色，再进行灰度差值扫描。
    if gray.ndim == 3 and gray.shape[2] == 4:
        bgra = gray[:, :, [2, 1, 0, 3]]
        bgr = _bgra_to_bgr_composite(bgra)
        gray = np.round(
            0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
        ).astype(np.uint8)
    elif gray.ndim == 3 and gray.shape[2] == 3:
        gray = np.round(
            0.299 * gray[:, :, 0] + 0.587 * gray[:, :, 1] + 0.114 * gray[:, :, 2]
        ).astype(np.uint8)
    elif gray.ndim != 2:
        return np.array([])
    if debug_parent_id is not None:
        _save_vertical_mutation_gray_png(gray, debug_parent_id)
    h, w = gray.shape
    vertical_array = np.zeros(w, dtype=np.float64)
    if w == 0:
        return vertical_array
    if h <= 1:
        return vertical_array
    g = gray.astype(np.int16)
    for x in range(w):
        for y in range(1, h):
            if abs(g[y, x] - g[y - 1, x]) > GRAY_VERTICAL_MUTATION_THRESHOLD:
                vertical_array[x] = 1
                break
    return vertical_array


def _vertical_projection_children_max_horizontal_gap_leq(
    current_item, max_gap: float, context_share_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    优先根据父容器区域截图的灰度纵向突变生成 x 向投影（与 layout 同宽），
    合并连续为 1 的区间后，相邻块之间的横向间隙（像素）均 <= max_gap 则返回 True。
    无 pil_image 时回退为子元素几何投影（calc_component_vertical_projection_list）。
    无有效区间或仅一块时视为满足。
    """
    if current_item.layout is None:
        return False
    parent_width = int(current_item.layout.size.width)
    if parent_width <= 0:
        return False
    vertical_array: np.ndarray
    if context_share_data is not None:
        gray = _crop_parent_region_grayscale_design_coords(current_item, context_share_data)
        if gray is not None and gray.shape[1] == parent_width:
            save_gray = False
            vertical_array = _vertical_array_from_gray_vertical_mutation(
                gray,
                debug_parent_id=str(current_item.id) if save_gray else None,
            )
        else:
            _, _, vertical_array = calc_component_vertical_projection_list(current_item)
    else:
        _, _, vertical_array = calc_component_vertical_projection_list(current_item)
    i = 0
    runs = []
    while i < parent_width:
        if vertical_array[i] != 1:
            i += 1
            continue
        start = i
        i += 1
        while i < parent_width and vertical_array[i] == 1:
            i += 1
        runs.append((start, i - 1))
    if len(runs) <= 1:
        return True
    for k in range(len(runs) - 1):
        gap = runs[k + 1][0] - runs[k][1] - 1
        if gap >= max_gap:
            return False
    return True


def calc_component_horizon_projection_list(parent_item):
    parent_y = parent_item.layout.position.y
    parent_height = int(parent_item.layout.size.height)
    horizon_array = np.zeros(parent_height)
    input_list = parent_item.children
    child_over_parent = False

    for i, elem in enumerate(input_list):
        child_y = elem.layout.position.y
        child_height = elem.layout.size.height
        if child_height >1 :
          y_top = child_y - parent_y
          y_bottom = child_y + child_height - parent_y-1
          if y_top < 0:
              y_top = 0
              child_over_parent = True
          if y_bottom > parent_height - 1:
             y_bottom = parent_height - 1
             child_over_parent = True
          horizon_array[int(y_top):int(y_bottom)] = 1

    split_line_list = list()
    for i in range(parent_height - 1):
        if horizon_array[i] == 1 and horizon_array[i + 1] != 1:
            split_line_list.append(i + 1)
    return split_line_list,child_over_parent

def like_a_image(input_component, tree_share_data):
    """判断组件是否可以合并为图片（本地规则）。"""
    return _like_a_image_local(input_component, tree_share_data)


def _like_a_image_local(input_component, tree_share_data):
    """使用本地规则判断组件是否可以合并为图片。"""
    children_list = input_component.children
    if len(children_list) <= 0:
        return True
    elif len(children_list) == 1:  # 当只有元素时候,观察根据位置和布局判断
        if children_list[0].layout.size.width / input_component.layout.size.width <= ICON_CONTAINER_PROPORTION_THRESHOLD:
            return False
        else:
            return True
    if is_icon_container_proportion_below_threshold(input_component):
        return False
    if is_complex_bg(input_component, FIGMA_DESIGN_WIDTH, tree_share_data):
        return True
    vertical_lines, x_over_flag, _ = calc_component_vertical_projection_list(input_component,True)
    horizon_lines, y_over_flag = calc_component_horizon_projection_list(input_component)
    height_list = list()
    center_x_list = list()
    center_y_list = list()
    for i, elem in enumerate(children_list):
        if elem.layout.size.width < 0.9 * input_component.layout.size.width:
            center_x_list.append(elem.layout.position.x + elem.layout.size.width)
            center_y_list.append(elem.layout.position.y + elem.layout.size.height)
            height_list.append(elem.layout.size.height)
        if len(vertical_lines) <= 1 and len(horizon_lines) <= 1:
            if len(height_list) <= 1:
                return True
            if np.var(height_list) >= 1 or np.var(center_x_list) >= 1 or np.var(center_y_list) > 1:
                return True
    return False


def replace_node_by_image(elem, context_share_data):
  
    new_image = ImageComponent(id=elem.id, style=Style(), layout=elem.layout,
                               props=ImageComponentProps(src=elem.figma.node_id))
    new_image.figma = elem.figma
    if 'icon_merge_list' not in context_share_data:
        context_share_data['icon_merge_list'] = list()
    context_share_data['icon_merge_list'].append(elem.id)
    
    # debug 模式下，根据背景图片和坐标区域截取图片保存到文件中
    if context_share_data.get("debug") == 1:
        _save_cropped_image(elem, context_share_data)
    
    return new_image


def _save_cropped_image(elem, context_share_data):
    """
    根据背景图片和坐标区域截取图片保存到文件中
    
    Args:
        elem: 要截取的元素
        context_share_data: 上下文共享数据，包含背景图片
    """
    try:
        # 获取背景图片
        pil_image = context_share_data.get('pil_image')
        if pil_image is None:
            _logger.warning(f"无法获取背景图片，跳过截图: {elem.id}")
            return
        
        # 获取图片缩放比例（默认为1）
        image_scale = context_share_data.get("image_scale", 1)
        
        # 获取元素坐标和尺寸
        x = int(elem.layout.position.x * image_scale)
        y = int(elem.layout.position.y * image_scale)
        width = int(elem.layout.size.width * image_scale)
        height = int(elem.layout.size.height * image_scale)
        
        # 计算裁剪区域 (left, upper, right, lower)
        left = max(0, x)
        upper = max(0, y)
        right = min(pil_image.width, x + width)
        lower = min(pil_image.height, y + height)
        
        # 检查裁剪区域是否有效
        if right <= left or lower <= upper:
            _logger.warning(f"裁剪区域无效，跳过截图: {elem.id}, area=({left}, {upper}, {right}, {lower})")
            return
        
        # 裁剪图片
        cropped_image = pil_image.crop((left, upper, right, lower))
        
        # 创建保存目录
        debug_dir = os.path.join(os.getcwd(), "icon_merge_debug")
        os.makedirs(debug_dir, exist_ok=True)
        
        # 生成文件名（使用元素 id，替换特殊字符）
        safe_id = elem.id.replace(":", "_").replace("/", "_").replace("\\", "_")
        file_path = os.path.join(debug_dir, f"{safe_id}.png")
        
        # 保存图片
        cropped_image.save(file_path, "PNG")
        _logger.info(f"截图已保存: {file_path}, 区域=({left}, {upper}, {right}, {lower})")
        
    except Exception as e:
        _logger.error(f"截取图片失败: {elem.id}, 错误: {e}")
VERY_SMALL_SIZE = 20 #之前出现一个竖线和icon的大小是22，所以定20更小的场景就不继续二次判断了。
def icon_merge(input_component: AbstractComponent, context_share_data):
    if is_rich_text_container(AbstractComponent) :
        return
    children_list =  input_component.children
    for i, elem in enumerate(children_list):
        if len(elem.children) == 0 or elem.layout is None:
            continue
        elif component_style_utils.regconize_split_line(elem.layout.size.width, elem.layout.size.height):
            continue
        elif is_text_container(elem, context_share_data) == True:
            icon_merge(elem, context_share_data)
        elif have_border(elem) and elem.layout.size.width >= VERY_SMALL_SIZE and elem.layout.size.height >= VERY_SMALL_SIZE: #部分小图标是用边框+执行组合的方式
            icon_merge(elem, context_share_data)
        elif is_small_or_square_container(elem,50) and _vertical_projection_children_max_horizontal_gap_leq(
            elem, SMALL_CONTAINER_PROJECTION_MAX_H_GAP, context_share_data) :
            new_image = replace_node_by_image(elem, context_share_data)
            input_component.children[i] = new_image
        elif like_a_image(elem, context_share_data):
            new_image = replace_node_by_image(elem, context_share_data)
            input_component.children[i] = new_image
        else:
            # debug 模式下，保存无法合并的节点截图
            if context_share_data.get("debug") == 1:
                _save_unmerged_node_image(elem, context_share_data)
            icon_merge(elem, context_share_data)


def _save_unmerged_node_image(elem, context_share_data):
    """
    保存无法合并的节点截图到单独的文件夹
    
    Args:
        elem: 无法合并的元素
        context_share_data: 上下文共享数据，包含背景图片
    """
    try:
        # 获取背景图片
        pil_image = context_share_data.get('pil_image')
        if pil_image is None:
            _logger.warning(f"无法获取背景图片，跳过截图: {elem.id}")
            return
        
        # 获取图片缩放比例（默认为1）
        image_scale = context_share_data.get("image_scale", 1)
        
        # 获取元素坐标和尺寸
        x = int(elem.layout.position.x * image_scale)
        y = int(elem.layout.position.y * image_scale)
        width = int(elem.layout.size.width * image_scale)
        height = int(elem.layout.size.height * image_scale)
        
        # 计算裁剪区域 (left, upper, right, lower)
        left = max(0, x)
        upper = max(0, y)
        right = min(pil_image.width, x + width)
        lower = min(pil_image.height, y + height)
        
        # 检查裁剪区域是否有效
        if right <= left or lower <= upper:
            _logger.warning(f"裁剪区域无效，跳过截图: {elem.id}, area=({left}, {upper}, {right}, {lower})")
            return
        
        # 裁剪图片
        cropped_image = pil_image.crop((left, upper, right, lower))
        
        # 创建保存目录（与 replace_node_by_image 不同的文件夹）
        debug_dir = os.path.join(os.getcwd(), "icon_unmerged_debug")
        os.makedirs(debug_dir, exist_ok=True)
        
        # 生成文件名（使用元素 id，替换特殊字符）
        safe_id = elem.id.replace(":", "_").replace("/", "_").replace("\\", "_")
        file_path = os.path.join(debug_dir, f"{safe_id}.png")
        
        # 保存图片
        cropped_image.save(file_path, "PNG")
        _logger.info(f"无法合并节点截图已保存: {file_path}, 区域=({left}, {upper}, {right}, {lower})")
        
    except Exception as e:
        _logger.error(f"截取无法合并节点图片失败: {elem.id}, 错误: {e}")




# 对多个复杂背景的图片进行合并
def is_complex_bg(input_component: AbstractComponent, root_width,share_data):
    if input_component.type == dsl_enum.ComponentType.CONTAINER and abs(
            input_component.layout.size.width - root_width) <= 1:
        children_list = input_component.children
        sub_gradient_cnt = 0
        if len(children_list) >= 2:
            for i, elem in enumerate(children_list):
                if elem.style.background is not None and "gradient" in elem.style.background:  # 顶部渐变色
                    sub_gradient_cnt += 1
            if sub_gradient_cnt >= 2 and is_text_container(input_component,share_data) == False:
                return True
    return False








