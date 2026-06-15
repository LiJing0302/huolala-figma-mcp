"""
Figma节点坐标系计算
"""
from typing import Dict, Any
from mdap_u2c.models import common_model
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import StyleValueUtils


class CoordinateResolver:
    """Figma节点坐标系计算"""
    _root_node_id: str = ""                 # 根节点id(此处为figma的节点id)
    _page_size: common_model.Rect           # 页面画布实际大小(坐标系构建对象)
    _check_node: Dict[str, Any]             # 需要检测的目标节点
    _component_type: dsl_enum.ComponentType # 组件类型
    _root_node_size: common_model.Rect      # 页面实际坐标尺寸(figma坐标系)

    def __init__(self, page_node: Dict[str, Any]):
        absoluteBoundingBox = page_node.get('absoluteBoundingBox')

        self._root_node_id = page_node.get("id", "")
        self._page_size = common_model.Rect(
            x=0, y=0,
            width=StyleValueUtils.format_number(absoluteBoundingBox.get("width", 0)),
            height=StyleValueUtils.format_number(absoluteBoundingBox.get("height", 0))
        )
        self._root_node_size = common_model.Rect(
            x=StyleValueUtils.format_number(absoluteBoundingBox.get("x", 0)),
            y=StyleValueUtils.format_number(absoluteBoundingBox.get("y", 0)),
            width=StyleValueUtils.format_number(absoluteBoundingBox.get("width", 0)),
            height=StyleValueUtils.format_number(absoluteBoundingBox.get("height", 0))
        )

    def get_page_size(self) -> common_model.Rect:
        """获取页面大小"""
        return self._page_size

    def set_check_node(self, node: Dict[str, Any], component_type: dsl_enum.ComponentType):
        """设置检查节点"""
        self._check_node = node
        self._component_type = component_type
        return self


    def get_position(self) -> common_model.Rect:
        """获取节点位置"""
        node = self._get_check_node()
        box = node.get('absoluteBoundingBox')
        # 图片节点必须使用渲染矩阵计算
        if self._component_type == dsl_enum.ComponentType.IMAGE:
            box = node.get("absoluteRenderBounds")
            if not box:
                box = node.get('absoluteBoundingBox')
        elif box.get("width", 0) == 0:
            box = node.get("absoluteRenderBounds")
            if not box:
                box = node.get('absoluteBoundingBox')

        x = box.get("x", 0)
        y = box.get("y", 0)
        return common_model.Rect(
            x=StyleValueUtils.format_number(x - self._root_node_size.x),
            y=StyleValueUtils.format_number(y - self._root_node_size.y),
            width=StyleValueUtils.format_number(box.get("width", 0)),
            height=StyleValueUtils.format_number(box.get("height", 0))
        )

    def _get_check_node(self):
        if not self._check_node:
            raise ValueError("未设置检查节点")

        return self._check_node


