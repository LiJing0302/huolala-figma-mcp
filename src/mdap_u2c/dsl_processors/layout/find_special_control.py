from PIL import Image

import os
import io

import cv2
import numpy
import logging
import traceback

from mdap_u2c.dsl_processors.cv_module import find_color, calc_similarity, find_image
from mdap_u2c.dsl_processors.layout import gen_tree, ai_type_def, calc_layout_position
from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model
from mdap_u2c.utils import component_style_utils
from mdap_u2c.utils.component_style_utils import get_border_radii

from mdap_u2c.dsl_processors.layout import remove_redundancy
from mdap_u2c.models.dsl_model import Style
from mdap_u2c.utils import path_config
from mdap_u2c.utils.download_file import get_image_by_url
from mdap_u2c.utils.component_style_utils import convert_str_to_float

_logger = logging.getLogger("find_special_control")

BOTTOM_BAR_ID = 'layout_bottom_bar'
IOS_HOME_BAR = 34
dp_factor = 1
IOS_STATUS_HEIGHT = 44

MAX_NAVBAR_HEIGHT = IOS_STATUS_HEIGHT + 56
MIN_NAVBAR_HEIGHT = IOS_STATUS_HEIGHT + 30

BOTTOMBAR_IMAGE_DIR = path_config.getAssetsImagesDir() + '/bottombar/'


def calc_min_container_tree(input_list):
    min_x = 9999999
    min_y = 9999999
    max_x = 0
    max_y = 0

    for i, sub_elem in enumerate(input_list):
        elem = sub_elem.data
        if elem.x < min_x:
            min_x = elem.x
        if elem.y < min_y:
            min_y = elem.y
        if elem.x + elem.width > max_x:
            max_x = elem.x + elem.width
        if elem.y + elem.height > max_y:
            max_y = elem.y + elem.height
    return min_x, min_y, max_x - min_x, max_y - min_y


def move_to_bottom_bar(input_tree, current_uid, root_width, root_height, bottombar_height):
    move_node_list = list()
    if current_uid == input_tree.root:
        parent_value = input_tree.get_node(current_uid).data
        min_x = 0
        min_y = parent_value.height - bottombar_height
        width = parent_value.width
        height = bottombar_height

        container1 = gen_tree.UIControl(min_x, min_y, width, height, BOTTOM_BAR_ID)
        container_component = dsl_model.ContainerComponent(id=BOTTOM_BAR_ID, parent_id=None,
                                                          layout=None, style=Style(), props=None, children=[], figma=None)

        container1.extra_dict['desc'] = 'bottom_bar'
        container1.ai_type = ai_type_def.AI_TYPE.BOTTOM_BAR.value
        container1.src = container_component
        input_tree.create_node(container1.uid, container1.uid, parent=current_uid, data=container1)

    children_list = input_tree.children(current_uid)
    if len(children_list) != 0:
        for i, sub_elem in enumerate(children_list):
            elem = sub_elem.data
            if elem.uid == BOTTOM_BAR_ID:
                continue
            if elem.x <= 12 and abs(elem.width - root_width) <= 24:
                if elem.y >= root_height - bottombar_height and elem.x <= 0.01 and abs(elem.width - root_width) <= 0.1:
                    input_tree.move_node(elem.uid, BOTTOM_BAR_ID)
                    elem.extra_dict['move'] = 1
                    move_node_list.append(elem)
                elif (elem.y + elem.height) > root_height - bottombar_height:
                    sub_move_node_list = move_to_bottom_bar(input_tree, elem.uid, root_width, root_height,
                                                            bottombar_height)
                    move_node_list.extend(sub_move_node_list)

    return move_node_list


def find_bottombar_height(origImage, templateDir,homebar_height):
    if origImage is None:
        return 0
    max_simularity = 0
    result_height = 0
    result_filename = ''
    files = os.listdir(templateDir)
    imageList = list()
    for fileName in files:
        if fileName.endswith("png") or fileName.endswith("jpg"):  # 固定file extension，避免使用.DS_Store
            filePath = templateDir + fileName
            template_img = Image.open(filePath)
            if homebar_height >0 :
                temp_width,temp_height = template_img.size
                template_img = template_img.crop((0,0,temp_width,temp_height - homebar_height))
            template_size = template_img.size
            origin_size = origImage.size
            factor = origin_size[0] / template_size[0]
            newsize = (int(origin_size[0] / factor), int(origin_size[1] / factor))
            obj_img = origImage.resize(newsize)
            ojb_img2 = obj_img.crop([0, newsize[1] - template_size[1], newsize[0], newsize[1]])  #
            result = calc_similarity.calc_ssim(ojb_img2, template_img)
            if result > max_simularity:
                max_simularity = result
                result_height = template_size[1]
                result_filename = fileName
    _logger.info('最相似的图：' + fileName + ',相似度:' + str(max_simularity))
    if max_simularity < 0.90:
        return 0
    return result_height


