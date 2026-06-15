# 修复导入语句，使用相对导入
from mdap_u2c.utils.component_style_utils import is_transparent_container


#对子节点超出父节点的情况做标记，方便后续投影算法中做容器大小调整

def mark_over_parent_node(input_tree,parent_name,current_x,current_y,current_width,current_height,current_uid):
    if parent_name == input_tree.root or parent_name is None:
        return None
    parent_node = input_tree.get_node(parent_name)
    parent_x = parent_node.data.x
    parent_y = parent_node.data.y
    parent_width = parent_node.data.width
    parent_height = parent_node.data.height
    if current_x < parent_x or current_x + current_width > parent_x + parent_width + 0.1   or current_y < parent_y or current_y + current_height > parent_height + parent_y + 0.1  : #发生越界
        parent_node.data.over_edge.append(current_uid)
        grand_parent_node = input_tree.parent(parent_name)
        mark_over_parent_node(input_tree, grand_parent_node.data.uid, current_x, current_y, current_width,
                              current_height,current_uid) #递归判断子节点是否超过爷爷节点


def adjust_over_parent_size(input_tree,parent_name,current_x,current_y,current_width,current_height):
    if parent_name == input_tree.root or parent_name is None:
        return
    parent_node = input_tree.get_node(parent_name)
    if not is_transparent_container(parent_node.data.src):
        return #非透明容器不能调整父节点
    parent_x = parent_node.data.x
    parent_y = parent_node.data.y
    parent_width = parent_node.data.width
    parent_height = parent_node.data.height

    if current_x < parent_x :
        parent_x = current_x
    if current_x + current_width > parent_x + parent_width :
        parent_width = current_x + current_width - parent_x
    if current_y < parent_y:
        parent_y = current_y
    if current_y + current_height > parent_height + parent_y :
        parent_height = current_y + current_height - parent_y
    parent_node.data.x = parent_x
    parent_node.data.y = parent_y
    parent_node.data.width = parent_width
    parent_node.data.height = parent_height
    parent_node.data.src['props']['attrs']['x'] = parent_x
    parent_node.data.src['props']['attrs']['y'] = parent_y
    parent_node.data.src['props']['style']['width'] = parent_width
    parent_node.data.src['props']['style']['height'] = parent_height
    parent_node.data.src['nodeLayerName'] = parent_node.data.src['nodeLayerName'] + "_resize_child_over"
    grand_parent_node = input_tree.parent(parent_name)
    adjust_over_parent_size(input_tree, grand_parent_node.data.uid, current_x, current_y, current_width, current_height)