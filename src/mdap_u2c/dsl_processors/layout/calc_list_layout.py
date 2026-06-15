import logging

import numpy

from mdap_u2c.enums import dsl_enum
from mdap_u2c.models.dsl_model import ContainerComponent
from mdap_u2c.utils import component_style_utils
from mdap_u2c.utils.component_style_utils import is_text
from treelib import Node

from mdap_u2c.models.dsl_model import Layout, Style
# 修复导入语句，使用相对导入
from . import tree_rebuild, gen_tree
import functools
from . import ai_type_def
from . import tree_projection

_logger = logging.getLogger("calc_list_layout")

ImageTextList_TextWidth_DIFF_RATIO = 2.5  # 图文组合的列表，文本最大宽度/最小文本宽度阈值
grid_container_cnt = 0

def is_same_emebbed_list(list_list):
    if len(list_list) < 2:
        return False
    for i in range(1,len(list_list)):
        if not (list_list[i] == list_list[i - 1]):
            return False
    return True

def judge_horizon_list_control(input_tree, parent_id, grid_flag_dict, start_flag, next_line_id):
    if input_tree.get_node(parent_id) == None:
        _logger.warning('parent_id is not exist!')
        return False
    if 'image_text_list' in input_tree.get_node(parent_id).data.extra_dict:  # 上一行已经提前判断过列表
        return True
    children_list = input_tree.children(parent_id)
    width_list = list()
    y_list = list()
    height_list = list()
    x_center_list = list()
    text_list_flag = True
    children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))
    for j, child in enumerate(children_list):
        if  (child.data.ai_type == ai_type_def.AI_TYPE.BUBBLE.value or child.data.ai_type == ai_type_def.AI_TYPE.RED_POINT.value):
            continue
        if j > 1 and (
                children_list[j - 1].data.y + children_list[j - 1].data.height - child.data.y - child.data.height) > \
                children_list[j - 1].data.height / 2 - 1:
            continue
        y_list.append(int(children_list[j].data.y))
        x_center_list.append(int(children_list[j].data.x + children_list[j].data.width / 2))
        height_list.append(int(children_list[j].data.height))
        if j > 0 and (children_list[j].data.x + 1 < children_list[j - 1].data.x + children_list[j - 1].data.width):
            return False  # 横向重叠的无法构成横向列表
        if start_flag == True:
            if is_text(children_list[j].data.src):  # 不允许文本控件开头
                return False
        else:
            if is_text(children_list[j].data.src) == False:
                text_list_flag = False
        width = int(children_list[j].data.width)
        width_list.append(width)
    max_height = numpy.max(height_list)
    if len(width_list) <= 1 and len(x_center_list) > 0 and len(grid_flag_dict['center_x_list']) > 0:  # 只有一个元素情况特殊处理
        if abs(x_center_list[0] - grid_flag_dict['center_x_list'][0][0]) <= 5:
            if text_list_flag and start_flag is False:
                input_tree.get_node(parent_id).data.extra_dict['image_text_list'] = 2  # 图文列表，后续需要相邻合并
                grid_flag_dict['height_list'].append(max_height)
                grid_flag_dict['center_x_list'].append(x_center_list)

            return True
        return False  # 对于末尾最后只有一个元素场景，先简单处理

    if start_flag == True and numpy.var(width_list) >= 2 and abs(
            numpy.average(x_center_list) - numpy.median(x_center_list)) >= 2:  # 该情况肯定无法构成列表
        return False
    if numpy.var(y_list) <= 2 and numpy.var(height_list) <= 2:
        if text_list_flag and min(width_list) != 0 and max(width_list) / min(
                width_list) < ImageTextList_TextWidth_DIFF_RATIO:  # 1.4:  # 文本构成列表条件,宽度差异阈值
            if start_flag is False:
                input_tree.get_node(parent_id).data.extra_dict['image_text_list'] = 2  # 图文列表，后续需要相邻合并
            grid_flag_dict['height_list'].append(max_height)
            grid_flag_dict['center_x_list'].append(x_center_list)
            return True
        elif numpy.var(width_list) <= 2:  # 非文本列表构成条件严格
            grid_flag_dict['height_list'].append(max_height)
            grid_flag_dict['center_x_list'].append(x_center_list)
            return True
    if len(width_list) >= 2 and abs(numpy.average(x_center_list) - numpy.median(
            x_center_list)) <= 1 and next_line_id is not None:  # 多于3个且中间对齐情况，结合下一行情况综合判断
        text_y_list = list()
        text_x_center_list = list()
        text_height_list = list()
        text_children_list = input_tree.children(next_line_id)
        text_children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))
        for j, child in enumerate(text_children_list):
            text_y_list.append(int(text_children_list[j].data.y))
            text_x_center_list.append(int(text_children_list[j].data.x + text_children_list[j].data.width / 2))
            text_height_list.append(int(text_children_list[j].data.height))
            if j > 0 and (text_children_list[j].data.x < text_children_list[j - 1].data.x + text_children_list[
                j - 1].data.width):
                return False  # 横向重叠的无法构成横向列表
            if is_text(text_children_list[j].data.src) == False:  # ['type'] != 'Text':
                return False
        if numpy.var(text_height_list) == 0 and numpy.var(text_y_list) == 0 and len(text_x_center_list) == len(
                x_center_list):
            for i, elem in enumerate(text_x_center_list):
                if abs(text_x_center_list[i] - x_center_list[i]) >= 6:  # 上下两行的中心距离偏移不能太大
                    return False
            grid_flag_dict['height_list'].append(max_height)
            grid_flag_dict['height_list'].append(numpy.max(text_height_list))
            grid_flag_dict['center_x_list'].append(x_center_list)
            grid_flag_dict['center_x_list'].append(text_x_center_list)

            input_tree.get_node(next_line_id).data.extra_dict['image_text_list'] = 2
            return True
    return False