def find_bottom_bar(pil_image,homebar_height):
    return find_bottombar_height(pil_image, BOTTOMBAR_IMAGE_DIR,homebar_height)


def move_bottombar_elem(input_tree, bottombar_height, root_height, current_uid, move_node_list):
    current_data = input_tree.get_node(current_uid).data
    if current_data.y >= root_height - bottombar_height:
        if current_data.seq >= 0 and len(move_node_list) > 0 and move_node_list[0].seq < current_data.seq:
            current_data.extra_dict['move'] = 1
            if input_tree.get_node(move_node_list[0].uid) is None:
                _logger.warning('节点为空')
            input_tree.move_node(current_data.uid, move_node_list[0].uid)
    else:
        children_list = input_tree.children(current_uid)
        for i, elem in enumerate(children_list):
            move_bottombar_elem(input_tree, bottombar_height, root_height, elem.data.uid, move_node_list)


def change_bottom_bar_location(input_tree, input_id):
    current_data = input_tree.get_node(input_id).data
    current_data.y = current_data.y + IOS_HOME_BAR

    children_list = input_tree.children(input_id)
    if len(children_list) != 0:
        for i, elem in enumerate(children_list):
            change_bottom_bar_location(input_tree, elem.data.uid)


def create_bottom_bar(input_tree, bottombar_height):
    root_id = input_tree.root
    parent_value = input_tree.get_node(root_id).data
    root_width = parent_value.width
    root_height = parent_value.height
    move_node_list = move_to_bottom_bar(input_tree, root_id, root_width, root_height, bottombar_height)

    move_bottombar_elem(input_tree, bottombar_height, root_height, root_id, move_node_list)
    children_list = input_tree.children(BOTTOM_BAR_ID)
    if len(children_list) >= 1:
        change_bottom_bar_location(input_tree, BOTTOM_BAR_ID)
    if len(children_list) >= 2:
        min_x, min_y, min_width, min_height = calc_min_container_tree(children_list)
        bottom_value = input_tree.get_node(BOTTOM_BAR_ID).data
        bottom_value.x = min_x
        bottom_value.y = min_y
        bottom_value.width = min_width
        bottom_value.height = min_height
        calc_layout_position.change_bottombar_coordinate(bottom_value, parent_value)
    elif len(children_list) == 1:
        elem = children_list[0].data
        input_tree.move_node(elem.uid, root_id)
        input_tree.remove_node(BOTTOM_BAR_ID)
        write_del_bottom_flag(input_tree,BOTTOM_BAR_ID)
        elem.ai_type = ai_type_def.AI_TYPE.BOTTOM_BAR.value
        calc_layout_position.change_bottombar_coordinate(elem, parent_value)

    elif len(children_list) == 0:
        input_tree.remove_node(BOTTOM_BAR_ID)
        write_del_bottom_flag(input_tree,BOTTOM_BAR_ID)

def find_homebar_control(PIL_img, input_tree):
    real_homebar_height = 0
    if PIL_img is None:
        return False, list(), False, 0
    home_id_list = list()
    hombar_list = find_home_bar(PIL_img, path_config.getAssetsImagesDir() + '/homebar/')
    need_crop_home_bar = False
    home_area_control_list = list()
    if len(hombar_list) > 0:
        need_crop_home_bar = True  # 有homebar，先标记要裁剪.简化处理,homebar的直接裁减,如果需要展示homebar,设计提供拉平的设计稿
        home_id_list, real_homebar_height = find_home_bar_arealist(input_tree, input_tree.root, home_area_control_list)
    return len(hombar_list) > 0, home_id_list, need_crop_home_bar, real_homebar_height


