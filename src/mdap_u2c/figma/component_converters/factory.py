"""
组件工厂
"""
from typing import Dict, Any, Optional

from mdap_u2c.models import dsl_model, common_model
from mdap_u2c.enums import dsl_enum
from .type_resolver import TypeResolver
from .coordinate_resolver import CoordinateResolver
from .rich_text_resolver import RichTextResolver
from .style import StyleConverter
from mdap_u2c.utils.generator_utils import GeneratorUtils
from mdap_u2c.utils import StyleValueUtils
from .layout import LayoutConverter


class ComponentFactory:
    """组件工厂 - 统一创建组件的入口"""

    def __init__(self):
        self._style_converter = StyleConverter()

    def of(
            self,
            node: Dict[str, Any],
            coordinate: CoordinateResolver,
            node_id_map: Dict[str, Dict[str, Any]],
            component_id: Optional[str] = None,
            parent_component: Optional[dsl_model.AbstractComponent] = None
    ) -> dsl_model.AbstractComponent | None:
        """
        创建组件
        :param node:  figma节点对象
        :param coordinate: 坐标解析对象
        :param component_id: 组件id(可选，默认自动生成)
        :param parent_component: 父组件(可选，默认无)
        :param node_id_map: figma组件id和对应关系
        :return: 组件对象或None
        """
        if component_id is None:
            component_id = GeneratorUtils.get_instance().generate_component_id()

        parent_node = None
        if parent_component:
            parent_node = node_id_map.get(parent_component.figma.node_id, None)
        component_type = TypeResolver(parent_node=parent_node, node=node, parent_component=parent_component).get_type()
        if component_type is None:
            sub_style = self._style_converter.set_data(dsl_enum.ComponentType.CONTAINER, node).get_common_style()
            self._style_converter.style_merge(parent_component.style, sub_style)
            return None

        coordinate.set_check_node(node, component_type)
        node_rect = coordinate.get_position()
        figma_info = self._build_figma_info(node, node_rect)
        layout = LayoutConverter(node, node_rect, parent_component).to_layout()
        common_style = self._style_converter.set_data(component_type, node).get_common_style()

        if component_type == dsl_enum.ComponentType.TEXT:
            if self._is_rich_text(node):
                return RichTextResolver.create_component(
                    node=node,
                    layout=layout,
                    style=common_style,
                    component_id=component_id,
                    parent_component=parent_component,
                    figma_info=figma_info
                )

            # 普通文本组件
            return dsl_model.TextComponent.create_with_node(
                node=node,
                layout=layout,
                style=common_style,
                component_id=component_id,
                parent_component=parent_component,
                figma_info=figma_info
            )

        elif component_type == dsl_enum.ComponentType.IMAGE:
            return dsl_model.ImageComponent.create_with_node(
                node=node,
                layout=layout,
                style=common_style,
                component_id=component_id,
                parent_component=parent_component,
                figma_info=figma_info
            )

        else:
            return dsl_model.ContainerComponent.create_container(
                node=node,
                layout=layout,
                style=common_style,
                component_id=component_id,
                parent_component=parent_component,
                figma_info=figma_info
            )

    @staticmethod
    def _build_figma_info(node: Dict[str, Any], node_rect: common_model.Rect):
        """构建 Figma 元数据"""
        bounding_box_size = None
        render_bounds_size = None
        bounding = node.get('absoluteBoundingBox')
        render = node.get('absoluteRenderBounds')

        render_bounds_position = None
        bounding_box_position = None
        if bounding:
            bounding_box_size = dsl_model.Size(
                width=StyleValueUtils.format_number(bounding.get("width", 0)),
                height=StyleValueUtils.format_number(bounding.get("height", 0))
            )
            bounding_box_position = dsl_model.Point(
                x=StyleValueUtils.format_number(bounding.get("x", 0)),
                y=StyleValueUtils.format_number(bounding.get("y", 0))
            )
        if render:
            render_bounds_size = dsl_model.Size(
                width=StyleValueUtils.format_number(render.get("width", 0)),
                height=StyleValueUtils.format_number(render.get("height", 0))
            )
            render_bounds_position = dsl_model.Point(
                x=StyleValueUtils.format_number(render.get("x", 0)),
                y=StyleValueUtils.format_number(render.get("y", 0))
            )

        return dsl_model.FigmaInfo(
            node_id=node.get("id", ""),
            name=node.get("name", ""),
            type=node.get("type", "FRAME"),
            width=node_rect.width,
            height=node_rect.height,
            font_post_script_name=node.get("style", {}).get("fontPostScriptName", None),
            bounding_box_size=bounding_box_size,
            render_bounds_size=render_bounds_size,
            render_bounds_position=render_bounds_position,
            bounding_box_position=bounding_box_position
        )

    @staticmethod
    def _is_rich_text(node: Dict[str, Any]):
        """
        判断节点是否为富文本
        富文本包括：
        1. 混合样式文本（有styleOverrideTable，即文本中有不同的样式，如颜色、字体等）
        2. 列表文本（有序列表或无序列表，即lineTypes中包含ORDERED或UNORDERED）

        :param node: Figma API 返回的节点信息
        :return: True 表示富文本，False 表示普通文本
        """
        has_mixed_styles = bool(node.get("styleOverrideTable", {}))
        line_types = node.get("lineTypes", [])
        line_indentations = node.get("lineIndentations", [])
        # 检查是否有列表类型（排除空数组和只包含NONE/none的情况）
        has_list = bool(line_types) and any(lt not in ("NONE", "none") for lt in line_types)

        return has_mixed_styles or has_list or len(line_indentations) > 1

