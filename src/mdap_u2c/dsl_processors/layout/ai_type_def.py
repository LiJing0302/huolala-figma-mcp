from enum import Enum,IntEnum
class AI_TYPE(Enum):
    RED_POINT = 0
    BUBBLE = 1
    BOTTOM_BAR = 2
    RED_POINT_BUBBLE_CONTAINER = 3
    RADIO = 4
    CHECKBOX = 5
    BUTTON = 6
    INPUT_TEXT = 7
    SWITCH = 8
    PAGE_CONTAINER = 9
    CLOSE_ICON = 10
    ARROW_ICON = 11
    BOTTOM_FLOAT_CONTAINER = 12
    TAB_BAR_VIEW = 13
    SPLIT_LINE = 14
    HORIZON_SPLIT_CONTAINER = 15
    OTHER_TYPE = 16

AI_TYPE_STR = [
    "redPoint",
    "bubble",
    "bottomBar",
    "redPointBubbleContainer",
    "radio",
    "checkbox",
    "button",
    "input",
    "switch",
    "pageContainer",
    "closeIcon",
    "arrowIcon",
    "bottomFloatContainer",
    "tabBarView",
    "splitLine",
    "horizontalSplitContainer",
    "otherType"
]
class LIST_TYPE(Enum):
    NONE_CONTAINER = 0
    LOOP_CONTAINER = 1
    REGULAR_CONTAINER = 2
    VERTICAL_SPLIT_LIST = 3


class PROJECTION_TYPE(Enum):
    HORIZON = 0
    VERTICAL = 1
class ROW_ALIGNMENT_TYPE(IntEnum):
    INVALID = -1  # 无效/未知对齐类型
    LEFT_TO_RIGHT = 1  # 从左到右对齐
    RIGHT_TO_LEFT = 2  # 从右到左对齐  
    SPACE_BETWEEN = 3  # 分散对齐
    LEFT_CENTER_RIGHT = 4 #左中右对齐

class COLUMN_ALIGNMENT_TYPE(IntEnum):
    INVALID = -1  # 无效/未知对齐类型
    TOP_TO_BOTTOM = 1  # 从上到下对齐
    SPACE_BETWEEN = 3  # 分散对齐

class LAYOUT_TYPE(IntEnum):
    COLUMN = 0
    ROW = 1
    GRID = 2
    MESS = 3