def is_control_in_homebar_area(input_tree, current_uid, homebar_height):
    root_node_data = input_tree.get_node(input_tree.root).data
    origin_height = root_node_data.extra_dict["origin_height"]
    root_width = root_node_data.width
    max_height = origin_height - homebar_height
    elem_data = input_tree.get_node(current_uid).data
    if elem_data.y >= max_height:  #标注homebar高度=34 ，直接删除
        return True
    elif elem_data.y >= max_height - 4:
        cross_result = gen_tree.judge_box2((elem_data.x, elem_data.y, elem_data.width, elem_data.height),
                                            (0, origin_height - IOS_HOME_BAR, root_width, IOS_HOME_BAR))
        if cross_result > 0.8:  # 有些设计稿home建高度为37，并非34,设定一样阈值
            return True
    elif elem_data.y + elem_data.height > max_height:  #裁剪背景等容器高度
        elem_data.height = max_height - elem_data.y
        elem_data.extra_dict['desc'] =  "homebar_cover"
        if elem_data.src.type == dsl_enum.ComponentType.IMAGE:
            crop_image_and_upload(elem_data.src, 0, elem_data.height)
    return False


def is_control_on_status_bar(input_tree, current_uid):
    elem_data = input_tree.get_node(current_uid).data
    if elem_data.y + elem_data.height <= IOS_STATUS_HEIGHT:
        return True
    return False


def bg_image_remove_sys_bar(pil_img, top_bar_height, crop_home_bar, real_homebar_height):
    try:
        if crop_home_bar == 1:
            home_bar_height = real_homebar_height
        else:
            home_bar_height = 0

        origin_size = pil_img.size
        new_bottom_pt = origin_size[1] - home_bar_height * dp_factor
        crop_img = pil_img.crop([0, top_bar_height * dp_factor, origin_size[0], new_bottom_pt])
        return crop_img
    except Exception as e:
        _logger.error('bg_image_remove_sys_bar:' + traceback.format_exc())
        return None


def crop_image_and_upload(image_origin_data, new_y1, new_y2=None):
    _logger.warning(f"图片需要裁剪{image_origin_data.id}")


def adjust_y_because_of_top_bar(input_tree, current_uid, top_height):
    elem_data = input_tree.get_node(current_uid).data
    y = elem_data.y
    height = elem_data.height
    if y >= top_height:
        y = y - top_height
        elem_data.y = y
    elif y < top_height:
        offset = top_height - y
        new_y = 0
        new_height = elem_data.height - offset
        if new_height <= 0:
            return True
        elem_data.y = new_y
        elem_data.height = new_height
        elem_data.extra_dict['desc'] = "topbar_adjust_height"
        if elem_data.src.type == dsl_enum.ComponentType.IMAGE:
            crop_image_and_upload(elem_data.src, offset)
    return False


def judge_translucent_sys_bar(statusbar_img):
    if find_color.is_colorful_image(statusbar_img):
        return True
    return False


def get_status_icon_color_type_str(PIL_img, img_list):
    width, height = PIL_img.size
    if len(img_list) > 0 and img_list[0].y >= 2 and (img_list[0].x + img_list[0].width / 2) * dp_factor < width:
        pil_pt_image = PIL_img.crop([(img_list[0].x + img_list[0].width / 2) * dp_factor, img_list[0].y,
                                     (img_list[0].x + img_list[0].width / 2) * dp_factor + 1, img_list[0].y + 1])

        cv_image = cv2.cvtColor(numpy.asarray(pil_pt_image), cv2.COLOR_RGB2GRAY)
        if cv_image[0, 0] >= 127:
            return 'dark'
        else:
            return 'light'
    return 'dark'


def get_top_bar_heigth(PIL_img, input_tree):
    is_translucent_top_bar = False
    if PIL_img is None:
        return 0,is_translucent_top_bar
    top_bar_height = 0
    root_node = input_tree.get_node(input_tree.root)
    root_width = root_node.data.width
    img_list, statusbar_img = find_status_bar(PIL_img, path_config.getAssetsImagesDir() + '/statusbar/')
    if len(img_list) > 0:
        if judge_translucent_sys_bar(statusbar_img):
            is_translucent_top_bar = True
            top_bar_height = 0
            root_node.data.extra_dict['isFullScreen'] = True
            root_node.data.extra_dict['statusBarStyle'] = get_status_icon_color_type_str(PIL_img, img_list)
            return top_bar_height,is_translucent_top_bar
        top_bar_height += IOS_STATUS_HEIGHT
        _logger.info('find iOS status bar!')
        nav_bar_height = get_nav_bar_height(PIL_img, input_tree, root_width, MIN_NAVBAR_HEIGHT, MAX_NAVBAR_HEIGHT,
                                            IOS_STATUS_HEIGHT)
        if nav_bar_height == 0:
            nav_bar_height = get_nav_bar_height(PIL_img, input_tree, 24, IOS_STATUS_HEIGHT + 22, IOS_STATUS_HEIGHT + 40,
                                                IOS_STATUS_HEIGHT)


    else:
        status_height = get_status_bar_height(PIL_img, input_tree,
                                              path_config.getAssetsImagesDir() + '/android_statusbar/', root_width)
        if status_height == 0:  #比较极端的情况，没有状态栏，可能有导航栏。
            _logger.warning('not find status bar')
            nav_bar_height = get_nav_bar_height(PIL_img, input_tree, 24, 22, 88,
                                                status_height)
            return nav_bar_height,is_translucent_top_bar
        top_bar_height += status_height
        nav_bar_height = get_nav_bar_height(PIL_img, input_tree, 24, status_height + 22, status_height + 40,
                                            status_height)

    _logger.info('navbar height:' + str(nav_bar_height))
    top_bar_height += nav_bar_height
    root_node.data.extra_dict['top_bar_height'] = top_bar_height

    return top_bar_height,is_translucent_top_bar


