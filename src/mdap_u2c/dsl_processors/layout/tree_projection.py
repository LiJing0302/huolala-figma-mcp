import json
import logging

import numpy
from mdap_u2c.models.dsl_model import ContainerComponent, ContainerComponentProps
from mdap_u2c.utils import component_style_utils
from mdap_u2c.utils.component_style_utils import is_text
from treelib import Tree, Node
import numpy as np
import functools

from mdap_u2c.dsl_processors.layout import ai_type_def, tree_rebuild, gen_tree, calc_list_layout, same_list_merge
from mdap_u2c.dsl_processors.layout import preset_layout_processor, split_line_processor
from mdap_u2c.enums import dsl_enum

from mdap_u2c.models.dsl_model import Style

_logger = logging.getLogger("tree_projection")
MIN_HOR_LINE_WIDTH = 32


def _is_image_control(elem):
    """判断是否为图片控件"""
    if elem is None or not hasattr(elem, 'data'):
        return False
    src = getattr(elem.data, 'src', None)
    return src is not None and getattr(src, 'type', None) == dsl_enum.ComponentType.IMAGE.value


def _is_bg_image(elem):
    """判断是否为已标记的背景图片（不参与投影）"""
    return (getattr(elem.data, 'extra_dict', None) or {}).get('bg_image') == 1


def calc_horizon_projection_list(parent_item, input_list):
    parent_y = parent_item.data.y
    parent_height = int(parent_item.data.height)
    horizon_array = np.zeros(parent_height)
    if parent_height < 1:
        return []
    for i, elem in enumerate(input_list):
        if _is_bg_image(elem):
            continue
        child_y = elem.data.y
        child_height = elem.data.height
        y_top = child_y - parent_y
        y_bottom = child_y + child_height - parent_y - 1
        if y_top < 0:
            y_top = 0
        if y_bottom > parent_height - 1:
            y_bottom = parent_height - 1
        if y_top > y_bottom and y_bottom >= 0:
            y_top = y_bottom
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value and elem.data.height <= 2:
            parent_item.data.extra_dict["have_horizon_line"] = 1  #水平分割线特殊处理 #不改AI_type，之前出现了分割线保护分割线情况
            horizon_array[int(y_top)] = 1
        else:
            horizon_array[int(y_top):int(y_bottom)] = 1
    split_line_list = list()
    for i in range(parent_height - 1):
        if horizon_array[i] == 1 and horizon_array[i + 1] != 1:
            split_line_list.append(i + 1)
    return split_line_list


def calc_vertical_projection_list_new(parent_item, input_list):
    parent_x = parent_item.data.x
    parent_width = int(parent_item.data.width)
    vertical_array = np.zeros(parent_width)
    for i, elem in enumerate(input_list):
        if _is_bg_image(elem):
            continue
        child_x = elem.data.x  # get_control_assume_x(elem)  #

        child_width = elem.data.width  # get_control_assume_width(elem)
        x_left = child_x - parent_x
        x_right = child_x + child_width - parent_x - 1
        if x_left < 0:
            x_left = 0
        if x_right > parent_width - 1:
            x_right = parent_width - 1
        if x_left > x_right:
            x_left = x_right
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            if child_width <= 2:
                parent_item.data.extra_dict["have_vertical_line"] = 1  #垂直分割线特殊处理
                vertical_array[int(x_left)] = 1
            elif child_width >= MIN_HOR_LINE_WIDTH:  #太长的水平分割线不填充纵向区域
                parent_item.data.extra_dict["have_horizon_line"] = 1  # 水平分割线特殊处理 ，不该ai_type之前出现了分割线保护分割线情况
                continue
        elif x_right > x_left:
            vertical_array[int(x_left):int(x_right)] = 1  # 留一个像素空缺，解决两个紧紧挨着的控件无法分割问题
        elif x_right == x_left:
            vertical_array[int(x_left)] = 1
    split_line_list = list()
    for i in range(parent_width - 1):
        if vertical_array[i] == 1 and vertical_array[i + 1] != 1:
            split_line_list.append(i + 1)
    return split_line_list


