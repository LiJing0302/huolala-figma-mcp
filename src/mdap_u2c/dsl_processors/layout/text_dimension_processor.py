"""
文本宽高去除处理模块

负责文本高度去除、文本宽度去除等相关功能
"""
import logging
import re
from typing import Optional, Dict, Any

import numpy
from PIL import Image

from mdap_u2c.enums import dsl_enum, common_enum
from mdap_u2c.dsl_processors.layout.layout_constant import ADJUST_WIDTH_MARGIN
from mdap_u2c.dsl_processors.layout.parent_padding import get_parent_padding

# Web 平台列表（用于文本高度去除判断）
_WEB_PLATFORMS = [
    common_enum.PlatformType.H5.value,
    common_enum.PlatformType.React.value,
    common_enum.PlatformType.Vue.value
]

# 常量
EPSILON = 2.1
LEFT_RIGHT_THROLD = 20

_logger = logging.getLogger("text_dimension_processor")


# ============================================================================
# 文本解析工具函数
# ============================================================================

def _parse_font_size(font_size_str: Optional[str]) -> float:
    """
    从字体大小字符串中解析出数值（如 "16px" -> 16.0）
    
    Args:
        font_size_str: 字体大小字符串，如 "16px", "1.5em" 等
    
    Returns:
        float: 字体大小数值，解析失败返回 14.0（默认值）
    """
    if not font_size_str:
        return 14.0
    
    # 移除单位，只保留数字
    match = re.match(r'^([\d.]+)', str(font_size_str))
    if match:
        return float(match.group(1))
    return 14.0


def _parse_px_value(px_str: Optional[str], default: float = 0.0) -> float:
    """
    从像素字符串中解析出数值（如 "16px" -> 16.0）
    
    Args:
        px_str: 像素字符串，如 "16px", "24.5px" 等
        default: 解析失败时的默认值
    
    Returns:
        float: 数值，解析失败返回 default
    """
    if px_str is None:
        return default
    
    if isinstance(px_str, (int, float)):
        return float(px_str)
    
    # 移除单位，只保留数字
    match = re.match(r'^([\d.]+)', str(px_str))
    if match:
        return float(match.group(1))
    return default


def _parse_line_height(line_height_value) -> tuple:
    """
    解析 lineHeight 值，返回 (数值, 是否有px单位)
    
    支持的格式：
    - "24px" -> (24.0, True)
    - "150%" -> (1.5, False)  # 百分比转换为倍数
    - 1.5 -> (1.5, False)
    - None -> (None, False)
    
    :param line_height_value: lineHeight 值
    :return: (数值, 是否有px单位)
    """
    if line_height_value is None:
        return None, False
    
    if isinstance(line_height_value, (int, float)):
        return float(line_height_value), False
    
    if isinstance(line_height_value, str):
        line_height_str = line_height_value.strip()
        
        # 检查是否有 px 单位
        if line_height_str.endswith('px'):
            try:
                value = float(line_height_str[:-2])
                return value, True
            except ValueError:
                return None, False
        
        # 检查是否有 % 单位
        if line_height_str.endswith('%'):
            try:
                value = float(line_height_str[:-1]) / 100.0
                return value, False
            except ValueError:
                return None, False
        
        # 尝试解析纯数字
        try:
            value = float(line_height_str)
            return value, False
        except ValueError:
            return None, False
    
    return None, False


# ============================================================================
# 文本字符统计函数
# ============================================================================

def _count_text_characters(text: str) -> tuple:
    """
    统计文本中的字符类型数量
    
    Args:
        text: 文本内容
    
    Returns:
        tuple: (汉字个数, 中文标点个数, 其他字符个数)
    """
    if not text:
        return 0, 0, 0
    
    chinese_chars = 0      # 汉字个数
    chinese_puncts = 0     # 中文标点个数
    other_chars = 0        # 其他字符（数字、英文字母、英文符号等）
    
    # 中文标点符号集合
    chinese_punctuation = set('，。！？、；：""''【】《》（）…—～·')
    
    for char in text:
        # 判断是否为汉字
        if '\u4e00' <= char <= '\u9fff':
            chinese_chars += 1
        # 判断是否为中文标点
        elif char in chinese_punctuation:
            chinese_puncts += 1
        # 其他字符（数字、英文字母、英文符号、空格等）
        elif not char.isspace():  # 忽略空白字符
            other_chars += 1
    
    return chinese_chars, chinese_puncts, other_chars


def _collect_rich_text_content(container_node) -> str:
    """
    递归收集复文本容器中的所有文本内容
    
    Args:
        container_node: 复文本容器节点
    
    Returns:
        str: 所有文本内容的拼接
    """
    text_parts = []
    
    def _collect_from_node(node):
        if node is None:
            return
        
        src = node.data.src if hasattr(node, 'data') else node
        
        # 如果是文本组件，提取文本
        if hasattr(src, 'type') and src.type == dsl_enum.ComponentType.TEXT:
            if hasattr(src, 'props') and hasattr(src.props, 'text'):
                text_parts.append(src.props.text or "")
        
        # 递归处理子节点
        if hasattr(src, 'children'):
            for child in src.children or []:
                _collect_from_node(child)
    
    _collect_from_node(container_node)
    return "".join(text_parts)


# 文本多行判断函数
# ============================================================================