def get_status_bar_height(origImage, input_tree, statusbar_dir, root_width):
    find_result, _ = find_status_bar(origImage, statusbar_dir)
    if len(find_result) >= 1:
        status_y = find_result[0].y
        status_height = find_result[0].height
        if status_y < IOS_STATUS_HEIGHT:
            current_uid, current_height = calc_android_status_bar_height(status_y, status_height, input_tree,
                                                                         root_width,input_tree.root)
            return current_height
    return 0


#计算安卓顶部栏高度（支持状态栏和导航栏）
def calc_android_status_bar_height(y, height, input_tree, root_width,current_uid):
    current_node = input_tree.get_node(current_uid)
    current_height = current_node.data.height
    find_children = len(input_tree.children(current_uid)) > 0
    if find_children:
        children_list = input_tree.children(current_uid)
        for i, elem in enumerate(children_list):
            elem_uid = elem.data.uid
            elem_x = elem.data.x
            elem_y = elem.data.y
            elem_width = elem.data.width
            elem_height = elem.data.height
            if (elem_y == 0 and elem_y + elem_height >= y + height and elem_x == 0 and elem_width == root_width):
                if elem_height <= IOS_STATUS_HEIGHT:
                    return elem_uid, elem_height
                new_uid, new_height = calc_android_status_bar_height(y, height, input_tree, root_width,elem_uid)
                if new_uid != None and new_height <= IOS_STATUS_HEIGHT:
                    return new_uid, new_height
            else:
                continue
    return current_uid, current_height


def find_status_bar(origImage, statusbar_dir):
    origin_size = origImage.size
    newsize = (int(origin_size[0] / dp_factor), int(origin_size[1] / dp_factor))
    obj_img = origImage.resize(newsize)
    ojb_img2 = obj_img.crop([0, 0, newsize[0], IOS_STATUS_HEIGHT])  #
    cv_image = cv2.cvtColor(numpy.asarray(ojb_img2), cv2.COLOR_BGR2GRAY)
    files = os.listdir(statusbar_dir)
    imageList = list()
    for fileName in files:
        if fileName.endswith("jpg") or fileName.endswith("png"):  # 固定file extension，避免使用.DS_Store
            filePath = statusbar_dir + fileName
            template_org = cv2.imread(filePath)
            if template_org.shape[2] == 4:
                # 图像有透明通道
                # 将透明通道设置为白色
                template_org[..., 3] = 255
            template_img = cv2.cvtColor(template_org, cv2.COLOR_BGR2GRAY)  # 模
            subList = find_image.find_image_area(cv_image, template_img, fileName)
            if subList is not None:
                imageList.extend(subList)
    return imageList, ojb_img2


