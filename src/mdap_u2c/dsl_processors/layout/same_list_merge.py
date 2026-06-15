import functools

from mdap_u2c.dsl_processors.layout import remove_redundancy, tree_projection, ai_type_def, calc_list_layout, \
    tree_rebuild
from mdap_u2c.utils import component_style_utils


def list_merge_new(input_tree, parent_id):
    del_list = list()
    first_container_list = list()
    second_container_list = list()
    children_list = input_tree.children(parent_id)
    children_list.sort(key=functools.cmp_to_key(tree_rebuild.compare_x_y))
    for i, elem in enumerate(children_list):
        if component_style_utils.is_redpoint_bubble(elem.data):  #气泡红点直接忽略
            continue
        elif is_list_container(elem):
            if len(first_container_list) == 0:
                first_container_list.append(elem)
            else:  #已经存了上一个列表容器,所以先比较能否合并
                compare_result = compare_two_list(input_tree, first_container_list[-1].data.uid, elem.data.uid)
                if compare_result == 1:  #相同类型列表
                    first_container_list.append(elem)
                elif compare_result == 2:  #不同类型列表,但是可以合并,类似图文组合那种
                    second_container_list.append(elem)
                elif compare_result == 0:  #不同类型且不能合并的列表
                    if len(second_container_list) == 1 and len(first_container_list) == len(second_container_list):
                        temp_del_list = _merge_different_list_in_a_container(input_tree, first_container_list,
                                                                             second_container_list)
                        del_list.extend(temp_del_list)
                        first_container_list.clear()
                        second_container_list.clear()
                        first_container_list.append(elem)
                        continue
                    elif len(first_container_list) >= 1:
                        temp_del_list = _merge_same_list_in_a_container(input_tree, first_container_list,None)
                        del_list.extend(temp_del_list)
                        first_container_list.clear()
                        second_container_list.clear()
                        first_container_list.append(elem)
        else:  #中间被非列表元素隔断
            if len(second_container_list) == 1 and len(first_container_list) ==1:
                temp_del_list = _merge_different_list_in_a_container(input_tree, first_container_list,
                                                                     second_container_list)
                del_list.extend(temp_del_list)
                first_container_list.clear()
                second_container_list.clear()
                continue
            elif len(first_container_list) >= 1:
                temp_del_list = _merge_same_list_in_a_container(input_tree, first_container_list,elem)
                del_list.extend(temp_del_list)
                first_container_list.clear()
                second_container_list.clear()
    if len(second_container_list) == 1 and len(first_container_list) == 1:
        temp_del_list = _merge_different_list_in_a_container(input_tree, first_container_list,
                                                             second_container_list)
        del_list.extend(temp_del_list)
    elif len(first_container_list) >= 1:
        temp_del_list = _merge_same_list_in_a_container(input_tree, first_container_list,None)
        del_list.extend(temp_del_list)
    return del_list

