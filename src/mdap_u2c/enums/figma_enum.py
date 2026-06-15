"""
Figma 枚举定义

Figma 特定的枚举类型，直接对应 Figma API 返回的值
参考：https://www.figma.com/developers/api
"""
from enum import Enum


# ============================================================================
# Figma 节点类型
# ============================================================================
class FigmaNodeType(str, Enum):
    """Figma 节点类型"""
    DocumentNode = "DOCUMENT"                       # 页面节点(不能作为导出节点)
    CanvasNode = "CANVAS"                           # 画布节点(该类型为document直接子节点，不可作为导出节点)
    FrameNode = "FRAME"                             # 框架节点
    VectorNode = "VECTOR"                           # 矢量节点
    RectangleNode = "RECTANGLE"                     # 矩形节点
    InstanceNode = "INSTANCE"                       # 实例节点
    TextNode = "TEXT"                               # 文本节点
    LineNode = "LINE"                               # 线节点
    EllipseNode = "ELLIPSE"                         # 椭圆节点
    BooleanOperationNode = "BOOLEAN_OPERATION"      # boolean操作节点
    GroupNode = "GROUP"                             # 组节点
    ComponentSetNode = "COMPONENT_SET"              # 组件集合节点
    ComponentNode = "COMPONENT"                     # 组件节点
    RegularPolygonNode = "REGULAR_POLYGON"          # 正多边形(包括三角形)
    SectionNode = "SECTION"                         # 切面节点
    StarNode = "STAR"                               # 星
    SliceNode = "SLICE"                             # SliceNode