def get_nav_bar_height(origImage, input_tree, root_width, min_nav_height, max_nav_y, status_bar_height):
    navbar_dir = path_config.getAssetsImagesDir() + '/backbutton/'
    origin_size = origImage.size
    newsize = (int(origin_size[0] / dp_factor), int(origin_size[1] / dp_factor))
    obj_img = origImage.resize(newsize)
    ojb_img2 = obj_img.crop([0, 0, newsize[0], IOS_STATUS_HEIGHT + MAX_NAVBAR_HEIGHT])
    cv_image = cv2.cvtColor(numpy.asarray(ojb_img2), cv2.COLOR_BGR2GRAY)
    files = os.listdir(navbar_dir)
    imageList = list()
    for fileName in files:
        if fileName.endswith("jpg") or fileName.endswith("png"):  # 固定file extension，避免使用.DS_Store
            filePath = navbar_dir + fileName
            template_org = cv2.imread(filePath)
            if template_org.shape[2] == 4:
                # 图像有透明通道
                # 将透明通道设置为白色
                template_org[..., 3] = 255
            template_img = cv2.cvtColor(template_org, cv2.COLOR_BGR2GRAY)  # 模
            subList = find_image.find_image_area(cv_image, template_img, fileName)
            if subList is not None:
                imageList.extend(subList)
    if len(imageList) >= 1:
        backbutton_x = imageList[0].x
        backbutton_y = imageList[0].y
        backbutton_width = imageList[0].width
        backbutton_height = imageList[0].height
        navbar_uid, nav_y, nav_height = calc_nav_bar_height(backbutton_x, backbutton_y, backbutton_height, input_tree,
                                                            input_tree.root, root_width, min_nav_height, max_nav_y)
        _logger.info('navbar id:' + navbar_uid)
        if nav_height > max_nav_y:
            return 0
        return nav_height + nav_y - status_bar_height  #iOS_STAUT_HEIGHT
    return 0


def calc_nav_bar_height(x, y, height, input_tree, current_uid, root_width, min_nav_height, max_nav_y):
    current_node = input_tree.get_node(current_uid)
    current_y = current_node.data.y
    current_height = current_node.data.height

    children_list = input_tree.children(current_uid)
    for i, elem in enumerate(children_list):
        elem_uid = elem.data.uid
        elem_x = elem.data.x
        elem_y = elem.data.y
        elem_width = elem.data.width
        elem_height = elem.data.height
        if (elem_y <= y and elem_y + elem_height >= y + height and elem_width >= root_width and elem_x <= x):
            if (elem_y + elem_height) >= min_nav_height and (elem_y + elem_height) <= max_nav_y:
                return elem_uid, elem_y, elem_height
            new_uid, new_y, new_height = calc_nav_bar_height(x, y, height, input_tree, elem_uid, root_width, min_nav_height,
                                                             max_nav_y)
            if new_uid != None and (new_y + new_height) >= min_nav_height and (new_y + new_height) <= max_nav_y:
                return new_uid, new_y, new_height
        else:
            continue
    return current_uid, current_y, current_height

def get_crop_gray_cv_img(pil_image):
    origin_size = pil_image.size
    new_size = (int(origin_size[0] / dp_factor), int(origin_size[1] / dp_factor))
    obj_img = pil_image.resize(new_size)
    ojb_img2 = obj_img.crop([0, new_size[1] - IOS_HOME_BAR, new_size[0], new_size[1]])  #
    
    # 如果图片有透明通道，根据非透明部分的亮度决定透明部分的填充颜色
    if ojb_img2.mode == 'RGBA':
        img_array = numpy.asarray(ojb_img2)
        alpha_channel = img_array[:, :, 3]
        rgb_channels = img_array[:, :, :3]
        
        # 获取非透明像素的掩码 (alpha > 0)
        non_transparent_mask = alpha_channel > 0
        
        if numpy.any(non_transparent_mask):
            # 计算非透明部分的平均亮度
            non_transparent_pixels = rgb_channels[non_transparent_mask]
            avg_brightness = numpy.mean(non_transparent_pixels)
            
            # 如果非透明部分是暗色（亮度 < 128），则透明部分填充白色，反之填充黑色
            fill_color = (255, 255, 255) if avg_brightness < 128 else (0, 0, 0)
        else:
            fill_color = (255, 255, 255)  # 默认填充白色
        
        # 创建填充背景并合成图片
        background = Image.new('RGB', ojb_img2.size, fill_color)
        background.paste(ojb_img2, mask=ojb_img2.split()[3])  # 使用 alpha 通道作为 mask
        ojb_img2 = background
    
    cv_image = cv2.cvtColor(numpy.asarray(ojb_img2), cv2.COLOR_BGR2GRAY)
    return cv_image,new_size

def find_home_bar(origImage, statusbar_dir):
#
    cv_image,new_size = get_crop_gray_cv_img(origImage)
    files = os.listdir(statusbar_dir)
    imageList = list()
    for fileName in files:
        if fileName.endswith("jpg") or fileName.endswith("png"):  # 固定file extension，避免使用.DS_Store
            filePath = statusbar_dir + fileName
            template_org = cv2.imread(filePath)
            if template_org.shape[2] == 4:
                # 图像有透明通道
                # 将透明通道设置为白色
                template_org[..., 3] = 255
            template_img = cv2.cvtColor(template_org, cv2.COLOR_BGR2GRAY)  # 模
            subList = find_image.find_image_area(cv_image, template_img, fileName)
            if subList is not None and len(subList) > 0:
                subList[0].y = subList[0].y + new_size[1] - IOS_HOME_BAR
                imageList.extend(subList)
    return imageList