def merge_split_elem_to_grid(input_tree, current_uid):
    children_list = input_tree.children(current_uid)
    if len(children_list) <= 1:
        return
    children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))  # 从小到大排序
    children_num = len(children_list)
    merge_layout_list = list()
    grid_flag_dict = dict()
    grid_flag_dict['height_list'] = list()
    grid_flag_dict['center_x_list'] = list()
    i = 0
    while i < children_num - 1:
        if i + 1 <= children_num:
            next_line_id = children_list[i + 1].data.uid  # 某些列表需要结合上下文判断可否切分
        else:
            next_line_id = None
        if children_list[i].data.uid.find('layout_') >= 0 and judge_horizon_list_control(input_tree,
                                                                                         children_list[i].data.uid,
                                                                                         grid_flag_dict, True,
                                                                                         next_line_id):
            merge_layout_list.append(children_list[i])
            i = i + 1
            while (i < children_num and ((children_list[i].data.uid.find(
                    'layout_') >= 0 and judge_horizon_list_control(input_tree, children_list[i].data.uid,
                                                                   grid_flag_dict, False, children_list[
                                                                       i + 1].data.uid if i + 1 < children_num else None)) or (
                                                 children_list[i].data.uid.find(
                                                     'layout_') < 0 and is_two_line_compose_grid(children_list[i - 1],
                                                                                                 children_list[i],
                                                                                                 input_tree)))

            ):  # 网格最后一个元素可能只有一个元素，也要考虑合并.不过此次还有问题，如果出现图片混排，且最后一行只有一个元素则无法识别

                merge_layout_list.append(children_list[i])
                i = i + 1
            merge_list_cnt = len(merge_layout_list)
            if merge_list_cnt >= 2:
                if numpy.max(grid_flag_dict['height_list']) / numpy.min(
                        grid_flag_dict['height_list']) <= 1.01:  # numpy.var(merge_height_list) < 0.1: 单一控件类型的网格标志
                    simple_list_merge(current_uid, merge_layout_list, input_tree)
                else:  # 图文组合的网格
                    if len(numpy.unique(grid_flag_dict['height_list'])) == 2 and is_same_emebbed_list(
                            grid_flag_dict['center_x_list']):  # 表格场景

                        final_container = image_text_merge_grid(current_uid, merge_layout_list,
                                                                input_tree, children_list)
                    else:

                        new_temp_layout_list = list()
                        for i, temp_item in enumerate(merge_layout_list):
                            if 'image_text_list' in temp_item.data.extra_dict:
                                image_center_x_list = grid_flag_dict['center_x_list'][i - 1]
                                text_center_x_list = grid_flag_dict['center_x_list'][i]
                                if len(image_center_x_list) == len(text_center_x_list):
                                    need_merge_flag = True
                                    for j, elem in enumerate(text_center_x_list):
                                        if abs(text_center_x_list[j] - image_center_x_list[j]) >= 6:
                                            need_merge_flag = False
                                            break
                                    if need_merge_flag:
                                        temp_merge_list = list()
                                        temp_merge_list.append(merge_layout_list[i - 1])
                                        temp_merge_list.append(merge_layout_list[i])

                                        new_temp_layout_list.extend(temp_merge_list)
                                        final_container = image_text_merge_grid(current_uid, temp_merge_list,
                                                                                input_tree, children_list)
                                        merge_layout_list.append(input_tree.get_node(final_container))

                        merge_layout_list = [item for item in merge_layout_list if item not in new_temp_layout_list]
                        simple_list_merge(current_uid, merge_layout_list, input_tree)

        else:
            merge_layout_list.clear()
            grid_flag_dict['center_x_list'] = list()
            grid_flag_dict['height_list'] = list()
            i = i + 1


