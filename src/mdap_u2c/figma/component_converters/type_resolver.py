"""
组件类型自动解析
负责将 Figma 节点类型映射为 DSL 组件类型
"""
from typing import Dict, Any, Set, Optional

from mdap_u2c.enums import dsl_enum
from mdap_u2c.enums import figma_enum
from mdap_u2c.figma.check import FigmaCheckUtils
from mdap_u2c.figma.check.image_merge_check import ImageMergeCheck
from mdap_u2c.models import dsl_model
from mdap_u2c.utils import StyleValueUtils
from mdap_u2c.figma.check import NodeOverlapCheck


class TypeResolver:
    """组件类型判断"""
    _container_types: Set[str] = {
        figma_enum.FigmaNodeType.InstanceNode,
        figma_enum.FigmaNodeType.FrameNode,
        figma_enum.FigmaNodeType.ComponentNode,
        figma_enum.FigmaNodeType.GroupNode,
        figma_enum.FigmaNodeType.ComponentSetNode,
        figma_enum.FigmaNodeType.BooleanOperationNode,
        figma_enum.FigmaNodeType.RectangleNode,  # 矩形节点较特殊，需要使用view实现，所以可以导出容器类型
    }

    def __init__(self, node: Dict[str, Any], parent_node: Dict[str, Any] = None, parent_component: Optional[dsl_model.AbstractComponent] = None):
        self._node = node
        self._node_type = node.get("type", None)
        self._parent_component = parent_component
        self._absolute_render_bounds = node.get("absoluteRenderBounds", None)
        self._absolute_bounding_box = node.get("absoluteBoundingBox", None)
        self._parent_node = parent_node
        self._overlap_check = NodeOverlapCheck.get_instance().set_node(node, parent_node)

    def get_type(self) -> dsl_enum.ComponentType | None:
        """
        根据节点类型判断组件类型
        Text:
        1. 文本节点

        Image:
        1. 有图片填充
        2. 有旋转(旋转的角度不是0、90、/180、-90、-180)需要导图
        3. 未知所有判断都当图片对待

        Container:
        1. 包含在容器类型_container_types
        2. RectangleNode类型
        3. VectorNodel类型且fillOverrideTable为空
        4. [line]旋转角度在垂直和水平特殊位置
        5. [ellipse]如果是原型则转换容器

        :return: 组件类型
        """
        if self._node_type is None:
            return dsl_enum.ComponentType.IMAGE

        if self._node_type == figma_enum.FigmaNodeType.TextNode:
            return dsl_enum.ComponentType.TEXT

        if FigmaCheckUtils.has_image_fill(self._node):
            return dsl_enum.ComponentType.IMAGE

        # 非垂直水平旋转，导出图片
        if FigmaCheckUtils.is_vertical_horizontal_rotation(self._node.get("rotation", None)) is False:
            return dsl_enum.ComponentType.IMAGE

        # 检测节点样式是否满足合并至父容器中(如果满足，则会忽略该节点，把该节点的样式追加到父容器上)
        if self._is_merge_node_style_to_parent_node():
            return None

        # 矢量节点检测
        component_type = self._vector_node_check()
        if component_type is not None:
            return component_type

        component_type = self._line_node_check()
        if component_type is not None:
            return component_type

        component_type = self._ellipse_node_check()
        if component_type is not None:
            return component_type

        component_type = self._boolean_operation_node_check()
        if component_type is not None:
            return component_type

        # 图片合并检测（图标和装饰元素识别）
        if ImageMergeCheck.check(self._node) is True:
            return dsl_enum.ComponentType.IMAGE

        if self._node_type in self._container_types:
            return dsl_enum.ComponentType.CONTAINER

        # 以上都处理不了的类型，直接以图片导出
        return dsl_enum.ComponentType.IMAGE

    def _vector_node_check(self) -> Optional[dsl_enum.ComponentType]:
        """VectorNode check"""
        if self._node_type != figma_enum.FigmaNodeType.VectorNode:
            return None
        return None

    def _line_node_check(self) -> Optional[dsl_enum.ComponentType]:
        """Line 节点处理(能进入这里，表示旋转角度都是垂直的)"""
        if self._node_type != figma_enum.FigmaNodeType.LineNode:
            return None

        return dsl_enum.ComponentType.CONTAINER

    def _ellipse_node_check(self) -> Optional[dsl_enum.ComponentType]:
        if self._node_type != figma_enum.FigmaNodeType.EllipseNode:
            return None

        absolute_render_bounds = self._node.get("absoluteRenderBounds")
        if absolute_render_bounds is None:
            return None

        # 渲染的宽和高一样，是原型，可以使用容器来实现
        if absolute_render_bounds.get("width") == absolute_render_bounds.get("height"):
            return dsl_enum.ComponentType.CONTAINER

    def _boolean_operation_node_check(self) -> Optional[dsl_enum.ComponentType]:
        """
        BOOLEAN_OPERATION 节点检查
        BOOLEAN_OPERATION 通常用于创建复杂图标，应该优先考虑导出为图片
        判断逻辑：
        1. 如果包含子节点（通常是矢量元素），倾向于导出为图片（图标）
        2. 如果节点较小（可能是图标），导出为图片
        3. 否则导出为容器
        """
        if self._node_type != figma_enum.FigmaNodeType.BooleanOperationNode:
            return None
        
        # 检查是否有子节点（布尔运算通常包含多个形状子节点）
        children = self._node.get("children", [])
        if children:
            vector_count = sum(1 for child in children if child.get("type") == figma_enum.FigmaNodeType.VectorNode)
            if vector_count > 0:
                return dsl_enum.ComponentType.IMAGE
        
        # 检查节点大小
        absolute_render_bounds = self._node.get("absoluteRenderBounds")
        if absolute_render_bounds:
            width = absolute_render_bounds.get("width", 0)
            height = absolute_render_bounds.get("height", 0)
            # 如果节点较小（宽高都小于 200px），可能是图标，导出为图片
            if width > 0 and height > 0 and width < 60 and height < 60:
                return dsl_enum.ComponentType.IMAGE
        
        # 默认导出为容器
        return dsl_enum.ComponentType.CONTAINER

    def _is_merge_node_style_to_parent_node(self) -> bool:
        """判断是否需要把样式合并到父容器中"""
        if self._absolute_render_bounds is None:
            return False

        need_types = [
            figma_enum.FigmaNodeType.RectangleNode,
            figma_enum.FigmaNodeType.EllipseNode
        ]
        if self._node_type not in need_types or self._parent_component is None:
            return False

        parent_size = self._parent_component.layout.size
        width = StyleValueUtils.format_number(self._absolute_render_bounds.get("width", 0))
        height = StyleValueUtils.format_number(self._absolute_render_bounds.get("height", 0))
        if self._parent_node and self._parent_node.get("type", None) == figma_enum.FigmaNodeType.GroupNode:
            children = self._parent_node.get("children", [])
            if len(children) == 2:
                text_node_num = 0
                round_node_num = 0
                for child in children:
                    child_type = child.get("type", None)
                    if child_type in need_types:
                        text_node_num += 1
                    elif child_type == figma_enum.FigmaNodeType.TextNode:
                        round_node_num += 1

                max_poor = 4
                if text_node_num == 1 and round_node_num == 1 and self._overlap_check.is_fully_contained():
                    width_poor = parent_size.width - width
                    height_poor = parent_size.height - height
                    if -max_poor < width_poor < max_poor and -max_poor < height_poor < max_poor:
                        self._parent_component.layout.size.width = width
                        self._parent_component.layout.size.height = height
                        return True

        if self._node.get("opacity", 1) != 1:
            return False

        return self._overlap_check.is_fully_overlapped()