# 纵向投影树组计算

# 搜索控件坐标在投影分组中的位置
def search_in_line_list(line_list, location):
    if location < line_list[0]:
        return 0
    cnt = len(line_list)
    if location > line_list[cnt - 1]:
        return cnt
    for i in range(cnt - 1):
        if line_list[i] < location <= line_list[i + 1]:
            return i + 1
    _logger.warning('search error,not find')
    return -1


# 计算需要的包含容器的最小尺寸

# 只保留2为位小数
def calc_min_container(input_list):
    redpoint_count = 0
    min_x = 9999999
    min_y = 9999999
    max_x = 0
    max_y = 0

    for i, temp_elem in enumerate(input_list):
        if isinstance(temp_elem, Node):
            elem = temp_elem.data
        else:
            elem = temp_elem
        if component_style_utils.is_redpoint_bubble(elem):
            redpoint_count = redpoint_count + 1
            continue
        if elem.x < min_x:
            min_x = elem.x
        if elem.y < min_y:
            min_y = elem.y
        if elem.x + elem.width > max_x:
            max_x = elem.x + elem.width
        if elem.y + elem.height > max_y:
            max_y = elem.y + elem.height
    if len(input_list) - redpoint_count <= 0:
        return 0, 0, 0, 0
    return round(min_x, 2), round(min_y, 2), round(max_x - min_x, 2), round(max_y - min_y, 2)


layout_container_cnt = 0


def is_grid_list(children_list, horizon_lines, vertical_lines):
    if len(horizon_lines) >= 2 and len(vertical_lines) >= 2:
        list_width = list()
        list_height = list()
        for i, elem in enumerate(children_list):
            if component_style_utils.is_redpoint_bubble(elem.data):
                continue
            list_height.append(elem.data.height)
            list_width.append(elem.data.width)
        if numpy.var(list_height) < 0.2 and numpy.var(list_width) < 0.2:
            return True
    return False


ROW_GAP = 16


def is_horizon_list(children_list, parent_item, horizon_lines, vertical_lines):
    if is_grid_list(children_list, horizon_lines, vertical_lines):
        return False
    # 分离分割线和非分割线元素
    split_line_elements = []
    non_line_elements = []
    for elem in children_list:
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            split_line_elements.append(elem)
        else:
            non_line_elements.append(elem)

    # 检查分割线特殊情况：分割线宽度<=2，且最左边和最右边分割线到父元素右边的距离差值<=2，且分割线和其他分组间隔排列
    if len(split_line_elements) >= 1 and len(non_line_elements) >= 1:
        # 检查所有分割线宽度是否 <= 2
        all_lines_thin = all(elem.data.width <= 2 for elem in split_line_elements)

        if all_lines_thin:
            # 计算分割线按 x 坐标排序
            sorted_lines = sorted(split_line_elements, key=lambda e: e.data.x)
            leftmost_line = sorted_lines[0]
            rightmost_line = sorted_lines[-1]

            # 计算到父元素右边缘的距离
            leftmost_distance = leftmost_line.data.x + leftmost_line.data.width - parent_item.data.x
            rightmost_distance = parent_item.data.x + parent_item.data.width - (
                        rightmost_line.data.x + rightmost_line.data.width)

            distance_diff = abs(leftmost_distance - rightmost_distance)
            if distance_diff <= 2:
                parent_item.data.extra_dict["list_type"] = ai_type_def.LIST_TYPE.VERTICAL_SPLIT_LIST.value
                return True

    if len(non_line_elements) < 2:
        return False

    # 根据 vertical_lines 将非分割线元素分组
    parent_x = parent_item.data.x
    group_count = len(vertical_lines) + 1
    groups = [[] for _ in range(group_count)]

    for elem in non_line_elements:
        offset_x = elem.data.x - parent_x
        index = search_in_line_list(vertical_lines, offset_x)
        groups[index].append(elem)

    # 收集每个分组中最上方的元素（除红点外）
    top_elements = []

    # 检查每组元素的横向中心坐标差值和纵向间隔
    for group in groups:
        if len(group) < 2:
            continue

        # 计算该组元素的横向中心坐标
        # 按 y 坐标排序分组内元素
        sorted_group = sorted(group, key=lambda elem: elem.data.y)

        # 找出该组中最上方的非红点元素
        for elem in sorted_group:
            if not component_style_utils.is_redpoint_bubble(elem.data):
                top_elements.append(elem)
                break

        # 检查从上往下相邻元素间隔是否超过16
        for i in range(len(sorted_group) - 1):
            current_elem = sorted_group[i]
            next_elem = sorted_group[i + 1]
            current_bottom = current_elem.data.y + current_elem.data.height
            next_top = next_elem.data.y
            row_gap = next_top - current_bottom
            if row_gap > ROW_GAP:
                return False

    # 检查每个分组中最上方元素的 y 坐标和高度是否相等
    if len(top_elements) >= 2:
        first_y = top_elements[0].data.y
        first_height = top_elements[0].data.height
        for elem in top_elements[1:]:
            if abs(elem.data.y + elem.data.height/2 - first_y - first_height/2) >= 5:
                return False

    return True