def _merge_different_list_in_a_container(input_tree, first_container_list, second_container_list):
    del_list = list()
    if len(second_container_list) == 1 and len(first_container_list) == 1:
        first_children_list = input_tree.children(first_container_list[0].data.uid)
        second_children_list = input_tree.children(second_container_list[0].data.uid)
        if len(first_children_list) == len(second_children_list):
            # 检查条件1: first_container_list[0] 和 second_container_list[0] 均为行布局
            first_container_node = input_tree.get_node(first_container_list[0].data.uid)
            second_container_node = input_tree.get_node(second_container_list[0].data.uid)
            
            first_layout_type = tree_projection.calc_layout_type(first_container_node, first_children_list)
            second_layout_type = tree_projection.calc_layout_type(second_container_node, second_children_list)
            
            if first_layout_type != ai_type_def.LAYOUT_TYPE.ROW.value or \
               second_layout_type != ai_type_def.LAYOUT_TYPE.ROW.value:
                return del_list
            
            # 检查条件2: first_container_list[0] 和 second_container_list[0] 的纵向间距 <= 5
            first_y = first_container_list[0].data.y
            first_height = first_container_list[0].data.height
            second_y = second_container_list[0].data.y
            second_height = second_container_list[0].data.height
            
            # 计算纵向间距（两个容器之间的垂直距离）
            if first_y + first_height <= second_y:
                # 第一个容器在第二个容器上方
                vertical_gap = second_y - (first_y + first_height)
            elif second_y + second_height <= first_y:
                # 第二个容器在第一个容器上方
                vertical_gap = first_y - (second_y + second_height)
            else:
                # 两个容器有重叠，间距为0
                vertical_gap = 0
            
            if vertical_gap > 5:
                return del_list
            
            # 检查条件3: 内部子元素按照行布局排序后，相同索引号的元素水平中心坐标不超过2
            # 对两个容器的子元素按照行布局排序（按x坐标排序）
            first_children_sorted = sorted(first_children_list, key=functools.cmp_to_key(tree_rebuild.compare_x))
            second_children_sorted = sorted(second_children_list, key=functools.cmp_to_key(tree_rebuild.compare_x))
            
            # 检查相同索引号的元素水平中心坐标差
            for i in range(len(first_children_sorted)):
                first_center_x = first_children_sorted[i].data.x + first_children_sorted[i].data.width / 2
                second_center_x = second_children_sorted[i].data.x + second_children_sorted[i].data.width / 2
                if abs(first_center_x - second_center_x) > 2:
                    return del_list
            
            # 所有条件都满足，执行合并
            for k, sub_item in enumerate(first_children_list):
                for h, grand_item in enumerate(second_children_list):
                    input_tree.move_node(grand_item.data.uid, sub_item.data.uid)
                min_x, min_y, width, height = tree_projection.calc_min_container(
                    input_tree.children(sub_item.data.uid))
                node_data = input_tree.get_node(sub_item.data.uid).data
                node_data.x = min_x
                node_data.y = min_y
                node_data.width = width
                node_data.height = height
                new_container_mark_tag(input_tree, first_container_list[0])

    return del_list

def _merge_same_list_in_a_container(input_tree, first_container_list, last_node):
    if len(first_container_list) <= 1:
        return []
    new_container_node = first_container_list[0]
    new_container_id = new_container_node.data.uid
    first_target_elem_node = input_tree.children(new_container_id)[0]
    if last_node is not None and calc_list_layout.is_two_elem_simular(input_tree,first_target_elem_node,last_node):
        first_container_list.append(last_node)
    else:
        last_node = None
    min_x, min_y, width, height = tree_projection.calc_min_container(first_container_list)
    node_data = input_tree.get_node(new_container_id).data
    node_data.x = min_x
    node_data.y = min_y
    node_data.width = width
    node_data.height = height

    del_list = list()
    del_list.append(new_container_id)  #防止后面重复遍历.
    for index, child in enumerate(first_container_list[1:], start=1):
        if last_node is not None and child.data.uid == last_node.data.uid:
            input_tree.move_node(child.data.uid, new_container_id)
            continue
        # 处理从第二个元素开始的逻辑，并保留原始索引
        grandson_list = input_tree.children(child.data.uid)
        for grandson in grandson_list:
            input_tree.move_node(grandson.data.uid, new_container_id)
        input_tree.remove_node(child.data.uid)
        del_list.append(child.data.uid)

    layout_type = tree_projection.calc_layout_type(input_tree.get_node(new_container_id),
                                                      input_tree.children(new_container_id))
    node_data.layout_type = layout_type
    new_container_mark_tag(input_tree, new_container_node)

    parent_id = input_tree.parent(new_container_id).data.uid
    if len(input_tree.children(parent_id)) == 1:
        remove_redundancy.remove_container_only(input_tree, parent_id)
        del_list.append(parent_id)
    return del_list


def compare_two_list(input_tree, list_id1, list_id2):
    children_list1 = input_tree.children(list_id1)
    children_list2 = input_tree.children(list_id2)
    if len(children_list2) <= len(children_list1):
        for i, elem in enumerate(children_list2):
            center_x1 = elem.data.x + elem.data.width / 2
            center_x2 = children_list1[i].data.x + children_list1[i].data.width / 2
            if abs(center_x1 - center_x2) > 5:
                return 0  #不同类型列表,且不能合并
    node1 = children_list1[0]
    node2 = children_list2[0]
    if abs(node1.data.width - node2.data.width) < 5 and abs(node1.data.height - node2.data.height) < 2:
        return 1  #相同类型且能合并的列表
    return 2  #不同类型的列表,但是能合并
def new_container_mark_tag(input_tree, new_container_node):
    new_container_node.data.extra_dict["need_re_calc"] = 1
    return

def is_list_container(child):
    if "list_type" in child.data.extra_dict and child.data.extra_dict["list_type"] == ai_type_def.LIST_TYPE.LOOP_CONTAINER.value:
        return True
    return False