def _is_text_multiline(text_node, context_share_data: Optional[Dict[str, Any]] = None, input_tree=None) -> bool:
    """
    预测文本是否有多行
    
    判断策略：
    - 文字内容 <= 8 字符：采用宽度估算法
    - 文字内容 > 8 字符：采用 _calc_text_row_count_by_image 图像检测（需提供 pil_image）
    
    宽度估算法条件：
    1.1 如果汉字个数 * fontsize > text_width，则为多行
    1.2 预估宽度 = 汉字个数 * fontsize + 中文标点个数 * fontsize * 0.7 + 其他 * fontsize * 0.5
        如果预估宽度 - text_width >= font_size * 2，则为多行
    
    Args:
        text_node: 文本节点（支持 TEXT 和 CONTAINER_RICH 类型）
        context_share_data: 上下文共享数据，需包含 pil_image 才能使用图像检测
        input_tree: 可选，布局树，用于裁剪文本区域时取父容器边界
    
    Returns:
        bool: 如果预测为多行返回 True，否则返回 False
    """
    if text_node is None:
        return False
    
    src = text_node.data.src
    text_width = text_node.data.width
    
    if text_width <= 0:
        return False
    
    # 获取字体大小
    font_size = 14.0  # 默认字体大小
    if src.style and src.style.font_size:
        font_size = _parse_font_size(src.style.font_size)
    
    # 获取文本内容
    text_content = ""
    if src.type == dsl_enum.ComponentType.TEXT:
        # 单文本
        if hasattr(src, 'props') and hasattr(src.props, 'text'):
            text_content = src.props.text or ""
    elif src.type == dsl_enum.ComponentType.CONTAINER_RICH:
        # 复文本容器 - 需要收集所有子文本
        text_content = _collect_rich_text_content(text_node)
    
    if not text_content:
        return False
    
    # 计算字符数
    chinese_chars, chinese_puncts, other_chars = _count_text_characters(text_content)
    char_count = chinese_chars + chinese_puncts + other_chars
    
    # 文字内容 > 8 时，优先使用图像检测
    if char_count > 8 and context_share_data is not None:
        pil_image = context_share_data.get('pil_image')
        if pil_image is not None:
            cropped_image = _crop_text_region(pil_image, text_node.data, input_tree=input_tree)
            if cropped_image is not None:
                row_cnt = _calc_text_row_count_by_image(
                    cropped_image, font_size_px=font_size, text_content=text_content
                )
                return row_cnt > 1
    
    # 文字内容 <= 8 或无法使用图像检测时，采用宽度估算法.文本太少比如一个文本，比如元字投影也会切成2行
    estimated_width = _estimate_text_width(text_content, font_size)
    if text_width > 0 and estimated_width - text_width >= font_size * 2:
        return True
    
    return False
def _estimate_text_width(text_content: str, font_size: float) -> float:
    """
    预估文本宽度
    
    Args:
        text_content: 文本内容
        font_size: 字体大小
    """
    chinese_chars, chinese_puncts, other_chars = _count_text_characters(text_content)
    return (
        chinese_chars * font_size + 
        chinese_puncts * font_size * 0.6 + 
        other_chars * font_size * 0.5
    )

def _get_text_position_relative_to_parent(current_node, parent_node, epsilon: float = EPSILON) -> str:
    """
    判断文本相对父容器的位置：偏左、居中还是偏右
    
    Args:
        current_node: 当前文本节点
        parent_node: 父容器节点
        epsilon: 判断居中的容差值
    
    Returns:
        str: "left"（偏左）, "center"（居中）, "right"（偏右）
    """
    if parent_node is None:
        return "left"
    
    parent_x = parent_node.data.x
    parent_width = parent_node.data.width
    parent_right = parent_x + parent_width
    
    current_x = current_node.data.x
    current_width = current_node.data.width
    current_right = current_x + current_width
    
    # 计算左右边距
    left_margin = current_x - parent_x
    right_margin = parent_right - current_right
    
    # 判断是否居中（左右边距差异在容差范围内）
    if abs(left_margin - right_margin) <= epsilon:
        return "center"
    
    # 判断偏左还是偏右
    if left_margin - right_margin >= LEFT_RIGHT_THROLD:
        return "right"
    else:
        return "left"


# ============================================================================
# 图像处理相关函数（用于文本行数检测）
# ============================================================================

def _is_row_uniform_for_text(row: numpy.ndarray, max_diff_threshold: int = 8, edge_margin: int = 2) -> bool:
    """
    检查一行像素是否颜色基本一致（用于检测空隙行）
    采用最大值-最小值差异判断
    
    :param row: 一行像素数据，shape 为 (width,) 或 (width, channels)
    :param max_diff_threshold: 最大值-最小值差异阈值，默认8（比VLM的5稍宽松）
    :param edge_margin: 边缘忽略的像素数，默认2
    :return: 是否颜色基本一致
    """
    width = row.shape[0]
    
    if width <= edge_margin * 3:
        edge_margin = 0
    
    if edge_margin > 0:
        row = row[edge_margin:-edge_margin]
    
    if len(row.shape) == 1:
        # 灰度图
        return (numpy.max(row) - numpy.min(row)) <= max_diff_threshold
    else:
        # 彩色图 (RGB)，检查每个通道的最大值-最小值差异是否都 <= 阈值
        for c in range(row.shape[1]):
            if (numpy.max(row[:, c]) - numpy.min(row[:, c])) > max_diff_threshold:
                return False
        return True