def create_sub_container(input_tree, current_uid, children_list, container_id):
    # 创建新的包含容器
    min_x, min_y, width, height = calc_min_container(children_list)
    if width == 0:
        return None
    container1 = gen_tree.UIControl(min_x, min_y, width, height, container_id)
    new_container_data = ContainerComponent(id=container_id, style=Style(), layout=None,
                                            props=ContainerComponentProps())
    new_container_data.id = container_id
    container1.extra_dict["create_flag"] = "projection"
    container1.seq = input_tree.get_node(current_uid).data.seq + 0.2
    new_container_data.id = container_id
    container1.src = new_container_data
    # 在多叉树上创建容器节点
    new_node = input_tree.create_node(container1.uid, container1.uid, parent=current_uid, data=container1)
    for k, sub_item in enumerate(children_list):
        if isinstance(sub_item, Node):
            input_tree.move_node(sub_item.data.uid, container1.uid)
        else:
            input_tree.move_node(sub_item.uid, container1.uid)
    adujust_child_control(input_tree, container1.uid)
    return new_node


def two_elem_contain_one_redpoint(children_list):
    if len(children_list) == 2:
        if component_style_utils.is_redpoint_bubble(children_list[0]) or component_style_utils.is_redpoint_bubble(children_list[1]):
            return True
    return False


