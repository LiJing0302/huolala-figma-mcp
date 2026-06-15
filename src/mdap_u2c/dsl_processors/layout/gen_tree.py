import logging

import treelib
import json

from mdap_u2c.dsl_processors.layout import ai_type_def
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import component_style_utils

_logger = logging.getLogger("gen_tree")


def mat_inter(box1, box2):
    x01, y01, x02, y02 = box1
    x11, y11, x12, y12 = box2

    lx = abs((x01 + x02) / 2 - (x11 + x12) / 2)
    ly = abs((y01 + y02) / 2 - (y11 + y12) / 2)
    sax = abs(x01 - x02)
    sbx = abs(x11 - x12)
    say = abs(y01 - y02)
    sby = abs(y11 - y12)
    if lx <= (sax + sbx) / 2 and ly <= (say + sby) / 2:
        return True
    else:
        return False


#1 完全一样
#2 A 包含B
#3 B 包含A
#0～1 局部
#0 不重叠


def _is_rect_special_type(rect) -> bool:
    """
    判断 rect 是否为文本类型（TEXT 或 CONTAINER_RICH）。
    rect 可能为节点 data，通过 rect.src.type 获取类型。
    """
    src = getattr(rect, "src", None)
    if src is None:
        return False
    t = getattr(src, "type", None)
    return t == dsl_enum.ComponentType.TEXT or t == dsl_enum.ComponentType.CONTAINER_RICH


def judge_box_special_type(rect1, rect2, coincide, intersection, area1, area2):
    """
    文本容器特殊处理：在包含/完全重叠且某一侧为文本类型时返回 0.9。
    - rect1 包含 rect2 或 rect1 与 rect2 完全重叠，且 rect1 为文本类型 → 返回 0.9
    - rect2 包含 rect1，且 rect2 为文本类型 → 返回 0.9
    否则返回 None（不覆盖原逻辑）。
    """
    # rect1 包含 rect2（intersection == area2）或完全重叠（coincide == 1），且 rect1 为文本类型
    if (coincide == 1 or intersection == area2) and _is_rect_special_type(rect1):
        return 0.9
    # rect2 包含 rect1，且 rect2 为文本类型
    if intersection == area1 and _is_rect_special_type(rect2):
        return 0.9
    return None


def _rect_to_box(rect):
    """将带 x,y,width,height 的对象转为 (x1, y1, x2, y2) 格式。"""
    return (rect.x, rect.y, rect.x + rect.width - 1, rect.y + rect.height - 1)


def _tuple_to_box(tuple_xywh):
    """将 (x, y, width, height) 元组转为 (x1, y1, x2, y2) 格式。"""
    x, y, w, h = tuple_xywh
    return (x, y, x + w - 1, y + h - 1)