def children_have_homebar(input_tree, current_uid):
    root_node_data = input_tree.get_node(input_tree.root).data
    current_node_data = input_tree.get_node(current_uid).data
    root_width = root_node_data.width
    root_height = root_node_data.height
    parent_height = current_node_data.width
    parent_y = current_node_data.y
    if parent_height >= 40 or parent_y <= root_height - 40:
        return False

    children_list = input_tree.children(current_uid)
    for i, elem in enumerate(children_list):
        width = elem.data.width
        height = elem.data.height
        center_x = elem.data.x + elem.data.width / 2
        if width == 134 and height == 5 and abs(center_x - root_width / 2) <= 2:
            return True
    return False


def find_home_bar_arealist(input_tree, current_uid, bottom_area_control_list):
    max_value = 0
    max_id = None
    root_node_data = input_tree.get_node(input_tree.root).data
    root_width = root_node_data.width
    root_height = root_node_data.height
    real_home_bar_height = 0
    home_id_list = list()
    current_node_data = input_tree.get_node(current_uid).data
    current_y = current_node_data.y
    current_height = current_node_data.height
    current_x = current_node_data.x
    current_width = current_node_data.width
    if current_y + current_height >= root_height - IOS_HOME_BAR:
        if current_width < root_width and current_height > 5 and current_node_data.src.type != dsl_enum.ComponentType.CONTAINER:
            bottom_area_control_list.append((current_uid, current_x, current_y, current_width, current_height))
        if IOS_HOME_BAR - 12 <= root_height - current_y <= 4 + IOS_HOME_BAR and current_width >= 134 or children_have_homebar(
                input_tree, current_uid):  # 某些设计稿底部栏高度为37，非34,最小的23   某些底部栏宽度为374.5
            home_id_list.append(current_uid)
            real_home_bar_height = root_height - current_y

        children_list = input_tree.children(current_uid)
        for i, elem in enumerate(children_list):
            sub_home_id_list, temp_home_bar_height = find_home_bar_arealist(input_tree, elem.data.uid,
                                                                            bottom_area_control_list)
            if temp_home_bar_height != 0:
                real_home_bar_height = temp_home_bar_height
            if len(sub_home_id_list) > 0:
                home_id_list.extend(sub_home_id_list)
    return home_id_list, real_home_bar_height


def match_text(text, text_list):
    for text_elem in text_list:
        if text_elem == text:
            return True
    return False


def find_texts(input_tree, uid, text_list=["首页", "我的"]):
    children_list = input_tree.children(uid)
    ret = False
    for elem in children_list:
        if elem.data.src.type == dsl_enum.ComponentType.TEXT:
            ret = match_text(elem.data.src.props.text, text_list)
        elif elem.data.src.type == dsl_enum.ComponentType.CONTAINER:
            ret = find_texts(input_tree, elem.data.uid, text_list)
        if ret is True:
            return True
    return ret


def judge_bottombar_by_location(input_tree, uid):
    current_node = input_tree.get_node(uid)
    if current_node is None:
        return False
    root_height = input_tree.get_node(input_tree.root).data.height
    if current_node.data.width == input_tree.get_node(
            input_tree.root).data.width and current_node.data.height >= 50 and current_node.data.height <= 135:
        if abs(current_node.data.y + current_node.data.height - root_height) <= 1:
            return find_texts(input_tree, uid)

    return False


def judge_bottombar_and_bottomfloat_by_layer(input_tree, projection_map):
    float_set = input_tree.get_node(input_tree.root).data.float_control
    for elem_uid in float_set:
        if judge_bottombar_by_location(input_tree, elem_uid):
            child_node = input_tree.get_node(elem_uid)
            child_node.data.extra_dict['nodeLayerName'] = "float_bottombar_move_down"
            child_node.data.ai_type = ai_type_def.AI_TYPE.BOTTOM_BAR.value
            input_tree.move_node(elem_uid, input_tree.root)
            return True
        elif is_float_bottom_window(input_tree, elem_uid, projection_map):
            child_node = input_tree.get_node(elem_uid)
            child_node.data.ai_type = ai_type_def.AI_TYPE.BOTTOM_FLOAT_CONTAINER.value
            input_tree.move_node(elem_uid, input_tree.root)
            return True

    return False