def _is_column_uniform(column: numpy.ndarray, max_diff_threshold: int = 8) -> bool:
    """
    检查一列像素是否颜色基本一致（用于检测文本列间空隙）
    
    :param column: 一列像素数据
    :param max_diff_threshold: 最大值-最小值差异阈值，默认8
    :return: 是否颜色基本一致
    """
    if len(column.shape) == 1:
        # 灰度图
        return (numpy.max(column) - numpy.min(column)) <= max_diff_threshold
    else:
        # 彩色图 (RGB)，检查每个通道的最大值-最小值差异是否都 <= 阈值
        for c in range(column.shape[1]):
            if (numpy.max(column[:, c]) - numpy.min(column[:, c])) > max_diff_threshold:
                return False
        return True


def _crop_text_region(
    pil_image: Image.Image,
    node_data,
    image_scale: int = 1,
    input_tree=None,
) -> Optional[Image.Image]:
    """
    从背景图片中裁剪出文本节点对应的区域。

    若文本节点超出父容器（或未传 input_tree 时超出图片边界），则先取文本区域与父容器
    区域的交集作为裁剪区域，再向内缩小 2 像素，避免裁到容器边缘。

    :param pil_image: 背景 PIL 图片对象
    :param node_data: 文本节点数据，包含 x, y, width, height，且应有 uid 以便从树中取父节点
    :param image_scale: 图片缩放比例
    :param input_tree: 可选，布局树；传入时从树中取当前节点的父节点作为父容器边界，为 None 时以图片边界为容器
    :return: 裁剪后的 PIL 图片，如果裁剪失败返回 None
    """
    if pil_image is None or node_data is None:
        return None

    try:
        # 文本区域（像素）
        x = int(node_data.x * image_scale)
        y = int(node_data.y * image_scale)
        width = int(node_data.width * image_scale)
        height = int(node_data.height * image_scale)
        text_left, text_upper = x, y
        text_right, text_lower = x + width, y + height

        # 容器区域（像素）：有 input_tree 则取父节点边界，否则用图片边界
        parent_bounds = None
        if input_tree is not None and getattr(node_data, "uid", None) is not None:
            try:
                parent = input_tree.parent(node_data.uid)
                if parent is not None and parent.data is not None:
                    p = parent.data
                    parent_bounds = (p.x, p.y, p.width, p.height)
            except Exception:
                pass
        if parent_bounds is not None:
            px, py, pw, ph = parent_bounds
            container_left = int(px * image_scale)
            container_upper = int(py * image_scale)
            container_right = int((px + pw) * image_scale)
            container_lower = int((py + ph) * image_scale)
        else:
            container_left = 0
            container_upper = 0
            container_right = pil_image.width
            container_lower = pil_image.height

        # 与图片边界做交集，避免越界
        container_left = max(0, container_left)
        container_upper = max(0, container_upper)
        container_right = min(pil_image.width, container_right)
        container_lower = min(pil_image.height, container_lower)

        # 文本与容器的交集（最小区域）
        left = max(text_left, container_left)
        upper = max(text_upper, container_upper)
        right = min(text_right, container_right)
        lower = min(text_lower, container_lower)

        # 若文本节点超出父容器，则交集后再向内缩小 2 个单位
        text_exceeds_container = (
            text_left < container_left
            or text_right > container_right
            or text_upper < container_upper
            or text_lower > container_lower
        )
        if text_exceeds_container:
            shrink = 2
            left = left + shrink
            upper = upper + shrink
            right = right - shrink
            lower = lower - shrink
            # 保证缩小后仍为有效区域（至少 1x1）
            if right <= left:
                right = left + 1
            if lower <= upper:
                lower = upper + 1

        if right <= left or lower <= upper:
            return None

        cropped_image = pil_image.crop((left, upper, right, lower))
        return cropped_image
    except Exception as e:
        _logger.warning(f"裁剪文本区域失败: {e}")
        return None