def split_list_by_line(line_list, split_type, input_tree, current_uid):
    if len(line_list) <= 0:  # 只有有2个及以上分组就分割
        return
    parent_value = input_tree.get_node(current_uid).data
    if split_type == ai_type_def.PROJECTION_TYPE.HORIZON.value:
        parent_value.layout_type = ai_type_def.LAYOUT_TYPE.COLUMN.value
    elif split_type == ai_type_def.PROJECTION_TYPE.VERTICAL.value:
        parent_value.layout_type = ai_type_def.LAYOUT_TYPE.ROW.value
    cnt = len(line_list) + 1  #+ 1
    control_list = list()
    for i in range(cnt):
        sublist = list()
        control_list.append(sublist)
    children_list = input_tree.children(current_uid)
    for i, elem in enumerate(children_list):
        if (getattr(elem.data, 'extra_dict', None) or {}).get('bg_image') == 1:
            continue
        index = 0
        if elem.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            if elem.data.width >= MIN_HOR_LINE_WIDTH:  # 水平分割线,不和其他元素合并一起
                continue
        if split_type == ai_type_def.PROJECTION_TYPE.HORIZON.value:  # 0
            offset_y = elem.data.y - parent_value.y
            index = search_in_line_list(line_list, offset_y)
        elif split_type == ai_type_def.PROJECTION_TYPE.VERTICAL.value:  # 1
            offset_x = elem.data.x - parent_value.x
            index = search_in_line_list(line_list, offset_x)
        control_list[index].append(elem.data)
    for j, elem in enumerate(control_list):

        if two_elem_contain_one_redpoint(elem):
            continue
        if len(elem) >= 2:
            global layout_container_cnt
            container_id = 'layout_' + str(
                layout_container_cnt)  # str(int(min_x)) + str(int(min_y)) + str(int(width)) + str(int(height))
            layout_container_cnt = layout_container_cnt + 1
            container1 = create_sub_container(input_tree, current_uid, elem, container_id)
            if container1 is None:
                continue
            if split_type == ai_type_def.PROJECTION_TYPE.HORIZON.value:
                vertical_lines = calc_vertical_projection_list_new(input_tree.get_node(container_id),
                                                                   input_tree.children(container_id))
                if len(vertical_lines) > 1:
                    split_list_by_line(vertical_lines, ai_type_def.PROJECTION_TYPE.VERTICAL.value, input_tree,
                                       container_id)
                    calc_list_layout.regularization_horizon_list_size(input_tree, container_id)
                else:
                    _try_bg_image_projection(input_tree, container_id,input_tree.children(container_id),container1,50)
            elif split_type == ai_type_def.PROJECTION_TYPE.VERTICAL.value:  #横向可分时候继续递归切分
                horizontal_lines = calc_horizon_projection_list(input_tree.get_node(container_id),
                                                                    input_tree.children(container_id))
                if len(horizontal_lines) > 1:
                    split_list_by_line(horizontal_lines, ai_type_def.PROJECTION_TYPE.HORIZON.value, input_tree,
                                       container_id)
                else:
                    _try_bg_image_projection(input_tree, container_id, input_tree.children(container_id), container1,
                                             50)

    if split_type == ai_type_def.PROJECTION_TYPE.VERTICAL.value:
        if len(line_list) >= 3:
            calc_list_layout.regularization_horizon_list_size(input_tree, current_uid)
        else:
            calc_list_layout.regularization_horizon_list_size(input_tree, current_uid)

    calc_list_layout.merge_split_elem_to_grid(input_tree, current_uid)


def adujust_child_control(input_tree, parent_id):
    children_list = input_tree.children(parent_id)
    children_list_len = len(children_list)
    if children_list_len <= 1:
        return
    for i in range(0, children_list_len - 1):
        for j in range(i + 1, children_list_len):
            node1 = children_list[i].data
            node2 = children_list[j].data
            result = gen_tree.judge_box(node1, node2)
            if result == 2:
                for k, elem in enumerate(node2.cross_control):
                    #因为做了冗余控件去除,所以最早记录的cross_control有被删除的情况
                    if input_tree.contains(elem) == False:
                        continue
                    if node1.seq < input_tree.get_node(elem).data.seq < node2.seq:
                        _logger.warning("重叠关系取消层级移动" + node1.uid + "," + node2.uid)
                        return
                if node2.seq > node1.seq:
                    tree_node_move(input_tree, node2, node1)
                    node2.extra_dict['move'] = 4
                    _logger.warning("层级调整，保持原始层级顺序" + node1.uid + "," + node2.uid)
            elif result == 3:
                for k, elem in enumerate(node1.cross_control):
                    if input_tree.contains(elem) == False:
                        continue
                    if node2.seq < input_tree.get_node(elem).data.seq < node1.seq:
                        _logger.warning("重叠关系取消层级移动" + node1.uid + "," + node2.uid)
                        return
                if node2.seq < node1.seq:
                    tree_node_move(input_tree, node1, node2)
                    node1.extra_dict['move'] = 4
                    _logger.warning("层级调整，保持原始层级顺序" + node2.uid + "," + node1.uid)
            elif result == 1:
                _logger.warning("大小宽高一致,层级调整" + node2.uid + "," + node1.uid)
                if node2.seq > node1.seq:
                    tree_node_move(input_tree, node2, node1)
                else:
                    tree_node_move(input_tree, node1, node2)
            elif result > 0 and result < 1:
                pass