def tree_homebar_remove(input_tree, current_uid, root_height, root_width, home_bar_height, need_crop_home_bar):
    bottombar_height = home_bar_height + 10
    children_list = input_tree.children(current_uid)
    if len(children_list) != 0:
        for i, sub_elem in enumerate(children_list):
            elem = sub_elem.data
            if elem.y >= root_height - bottombar_height:
                if need_crop_home_bar is False:
                    temp_result = is_control_in_homebar_area(input_tree, elem.uid, home_bar_height)
                    if temp_result is True:
                        input_tree.remove_node(elem.uid)
                        write_del_home_flag(input_tree,elem.uid)
            elif (elem.y + elem.height) > root_height - bottombar_height:
                tree_homebar_remove(input_tree, sub_elem.data.uid, root_height, root_width, home_bar_height,
                                    need_crop_home_bar)


def get_bottom_bar(input_tree, parrent_id, root_width, root_height):
    children_list = input_tree.children(parrent_id)
    for i, elem in enumerate(children_list):
        if elem.data.ai_type == ai_type_def.AI_TYPE.BOTTOM_BAR.value:
            return elem
        if elem.data.width == root_width and (elem.data.height + elem.data.y) >= root_height - IOS_HOME_BAR:
            return get_bottom_bar(input_tree, elem.data.uid, root_width, root_height)
    return None


def adjust_y(input_tree, parrent_id, offset):
    children_list = input_tree.children(parrent_id)
    for i, elem in enumerate(children_list):
        elem.data.y = elem.data.y + offset
        if input_tree.children(elem.data.uid) != None:
            adjust_y(input_tree, elem.data.uid, offset)


def bottombar_move(input_tree, find_bottombar):
    root_node_data = input_tree.get_node(input_tree.root).data
    root_width = root_node_data.width
    root_height = root_node_data.height
    if find_bottombar is True:
        bottom_bar_node = get_bottom_bar(input_tree, input_tree.root, root_width, root_height)
        if bottom_bar_node != None:
            children_list = input_tree.children(bottom_bar_node.data.uid)
            for i, elem in enumerate(children_list):
                if elem.data.src.type == dsl_enum.ComponentType.CONTAINER and elem.data.width == root_width and elem.data.y + elem.data.height < bottom_bar_node.data.y + bottom_bar_node.data.height and elem.data.height >= 38:
                    offset = bottom_bar_node.data.y + bottom_bar_node.data.height - elem.data.y + elem.data.height < bottom_bar_node.data.y
                    new_y = bottom_bar_node.data.y + offset
                    new_height = bottom_bar_node.data.height - offset
                    bottom_bar_node.data.y = new_y
                    bottom_bar_node.data.height = new_height

                    adjust_y(input_tree, elem.data.uid, offset)
                    elem.data.ai_type = ai_type_def.AI_TYPE.BOTTOM_BAR.value
                    elem.data.extra_dict["newId"] = "BottomBar"
                    input_tree.move_node(elem.data.uid, input_tree.root)
                    input_tree.remove_node(bottom_bar_node.data.uid)
                    write_del_bottom_flag(input_tree,bottom_bar_node.data.uid)
                    break


def is_float_bottom_window(input_tree, current_uid, projection_map):
    """
    判断是否为浮动底部窗口
    判断条件：
    1. 当前容器的"borderTopLeftRadius"和"borderTopRightRadius"的值不为0
    2. 根据投影矩阵发现它的层级是置顶的
    3. 宽度和根容器宽度一样
    4. 高度<=80
    5. 容器位置比较靠近底部
    """

    # 获取当前节点
    current_node = input_tree.get_node(current_uid)
    if not current_node:
        return False

    current_data = current_node.data
    current_src = current_data.src

    # 获取根容器
    root_node = input_tree.get_node(input_tree.root)
    if not root_node:
        return False

    root_data = root_node.data
    root_width = root_data.width
    root_height = root_data.height

    # 条件1: 检查borderTopLeftRadius和borderTopRightRadius不为0
    top_left_radius, top_right_radius, _, _ =   get_border_radii(current_src)
    top_left_radius = convert_str_to_float(top_left_radius,min(current_data.width, current_data.height))
    top_right_radius = convert_str_to_float(top_right_radius,min(current_data.width, current_data.height))
    if top_left_radius <= 0 or top_right_radius <= 0:
        return False

    # 条件2: 检查层级是否置顶 (seq值越大层级越高)
    # 获取所有节点的seq值，判断当前节点是否在最高层级
    current_seq = current_data.seq
    min_seq = remove_redundancy.get_min_seq_from_map_exclude_rounded_rect(projection_map, current_node)
    # 如果当前容器层级不够高
    if int(current_seq) != min_seq:
        return False

    # 条件3: 宽度和根容器宽度一样
    current_width = current_data.width
    if abs(current_width - root_width) > 1:  # 允许1像素的误差
        return False

    # 条件4: 高度<=80
    current_height = current_data.height
    if current_height > 80:
        return False
    # 条件5: 容器位置比较靠近底部
    # 计算容器底部到根容器底部的距离
    current_y = current_data.y
    current_bottom = current_y + current_height
    root_bottom = root_data.y + root_height
    # 距离底部的距离
    distance_to_bottom = root_bottom - current_bottom
    # 判断是否靠近底部：
    if distance_to_bottom > 0:
        return False

    return True