def _calc_text_row_count_by_image(pil_image: Image.Image, min_gap_height: int = 1,
                                   max_diff_threshold: int = 8,
                                   font_size_px: Optional[float] = None,
                                   text_content: Optional[str] = None) -> int:
    """
    使用纯图像处理方式扫描文本容器截图区域，计算文本行数
    
    计算逻辑：
    0. 若传入文本内容且字符数为 1，直接返回行数 1，不做图像处理
    1. 扫描图片中的横向空隙（从左到右颜色基本一致的连续行）
    2. 统计中间空隙时，若当前空隙与上一个空隙的距离 < lineHeight * 0.6，则剔除该空隙
    3. row_cnt = 中间空隙区域数量 + 1
    
    :param pil_image: 文本区域的 PIL 图片对象
    :param min_gap_height: 最小空隙高度（过滤噪声），默认2像素
    :param max_diff_threshold: RGB各通道最大值-最小值差异阈值，默认8
    :param font_size_px: 用于过滤距离过近的空隙；为 None 时不应用该过滤
    :param text_content: 文本内容；若为单字符则直接返回 1，不进行图像处理
    :return: 文本行数（至少为1）
    """
    # 若文本内容为单字符，直接返回行数 1
    if text_content is not None and len(text_content.strip()) == 1:
        return 1
    
    if pil_image is None:
        return 1
    
    img_width, img_height = pil_image.size
    if img_width <= 0 or img_height <= 0:
        return 1
    
    # 转换为numpy数组
    img_array = numpy.array(pil_image)
    
    # 确保是RGB格式（去掉alpha通道）
    if len(img_array.shape) == 3 and img_array.shape[2] == 4:
        img_array = img_array[:, :, :3]
    
    # 标记每行是否是空隙行
    uniform_rows = []
    for y in range(img_height):
        row = img_array[y, :]
        uniform_rows.append(_is_row_uniform_for_text(row, max_diff_threshold))
    
    # 找到连续的空隙区域（排除顶部和底部的空隙，只统计中间的空隙）
    # 首先找到第一个非空隙行（文本开始）
    first_text_row = 0
    for y in range(img_height):
        if not uniform_rows[y]:
            first_text_row = y
            break
    
    # 找到最后一个非空隙行（文本结束）
    last_text_row = img_height - 1
    for y in range(img_height - 1, -1, -1):
        if not uniform_rows[y]:
            last_text_row = y
            break
    
    # 只在文本区域内统计空隙
    if first_text_row >= last_text_row:
        return 1
    
    # 统计中间的空隙区域数量；若提供 font_size_px，则与上一空隙距离 < lineHeight*0.6 的空隙剔除
    gap_count = 0
    in_gap = False
    gap_start = 0
    prev_gap_end: Optional[int] = first_text_row  # 上一个被统计的空隙的结束行（下一行 y）
    min_gap_distance = (font_size_px * 0.6) if font_size_px is not None and font_size_px > 0 else None
    
    for y in range(first_text_row, last_text_row + 1):
        if uniform_rows[y] and not in_gap:
            in_gap = True
            gap_start = y
        elif not uniform_rows[y] and in_gap:
            in_gap = False
            gap_height = y - gap_start
            # 只统计高度大于阈值的空隙（过滤噪声）
            if gap_height >= min_gap_height:
                if min_gap_distance is not None and prev_gap_end is not None:
                    # 当前空隙起始行与上一空隙结束行的距离
                    distance_to_prev = gap_start - prev_gap_end
                    if distance_to_prev < min_gap_distance:
                        continue  # 剔除：距离过近，不计数
                gap_count += 1
                prev_gap_end = y
    
    # 行数 = 空隙数 + 1
    row_count = gap_count + 1
    return max(1, row_count)


def _calc_text_display_x_range(pil_image: Image.Image, node_data, image_scale: int = 1,
                                max_diff_threshold: int = 8, input_tree=None) -> tuple:
    """
    使用图像处理方式计算文本渲染区域的 x 坐标范围
    
    通过扫描文本区域图片的每一列，找到第一个有内容的列和最后一个有内容的列，
    返回文本实际渲染区域相对于画布的绝对坐标。
    
    :param pil_image: 背景 PIL 图片对象
    :param node_data: 文本节点数据，包含 x, y, width, height
    :param image_scale: 图片缩放比例
    :param max_diff_threshold: RGB各通道最大值-最小值差异阈值，默认8
    :param input_tree: 可选，布局树，用于裁剪文本区域时取父容器边界
    :return: (display_x_start_offset, display_x_end_offset, text_display_position)
             - display_x_start_offset: 文本渲染区域左边缘的绝对 x 坐标
             - display_x_end_offset: 文本渲染区域右边缘的绝对 x 坐标
             - text_display_position: 文本渲染区域相对于控件的位置 ("left", "center", "right")
             如果无法计算，返回 (node_data.x, node_data.x + node_data.width - 1, "center")
    """
    # 默认返回控件的边界
    default_start = node_data.x
    default_end = node_data.x + node_data.width - 1
    default_position = "center"
    
    if pil_image is None or node_data is None:
        return default_start, default_end, default_position
    
    # 裁剪文本区域
    cropped_image = _crop_text_region(pil_image, node_data, image_scale, input_tree=input_tree)
    if cropped_image is None:
        return default_start, default_end, default_position
    
    try:
        img_width, img_height = cropped_image.size
        if img_width <= 0 or img_height <= 0:
            return default_start, default_end, default_position
        
        # 转换为numpy数组
        img_array = numpy.array(cropped_image)
        
        # 确保是RGB格式（去掉alpha通道）
        if len(img_array.shape) == 3 and img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]
        
        # 标记每列是否是空白列
        uniform_columns = []
        for x in range(img_width):
            column = img_array[:, x]
            uniform_columns.append(_is_column_uniform(column, max_diff_threshold))
        
        # 找到第一个非空白列（文本开始）
        first_content_col = 0
        for x in range(img_width):
            if not uniform_columns[x]:
                first_content_col = x
                break
        else:
            # 整个区域都是空白，返回默认值
            return default_start, default_end, default_position
        
        # 找到最后一个非空白列（文本结束）
        last_content_col = img_width - 1
        for x in range(img_width - 1, -1, -1):
            if not uniform_columns[x]:
                last_content_col = x
                break
        
        # 计算绝对坐标（考虑缩放比例）
        display_x_start = node_data.x + first_content_col / image_scale
        display_x_end = node_data.x + last_content_col / image_scale
        
        # 计算文本渲染区域相对于控件的位置
        # 文本渲染区域的中心
        display_center = (display_x_start + display_x_end) / 2
        # 控件的中心
        elem_center = node_data.x + node_data.width / 2
        # 容差阈值
        center_tolerance = 5
        
        if abs(display_center - elem_center) <= center_tolerance:
            text_display_position = "center"
        elif display_center < elem_center:
            text_display_position = "left"
        else:
            text_display_position = "right"
        
        return display_x_start, display_x_end, text_display_position
        
    except Exception as e:
        _logger.warning(f"计算文本渲染区域失败: {e}")
        return default_start, default_end, default_position