def tree_node_move(input_tree, src_node_data, dst_node_data):
    input_tree.move_node(src_node_data.uid, dst_node_data.uid)
    if "list_type" in dst_node_data.extra_dict and dst_node_data.extra_dict[
        "list_type"] == ai_type_def.LIST_TYPE.LOOP_CONTAINER.value:
        pass
    else:
        input_tree.move_node(src_node_data.uid, dst_node_data.uid)


def save_del_list_in_root_node_extra_dict(input_tree, del_list):
    """
    将删除的节点列表保存到根节点的 extra_dict 中
    
    Args:
        input_tree: 控件树
        del_list: 删除的节点 ID 列表
    """
    if del_list is None or len(del_list) == 0:
        return

    # 获取根节点的 extra_dict
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict

    # 确保 del_merge 键存在
    if "del_merge" not in json_dict:
        json_dict["del_merge"] = []

    # 将删除列表中的节点 ID 添加到 extra_dict
    for item in del_list:
        if isinstance(item, str):
            json_dict["del_merge"].append(item)
        elif hasattr(item, 'data') and hasattr(item.data, 'uid'):
            json_dict["del_merge"].append(item.data.uid)
        elif hasattr(item, 'uid'):
            json_dict["del_merge"].append(item.uid)


def adjust_child_control_recurve(input_tree, parent_id):
    layout_type = calc_layout_type(input_tree.get_node(parent_id), input_tree.children(parent_id))
    if layout_type == ai_type_def.LAYOUT_TYPE.COLUMN.value:
        del_list = same_list_merge.list_merge_new(input_tree, parent_id)
        save_del_list_in_root_node_extra_dict(input_tree, del_list)
    if input_tree.get_node(parent_id) is None:  #合并完成后可能被删除
        return
    adujust_child_control(input_tree, parent_id)
    new_children_list = input_tree.children(parent_id)
    for i, elem in enumerate(new_children_list):
        adjust_child_control_recurve(input_tree, elem.data.uid)


def _rects_overlap(elem1, elem2):
    """判断两个元素矩形是否重叠。judge_box 返回非 0 表示有重叠"""
    return gen_tree.judge_box(elem1.data, elem2.data) != 0


def _collect_node_and_descendants(input_tree, node):
    """收集节点及其所有后代，用于 calc_min_container 计算最小虚拟包裹容器"""
    result = [node]
    for child in input_tree.children(node.data.uid):
        result.extend(_collect_node_and_descendants(input_tree, child))
    return result

def _move_overlap_image_children(input_tree, image_uid,remaining_uncle_children_list):
    image_children = input_tree.children(image_uid)
    container_id = input_tree.parent(image_uid).data.uid
    move_image_sub_children_list = list()
    uncle_overlap = False
    parent_item = input_tree.get_node(image_uid)
    parent_width = parent_item.data.width
    parent_top = parent_item.data.y
    parent_bottom = parent_item.data.y + parent_item.data.height
    min_x, min_y, width, height = calc_min_container(image_children)
    # 若虚拟包裹容器宽>=父容器70% 且 距离父容器上下距离<=30，则不移动
    top_dist = min_y - parent_top
    bottom_dist = parent_bottom - (min_y + height)
    if width >= parent_width * 0.7 and abs(top_dist - bottom_dist) <= 20:
        pass
    else:
        for ic in image_children:
            move_image_sub_children_list.append(ic)
            for uncle in remaining_uncle_children_list:
                if _rects_overlap(ic, uncle):
                    uncle_overlap = True
                    break
            move_image_sub_children_list.append(ic)
        if not uncle_overlap:
            for elem in move_image_sub_children_list:
                input_tree.move_node(elem.data.uid, container_id)
            return True,move_image_sub_children_list
    return False,[]

