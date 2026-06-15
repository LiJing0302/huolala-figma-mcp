"""
Grid 布局属性转化
"""
from typing import Dict, Any, Optional
from mdap_u2c.models import dsl_model
from mdap_u2c.enums import dsl_enum


class GridResolver:
    """ Grid 布局属性识别 """
    def __init__(self, node: Dict[str, Any], display_mode: Optional[dsl_enum.DisplayMode], parent_display_mode: Optional[dsl_enum.DisplayMode]):
        self._node = node
        gridbox = dsl_model.Gridbox()
        self._self_is_grid = display_mode == dsl_enum.DisplayMode.GRID
        self._parent_is_grid = parent_display_mode == dsl_enum.DisplayMode.GRID
        self._gridbox = gridbox

    def get(self) -> Optional[dsl_model.Gridbox]:
        if self._self_is_grid:
            self._handler_self_grid_container()

        if self._parent_is_grid:
            self._handler_grid_child_element()

        if self._gridbox.all_none():
            return None

        return self._gridbox

    def _handler_self_grid_container(self):
        self._gridbox.grid_template_rows = self._node.get("gridRowsSizing")
        self._gridbox.grid_template_columns = self._node.get("gridColumnsSizing")
        self._gridbox.row_gap = self._node.get('gridRowGap', 0)
        self._gridbox.column_gap = self._node.get('gridColumnGap', 0)

    def _handler_grid_child_element(self):
        """处理父容器为 flex 布局相关属性"""
        row_span = self._node.get('gridRowSpan')
        column_span = self._node.get('gridColumnSpan')
        row_index = self._node.get('gridRowAnchorIndex')
        column_index = self._node.get('gridColumnAnchorIndex')

        self._gridbox.grid_row = f"{row_index + 1} / span {row_span}"
        self._gridbox.grid_column = f"{column_index + 1} / span {column_span}"