# ============================================================================
# 平台判断函数
# ============================================================================

def _is_web_platform(context_share_data: Optional[Dict[str, Any]]) -> bool:
    """
    检查目标平台是否为 Web 平台（H5/React/Vue）
    
    :param context_share_data: 上下文共享数据
    :return: 是否为 Web 平台
    """
    if context_share_data is None:
        # 默认情况下（没有平台信息），也执行去除逻辑
        return True
    
    code_type = context_share_data.get("code_type")
    if code_type is None:
        # 没有指定平台，默认为 Web 平台
        return True
    
    return code_type in _WEB_PLATFORMS

# ============================================================================
# 文本高度去除函数
# ============================================================================


def remove_text_height(input_tree, uid, context_share_data: Optional[Dict[str, Any]] = None):
    """
    去除文本高度（适用于 Web/H5/React/Vue 平台）
    
    去除逻辑：
    1. 转码目标平台是 web、H5、react、vue
    2. 计算文本行数 row_cnt，用纯图像处理扫描文本容器截图区域横向空隙的方式
       row_cnt = 中间空隙区域数量 + 1
    3. 根据 lineHeight 计算 display_height：
       - 如果 lineHeight 单位 px：display_height = lineHeight * row_cnt
       - 如果 lineHeight 没有单位：display_height = lineHeight * font_size * row_cnt
    4. 如果 abs(display_height - text_height) <= 1，则去除高度
    
    注意：不再局限于容器只包含一个文本的情况
    
    返回值：
    - True: 成功移除了高度
    - False: 未移除高度
    """
    current_node = input_tree.get_node(uid)
    if current_node is None:
        return False
    
    # 检查是否是文本节点
    if current_node.data.src.type != dsl_enum.ComponentType.TEXT and current_node.data.src.type != dsl_enum.ComponentType.CONTAINER_RICH:
        return False

    # 检查是否有 style 对象
    if current_node.data.src.style is None:
        return False
    
    # 检查是否为 Web 平台
    if not _is_web_platform(context_share_data):
        return False
    
    # 获取文本高度
    text_height = current_node.data.height
    if text_height <= 0:
        return False
    
    # 获取 font_size
    font_size = 14.0  # 默认字体大小
    if current_node.data.src.style and current_node.data.src.style.font_size:
        font_size = _parse_font_size(current_node.data.src.style.font_size)
    
    # 获取 line_height
    line_height_value = None
    if current_node.data.src.style:
        line_height_value = current_node.data.src.style.line_height
    
    # 解析 line_height
    line_height_num, has_px_unit = _parse_line_height(line_height_value)
    
    # 如果没有 line_height，无法计算，跳过
    if line_height_num is None:
        return False
    
    # 计算文本行数（使用图像处理）
    row_cnt = 1
    if context_share_data is not None:
        pil_image = context_share_data.get('pil_image')

        if pil_image is not None:
            # 裁剪文本区域
            cropped_image = _crop_text_region(pil_image, current_node.data, input_tree=input_tree)
            if cropped_image is not None:
                # 获取文本内容（单字符时直接返回行数 1）
                text_content_rh = None
                if current_node.data.src.type == dsl_enum.ComponentType.TEXT and getattr(
                    current_node.data.src, "props", None
                ):
                    text_content_rh = getattr(current_node.data.src.props, "text", None)
                elif current_node.data.src.type == dsl_enum.ComponentType.CONTAINER_RICH:
                    text_content_rh = _collect_rich_text_content(current_node)
                row_cnt = _calc_text_row_count_by_image(
                    cropped_image, font_size_px=font_size, text_content=text_content_rh
                )
                _logger.debug(f"文本节点 {uid} 图像检测行数: {row_cnt}")
    
    # 计算 display_height
    if has_px_unit:
        # lineHeight 有 px 单位：display_height = lineHeight * row_cnt
        display_height = line_height_num * row_cnt
    else:
        # lineHeight 没有单位（是倍数）：display_height = lineHeight * font_size * row_cnt
        display_height = line_height_num * font_size * row_cnt

    # 特殊场景：非多行且 display_height < text_height 且 line_height < text_height 且 vertical_align 为 center
    '''
    if _try_remove_text_height_vertical_center_special_case(
        current_node,
        uid,
        text_height,
        line_height_value,
        line_height_num,
        has_px_unit,
        font_size,
        row_cnt,
        display_height,
    ):
        return True
    '''
    # 检查是否满足去除条件
    if abs(display_height - text_height) <= 0.1:
        current_node.data.src.style.height = None
        current_node.data.extra_dict["edit_height"] = 0
        _logger.debug(f"去除文本高度: uid={uid}, text_height={text_height}, display_height={display_height}, row_cnt={row_cnt}")
        return True
    
    return False


# 保持向后兼容的别名
_remove_text_height = remove_text_height


# ============================================================================
# 文本宽度去除辅助函数
# ============================================================================

def _to_pt_str(value):
    """将数值转换为像素字符串"""
    if value is None:
        return None
    return f"{round(value, 1)}px"


def _flex_enum_to_str(enum_value):
    """将枚举值转换为字符串"""
    if hasattr(enum_value, 'value'):
        return enum_value.value
    return enum_value


