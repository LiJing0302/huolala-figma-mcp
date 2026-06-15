
from typing import Optional, Dict, Any

from .base import AbstractComponent, AbstractComponentProps
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model


class ImageComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """图片组件属性"""
    src: str
    alt: Optional[str] = None


class ImageComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """图片组件"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.IMAGE.value
    props: ImageComponentProps

    @classmethod
    def create_with_node(
            cls,
            node: Dict[str, Any],
            layout: dsl_model.Layout,
            style: dsl_model.Style,
            component_id: str,
            figma_info: dsl_model.FigmaInfo,
            parent_component: Optional[dsl_model.AbstractComponent] = None,
    ) -> 'ImageComponent':
        """从 Figma 节点创建图片组件"""
        return cls(
            id=component_id,
            parent_id=parent_component.id if parent_component else None,
            figma=figma_info,
            layout=layout,
            style=cls._resolve_style(style, node),
            props=cls._convert_props(node)
        )

    @classmethod
    def _convert_props(cls, node: Dict[str, Any]) -> ImageComponentProps:
        """转换图片组件属性"""
        return ImageComponentProps(
            src="",                 # 打包时替换
            class_name=None,        # 语义化类名(dsl加工层处理)
            alt=node.get("name", "image")
        )

    @classmethod
    def _resolve_style(cls, style: dsl_model.Style, node: Dict[str, Any]) -> dsl_model.Style:
        """样式加工处理(属于组件特有样式)"""
        return style