def _try_bg_image_projection(input_tree, current_uid, children_list, parent_item, max_depth):
    """
    当无法进行投影切分时，尝试排除排序靠前的图片控件作为背景图。
    若排除图片后，剩余控件+图片的子控件可以投影切分，则：
    1. 标记图片 extra_dict["bg_image"]=1
    2. 用新容器包裹剩余控件+图片的子控件（元素数量>=2时）
    3. 调整层级使图片在底层

    约束：
    1. 遍历背景图时，与其他控件不重叠的图片先排除（不作为背景图候选）
    2. 移动图片子元素之前需满足：子元素与叔叔节点（父节点的其他子节点）不重叠
    """
    v_lines = list()
    h_lines = list()

    image_elems = list()
    for i, elem in enumerate(children_list):
        if _is_image_control(elem):
            image_elems.append(elem)
        else:
            break
    if len(image_elems) <= 0:
        return False

    # 1. 排除与其他控件不重叠的图片，只保留有重叠的作为背景图候选
    candidate_images = []
    for image_elem in image_elems:
        has_overlap_with_others = False
        for other in children_list:
            if other.data.uid == image_elem.data.uid:
                continue
            if _rects_overlap(image_elem, other):
                has_overlap_with_others = True
                break
        if has_overlap_with_others:
            candidate_images.append(image_elem)
    absolute_image_children_list = list()
    remaining_children_list = children_list.copy()
    for image_elem in candidate_images:
        image_uid = image_elem.data.uid
        absolute_image_children_list.append(image_elem)
        remaining_children_list.remove(image_elem)
        if len(remaining_children_list) < 1:#排除完了
            continue
        # 检查排除该图片后，剩余元素有超过2个内容是否可以投影切分
        if len(remaining_children_list) >= 2:
            h_lines = calc_horizon_projection_list(parent_item, remaining_children_list)
            v_lines = calc_vertical_projection_list_new(parent_item, remaining_children_list)
            if len(h_lines) <= 1 and len(v_lines) <= 1:
                continue
        for i, elem in enumerate(absolute_image_children_list):
            elem.data.extra_dict["bg_image"] = 1
        # 2.
        # 只移动最后一个重叠的图片中的子元素
        # 移动图片子元素之前，检查子元素是否与叔叔节点（remaining）重叠
        # 如果调整了图片内部节点，需要重新投影和切分
        result,sub_move_list =  _move_overlap_image_children(input_tree, image_uid, remaining_children_list)
        if result:
            remaining_children_list.extend(sub_move_list)
            h_lines = calc_horizon_projection_list(parent_item, remaining_children_list)
            v_lines = calc_vertical_projection_list_new(parent_item, remaining_children_list)
        container_id = current_uid
        # 根据投影线进行切分
        if len(v_lines) > 1 and len(h_lines) <= 1:
            split_list_by_line(v_lines, ai_type_def.PROJECTION_TYPE.VERTICAL.value, input_tree, container_id)
            calc_list_layout.regularization_horizon_list_size(input_tree, container_id)
        elif len(h_lines) > 1:
            split_list_by_line(h_lines, ai_type_def.PROJECTION_TYPE.HORIZON.value, input_tree, container_id)
        return True
    return False


def _special_container_procees(input_tree, parent_value, current_uid, max_depth):
    # 投影前：若有 have_horizon_line，先尝试将横向分割线转为 border-bottom（3.1/3.2）
    if parent_value.extra_dict.get("have_horizon_line"):
        if split_line_processor.process_horizontal_split_line_before_projection(input_tree, current_uid):

            return True

    if "list_type" in parent_value.extra_dict and parent_value.extra_dict[
        "list_type"] == ai_type_def.LIST_TYPE.LOOP_CONTAINER.value:  # 之前已经做了列表识别和处理了网格合并的可以不用计算了
        return True
    # 判断是否已经有现成的布局字段（预设的 flex/grid 布局）
    temp_layout_type = preset_layout_processor.get_layout_type_from_display_mode(parent_value)
    if temp_layout_type != None:
        parent_value.layout_type = temp_layout_type
        return True
    return False


