"""
布局转换器
负责将 Figma 节点的布局信息转换为 DSL Layout 对象
"""
from typing import Dict, Any, Optional

import msgspec

from mdap_u2c.models import dsl_model
from mdap_u2c.models import common_model
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import StyleValueUtils
from ._flex_resolver import FlexResolver
from ._grid_resolver import GridResolver


class _LayoutInfo(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    display_model: Optional[dsl_enum.DisplayMode] = dsl_enum.DisplayMode.BLOCK
    flexbox: Optional[dsl_model.Flexbox] = None
    gridbox: Optional[dsl_model.Gridbox] = None


class LayoutConverter:
    def __init__(self, node: Dict[str, Any], rect: common_model.Rect, parent_component: Optional[dsl_model.AbstractComponent]):
        self._node = node
        self._parent_component = parent_component

        position_type = dsl_enum.PositionType.FIXED
        if self._parent_component is None:
            position_type = None

        self._layout = dsl_model.Layout(size=self._resolve_size(rect), position=dsl_model.Position(x=rect.x, y=rect.y, type=position_type))

    """布局转换器"""
    def to_layout(self) -> dsl_model.Layout:
        self._layout.padding = self._resolve_padding()

        layout_info = self._resolve_layout_info()
        self._layout.display = layout_info.display_model
        self._layout.flexbox = layout_info.flexbox
        self._layout.gridbox = layout_info.gridbox

        return self._layout

    def _resolve_layout_info(self) -> _LayoutInfo:
        """布局模式处理"""
        result = _LayoutInfo()
        layout_mode = self._node.get("layoutMode", None)
        if layout_mode == "GRID":
            result.display_model = dsl_enum.DisplayMode.GRID

        if layout_mode in ["HORIZONTAL", "VERTICAL"]:
            result.display_model = dsl_enum.DisplayMode.FLEX

        parent_display_mode = self._get_parent_display_mode()
        result.gridbox = GridResolver(self._node, result.display_model, parent_display_mode).get()
        result.flexbox = FlexResolver(self._node, result.display_model, parent_display_mode).get(layout_mode)

        return result

    def _resolve_padding(self) -> Optional[dsl_model.Spacing]:
        """内边距处理"""
        padding_left = self._node.get("paddingLeft", 0)
        padding_right = self._node.get("paddingRight", 0)
        padding_top = self._node.get("paddingTop", 0)
        padding_bottom = self._node.get("paddingBottom", 0)

        # 如果全是 0，返回 None
        if padding_left == padding_right == padding_top == padding_bottom == 0:
            return None

        return dsl_model.Spacing(
            top=StyleValueUtils.format_number(padding_top),
            right=StyleValueUtils.format_number(padding_right),
            bottom=StyleValueUtils.format_number(padding_bottom),
            left=StyleValueUtils.format_number(padding_left)
        )

    def _get_parent_display_mode(self) -> Optional[dsl_enum.DisplayMode]:
        return self._parent_component.layout.display if self._parent_component else None

    def _resolve_size(self, rect: common_model.Rect) -> dsl_model.Size:
        size = dsl_model.Size(
            width=StyleValueUtils.format_number(rect.width),
            height=StyleValueUtils.format_number(rect.height),
            min_width=StyleValueUtils.format_number(self._node.get("minWidth")),
            min_height=StyleValueUtils.format_number(self._node.get("minHeight")),
            max_width=StyleValueUtils.format_number(self._node.get("maxWidth")),
            max_height=StyleValueUtils.format_number(self._node.get("maxHeight"))
        )

        return size