def _has_no_sibling_on_left_right(input_tree, current_node):
    """
    检查当前节点的左边和右边是否没有其他元素
    
    Args:
        input_tree: 树结构
        current_node: 当前节点
    
    Returns:
        bool: 如果左右都没有其他元素返回 True
    """
    current_uid = current_node.data.uid
    siblings = input_tree.siblings(current_uid)
    
    if not siblings:
        return True
    
    current_x = current_node.data.x
    current_right = current_x + current_node.data.width
    current_y = current_node.data.y
    current_bottom = current_y + current_node.data.height
    
    for sibling in siblings:
        sibling_x = sibling.data.x
        sibling_right = sibling_x + sibling.data.width
        sibling_y = sibling.data.y
        sibling_bottom = sibling_y + sibling.data.height
        
        # 检查垂直方向是否有重叠
        vertical_overlap = not (sibling_bottom <= current_y or sibling_y >= current_bottom)
        
        if vertical_overlap:
            # 检查是否在左边或右边
            if sibling_right <= current_x or sibling_x >= current_right:
                continue
            return False
    
    return True


def _has_no_sibling_on_right(input_tree, current_node):
    """
    检查当前节点的右边是否没有其他元素
    
    Args:
        input_tree: 树结构
        current_node: 当前节点
    
    Returns:
        bool: 如果右边没有其他元素返回 True
    """
    current_uid = current_node.data.uid
    siblings = input_tree.siblings(current_uid)
    
    if not siblings:
        return True
    
    current_right = current_node.data.x + current_node.data.width
    current_y = current_node.data.y
    current_bottom = current_y + current_node.data.height
    
    for sibling in siblings:
        sibling_x = sibling.data.x
        sibling_y = sibling.data.y
        sibling_bottom = sibling_y + sibling.data.height
        
        # 检查垂直方向是否有重叠
        vertical_overlap = not (sibling_bottom <= current_y or sibling_y >= current_bottom)
        
        if vertical_overlap:
            # 检查是否在右边
            if sibling_x >= current_right:
                return False
    
    return True


def _has_no_sibling_on_left(input_tree, current_node):
    """
    检查当前节点的左边是否没有其他元素
    
    Args:
        input_tree: 树结构
        current_node: 当前节点
    
    Returns:
        bool: 如果左边没有其他元素返回 True
    """
    current_uid = current_node.data.uid
    siblings = input_tree.siblings(current_uid)
    
    if not siblings:
        return True
    
    current_x = current_node.data.x
    current_y = current_node.data.y
    current_bottom = current_y + current_node.data.height
    
    for sibling in siblings:
        sibling_right = sibling.data.x + sibling.data.width
        sibling_y = sibling.data.y
        sibling_bottom = sibling_y + sibling.data.height
        
        # 检查垂直方向是否有重叠
        vertical_overlap = not (sibling_bottom <= current_y or sibling_y >= current_bottom)
        
        if vertical_overlap:
            # 检查是否在左边
            if sibling_right <= current_x:
                return False
    
    return True

# 检测文本渲染宽度是否占据文本本身宽度
def _is_text_rendering_width_full(current_node):
    """
    检测文本渲染宽度是否基本占满文本控件宽度
    
    支持 TEXT 与 CONTAINER_RICH：TEXT 从 props.text 取内容，CONTAINER_RICH 从子节点收集文本。
    
    Args:
        current_node: 当前文本节点（TEXT 或 CONTAINER_RICH）
    
    Returns:
        bool: 如果文本渲染宽度占比在 0.9 ~ 1.11 之间返回 True
    """
    src = current_node.data.src
    if not hasattr(src, 'style') or not src.style:
        return False

    if src.type == dsl_enum.ComponentType.TEXT:
        if not hasattr(src, 'props') or not hasattr(src.props, 'text'):
            return False
        text_content = src.props.text or ""
    elif src.type == dsl_enum.ComponentType.CONTAINER_RICH:
        text_content = _collect_rich_text_content(current_node)
    else:
        return False

    if not text_content:
        return False

    font_size = _parse_font_size(src.style.font_size)
    estimated_width = _estimate_text_width(text_content, font_size)
    if current_node.data.width > 0 and 0.9 < estimated_width / current_node.data.width <= 1.11:
        return True
    return False


# ============================================================================
# 文本宽度去除函数
# ============================================================================


# 父容器内「与文本纵坐标区间有重叠」的最右节点距离父容器右边的阈值（<= 该值时设置 nowrap）
_NOWRAP_RIGHT_EDGE_THRESHOLD = 1.0


