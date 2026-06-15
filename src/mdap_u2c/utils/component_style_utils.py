from mdap_u2c.constant import FIGMA_DESIGN_WIDTH
from mdap_u2c.dsl_processors.layout import ai_type_def
from mdap_u2c.enums import dsl_enum


def get_color_alpha(color_str):
    start_index = color_str.find('(')
    end_index = color_str.find(')')
    if start_index != -1 and end_index != -1:
        valueStr = color_str[start_index + 1:end_index]
        split_list = valueStr.split(",")
        if len(split_list) == 4:
            a_value = float(split_list[3])
            return a_value
    return 0

def is_redpoint_bubble(elem_data):
    if elem_data.ai_type == ai_type_def.AI_TYPE.BUBBLE.value or elem_data.ai_type == ai_type_def.AI_TYPE.RED_POINT.value:
        return True
    return False


# 分割线识别,用于后续循环组件抽取
def regconize_split_line(width, height):
    if width < 0.1 or height < 0.1:  # 可能出现直线宽高为0
        return True
    if 0 < width <= 1 and height >= 8 or 0 < height <= 1 and width  >= 32:
        return True


def is_small_or_square_container(component,default_width=50):
    if abs(component.layout.size.width - component.layout.size.height) <= 2 and component.layout.size.width <= default_width:
        return True
    if component.layout.size.width <= 5 or component.layout.size.height <= 5:#5个星星的场景高度刚好10
        return True
    return False


def is_rich_text_container(elem_src):
    if elem_src.type == dsl_enum.ComponentType.CONTAINER_RICH or elem_src.type == dsl_enum.ComponentType.ORDERED_LIST or  elem_src.type == dsl_enum.ComponentType.UNORDERED_LIST:
        return True
    return False


def have_border(component):
    if component.style.border_width is not None and  convert_str_to_float(component.style.border_width,0) > 0 and component.style.border_color is not None:
        return True
    return False


def is_text(componnet):
    if componnet.type == dsl_enum.ComponentType.TEXT:
        return True
    return False


def convert_str_to_int(radus, width):
    """
    将半径值转换为整数
    如果为数字，转成int
    如果为含有百分号的字符串，转成float然后乘width转成int返回
    如果为含有px/pt后缀的字符串，去掉后缀后转成int返回

    Args:
        radus: 半径值，可以是数字或百分比字符串（如 "50%"）或带单位字符串（如 "30.0px"）
        width: 宽度值，用于百分比计算

    Returns:
        int: 转换后的整数值
    """
    if isinstance(radus, (int, float)):
        return int(radus)
    if isinstance(radus, str):
        radus = radus.strip()
        if '%' in radus:
            # 去掉百分号，转成float，除以100得到比例，再乘以width
            percent_value = float(radus.replace('%', '').strip())
            return int(percent_value / 100.0 * width)
        elif 'px' in radus:
            # 去掉px后缀，转成float再转int
            return int(float(radus.replace('px', '').strip()))
        elif 'pt' in radus:
            # 去掉pt后缀，转成float再转int
            return int(float(radus.replace('pt', '').strip()))
        else:
            # 直接转float再转int
            return int(float(radus))
    else:
        # 如果是其他类型，尝试直接转成int
        return int(float(radus))

def convert_str_to_float(radus, width):
    """
    将半径值转换为整数
    如果为数字，转成int
    如果为含有百分号的字符串，转成float然后乘width转成int返回
    如果为含有px/pt后缀的字符串，去掉后缀后转成int返回

    Args:
        radus: 半径值，可以是数字或百分比字符串（如 "50%"）或带单位字符串（如 "30.0px"）
        width: 宽度值，用于百分比计算

    Returns:
        int: 转换后的整数值
    """
    if isinstance(radus, (int, float)):
        return float(radus)
    if isinstance(radus, str):
        radus = radus.strip()
        if '%' in radus:
            # 去掉百分号，转成float，除以100得到比例，再乘以width
            percent_value = float(radus.replace('%', '').strip())
            return percent_value / 100.0 * width
        elif 'px' in radus:
            # 去掉px后缀，转成float再转int
            return float(radus.replace('px', '').strip())
        elif 'pt' in radus:
            # 去掉pt后缀，转成float再转int
            return float(radus.replace('pt', '').strip())
        else:
            # 直接转float再转int
            return float(radus)
    else:
        # 如果是其他类型，尝试直接转成floaat
        return float(radus)

def is_transparent_container(componnet):
    if componnet.type == dsl_enum.ComponentType.CONTAINER:  # and 'children' not in json_dict
        if componnet.style.background is not None:  # 肩膀色,多颜色用这种
            return False
        if componnet.style.background_image is not None:
            return False
        if componnet.style.box_shadow is not None:
            return False
        if componnet.style.border_width is not None and convert_str_to_float(componnet.style.border_width,0) > 0 and componnet.style.border_color is not None:
            return False
        if componnet.style.background_color is not None and get_color_alpha(componnet.style.background_color) >= 0.02:
            return False
        return True


# 返回值:
# 0,不透,1全透 2,半透或者部分区域透明
def is_transparent_control(current_json):
    if current_json.type == dsl_enum.ComponentType.CONTAINER and current_json.style.background is not None:  # 渐变色会有不同背景叠加情况,所以当半透明处理
        return 2
    if  current_json.type == dsl_enum.ComponentType.IMAGE:  # 先假定文本都是透明的.图片场景太多,有半透明,一半区域透明,一半不透明等情况,过于复杂,先当透处理吧
        if is_small_or_square_container(current_json): #小图标当不透明处理.有些红点会盖在图标下面
            return 0
        else:
            return 2
    elif current_json.type == dsl_enum.ComponentType.TEXT or current_json.type == dsl_enum.ComponentType.CONTAINER_RICH:  # 有些富文本后面有个背景色容器,所以复合文本当半透明处理
        return 2
    elif is_transparent_container(current_json) == True:
        return 1
    return 0


def get_border_radii(src):
    """
    从src中提取四个圆角半径值
    返回: (top_left, top_right, bottom_left, bottom_right)
    """
    top_left = top_right = bottom_left = bottom_right = 0
    if src.style.border_radius is not None:
        top_left = top_right = bottom_left = bottom_right = src.style.border_radius
    else:
        if src.style.border_top_right_radius is not None:
            top_right = src.style.border_top_right_radius
        if src.style.border_bottom_right_radius is not None:
            bottom_right = src.style.border_bottom_right_radius
        if src.style.border_bottom_left_radius is not None:
            bottom_left = src.style.border_bottom_left_radius
        if src.style.border_top_left_radius is not None:
            top_left = src.style.border_top_left_radius

    return (top_left, top_right, bottom_left, bottom_right)

