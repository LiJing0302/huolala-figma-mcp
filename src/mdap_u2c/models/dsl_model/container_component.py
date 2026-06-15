from typing import Optional, Dict, Any

from .base import AbstractComponent, AbstractComponentProps
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model


class ContainerComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """容器组件属性"""
    scrollable: Optional[bool] = None       # 是否支持滚动
    scroll_direction: Optional[str] = None  # 滚动方向
    clickable: Optional[bool] = None        # 是否支持点击


class ContainerComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """容器组件"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.CONTAINER.value
    props: ContainerComponentProps

    @classmethod
    def create_with_custom(cls,
                           component_id: str,
                           parent_id: str,
                           style: dsl_model.Style,
                           props: ContainerComponentProps,
                           figma_info: Optional[dsl_model.FigmaInfo] = None,
                           layout: Optional[dsl_model.Layout] = None):
        return cls(
            id=component_id,
            parent_id=parent_id,
            figma=figma_info,
            layout=layout,
            style=style,
            props=props
        )

    @classmethod
    def create_container(
            cls,
            node: Dict[str, Any],
            layout: dsl_model.Layout,
            style: dsl_model.Style,
            component_id: str,
            figma_info: dsl_model.FigmaInfo,
            parent_component: Optional[dsl_model.AbstractComponent] = None,
    ) -> 'ContainerComponent':
        return cls(
            id=component_id,
            parent_id=parent_component.id if parent_component else None,
            figma=figma_info,
            layout=layout,
            style=cls._resolve_style(style, node),
            props=cls._convert_props(node)
        )

    @classmethod
    def create_rich_container(
            cls,
            node: Dict[str, Any],
            layout: dsl_model.Layout,
            style: dsl_model.Style,
            component_id: str,
            figma_info: dsl_model.FigmaInfo,
            parent_component: Optional[dsl_model.AbstractComponent] = None,
    ) -> 'ContainerComponent':
        return cls(
            id=component_id,
            parent_id=parent_component.id if parent_component else None,
            figma=figma_info,
            layout=layout,
            type=dsl_enum.ComponentType.CONTAINER_RICH.value,
            style=cls._resolve_style(style, node),
            props=cls._convert_props(node)
        )

    @classmethod
    def _convert_props(cls, node: Dict[str, Any]) -> ContainerComponentProps:
        """转换容器组件属性"""
        return ContainerComponentProps(
            scrollable=None,
            scroll_direction=None,
            clickable=None,
            class_name=None
        )

    @classmethod
    def _resolve_style(cls, style: dsl_model.Style, node: Dict[str, Any]) -> dsl_model.Style:
        """样式加工处理(属于组件特有样式)"""
        return style