def _try_set_text_nowrap_when_trailing(
    input_tree, current_uid, context_share_data: Optional[Dict[str, Any]] = None
) -> None:
    """
    文本属性添加：当单行文本且渲染宽度与文本宽度基本一致，且与文本纵坐标区间有重叠的
    父容器子节点中，最右边节点距离父容器右边 <= 1 时，设置 white_space = "nowrap"。

    条件：
    1. 当前为单行文本
    2. 渲染宽度与文本宽度基本一致（_is_text_rendering_width_full）
    3. 父容器中与文本纵坐标区间有重叠的所有子节点里，最右边节点的右边缘距父容器右边 <= 1

    Args:
        input_tree: 树结构
        current_uid: 当前文本节点 uid
        context_share_data: 上下文共享数据（用于多行判断等）
    """
    current_node = input_tree.get_node(current_uid)
    if current_node is None:
        return
    if current_node.data.src.type != dsl_enum.ComponentType.TEXT and current_node.data.src.type != dsl_enum.ComponentType.CONTAINER_RICH:
        return
    if current_node.data.src.style is None:
        return
    if _is_text_multiline(current_node, context_share_data, input_tree=input_tree):
        return
    if not _is_text_rendering_width_full(current_node):
        return

    parent_node = input_tree.parent(current_uid)
    if parent_node is None:
        return

    parent_x = parent_node.data.x
    parent_width = parent_node.data.width
    parent_right = parent_x + parent_width

    text_y = current_node.data.y
    text_bottom = text_y + current_node.data.height

    # 与文本纵坐标区间有重叠的节点：父容器的直接子节点中 y 区间与文本重叠的（含当前文本节点）
    siblings = input_tree.siblings(current_uid)
    rightmost_right = current_node.data.x + current_node.data.width
    for sibling in siblings:
        sy = sibling.data.y
        s_bottom = sy + sibling.data.height
        if s_bottom <= text_y or sy >= text_bottom:
            continue
        s_right = sibling.data.x + sibling.data.width
        if s_right > rightmost_right:
            rightmost_right = s_right
    # 当前节点自身也参与最右比较，上面已用 current 初始化 rightmost_right

    distance_to_parent_right = parent_right - rightmost_right
    if distance_to_parent_right <= _NOWRAP_RIGHT_EDGE_THRESHOLD:
        current_node.data.src.style.white_space = "nowrap"


def remove_text_width_in_column(input_tree, current_uid, context_share_data: Optional[Dict[str, Any]] = None):
    """
    根据文本相对父容器的位置，移除文本节点的宽度设置
    
    改进逻辑：
    1. 使用文本相对父容器的位置（偏左、居中、偏右）替代 text_align 属性判断
    2. 只有当 _should_be_center_aligned 且非多行时才修改 text_align
    3. 文本居中且左右没有其他元素时，如果左右边距 <= ADJUST_WIDTH_MARGIN，去除宽度后计算 margin
    4. 使用图像处理方式计算文本实际渲染区域，辅助判断文本位置
    
    返回值：
    - True: 成功修改了宽度
    - False: 未修改宽度
    """
    current_node = input_tree.get_node(current_uid)
    if current_node is None:
        return False
    have_brother = len(input_tree.siblings(current_uid)) > 0
    # 检查是否是文本节点
    if current_node.data.src.type != dsl_enum.ComponentType.TEXT and current_node.data.src.type != dsl_enum.ComponentType.CONTAINER_RICH:
        return False
    if current_node.data.src.type == dsl_enum.ComponentType.TEXT and len(
            input_tree.children(current_uid)) >= 1:  # 文本的子节点包含其他控件时候宽度保留
        return False
    # 检查是否有 style 对象
    if current_node.data.src.style is None:
        return False
    # 获取父节点
    parent_node = input_tree.parent(current_uid)
    if parent_node is None:
        return False

    _try_set_text_nowrap_when_trailing(input_tree, current_uid, context_share_data)
    
    # 获取 extra_dict 中的 new_x 和 new_width
    extra_dict = current_node.data.extra_dict
    
    parent_x = parent_node.data.x
    parent_width = parent_node.data.width
    parent_right = parent_x + parent_width
    
    # 计算当前节点的左右边距
    current_x = current_node.data.x
    current_width = current_node.data.width
    current_right = current_x + current_width
    left_margin = current_x - parent_x
    right_margin = parent_right - current_right
    # 减去父容器的 padding，得到相对于内容区的有效 margin（CSS 中 margin 相对父容器内容框）
    padding_left, padding_right, _, _ = get_parent_padding(parent_node)
    effective_left_margin =   float(left_margin) - float(padding_left)
    effective_right_margin =  float(right_margin) - float(padding_right)

    # 使用文本相对父容器的位置判断（偏左、居中、偏右）
    text_position = _get_text_position_relative_to_parent(current_node, parent_node)
    
    # 使用图像处理方式计算文本渲染区域
    display_x_start_offset = current_x
    display_x_end_offset = current_x + current_width - 1
    text_display_position = "center"
    
    if context_share_data is not None:
        pil_image = context_share_data.get('pil_image')
        image_scale = 1
        if pil_image is not None:
            display_x_start_offset, display_x_end_offset, text_display_position = _calc_text_display_x_range(
                pil_image, current_node.data, image_scale, input_tree=input_tree
            )
    # 检查是否为多行文本
    is_multiline = _is_text_multiline(current_node, context_share_data, input_tree=input_tree)
    # 根据文本相对父容器的位置检查条件
    should_remove_width = False
    
    # 条件1：文本控件区域居中，文本渲染位置居中
    if text_position == "center" and text_display_position == "center":
        # 只有当 _should_be_center_aligned 且非多行时才修改 text_align
        if  not is_multiline :
            current_node.data.src.style.text_align = "center"
        # 条件：文本居中且左右没有其他元素
        no_sibling_on_sides = _has_no_sibling_on_left_right(input_tree, current_node)
        if no_sibling_on_sides:
            should_remove_width = True
            current_node.data.src.style.width = None
            
            # 如果左右边距 <= ADJUST_WIDTH_MARGIN，去除宽度后计算 margin_left 和 margin_right（使用有效 margin，已扣除父 padding）
            if left_margin <= ADJUST_WIDTH_MARGIN and right_margin <= ADJUST_WIDTH_MARGIN and is_multiline:#多行文本处理
                if abs(effective_left_margin) > 0.1:
                    current_node.data.src.style.margin_left = _to_pt_str(effective_left_margin)
                if abs(effective_right_margin) > 0.1:
                    current_node.data.src.style.margin_right = _to_pt_str(effective_right_margin)
                current_node.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
            else:
                if have_brother is False:
                    parent_node.data.src.style.align_items = _flex_enum_to_str(dsl_enum.AlignItems.CENTER)
                elif parent_node.data.src.style.align_items != _flex_enum_to_str(dsl_enum.AlignItems.CENTER):
                    current_node.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.CENTER)

    # 条件2：(text_position == "center" 或 text_position == "left") 且 文本渲染左边缘与控件左边缘距离 <= 5
    elif (text_position == "center" or text_position == "left") and (display_x_start_offset - current_x) <= 5:
        # 条件：元素偏左且右边没有其他元素
        no_sibling_on_right = _has_no_sibling_on_right(input_tree, current_node)
        if no_sibling_on_right:
            current_node.data.src.style.width = None
            if abs(effective_left_margin) > 0.1:
                current_node.data.src.style.margin_left = _to_pt_str(effective_left_margin)
            # 当右间距 <= ADJUST_WIDTH_MARGIN 时，计算 margin_right（使用有效 margin，已扣除父 padding）
            if right_margin <= ADJUST_WIDTH_MARGIN  and is_multiline and abs(effective_right_margin) > 0.1:
                current_node.data.src.style.margin_right = _to_pt_str(effective_right_margin)
            if have_brother is False:
                parent_node.data.src.style.align_items = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
            elif parent_node.data.src.style.align_items != _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START):
                current_node.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_START)
            should_remove_width = True
    
    # 条件3：text_position == "right" 且 控件右边缘与文本渲染右边缘距离 <= 5
    elif text_position == "right" and (current_x + current_width - 1 - display_x_end_offset) <= 5:
        # 条件：元素偏右且左边没有其他元素
        no_sibling_on_left = _has_no_sibling_on_left(input_tree, current_node)
        if no_sibling_on_left:
            current_node.data.src.style.width = None
            if abs(effective_right_margin) > 0.1:
                current_node.data.src.style.margin_right = _to_pt_str(effective_right_margin)
            if left_margin <= ADJUST_WIDTH_MARGIN  and is_multiline and abs(effective_left_margin) > 0.1:
                current_node.data.src.style.margin_left = _to_pt_str(effective_left_margin)
            if have_brother is False:
                parent_node.data.src.style.align_items = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
            elif parent_node.data.src.style.align_items != _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END):
                current_node.data.src.style.align_self = _flex_enum_to_str(dsl_enum.AlignItems.FLEX_END)
            should_remove_width = True
    
    # 先注释，看起来暂时用不上了
        # 恢复已置为 None 的 width，与当前节点 data.width 一致

    # 如果满足条件，将 width 设置为 None，并设置 extra_dict["edit_width"] = 0
    if should_remove_width:
        extra_dict["edit_width"] = 0
        return True

    return False