def simple_list_merge(current_uid, merge_layout_list, input_tree):
    merge_list_cnt = len(merge_layout_list)
    all_list_container = False
    if len(input_tree.children(current_uid)) == len(merge_layout_list):
        all_list_container = True
    layout_value = ai_type_def.LAYOUT_TYPE.GRID.value if merge_list_cnt > 1 else ai_type_def.LAYOUT_TYPE.ROW.value
    grid_children_list = list()
    for j, elem in enumerate(merge_layout_list):
        if elem.data.uid.find('layout_') < 0:
            grid_children_list.append(elem.data)
        else:
            sub_children = input_tree.children(elem.data.uid)
            for k, elem2 in enumerate(sub_children):
                grid_children_list.append(elem2.data)
    if all_list_container:
        for k, sub_item in enumerate(grid_children_list):
            if isinstance(sub_item, Node):
                sub_item = sub_item.data
            input_tree.move_node(sub_item.uid, current_uid)
        input_tree.get_node(current_uid).data.layout_type = layout_value

    else:
         create_flex_container(input_tree, grid_children_list, current_uid,layout_value)
    for j, elem in enumerate(merge_layout_list):  # 移除多余自建容器
        if elem.data.uid.find('layout_') >= 0:
            input_tree.remove_node(elem.data.uid)


def image_text_merge_grid(current_uid, merge_layout_list, input_tree, children_list):
    merge_list_len = len(merge_layout_list)
    temp_group_list = list()
    grid_children_list = list()
    temp_container_list = list()
    for j in range(0, int(merge_list_len / 2)):
        temp_list = list()
        redpoint_list = list()

        sub_children1 = input_tree.children(merge_layout_list[j * 2].data.uid)
        for k, elem2 in enumerate(sub_children1):
            if (
                    elem2.data.ai_type == ai_type_def.AI_TYPE.RED_POINT.value or elem2.data.ai_type == ai_type_def.AI_TYPE.BUBBLE.value):
                redpoint_list.append(elem2)
                continue
            temp_list.append(elem2.data)
        sub_children2 = input_tree.children(merge_layout_list[j * 2 + 1].data.uid)
        for k, elem2 in enumerate(sub_children2):
            if  (
                    elem2.data.ai_type == ai_type_def.AI_TYPE.RED_POINT.value or elem2.data.
                ai_type == ai_type_def.AI_TYPE.BUBBLE.value):
                redpoint_list.append(elem2)
                continue
            temp_list.append(elem2.data)
        temp_container_id = create_flex_container(input_tree, temp_list, current_uid, ai_type_def.LAYOUT_TYPE.ROW.value)
        temp_group_list.extend(list_elem_group(input_tree, temp_list, temp_container_id))
        redpoint_list_group(input_tree, redpoint_list, temp_container_id)
        temp_container_list.append(temp_container_id)
        grid_children_list.extend(temp_list)
    if len(merge_layout_list) == len(children_list):
        final_container = current_uid
    else:
        merge_list_cnt = len(merge_layout_list)
        final_container = create_flex_container(input_tree, temp_group_list, current_uid,
                                                ai_type_def.LAYOUT_TYPE.GRID.value if (
                                                            merge_list_cnt / 2 > 1) else ai_type_def.LAYOUT_TYPE.ROW.value)
    for j, elem in enumerate(merge_layout_list):
        input_tree.remove_node(elem.data.uid)
    for j, elem in enumerate(temp_container_list):
        elem_list = input_tree.children(elem)
        for k, elem3 in enumerate(elem_list):
            input_tree.move_node(elem3.data.uid, final_container)
        input_tree.remove_node(elem)
        if len(merge_layout_list) > 2:
            input_tree.get_node(final_container).data.layout_type = ai_type_def.LAYOUT_TYPE.GRID.value
        else:
            input_tree.get_node(final_container).data.layout_type = ai_type_def.LAYOUT_TYPE.ROW.value
    return final_container


