
from .base import AbstractComponent, AbstractComponentProps
from mdap_u2c.enums import dsl_enum


class BrComponentProps(AbstractComponentProps, kw_only=True, forbid_unknown_fields=True):
    """换行组件属性"""


class BrComponent(AbstractComponent, kw_only=True, forbid_unknown_fields=True):
    """换行组件"""
    type: dsl_enum.ComponentType = dsl_enum.ComponentType.BR.value
    props: BrComponentProps
