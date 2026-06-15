
from typing import Optional, Dict, Any

from .base import AbstractComponent, AbstractComponentProps
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model


class TextComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """文本组件属性"""
    text: str
    placeholder: Optional[str] = None


class TextComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """文本组件"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.TEXT.value
    props: TextComponentProps

    @classmethod
    def create_with_node(
            cls,
            node: Dict[str, Any],
            layout: dsl_model.Layout,
            style: dsl_model.Style,
            component_id: str,
            figma_info: dsl_model.FigmaInfo,
            parent_component: Optional[dsl_model.AbstractComponent] = None,
    ) -> 'TextComponent':
        from mdap_u2c.figma.component_converters.style import TextStyleConverter
        return cls(
            id=component_id,
            figma=figma_info,
            layout=layout,
            parent_id=parent_component.id if parent_component else None,
            style=TextStyleConverter.get_style_with_node(style, node, parent_component),
            props=cls._convert_props(node)
        )

    @classmethod
    def _convert_props(cls, node: Dict[str, Any]) -> TextComponentProps:
        """转换文本组件属性"""
        return TextComponentProps(
            text=node.get("characters", ""),
            placeholder=node.get("placeholderText"),
            class_name=None
        )