def remove_sys_bar(input_tree, pil_img):
    top_bar_height,is_translucent_top_bar = get_top_bar_heigth(pil_img, input_tree)
    have_home_bar, home_bar_id_list, need_crop_home_bar, real_homebar_height = find_homebar_control(
        pil_img,
        input_tree)

    new_bg = pil_img

    if top_bar_height > 0 or need_crop_home_bar > 0:
        new_bg = bg_image_remove_sys_bar(pil_img, top_bar_height,
                                                              need_crop_home_bar, real_homebar_height)
    #后端运算根节点高度会变化,先暂存原始值
    input_tree.get_node(input_tree.root).data.extra_dict["origin_height"] = input_tree.get_node(input_tree.root).data.height
    tree_remove_sys_bar(input_tree, input_tree.root, real_homebar_height, need_crop_home_bar, top_bar_height, is_translucent_top_bar)

    return new_bg, top_bar_height, real_homebar_height, is_translucent_top_bar


def tree_remove_sys_bar(input_tree, current_id, home_bar_height, need_crop_home_bar, top_bar_height,is_transluent_status_bar):
    if need_crop_home_bar:
        is_home_bar_elem = is_control_in_homebar_area(input_tree, current_id, home_bar_height)
        if is_home_bar_elem:
            input_tree.remove_node(current_id)
            write_del_home_flag(input_tree,current_id)
            return
    if top_bar_height > 0:
        if adjust_y_because_of_top_bar(input_tree, current_id, top_bar_height):
            input_tree.remove_node(current_id)
            write_del_top_flag(input_tree, current_id)
            return
    elif is_transluent_status_bar :
        if is_control_on_status_bar(input_tree, current_id):
            input_tree.remove_node(current_id)
            write_del_top_flag(input_tree, current_id)
            return
    if component_style_utils.is_rich_text_container(input_tree.get_node(current_id).data.src):
        return
    children_list = input_tree.children(current_id)
    for i, elem in enumerate(children_list):
        tree_remove_sys_bar(input_tree, elem.data.uid, home_bar_height, need_crop_home_bar, top_bar_height,is_transluent_status_bar)


def bottom_bar_layer_process(input_tree, pil_img, projection_map,homebar_height):
    find_bottombar = judge_bottombar_and_bottomfloat_by_layer(input_tree, projection_map['projection_map'])
    if not find_bottombar:
        bottombar_height = find_bottom_bar(pil_img,homebar_height)
        find_bottombar = True
        if bottombar_height > 0:
            _logger.info('create bottom bar!')
            create_bottom_bar(input_tree, bottombar_height)
    bottombar_move(input_tree, find_bottombar)

def write_del_home_flag(input_tree, flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_home" not in json_dict:
        json_dict["del_home"] = []
    json_dict["del_home"].append(flag_id)

def write_del_top_flag(input_tree, flag_id):
        json_dict = input_tree.get_node(input_tree.root).data.extra_dict
        if "del_top" not in json_dict:
            json_dict["del_top"] = []
        json_dict["del_top"].append(flag_id)


def write_del_overflow_flag(input_tree, flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_over" not in json_dict:
        json_dict["del_over"] = []
    json_dict["del_over"].append(flag_id)
def write_del_bottom_flag(input_tree, flag_id):
    json_dict = input_tree.get_node(input_tree.root).data.extra_dict
    if "del_bottom" not in json_dict:
        json_dict["del_bottom"] = []
    json_dict["del_bottom"].append(flag_id)