def is_two_line_compose_grid(last_horizon_list_elem, current_one_elem, input_tree):  # 某些网格布局最后一行只有一个元素
    chilren_list = input_tree.children(last_horizon_list_elem.data.uid)
    if abs(chilren_list[0].data.width - current_one_elem.data.width) <= 2 and abs(
            chilren_list[0].data.height - current_one_elem.data.height) <= 1:
        return True
    return False


def redpoint_list_group(input_tree, redpoint_list, container_id):
    children_list = input_tree.children(container_id)
    for k, elem in enumerate(redpoint_list):
        best_container = None
        min_x_distance = 999999
        for j, elem_node in enumerate(children_list):
            sub_container = elem_node.data
            distance = abs(elem.data.x + elem.data.width / 2 - sub_container.x - sub_container.width / 2)
            if distance < min_x_distance:
                min_x_distance = distance
                best_container = sub_container
        input_tree.move_node(elem.data.uid, best_container.uid)


# 返回容器列表
def list_elem_group(input_tree, input_list, current_uid):  # 控件重新分组算法
    return_list = list()
    if len(input_list) < 3:
        return return_list
    elem_list_group = list()
    type_cnt = 0
    current_y_center = 0
    input_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))  # 从小到大排序
    for i, elem in enumerate(input_list):
        if abs(elem.height / 2 + elem.y - current_y_center) >= 20:
            type_cnt = type_cnt + 1
            current_y_center = elem.height / 2 + elem.y
            elem_list = list()
            elem_list.append(elem)
            elem_list_group.append(elem_list)
        else:
            elem_list_group[type_cnt - 1].append(elem)
    elem_cnt = len(elem_list_group[0])
    if type_cnt == 2 and len(elem_list_group[0]) == len(elem_list_group[1]):
        elem_list_group[0].sort(key=functools.cmp_to_key(tree_rebuild.compare_x))  # 从
        elem_list_group[1].sort(key=functools.cmp_to_key(tree_rebuild.compare_x))  # 从

        for i in range(0, elem_cnt):
            sub_input_list = list()
            sub_input_list.append(elem_list_group[0][i])
            sub_input_list.append(elem_list_group[1][i])
            # 创建新的包含容器
            min_x, min_y, width, height = tree_projection.calc_min_container(sub_input_list)
            container_id = 'layout_group' + str(i) + str(int(min_x)) + str(int(min_y))
            new_container_data = ContainerComponent(id=container_id, parent_id=None,
                                                          layout=None, style=Style(), props=None, children=[], figma=None)

            container1 = gen_tree.UIControl(min_x, min_y, width, height, container_id)
            container1.layout_type = ai_type_def.LAYOUT_TYPE.COLUMN.value  # 目前分组后的容器控件都是这种类型
            container1.extra_dict["create_flag"] = "by_list_regroup"
            container1.seq = input_tree.get_node(current_uid).data.seq + 0.2
            container1.src = new_container_data
            # 在多叉树上创建容器节点
            container_node = input_tree.create_node(container1.uid, container1.uid, parent=current_uid, data=container1)
            return_list.append(container_node.data)

            for k, sub_item in enumerate(sub_input_list):
                input_tree.move_node(sub_item.uid, container1.uid)
        regularization_horizon_list_size(input_tree, current_uid)
        return return_list

    return return_list


def create_flex_container(input_tree, input_list, current_uid, layout_type, src=None):
    if len(input_list) >= 2:
        # 创建新的包含容器
        min_x, min_y, width, height = tree_projection.calc_min_container(input_list)
        global grid_container_cnt
        if src is None:
            container_id = 'layout_list_' + str(grid_container_cnt)
        else:
            container_id = src + str(grid_container_cnt)
        grid_container_cnt = grid_container_cnt + 1
        container1 = gen_tree.UIControl(min_x, min_y, width, height, container_id)
        new_container_data = ContainerComponent(id=container_id, parent_id=None,
                                                          layout= None, style=Style(), props=None, children=[], figma=None)
        container1.extra_dict["desc"] = "find_in_list"
        container1.seq = input_tree.get_node(current_uid).data.seq + 0.2
        container1.layout_type = layout_type
        container1.src = new_container_data
        # 在多叉树上创建容器节点
        input_tree.create_node(container1.uid, container1.uid, parent=current_uid, data=container1)
        for k, sub_item in enumerate(input_list):
            if isinstance(sub_item, Node):
                sub_item = sub_item.data
            input_tree.move_node(sub_item.uid, container1.uid)
        return container1.uid


