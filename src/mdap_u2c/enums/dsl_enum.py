"""
DSL 枚举定义

与 DSL 结构相关的枚举类型，包括：
- 组件类型和状态
- 布局和定位
- 样式和效果
- 文字排版
- 交互相关
"""

from enum import Enum


# ============================================================================
# 组件相关
# ============================================================================
class ComponentType(str, Enum):
    """组件类型（语义化）"""
    # 容器
    CONTAINER = "container"             # 容器
    CONTAINER_RICH = "container_rich"   # 富文本容器
    BR = "br"                           # 换行

    # 基础组件
    TEXT = "text"                       # 文本
    IMAGE = "image"                     # 图片
    
    # 列表组件
    ORDERED_LIST = "ordered_list"       # 有序列表
    UNORDERED_LIST = "unordered_list"   # 无序列表
    LIST_ITEM = "list_item"             # 列表项


# ============================================================================
# 布局相关
# ============================================================================
class DisplayMode(str, Enum):
    """布局显示模式"""
    FLEX = "flex"
    GRID = "grid"
    BLOCK = "block"
    INLINE = "inline"
    INLINE_BLOCK = "inline-block"
    INLINE_FLEX = "inline-flex"
    NONE = "none"


class PositionType(str, Enum):
    """定位类型"""
    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    FIXED = "fixed"


class FlexDirection(str, Enum):
    """Flex 方向"""
    ROW = "row"
    COLUMN = "column"
    ROW_REVERSE = "row-reverse"
    COLUMN_REVERSE = "column-reverse"


class FlexWrap(str, Enum):
    """Flex 换行"""
    NOWRAP = "nowrap"
    WRAP = "wrap"
    WRAP_REVERSE = "wrap-reverse"


class AlignItems(str, Enum):
    """对齐方式（交叉轴）"""
    FLEX_START = "flex-start"
    CENTER = "center"
    FLEX_END = "flex-end"
    STRETCH = "stretch"
    BASELINE = "baseline"


class JustifyItems(str, Enum):
    """对齐方式（主轴）"""
    START = "start"
    END = "end"
    CENTER = "center"


class JustifyContent(str, Enum):
    """内容分布（主轴）"""
    FLEX_START = "flex-start"
    CENTER = "center"
    FLEX_END = "flex-end"
    SPACE_BETWEEN = "space-between"
    SPACE_AROUND = "space-around"
    SPACE_EVENLY = "space-evenly"


class AlignContent(str, Enum):
    """内容分布（交叉轴）"""
    STRETCH = "stretch"   # 默认值
    FLEX_START = "flex-start"
    FLEX_END = "flex-end"
    CENTER = "center"
    SPACE_BETWEEN = "space-between"
    SPACE_AROUND = "space-around"
    SPACE_EVENLY = "space-evenly"


class StyleUnit(str, Enum):
    """样式单位"""
    PX = "px"
    PERCENT = "%"
    EM = "em"
    REM = "rem"
    VW = "vw"
    VH = "vh"
    AUTO = "auto"
    INHERIT = "inherit"
    INITIAL = "initial"