def _judge_slit_line_overlap(box1, box2):
    """
    判断「分割线」与矩形/线与的重叠。分割线即 width=0 或 height=0 的 box。
    返回格式与 _box_overlap 一致: (coincide, col, row, intersection, area1, area2)。
    语义: 3=B包含A, 2=A包含B, 1=完全重合, 0.1=局部重叠。
    """
    x01, y01, x02, y02 = box1
    x11, y11, x12, y12 = box2
    # 避免 0 面积导致除零，用 0.1 占位
    fake_area = 0.1
     # 两条都是线：横-横
    if y01 == y02 and y11 == y12:
        if y01 != y11:
            return None
        col = min(x02, x12) - max(x01, x11)
        if col < 0:
            return None
        if (min(x01, x02), max(x01, x02)) == (min(x11, x12), max(x11, x12)):
            return (1, col, 0, fake_area, 0, 0)
        return (0.1, col, 0, fake_area, 0, 0)

    # 两条都是线：竖-竖
    if x01 == x02 and x11 == x12:
        if x01 != x11:
            return None
        row = min(y02, y12) - max(y01, y11)
        if row < 0:
            return None
        if (min(y01, y02), max(y01, y02)) == (min(y11, y12), max(y11, y12)):
            return (1, 0, row, fake_area, 0, 0)
        return (0.1, 0, row, fake_area, 0, 0)

    # box1 横线 (y01==y02)，与 box2 相交
    if y01 == y02 and y11 <= y01 <= y12:
        col = min(x02, x12) - max(x01, x11)
        if col < 0:
            return None
        if min(x01, x02) >= min(x11, x12) and max(x01, x02) <= max(x11, x12):
            return (3, col, 0, fake_area, 0, 0)
        return (0.1, col, 0, fake_area, 0, 0)

    # box1 竖线 (x01==x02)，与 box2 相交
    if x01 == x02 and x11 <= x01 <= x12:
        row = min(y02, y12) - max(y01, y11)
        if row < 0:
            return None
        if min(y01, y02) >= min(y11, y12) and max(y01, y02) <= max(y11, y12):
            return (3, 0, row, fake_area, 0, 0)
        return (0.1, 0, row, fake_area, 0, 0)

    # box2 横线 (y11==y12)，与 box1 相交
    if y11 == y12 and y01 <= y11 <= y02:
        col = min(x02, x12) - max(x01, x11)
        if col < 0:
            return None
        if min(x11, x12) >= min(x01, x02) and max(x11, x12) <= max(x01, x02):
            return (2, col, 0, fake_area, 0, 0)
        return (0.1, col, 0, fake_area, 0, 0)

    # box2 竖线 (x11==x12)，与 box1 相交
    if x11 == x12 and x01 <= x11 <= x02:
        row = min(y02, y12) - max(y01, y11)
        if row < 0:
            return None
        if min(y11, y12) >= min(y01, y02) and max(y11, y12) <= max(y01, y02):
            return (2, 0, row, fake_area, 0, 0)
        return (0.1, 0, row, fake_area, 0, 0)

    # 横线 + 竖线：仅当交点重合时重叠
    if y01 == y02 and x11 == x12:  # box1 横, box2 竖
        if not (min(x01, x02) <= x11 <= max(x01, x02) and min(y11, y12) <= y01 <= max(y11, y12)):
            return None
        return (0.1, 0, 0, fake_area, 0, 0)
    if x01 == x02 and y11 == y12:  # box1 竖, box2 横
        if not (min(y01, y02) <= y11 <= max(y01, y02) and min(x11, x12) <= x01 <= max(x11, x12)):
            return None
        return (0.1, 0, 0, fake_area, 0, 0)

    return None


def _box_overlap(box1, box2):
    """
    核心重叠计算：判断两矩形是否相交并计算重合度与交叉区域尺寸。
    box 格式为 (x1, y1, x2, y2)。
    对 width=0 或 height=0 的分割线做特殊处理
    再按统一公式计算重叠和包含关系。
    返回:
        (coincide, col, row, intersection, area1, area2) 相交且面积合法；
        (-1, 0, 0, None, None, None) 相交但 area1+area2-intersection==0；
        None 表示不相交。
    """
    if _judge_slit_line_overlap(box1, box2) is not None:
        return _judge_slit_line_overlap(box1, box2)
    if not mat_inter(box1, box2):
        return None
    x01, y01, x02, y02 = box1
    x11, y11, x12, y12 = box2

    col = min(x02, x12) - max(x01, x11)
    row = min(y02, y12) - max(y01, y11)
    intersection = (col + 1) * (row + 1)
    area1 = (x02 - x01 + 1) * (y02 - y01 + 1)
    area2 = (x12 - x11 + 1) * (y12 - y11 + 1)
    if area1 + area2 - intersection == 0:
        return (-1, 0, 0, None, None, None)
    coincide = intersection / (area1 + area2 - intersection)
    return (coincide, col, row, intersection, area1, area2)


def judge_box(rect1, rect2):
    """判断两矩形重叠关系，返回语义值：1=完全一样，2=A包含B，3=B包含A，0~1=局部重叠，0.9=文本特殊，0=不重叠，-1=异常。"""
    raw = _box_overlap(_rect_to_box(rect1), _rect_to_box(rect2))
    if raw is None:
        return 0
    coincide, col, row, intersection, area1, area2 = raw
    if coincide == -1:
        return -1
    text_special = judge_box_special_type(rect1, rect2, coincide, intersection, area1, area2)
    if text_special is not None:
        return text_special
    if coincide == 1:
        return 1
    if intersection == area2:
        return 2
    if intersection == area1:
        return 3
    return coincide


