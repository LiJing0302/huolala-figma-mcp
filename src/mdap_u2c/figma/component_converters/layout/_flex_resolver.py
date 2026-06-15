"""
flex 布局属性转化
"""
from typing import Dict, Any, Optional

from mdap_u2c.models import dsl_model
from mdap_u2c.enums import dsl_enum


class FlexResolver:
    """ Flex 布局属性识别(注意：容器和子元素识别都统一在该类处理) """
    # primaryAxisAlignItems
    _justify_content = {
        "MIN": dsl_enum.JustifyContent.FLEX_START,
        "CENTER": dsl_enum.JustifyContent.CENTER,
        "MAX": dsl_enum.JustifyContent.FLEX_END,
        "SPACE_BETWEEN": dsl_enum.JustifyContent.SPACE_BETWEEN
    }

    # counterAxisAlignItems（单行/列-未换行时）
    _align_items = {
        "MIN": dsl_enum.AlignItems.FLEX_START,
        "CENTER": dsl_enum.AlignItems.CENTER,
        "MAX": dsl_enum.AlignItems.FLEX_END,
        "BASELINE": dsl_enum.AlignItems.BASELINE
    }

    # counterAxisAlignContent（多行/列-存在换行时）
    _align_content = {
        "AUTO": dsl_enum.AlignContent.STRETCH,
        "SPACE_BETWEEN": dsl_enum.AlignContent.SPACE_BETWEEN
    }

    # layoutAlign
    _align_self = {
        "STRETCH": "stretch",
        "MIN": "flex-start",
        "CENTER": "center",
        "MAX": "flex-end",
    }

    def __init__(self, node: Dict[str, Any], display_mode: Optional[dsl_enum.DisplayMode], parent_display_mode: Optional[dsl_enum.DisplayMode]):
        self._node = node
        self._flexbox = dsl_model.Flexbox()
        self._self_is_flex = display_mode == dsl_enum.DisplayMode.FLEX
        self._parent_is_flex = parent_display_mode == dsl_enum.DisplayMode.FLEX

    def get(self, layout_mode: str) -> Optional[dsl_model.Flexbox]:
        if self._self_is_flex:
            self._handler_self_flex_container(layout_mode)

        if self._parent_is_flex:
            self._handler_flex_child_element()

        if self._flexbox.all_none():
            return None

        return self._flexbox

    def _handler_self_flex_container(self, layout_mode: str):
        """处理自身为 flex 布局相关属性"""
        if layout_mode == "HORIZONTAL":
            self._flexbox.direction = dsl_enum.FlexDirection.ROW
        else:
            self._flexbox.direction = dsl_enum.FlexDirection.COLUMN
        justify_content = self._node.get("primaryAxisAlignItems", "MIN")
        self._flexbox.justify_content = self._justify_content.get(justify_content, dsl_enum.JustifyContent.FLEX_START)

        warp = self._node.get("layoutWrap", None)
        align_items = self._node.get("counterAxisAlignItems", "MIN")
        if warp == "WRAP":
            self._flexbox.wrap = dsl_enum.FlexWrap.WRAP
            self._flexbox.align_content = self._align_items.get(align_items, dsl_enum.JustifyContent.FLEX_START)
        else:
            self._flexbox.wrap = dsl_enum.FlexWrap.NOWRAP
            self._flexbox.align_items = self._align_items.get(align_items, dsl_enum.JustifyContent.FLEX_START)

        self._resolve_gap(warp)

    def _handler_flex_child_element(self):
        """处理父容器为 flex 布局相关属性"""
        grow = self._node.get("layoutGrow", 0)
        horizontal = self._node.get("layoutSizingHorizontal")
        vertical = self._node.get("layoutSizingVertical")
        if grow == 1:
            if horizontal == "FILL" or vertical == "FILL":
                self._flexbox.flex_grow = grow

        align = self._node.get("layoutAlign")
        align_self = self._align_self.get(align)
        if align_self:
            self._flexbox.align_self = align_self

    def _resolve_gap(self, warp: str):
        """计算 gap 值"""
        if self._flexbox.justify_content == dsl_enum.JustifyContent.SPACE_BETWEEN:
            return

        if self._flexbox.direction == dsl_enum.FlexDirection.COLUMN:
            self._flexbox.row_gap = self._node.get("itemSpacing", 0)
        else:
            if warp == "NO_WRAP":
                self._flexbox.column_gap = self._node.get('itemSpacing', 0)
            else:
                self._flexbox.column_gap = self._node.get("itemSpacing", 0)
                self._flexbox.row_gap = self._node.get("counterAxisSpacing", 0)


