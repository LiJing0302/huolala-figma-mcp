"""
DSL 相关数据模型
定义 DSL 结构的完整数据模型，使用 msgspec 提供高性能序列化和验证
"""

from typing import Optional, Dict, List, Union, Any
import msgspec
import copy

from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils.serializer_utils import SerializerUtils


# ============================================================================
# 布局系统
# ============================================================================
class Position(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """位置信息"""
    x: float
    y: float
    type: Optional[dsl_enum.PositionType] = dsl_enum.PositionType.ABSOLUTE


class Point(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """二维坐标点 (x, y)，用于记录 figma 原始 bounds 位置"""
    x: float = 0
    y: float = 0


class Size(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """尺寸信息"""
    width: Optional[float] = None
    height: Optional[float] = None
    min_width: Optional[float] = None
    min_height: Optional[float] = None
    max_width: Optional[float] = None
    max_height: Optional[float] = None

    def deep_copy(self):
        return copy.deepcopy(self)


class Spacing(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """间距（padding/margin）"""
    top: float = 0
    right: float = 0
    bottom: float = 0
    left: float = 0


class Flexbox(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """Flexbox 布局（不能有默认值，因为容器和子元素的属性统一定义了在这里）"""
    # 容器属性
    direction: dsl_enum.FlexDirection = None
    align_items: Optional[dsl_enum.AlignItems] = None
    justify_items: Optional[dsl_enum.JustifyItems] = None
    row_gap: Optional[float] = None
    column_gap: Optional[float] = None
    wrap: Optional[dsl_enum.FlexWrap] = None
    align_content: Optional[dsl_enum.AlignContent] = None
    justify_content: dsl_enum.JustifyContent = None

    # 子元素属性
    flex_grow: Optional[float] = None
    flex_shrink: Optional[float] = None
    flex_basis: Optional[float] = None
    align_self: Optional[str] = None

    def all_none(self):
        return all(getattr(self, field) is None for field in self.__slots__)


class Gridbox(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """Grid 布局"""
    # 容器属性
    row_gap: Optional[float] = None
    column_gap: Optional[float] = None
    grid_template_columns: Optional[str] = None
    grid_template_rows: Optional[str] = None

    # 子元素属性
    grid_row: Optional[str] = None
    grid_column: Optional[str] = None

    def all_none(self):
        return all(getattr(self, field) is None for field in self.__slots__)


class Layout(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """布局信息(包含：位置、尺寸、间距、布局等影响空间位置的属性都放在这里)"""
    position: Position
    size: Size
    display: Optional[dsl_enum.DisplayMode] = None
    flexbox: Optional[Flexbox] = None
    gridbox: Optional[Gridbox] = None
    padding: Optional[Spacing] = None
    margin: Optional[Spacing] = None
    z_index: Optional[int] = None

    def deep_copy(self):
        return copy.deepcopy(self)


# ============================================================================
# 样式系统
# ============================================================================
class Style(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """
    组件样式属性定义，属性名和值可以参考css 规范文档：https://www.w3school.com.cn/cssref/index.asp
    注意：
    1. 该对象的属性和值一定要和css规范保持一致，如果值有单位，一定要把对应的单位加上，不能省略，因为在代码生成测是不需要推理单位的，直接使用原值进行转换
    2. 所有CSS属性值都必须是字符串类型（如 "16px", "50%", "auto"），因为即使是数字值在CSS中也需要带单位（如 "16px"）
    3. 只有像 font-weight 这种既支持数字（如 500）也支持字符串关键字（如 "normal", "bold"）的属性，才使用 Union[int, str] 类型
    """
    # ===== 文本样式 =====
    font_family: Optional[str] = None                   # 字体名称，如 "Arial" 或字体栈 "Arial, sans-serif"
    font_size: Optional[str] = None                     # 字体大小（如 "16px", "1em", "1rem", "100%", "small"）
    font_weight: Optional[Union[int, str]] = None       # 字体粗细，支持数字（100-900）或字符串（如 100, "normal"）
    font_style: Optional[str] = None                    # 字体样式，支持 "normal" | "italic" | "oblique"
    line_height: Optional[Union[int, str]] = None       # 行高（如 1.5, "24px", "150%", "normal"）
    letter_spacing: Optional[str] = None                # 字间距（如 "2px", "0.1em", "normal"）
    text_indent: Optional[str] = None                   # 首行缩进（如 "2em", "50%", "10px"）

    text_align: Optional[str] = None                    # 文本水平对齐方式，支持 "left" | "center" | "right" | "justify"
    vertical_align: Optional[str] = None                # 文本垂直对齐方式，支持 "top" | "middle" | "bottom" | "baseline" | "sub" | "super" | 长度值或百分比（如 "10px", "50%"）
    text_decoration: Optional[str] = None               # 文本装饰器，支持 "none" | "underline" | "line-through" | "overline"
    text_transform: Optional[str] = None                # 文本转换，支持 "none" | "uppercase" | "lowercase" | "capitalize"
    text_overflow: Optional[str] = None                 # 文本溢出，支持 "clip" | "ellipsis" | 字符串值
    word_break: Optional[str] = None                    # 单词换行，支持 "normal" | "break-all" | "keep-all" | "break-word"
    white_space: Optional[str] = None                   # 文本是否折行

    # ===== 颜色 =====
    color: Optional[str] = None                         # 文本颜色（如 "#ff0000", "rgb(255,0,0)", "red"）或关键字
    background_color: Optional[str] = None              # 背景色（如 "#ff0000", "rgb(255,0,0)", "red"）或关键字（如 "transparent"）
    opacity: Optional[Union[int, str]] = None           # 透明度（如 0.5, 1, "inherit"），CSS中值为0-1之间的数字
    # ===== 图片 =====
    object_fit:Optional[str] = None                     #图片填充模式，支持cover contain fill等
    # ===== 背景 =====
    background: Optional[str] = None                    # 背景，支持简写值（如 "red", "url(image.jpg) no-repeat center"）或组合值
    background_image: Optional[str] = None              # [注意] 背景图片，支持 "none" | "url(...)" 注意：在打包前存储的值nodeId值，需要替换
    background_size: Optional[str] = None               # 背景尺寸，支持 "cover" | "contain" | 长度值（如 "100px 200px"）| 百分比
    background_position: Optional[str] = None           # 背景位置，支持关键字（如 "center", "top left"）| 长度值（如 "10px 20px"）| 百分比
    background_repeat: Optional[str] = None             # 背景重复，支持 "no-repeat" | "repeat" | "repeat-x" | "repeat-y" | "space" | "round"

    # ===== 边框 =====
    border_color: Optional[str] = None                  # 边框颜色，支持颜色值（如 "#ff0000", "rgb(255,0,0)"）或关键字，注意：可能存在渐变色值
    border_style: Optional[str] = None                  # 边框样式，支持 "solid" | "dashed" | "dotted" | "double" | "groove" | "ridge" | "inset" | "outset" | "none" | "hidden"
    border_width: Optional[str] = None                  # 边框宽度，支持字符串值（如 "1px", "thin", "medium", "thick"）
    border_top_width: Optional[str] = None              # 上边框宽度，支持字符串值（如 "1px", "thin", "medium", "thick"）
    border_bottom_width: Optional[str] = None           # 下边框宽度，支持字符串值（如 "1px", "thin", "medium", "thick"）
    border_left_width: Optional[str] = None             # 左边框宽度，支持字符串值（如 "1px", "thin", "medium", "thick"）
    border_right_width: Optional[str] = None            # 右边框宽度，支持字符串值（如 "1px", "thin", "medium", "thick"）
    border_bottom: Optional[str] = None                 # 下边框简写，支持 "width style color" 格式（如 "1px solid #000"）
    border_radius: Optional[str] = None                 # 边框圆角，支持字符串值（如 "10px", "50%", "10px 20px"）
    border_top_left_radius: Optional[str] = None        # 左上角圆角，支持字符串值（如 "10px", "50%"）
    border_top_right_radius: Optional[str] = None       # 右上角圆角，支持字符串值（如 "10px", "50%"）
    border_bottom_right_radius: Optional[str] = None    # 右下角圆角，支持字符串值（如 "10px", "50%"）
    border_bottom_left_radius: Optional[str] = None     # 左下角圆角，支持字符串值（如 "10px", "50%"）

    # ===== 效果 =====
    box_shadow: Optional[str] = None                    # 阴影，支持 "none" | 阴影值（如 "10px 10px 5px #888888"）| 多个阴影值
    overflow: Optional[str] = None                      # 溢出处理，支持 "visible" | "hidden" | "scroll" | "auto" | "clip"
    box_sizing: Optional[str] = None                    # 盒模型，支持 "border-box" | "content-box" - 用于处理边框与尺寸的关系
    transform: Optional[str] = None                     # 变换，支持 "translateX(-50%)" | "translate(-50%, -50%)" | "rotate(45deg)" 等

    # ===== 其他=====
    cursor: Optional[str] = None                        # 鼠标样式，支持 "pointer" | "default" | "move" | "text" | "wait" | "help" 等（Web用）
    width: Optional[str] = None                         # 宽度，支持字符串值（如 "100px", "50%", "auto", "100vw", "calc(100% - 20px)"）
    max_width: Optional[str] = None                     # 宽度，支持字符串值（如 "100px", "50%", "auto", "100vw", "calc(100% - 20px)"）
    min_width: Optional[str] = None                     # 宽度，支持字符串值（如 "100px", "50%", "auto", "100vw", "calc(100% - 20px)"）
    height: Optional[str] = None                        # 高度，支持字符串值（如 "100px", "50%", "auto", "100vh", "calc(100% - 20px)"）
    max_height: Optional[str] = None                    # 高度，支持字符串值（如 "100px", "50%", "auto", "100vh", "calc(100% - 20px)"）
    min_height: Optional[str] = None                    # 高度，支持字符串值（如 "100px", "50%", "auto", "100vh", "calc(100% - 20px)"）
    position: Optional[str] = None                      # 定位方式，支持值: "relative" | "absolute" | "fixed"
    top: Optional[str] = None                           # 顶部位置，支持字符串值（如 "10px", "50%", "auto"）
    left: Optional[str] = None                          # 左侧位置，支持字符串值（如 "10px", "50%", "auto"）
    right: Optional[str] = None                         # 右侧位置，支持字符串值（如 "10px", "50%", "auto"）
    bottom: Optional[str] = None                        # 底部位置，支持字符串值（如 "10px", "50%", "auto"）
    margin_left: Optional[str] = None                   # 左外边距，支持字符串值（如 "10px", "50%", "auto"）
    margin_right: Optional[str] = None                  # 右外边距，支持字符串值（如 "10px", "50%", "auto"）
    margin_top: Optional[str] = None                    # 上外边距，支持字符串值（如 "10px", "50%", "auto"）
    margin_bottom: Optional[str] = None                 # 下外边距，支持字符串值（如 "10px", "50%", "auto"）
    margin: Optional[str] = None                        # 外边距简写，格式 "top right bottom left"（如 "10px 5px 10px 5px"）
    padding_left: Optional[str] = None                  # 左内边距，支持字符串值（如 "10px", "50%", "calc(100% - 20px)"）
    padding_right: Optional[str] = None                 # 右内边距，支持字符串值（如 "10px", "50%", "calc(100% - 20px)"）
    padding_top: Optional[str] = None                   # 上内边距，支持字符串值（如 "10px", "50%", "calc(100% - 20px)"）
    padding_bottom: Optional[str] = None                # 下内边距，支持字符串值（如 "10px", "50%", "calc(100% - 20px)"）
    padding: Optional[str] = None                       # 内边距简写，格式 "top right bottom left"（如 "10px 5px 10px 5px"）
    white_space: Optional[str] = None                   # 设置空白处理，支持 "normal" | "nowrap" | "pre" | "pre-wrap" | "pre-line" | "inherit"
    
    # flexbox相关属性
    flex_direction: Optional[str] = None                # 弹性方向，支持值: "row" | "row-reverse" | "column" | "column-reverse"
    justify_content: Optional[str] = None               # 主轴对齐，支持值: "flex-start" | "flex-end" | "center" | "space-between" | "space-around" | "space-evenly"
    align_items: Optional[str] = None                   # 交叉轴对齐，支持值: "flex-start" | "flex-end" | "center" | "baseline" | "stretch"
    flex_wrap: Optional[str] = None                     # 换行方式，支持值: "nowrap" | "wrap" | "wrap-reverse"
    row_gap: Optional[str] = None                       # 行间距，支持字符串值（如 "10px", "1em", "50%"）
    column_gap: Optional[str] = None                    # 列间距，支持字符串值（如 "10px", "1em", "50%"）
    align_self: Optional[str] = None                    # 自身对齐，支持值: "auto" | "flex-start" | "flex-end" | "center" | "baseline"
    flex_grow: Optional[str] = None                     # 弹性增长因子，支持字符串值（如 "0", "1", "2"）
    flex_shrink: Optional[str] = None                   # 弹性收缩因子，支持字符串值（如 "0", "1", "2"）
    display: Optional[str] = None
    # grid相关属性
    grid_template_columns: Optional[str] = None         # Grid列模板，支持值如 "repeat(3, 1fr)", "100px 200px auto" 等
    grid_row: Optional[str] = None                      # Grid行位置，支持值如 "1 / 3", "span 2" 等
    grid_column: Optional[str] = None                   # Grid列位置，支持值如 "1 / 3", "span 2" 等
    justify_items: Optional[str] = None                 # Grid格子内元素水平对齐，支持值: "start" | "center" | "end" | "stretch"
    # 有序和无序列表样式
    padding_inline_start: Optional[str] = None          # 内联起始内边距，支持字符串值（如 "10px", "50%", "calc(100% - 20px)"）

    # webkit前缀属性
    webkit_line_clamp: Optional[int] = None            # 设置溢出显示行数，支持整数值
    webkit_box_orient: Optional[str] = None            # 设置多行文本的布局方向，支持值: "horizontal" | "vertical"
    
    # AI标记属性
    data_ai_type: Optional[str] = None                 # AI类型标记，用于标记 button, input, radio, checkbox, switch, icon 等类型
    data_ai_semantic: Optional[str] = None             # AI语义标记，用于存储控件的语义信息（如图标的语义描述）

    # 层叠顺序
    z_index: Optional[int] = None                      # 层叠顺序，支持整数值（如 1, 2, 100, -1）

    def deep_copy(self):
        return copy.deepcopy(self)
    

# ============================================================================
# 组件对应的figma原始信息
# ============================================================================
class FigmaInfo(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """figma 元数据"""
    name: Optional[str] = None                      # figma组件名称
    node_id: Optional[str] = None                   # figma nodeId
    type: Optional[str] = None                      # figma nodeType
    width: Optional[int] = None                     # figma width(原始值)
    height: Optional[int] = None                    # figma height(原始值)
    font_post_script_name: Optional[str] = None     # figma font_post_script_name(用于字体导出)
    bounding_box_size: Optional[Size] = None        # figma节点本身大小
    render_bounds_size: Optional[Size] = None       # figma节点实际渲染大小(包含阴影、边框等大小)
    render_bounds_position: Optional[Point] = None  # 原始设计稿 absoluteRenderBounds 的 x, y
    bounding_box_position: Optional[Point] = None   # 原始设计稿 absoluteBoundingBox 的 x, y


# ============================================================================
# 资源定义
# ============================================================================
class Assets(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """资源集合"""
    # 图片列表<id, url>
    images: Optional[Dict[str, str]] = msgspec.field(default_factory=dict)
    fonts: Optional[List[str]] = msgspec.field(default_factory=list)


# ============================================================================
# 元数据定义
# ============================================================================
class Metadata(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """DSL 元数据"""
    url: str                    # figma url
    node_id: str                # figma nodeId
    width: int                  # figma width
    height: int                 # figma height
    name: str                   # figma name
    image_url: str              # figma image_url
    file_key: str               # figma file key value
    image_scale: int            # image export scale
    extra_dict: dict            # extra info,top and bottom crop info
    def to_json(self):
        return SerializerUtils.to_json(self)

    def to_dict(self):
        return SerializerUtils.to_dict(self)


# ============================================================================
# 组件基本属性
# ============================================================================
class AbstractComponentProps(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """组件基本属性(共有属性)，子类可继承自行扩展"""
    class_name: Optional[str] = None


# ============================================================================
# 组件基类
# ============================================================================
class AbstractComponent(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """组件基类(注意，type属性有子类通过tag来实现，不要手动定义)"""
    id: str                                                 # 组件ID(全局唯一，该id由系统生成，和figma nodeId是两个维度值)
    type: str                                               # 组件类型
    parent_id: Optional[str] = None                         # 父组件ID（只有父节点才会为None，子节点必须有该值）
    figma: Optional[FigmaInfo] = None                       # figma元数据
    extensions: Optional[Dict[str, Any]] = None             # 扩展信息(DSL加工层可以自由添加)

    layout: Optional[Layout] = None                         # 布局信息
    style: Style = msgspec.field(default_factory=Style)     # 样式信息
    props: AbstractComponentProps                           # 根据type有不同的属性(子类可自行扩展)
    children: List["AbstractComponent"] = msgspec.field(default_factory=list)

    def is_instance_of(self, component_type: dsl_enum.ComponentType):
        """判断当前组件是否是指定类型的组件(不能使用isinstance判断，因为与导包路径有关系，可能存在误判)"""
        return self.type == component_type.value


# ============================================================================
# DSL 顶层结构
# ============================================================================
class DSL(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    version: str = "1.0.0"
    metadata: Metadata
    assets: Optional[Assets] = None
    components: List[AbstractComponent] = msgspec.field(default_factory=list)
    vlm_result: Optional[Dict[str, Any]] = None  # 多模态大模型返回的UI结构识别结果

    def to_json(self):
        return SerializerUtils.to_json(self)

    def to_dict(self):
        return SerializerUtils.to_dict(self)