def judge_box2(tuple1, tuple2):
    """
    基于 (x, y, width, height) 元组判断两矩形重叠比例。
    返回 coincide（0~1）、不重叠为 0、面积异常为 -1。
    """
    raw = _box_overlap(_tuple_to_box(tuple1), _tuple_to_box(tuple2))
    if raw is None:
        return 0
    coincide= raw[0]
    return coincide


def judge_box3(rect1, rect2):
    """判断两矩形重叠并返回 (重合度, 交叉宽度, 交叉高度)。不重叠返回 (0, 0, 0)。"""
    raw = _box_overlap(_rect_to_box(rect1), _rect_to_box(rect2))
    if raw is None:
        return (0, 0, 0)
    return (raw[0], raw[1], raw[2])


class UIControl(object):
    def __init__(self, x, y, width: float, height: float, uid):
        self.uid = uid
        self.x: float = float(x)  # 确保转换为 float 类型
        self.y: float = float(y)  # 确保转换为 float 类型
        self.width: float = float(width)  # 确保转换为 float 类型
        self.height: float = float(height)  # 确保转换为 float 类型
        self.ai_type = None
        self.seq = 0
        self.layout_type = None
        self.extra_dict = dict() #记录额外信息用于数据处理
        self.src = None
        self.cross_control = set()
        self.parent_control = list()
        self.float_control = set()
        self.overlap_control = list()
        self.over_edge = list()

    def jsonformat(self):
        return {
            "name": self.uid,
            "ai_type": self.ai_type,
            "seq": self.seq,
            "x": str(self.x),
            "y": str(self.y),
            "width": str(self.width),
            "height": str(self.height),
            "over_edge": list(self.over_edge),
            "extra_dict":self.extra_dict,
            "cross_control":list(self.cross_control)
        }


def _mark_parent_split_line(uiTree, parentNodeName, node1):
    """若 node1 为分割线，对父容器标记 have_vertical_line / have_horizon_line"""
    is_split = (
        getattr(node1, "ai_type", None) == ai_type_def.AI_TYPE.SPLIT_LINE.value
        or component_style_utils.regconize_split_line(node1.width, node1.height)
    )
    if not is_split:
        return
    parent_node = uiTree.get_node(parentNodeName)
    if not parent_node or not getattr(parent_node, "data", None):
        return
    # 横向：宽>=32 且 高<=1；纵向：宽<=1 且 高>=16
    if node1.width >= 32 and node1.height <= 1:
        parent_node.data.extra_dict["have_horizon_line"] = 1
    if node1.width <= 1 and node1.height >= 16:
        parent_node.data.extra_dict["have_vertical_line"] = 1


