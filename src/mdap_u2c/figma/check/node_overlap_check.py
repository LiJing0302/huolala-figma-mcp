from mdap_u2c.core import SingletonClass
from typing import Dict, Any, Optional, Tuple
from mdap_u2c.models import common_model


class NodeOverlapCheck(metaclass=SingletonClass):
    """Figma 节点重叠检测工具"""
    _node_rect = None
    _parent_rect = None

    @staticmethod
    def get_instance():
        return NodeOverlapCheck()

    def set_node(self, node: Dict[str, Any], parent_node: Dict[str, Any] = None):
        self._node_rect = self._get_rect(self._get_bounding_box(node))
        self._parent_rect = self._get_rect(self._get_bounding_box(parent_node))
        return self

    @staticmethod
    def _get_bounding_box(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """获取节点的边界框"""
        if not node:
            return None

        # 优先使用 absoluteBoundingBox，如果没有则使用 absoluteRenderBounds
        box = node.get('absoluteBoundingBox')
        if not box:
            box = node.get('absoluteRenderBounds')
        return box

    @staticmethod
    def _get_rect(box: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
        """获取节点的矩形信息 (x, y, width, height)"""
        if not box:
            return None

        width = box.get("width", 0)
        height = box.get("height", 0)
        # 如果宽度或高度为 0 或负数，认为无效
        if width <= 0 or height <= 0:
            return None
        return (
            box.get("x", 0),
            box.get("y", 0),
            width,
            height
        )

    def is_fully_overlapped(self) -> bool:
        """
        判断两个节点宽高是否100%完整重叠
        Returns:
            bool: 如果两个节点的边界框完全相同（x, y, width, height都相同），返回True
        """
        if not self._parent_rect or not self._node_rect:
            return False
        
        x1, y1, w1, h1 = self._node_rect
        x2, y2, w2, h2 = self._parent_rect
        
        # 判断是否完全重叠：位置和尺寸都完全相同
        return abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01 and \
               abs(w1 - w2) < 0.01 and abs(h1 - h2) < 0.01

    def is_fully_contained(self) -> bool:
        """
        判断检测节点是否完全包含在父节点内，并且有发生重叠
        Returns:
            bool: 如果检测节点的所有边界都在父节点内，返回True
        """
        rect1 = self._node_rect
        rect2 = self._parent_rect
        
        if not rect1 or not rect2:
            return False
        
        x1, y1, w1, h1 = rect1
        x2, y2, w2, h2 = rect2
        
        # 计算节点的边界
        node_left = x1
        node_right = x1 + w1
        node_top = y1
        node_bottom = y1 + h1
        
        parent_left = x2
        parent_right = x2 + w2
        parent_top = y2
        parent_bottom = y2 + h2
        
        # 判断是否完全包含：节点的所有边界都在父节点内
        return (node_left >= parent_left and node_right <= parent_right and
                node_top >= parent_top and node_bottom <= parent_bottom)

    def is_partially_overlapped(self) -> Tuple[bool, common_model.OverlapInfo]:
        """
        判断检测节点和父节点有重叠，但是没有完全包含，有溢出部分，并且能检测哪个方向溢出
        
        Returns:
            Tuple[bool, Dict[str, bool]]: 
                - 第一个值：是否有重叠但不完全包含
                - 第二个值：溢出方向字典，包含 'top', 'bottom', 'left', 'right' 四个方向的溢出情况
        """
        rect1 = self._node_rect
        rect2 = self._parent_rect

        overlap_info = common_model.OverlapInfo(top=False, bottom=False, left=False, right=False)
        if not rect1 or not rect2:
            return False,  overlap_info
        
        x1, y1, w1, h1 = rect1
        x2, y2, w2, h2 = rect2
        
        # 计算节点的边界
        node_left = x1
        node_right = x1 + w1
        node_top = y1
        node_bottom = y1 + h1
        
        parent_left = x2
        parent_right = x2 + w2
        parent_top = y2
        parent_bottom = y2 + h2
        
        # 判断是否有重叠
        has_overlap = not (node_right <= parent_left or node_left >= parent_right or
                          node_bottom <= parent_top or node_top >= parent_bottom)
        
        if not has_overlap:
            return False, overlap_info
        
        # 判断是否完全包含
        is_fully_contained = (node_left >= parent_left and node_right <= parent_right and
                             node_top >= parent_top and node_bottom <= parent_bottom)
        
        # 如果有重叠但不完全包含，则检测溢出方向
        if not is_fully_contained:
            overlap_info.top = node_top < parent_top            # 向上溢出
            overlap_info.bottom = node_bottom > parent_bottom   # 向下溢出
            overlap_info.left = node_left < parent_left         # 向左溢出
            overlap_info.right = node_right > parent_right      # 向右溢出
            return True, overlap_info
        
        return False, overlap_info