def remove_text_width_in_row(input_tree, current_uid, context_share_data: Optional[Dict[str, Any]] = None):
    """
    去除行布局中的文本宽度
    
    只处理以下情况：
    - 单行文本（非多行）
    - 文本渲染宽度基本占满控件宽度
    - 文本字符个数 >= 4
    
    去除宽度的条件：
    1. 如果 margin_left="auto" 且 margin_right=固定值，并且 text_align!="right"，则去除文本宽度
    2. 如果文本最右边没有其他控件，且只计算了 margin_left，text_align == None 或 "left"，则去除宽度
    3. 如果只计算了 margin_left，没有计算 margin_right，且 text_align == None 或 "left"，则去除文本宽度
    
    返回值：
    - True: 成功修改了宽度
    - False: 未修改宽度
    """
    current_node = input_tree.get_node(current_uid)
    if current_node is None:
        return False
    parent_node = input_tree.parent(current_uid)

    if current_node.data.src.type != dsl_enum.ComponentType.TEXT and current_node.data.src.type != dsl_enum.ComponentType.CONTAINER_RICH:
        return False
    if parent_node is not None:
        _try_set_text_nowrap_when_trailing(input_tree, current_uid, context_share_data)
    # 检查是否是文本节点
    # 文本的子节点包含其他控件时宽度保留
    if len(input_tree.children(current_uid)) >= 1:
        return False
    
    # 检查是否有 style 对象
    if current_node.data.src.style is None:
        return False


    # 检查是否为多行文本 - 只处理单行
    if _is_text_multiline(current_node, context_share_data, input_tree=input_tree):
        return False
    
    # 检查文本是否基本占满控件宽度
    if not _is_text_rendering_width_full(current_node):
        return False

    # 获取 extra_dict
    extra_dict = current_node.data.extra_dict

    # 条件1：
    should_remove_width = True

    # 如果满足条件，去除宽度
    if should_remove_width:
        current_node.data.src.style.width = None
        extra_dict["edit_width"] = 0
        return True
    
    return False


# 保持向后兼容的别名
_remove_text_width_in_column = remove_text_width_in_column
_remove_text_width_in_row = remove_text_width_in_row