def regularization_horizon_list_size(input_tree, container_id):  # 水平列表大小调整
    flex_list = list()
    children_list = input_tree.children(container_id)
    x_center_margin = list()
    y_bottom_list = list()
    width_list = list()
    height_list = list()
    red_point_cnt = 0
    for i, elem in enumerate(children_list):
        if component_style_utils.is_redpoint_bubble(elem.data):
            red_point_cnt += 1
            continue
        if elem.data.uid.find('layout_') < 0:  # 只规整化自建容器
            continue
        flex_list.append(elem)
        height_list.append(elem.data.height)
        y_bottom_list.append(elem.data.y + elem.data.height)
        width_list.append(elem.data.width)
        x_center_margin.append(elem.data.x + elem.data.width / 2)
    if len(width_list) < 2:
        return
    if len(children_list) - red_point_cnt - len(width_list) > 1:  # 非自建容器过多，多半无法构成横向列表，提前过滤
        return
    if ( abs((numpy.mean(x_center_margin) - numpy.median(x_center_margin))) <= 1 and len(width_list) >= 3):
        max_height = numpy.max(height_list)
        max_width = numpy.max(width_list)
        max_y = numpy.max(y_bottom_list)
        min_y = max_y - max_height
        for i, elem in enumerate(flex_list):
            new_y = min_y
            elem.data.height = max_height
            elem.data.y = new_y
            new_x = elem.data.x - (max_width - elem.data.width) / 2
            elem.data.width = max_width

            elem.data.x = new_x
            elem.data.extra_dict['desc'] = "_resize_hor"
        if container_id.find('layout_') >= 0:  # 只调整自建容器，不调整原有容器大小
            min_x, min_y, width, height = tree_projection.calc_min_container(children_list)
            container_data = input_tree.get_node(container_id).data
            container_data.x = min_x
            container_data.y = min_y
            container_data.width = width
            container_data.height = height

def judge_list(input_tree, parent_node, width_list, height_list):
    if "list_type" in parent_node.data.extra_dict:
        return parent_node.data.extra_dict["list_type"]
    if calc_size_simularity(width_list, height_list) == 0:
        return None
    elem_list = list()
    children_list = input_tree.children(parent_node.data.uid)
    for child in children_list:
        grandson_list = input_tree.children(child.data.uid)
        elem_list.append(len(grandson_list))
    if calc_content_similarity(elem_list):
        parent_node.data.extra_dict["list_type"] = ai_type_def.LIST_TYPE.LOOP_CONTAINER.value
        return ai_type_def.LIST_TYPE.LOOP_CONTAINER.value
    return None

def is_image_text_group(input_tree,current_uid):
    parent_node = input_tree.parent(current_uid)
    if  "list_elem" in parent_node.data.extra_dict and len(input_tree.children(parent_node.data.uid)) ==1:
        return False
    children_list = input_tree.children(current_uid)
    non_redpoint_list = list()
    for i,elem in enumerate(children_list):
        if component_style_utils.is_redpoint_bubble(elem.data) == False:
            non_redpoint_list.append(elem)
    if len(non_redpoint_list) == 2:
        non_redpoint_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))
        if non_redpoint_list[0].data.src.type == dsl_enum.ComponentType.IMAGE and non_redpoint_list[1].data.src.type == dsl_enum.ComponentType.TEXT:
            return True
    return False

def is_merged_list(input_tree,children_list):
    if len(children_list) <=1 :
        return False
    first_row_container = children_list[0]
    son_list = input_tree.children(first_row_container.data.uid)
    width_list = list()
    height_list = list()
    for i,elem in enumerate(son_list):
        if component_style_utils.is_redpoint_bubble(elem.data):
            continue
        if is_image_text_group(input_tree,elem.data.uid) == False:
            return False
        width_list.append(elem.data.width)
        height_list.append(elem.data.height)
    if numpy.var(width_list) >1 or numpy.var(height_list) >1:
        return False
    return True


