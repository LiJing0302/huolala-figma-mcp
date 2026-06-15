from typing import Optional

from .base import AbstractComponent, AbstractComponentProps
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model


class ListComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """列表组件属性"""
    start_index: Optional[int] = None   # 有序列表起始序号（从1开始）


class ListComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """列表组件（有序或无序）"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.ORDERED_LIST.value
    props: ListComponentProps

    @classmethod
    def create_ordered_list(
        cls,
        component_id: str,
        parent_id: Optional[str] = None,
        start_index: Optional[int] = None,
        style: Optional[dsl_model.Style] = None
    ) -> 'ListComponent':
        """创建有序列表"""
        return cls(
            id=component_id,
            parent_id=parent_id,
            style=cls._get_style(style),
            type=dsl_enum.ComponentType.ORDERED_LIST.value,
            props=ListComponentProps(start_index=start_index or 1),
            children=[]
        )

    @classmethod
    def create_unordered_list(
        cls,
        component_id: str,
        parent_id: Optional[str] = None,
        style: Optional[dsl_model.Style] = None
    ) -> 'ListComponent':
        """创建无序列表"""
        return cls(
            id=component_id,
            parent_id=parent_id,
            style=cls._get_style(style),
            type=dsl_enum.ComponentType.UNORDERED_LIST.value,
            props=ListComponentProps(start_index=None),
            children=[]
        )

    @classmethod
    def _get_style(cls, style: Optional[dsl_model.Style] = None) -> dsl_model.Style:
        style = style or dsl_model.Style()

        style.padding_inline_start = "16px"
        style.width = "initial"
        return style


class ListItemComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """列表项组件属性"""
    level: int = 0  # 嵌套级别（0表示顶级）


class ListItemComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """列表项组件"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.LIST_ITEM.value
    props: ListItemComponentProps

    @classmethod
    def create(
        cls,
        component_id: str,
        parent_id: Optional[str] = None,
        level: int = 0,
        style: Optional[dsl_model.Style] = None
    ) -> 'ListItemComponent':
        """创建列表项"""
        return cls(
            id=component_id,
            parent_id=parent_id,
            style=style or dsl_model.Style(),
            props=ListItemComponentProps(level=level),
            children=[]
        )