# 图像投影算法主要函数
# 输入：控件树，起始根节点，遍历最大深度
# 返回：没有返回参数，但会修改输入的控件树的不布局
def calc_children_projection(input_tree, current_uid, max_depth):
    if current_uid == input_tree.root:
        global layout_container_cnt
        layout_container_cnt = 0
    if max_depth <= 0:
        _logger.warning('已达最大深度，不再继续分割')
        return
    parent_item = input_tree.get_node(current_uid)
    parent_value = input_tree.get_node(current_uid).data
    if parent_value.height <= 0 or parent_value.width <= 0:
        return
    if _special_container_procees(input_tree, parent_value, current_uid, max_depth):
        children_list = input_tree.children(current_uid)
        for i, elem in enumerate(children_list):
            calc_children_projection(input_tree, elem.data.uid, max_depth - 1)
        return
    children_list = input_tree.children(current_uid)
    if len(children_list) == 0:
        return

    if len(children_list) == 1:
        # 子控件为1，不用投影，递归处理
        for i, elem in enumerate(children_list):
            calc_children_projection(input_tree, elem.data.uid, max_depth - 1)
        return
    horizon_lines = calc_horizon_projection_list(parent_item, children_list)
    vertical_lines = calc_vertical_projection_list_new(parent_item, children_list)
    if len(horizon_lines) <= 1 and len(vertical_lines) <= 1:  # 有些包含子容器，但紧贴贴合无法切分
        if _try_bg_image_projection(input_tree, current_uid, children_list, parent_item, max_depth):
            pass
    if len(horizon_lines) <= 1 and len(vertical_lines) <= 1:
        pass
    elif len(horizon_lines) <= 1 < len(vertical_lines):
        # 横向投影<1 ，用纵向投影
        split_list_by_line(vertical_lines, ai_type_def.PROJECTION_TYPE.VERTICAL.value, input_tree, current_uid)  # 1
    elif len(vertical_lines) <= 1 < len(horizon_lines):
        # 横向投影<1,用横向投影
        split_list_by_line(horizon_lines, ai_type_def.PROJECTION_TYPE.HORIZON.value, input_tree, current_uid)  # 0
    elif input_tree.get_node(current_uid).data.ai_type == ai_type_def.AI_TYPE.BOTTOM_BAR.value:
        split_list_by_line(vertical_lines, ai_type_def.PROJECTION_TYPE.VERTICAL.value, input_tree, current_uid)
    else:
        if len(vertical_lines) >= len(horizon_lines):
            children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))  # 从小到大排序.极端情况下纵向切分，其他情况横向切分
            if is_horizon_list(children_list, parent_item, horizon_lines, vertical_lines):
                split_list_by_line(vertical_lines, ai_type_def.PROJECTION_TYPE.VERTICAL.value, input_tree, current_uid)
            else:
                split_list_by_line(horizon_lines, ai_type_def.PROJECTION_TYPE.HORIZON.value, input_tree,
                                   current_uid)  # 0
        else:
            split_list_by_line(horizon_lines, ai_type_def.PROJECTION_TYPE.HORIZON.value, input_tree, current_uid)  # 0
    # 递归处理子控件
    if len(children_list) != 0:
        for i, elem in enumerate(children_list):
            calc_children_projection(input_tree, elem.data.uid, max_depth - 1)


def calc_layout_type(parent_item, children_list):
    horizon_lines = calc_horizon_projection_list(parent_item, children_list)
    vertical_lines = calc_vertical_projection_list_new(parent_item, children_list)
    if len(horizon_lines) <= 1 < len(vertical_lines):
        return ai_type_def.LAYOUT_TYPE.ROW.value
    elif len(vertical_lines) <= 1 < len(horizon_lines):
        return ai_type_def.LAYOUT_TYPE.COLUMN.value
    elif len(vertical_lines) > 1 and len(horizon_lines) > 1 and len(children_list) >= 3:
        return ai_type_def.LAYOUT_TYPE.GRID.value
    else:
        return ai_type_def.LAYOUT_TYPE.MESS.value