def judge_container_list(input_tree,parent_node):
    if "list_type" in parent_node.data.extra_dict:
        return parent_node.data.extra_dict["list_type"]
    children_list = input_tree.children(parent_node.data.uid)
    children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))  # 列表排序
    split_line_cnt = 0
    red_point_cnt = 0
    elem_list = list()
    last_width = 0
    last_height = 0
    last_node = None
    list_start_index = -1
    list_elem_cnt = 0
    for i,child in enumerate(children_list):
        if component_style_utils.is_redpoint_bubble(child.data):
            red_point_cnt += 1
            continue
        elif child.data.ai_type == ai_type_def.AI_TYPE.SPLIT_LINE.value:
            split_line_cnt += 1
            continue
        grandson_list = input_tree.children(child.data.uid)
        elem_list.append(len(grandson_list))
        if list_start_index ==-1:
            last_width = child.data.width
            last_height = child.data.height
            last_node = child
            list_start_index = 0
            list_elem_cnt = 1
        else:
            if abs(child.data.width - last_width) <=1 and abs(child.data.height - last_height) <=1:
                if child.data.src.type == last_node.data.src.type:
                    list_elem_cnt += 1
                continue
            else:
                if list_elem_cnt > 1:
                    break
                list_start_index = i
                last_width = child.data.width
                last_height = child.data.height

    if list_elem_cnt + red_point_cnt + split_line_cnt == len(children_list) and len(elem_list) >1:
            layout_type = tree_projection.calc_layout_type(input_tree.get_node(parent_node.data.uid), children_list)
            parent_node.data.layout_type = layout_type
            if layout_type == ai_type_def.LAYOUT_TYPE.COLUMN and is_merged_list(input_tree,children_list):
                return  None
            parent_node.data.extra_dict["list_type"] = ai_type_def.LIST_TYPE.LOOP_CONTAINER.value
            return ai_type_def.LIST_TYPE.LOOP_CONTAINER.value
    return None


def calc_size_simularity(width_list, height_list):
    if len(width_list) >= 2 and calculate_range_difference(width_list) <= 2 and calculate_range_difference(
            height_list) <= 2:
        return 1

    return 0


def calculate_range_difference(data):
    if len(data) == 0:
        return 0
    elif len(data) == 1:
        return 0
    else:
        return max(data) - min(data)


def calc_content_similarity(length_list):
    if len(length_list) == 0:
        return 0
    if numpy.max(length_list) - numpy.min(length_list) <= 1:
        return 1
    return 0


def is_two_elem_simular(input_tree, node1, node2):
    width_list = list()
    height_list = list()
    length_list = list()

    width_list.append(node1.data.width)
    width_list.append(node2.data.width)
    height_list.append(node1.data.height)
    height_list.append(node2.data.height)

    children_list1 = input_tree.children(node1.data.uid)
    children_list2 = input_tree.children(node2.data.uid)
    length_list.append(len(children_list1))
    length_list.append(len(children_list2))
    if calc_size_simularity(width_list, height_list) and calc_content_similarity(length_list):
        return True


def get_match_count(valid_list1,valid_list2,node1,node2):
    match_count = 0
    tree_rebuild.sort_tree_by_split(valid_list1, node1.data)
    tree_rebuild.sort_tree_by_split(valid_list2, node2.data)
    if len(valid_list1) <= len(valid_list2):
            for i, elem in enumerate(valid_list1):
                for j, elem2 in enumerate(valid_list2):
                    if elem_match(elem, elem2, node1, node2):
                        match_count  = match_count + 1
                        valid_list2.remove(elem2)
                        break

    return  match_count

def elem_match(elem1,elem2,parent1,parent2):
    if elem1.data.src.type != elem2.data.src.type:
        return False
    if elem1.data.src.type == dsl_enum.ComponentType.CONTAINER or elem1.data.src.type == dsl_enum.ComponentType.CONTAINER_RICH or elem1.data.src.type == dsl_enum.ComponentType.IMAGE:
        if abs(elem1.data.x - parent1.data.x - elem2.data.x + parent2.data.x ) <=5 or abs((elem1.data.x + elem1.data.width/2 - parent1.data.x- parent1.data.width/2) - (elem2.data.x + elem2.data.width/2 - parent2.data.x- parent2.data.width/2)) <=5 or  abs(elem1.data.y - parent1.data.y - elem2.data.y + parent2.data.y ) <= 5:
            return True
    elif  elem1.data.src.type == dsl_enum.ComponentType.TEXT:
        if elem1.data.src.style.font_size == elem2.data.src.style.font_size :#单文本的情况,可能两个字体font_family不一样
            return True
    return False