def gen_sub_tree(ui_elem, uiTree, parentNodeName):
        branchList = uiTree.children(parentNodeName)
        if len(branchList) == 0:
            uiTree.create_node(tag=ui_elem.uid, identifier=ui_elem.uid, parent=parentNodeName, data=ui_elem)
            _mark_parent_split_line(uiTree, parentNodeName, ui_elem)
        else:
            for j, elem2 in enumerate(branchList):

                node1 = ui_elem
                node2 = elem2.data
                result = judge_box(node1, node2)
                if (result == 0):
                    if (j == len(branchList) - 1):
                        uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                        _mark_parent_split_line(uiTree, parentNodeName, node1)
                        return
                    else:
                        continue
                elif (result == 1):
                    _logger.warning(f"出现大小宽高一致控件,{node1.uid},{node2.uid}")
                    gen_sub_tree(node1, uiTree, node2.uid)
                    mark_overlapped_invisible_control(node1, node2)
                    return
                elif (result == 3):

                    node1.parent_control.append(node2.uid)
                    for k in range(j + 1, len(branchList)):
                        compare_move_control(uiTree, node1, branchList[k].data)
                    parent_node = uiTree.get_node(node1.parent_control[-1])

                    for i, elem in enumerate(node1.cross_control):
                        if parent_node.data.seq < uiTree.get_node(elem).data.seq < node1.seq:
                            uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                            _mark_parent_split_line(uiTree, parentNodeName, node1)
                            return
                    gen_sub_tree(node1, uiTree, parent_node.data.uid)
                    break
                elif (result == 2):

                    process_overlapped_control(uiTree, node1, node2)
                    for k in range(j + 1, len(branchList)):
                        compare_move_control(uiTree, node1, branchList[k].data)
                    if len(node1.parent_control) > 0:
                        parent_node = uiTree.get_node(node1.parent_control[-1])
                        for i, elem in enumerate(node1.cross_control):
                            if parent_node.data.seq < uiTree.get_node(elem).data.seq < node1.seq:
                                uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                                _mark_parent_split_line(uiTree, parentNodeName, node1)
                                return
                        uiTree.create_node(node1.uid, node1.uid, parent=parent_node.data.uid, data=node1)
                        _mark_parent_split_line(uiTree, parent_node.data.uid, node1)
                    else:
                        uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                        _mark_parent_split_line(uiTree, parentNodeName, node1)
                    return
                elif (result > 0 and result < 1):
                    node2.cross_control.add(node1.uid)
                    node1.cross_control.add(node2.uid)
                    add_float_control(uiTree, node1, node2)
                    for k in range(j + 1, len(branchList)):
                        compare_move_control(uiTree, node1, branchList[k].data)
                    if len(node1.parent_control) > 0:
                        parent_node = uiTree.get_node(node1.parent_control[-1])
                        for i, elem in enumerate(node1.cross_control):
                            if parent_node.data.seq < uiTree.get_node(elem).data.seq < node1.seq:
                                if not uiTree.contains(node1.uid):
                                    uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                                    _mark_parent_split_line(uiTree, parentNodeName, node1)
                                return
                        gen_sub_tree(node1, uiTree, parent_node.data.uid)
                    else:
                        uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                        _mark_parent_split_line(uiTree, parentNodeName, node1)
                    return
                elif (result == -1):
                    uiTree.create_node(node1.uid, node1.uid, parent=parentNodeName, data=node1)
                    _mark_parent_split_line(uiTree, parentNodeName, node1)
                    return


def mark_overlapped_invisible_control(node1, node2):
    if node2.seq < node1.seq:
        node2.overlap_control.append(node1.uid)


def process_overlapped_control(input_tree, node1, node2):
    if node2.seq > node1.seq:
        input_tree.move_node(node2.uid, node1.uid)
        node2.src['move'] = 2
        _logger.warning(f"层级移动 {node1.uid},{node2.uid}")
    mark_overlapped_invisible_control(node1, node2)


def compare_move_control(input_tree, node1, node2):
    result = judge_box(node1, node2)
    if result == 2:
        process_overlapped_control(input_tree, node1, node2)
    elif result == 3:
        node1.parent_control.append(node2.uid)
    elif result == 1:
        _logger.warning(f"大小宽高一致{node2.uid},{node1.uid}")
        mark_overlapped_invisible_control(node1, node2)
    elif result > 0 and result < 1:
        node2.cross_control.add(node1.uid)
        node1.cross_control.add(node2.uid)
        add_float_control(input_tree, node1, node2)


def add_float_control(input_tree, node1, node2):
    top_node = node1 if node1.seq > node2.seq else node2
    parent_list = top_node.parent_control
    if len(parent_list) > 0:
        top_parent_node = input_tree.get_node(parent_list[-1])
        if top_parent_node.data.seq < top_node.seq:
            input_tree.get_node(input_tree.root).data.float_control.add(top_node.uid)
        else:
            input_tree.get_node(input_tree.root).data.float_control.discard(top_node.uid)
        return
    input_tree.get_node(input_tree.root).data.float_control.add(top_node.uid)

if __name__ == "__main__":
    button1 = UIControl(10, 50, 20, 10, 'button1')
    image1 = UIControl(10, 70, 10, 10, "image1")
    container1 = UIControl(5, 40, 50, 100, "container1")
    container2 = UIControl(5, 250, 50, 100, "container2")
    root1 = UIControl(1, 1, 600, 800, "root1")
    uiList = list()
    uiList.append(root1)
    uiList.append(button1)
    uiList.append(image1)
    uiList.append(container1)
    uiList.append(container2)

    result = json.dumps(uiList, ensure_ascii=False, default=UIControl.jsonformat)
    print(result)

    tree_from_file = treelib.Tree()
    print('read tree from file')
    print(tree_from_file)
