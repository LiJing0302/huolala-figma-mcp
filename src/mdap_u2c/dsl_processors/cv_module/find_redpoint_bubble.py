import logging

import numpy as np
import torch
from ultralytics import YOLO
from PIL import Image, ImageStat, ImageOps
import cv2
import numpy

from mdap_u2c.constant import FIGMA_DESIGN_WIDTH, FIGMA_DESIGN_HEIGHT
from mdap_u2c.dsl_processors.cv_module import find_image
from mdap_u2c.dsl_processors.layout import ai_type_def, gen_tree

from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils import path_config

dp_factor = 1
YOLO_THRESHOLD = 0.1
AREA_THRESHOLD = 0.62
MAX_POINT_SIZE = 36
REDPOINT_MAX_WIDTH = 200
CUR_PATH = ''
_logger = logging.getLogger("redpoint_bubble")
# 模块级别的 YOLO 模型变量，用于缓存已加载的模型
_yolo_model = None

def get_yolo_model():
    """
    获取 YOLO 模型实例
    只在第一次调用时加载模型，后续调用直接返回缓存的模型
    """
    import time
    start_time = time.time()
    global _yolo_model
    if _yolo_model is None:
        _logger.info("Loading YOLO model for bubble detection...")
        _yolo_model = YOLO(path_config.getAssetsSmallModelDir() + '/bubble_detect/best.pt')
        elapsed_time = time.time() - start_time
        _logger.info(f"YOLO model loaded successfully, elapsed time: {elapsed_time:.3f}s")
    else:
        elapsed_time = time.time() - start_time
        _logger.info(f"get_yolo_model (from cache), elapsed time: {elapsed_time:.6f}s")
    return _yolo_model


# 程序启动时预加载 YOLO 模型到缓存
get_yolo_model()

def calc_boundary_distance(node1_data, node2_data):
    """
    计算两个控件的匹配优先级值（值越小优先级越高）
    优先比较区域重叠度，寻找重叠区域最大的容器
    - 有重叠：返回负的重叠面积（重叠越大，值越小，优先级越高）
    - 无重叠：返回正的边界距离（距离越小，值越小，优先级越高）
    """
    x1, y1, w1, h1 = node1_data.x, node1_data.y, node1_data.width, node1_data.height
    x2, y2, w2, h2 = node2_data.x, node2_data.y, node2_data.width, node2_data.height
    
    # 计算重叠区域
    overlap_x1 = max(x1, x2)
    overlap_y1 = max(y1, y2)
    overlap_x2 = min(x1 + w1, x2 + w2)
    overlap_y2 = min(y1 + h1, y2 + h2)
    
    overlap_width = overlap_x2 - overlap_x1
    overlap_height = overlap_y2 - overlap_y1
    
    # 如果有重叠区域
    if overlap_width > 0 and overlap_height > 0:
        overlap_area = overlap_width * overlap_height
        # 返回负的重叠面积，重叠越大值越小，优先级越高
        return -overlap_area
    
    # 无重叠，计算边界距离
    # 计算 x 方向的边界距离
    if x1 + w1 <= x2:  # node1 在 node2 左边
        dx = x2 - (x1 + w1)
    elif x2 + w2 <= x1:  # node1 在 node2 右边
        dx = x1 - (x2 + w2)
    else:  # x 方向有重叠
        dx = 0
    
    # 计算 y 方向的边界距离
    if y1 + h1 <= y2:  # node1 在 node2 上边
        dy = y2 - (y1 + h1)
    elif y2 + h2 <= y1:  # node1 在 node2 下边
        dy = y1 - (y2 + h2)
    else:  # y 方向有重叠
        dy = 0
    
    # 返回正的边界距离（无重叠的情况）
    return dx ** 2 + dy ** 2


#调整气泡层级
def change_redpoint_layer(input_tree,redpoint_list):
   for i, redpoint_id in enumerate(redpoint_list):
     change_one_redpoint_layer(input_tree, redpoint_id)
     redpoint_parent_node = input_tree.parent(redpoint_id)
     if redpoint_parent_node is not None and redpoint_parent_node.data.uid != input_tree.root:
        if redpoint_parent_node.data.src.style.overflow == "hidden":
            redpoint_parent_node.data.src.style.overflow = None

def change_one_redpoint_layer(input_tree,redpoint_id):
    parent_node = input_tree.parent(redpoint_id)
    redpoint_node = input_tree.get_node(redpoint_id)
    children_list = input_tree.children(parent_node.data.uid)
    nearest_control = None
    min_offset = 1
    for i,target in enumerate(children_list):
        if target.data.uid == redpoint_id:
            continue
        # 使用边界距离计算
        current_offset = calc_boundary_distance(redpoint_node.data, target.data)
        if current_offset < min_offset:
            min_offset = current_offset
            nearest_control = target

    if nearest_control is not None:
        if nearest_control.data.src.type == dsl_enum.ComponentType.CONTAINER :
            cross_result = gen_tree.judge_box(nearest_control.data,redpoint_node.data)
            if 0 <cross_result <= 1 or  cross_result == 2:
                input_tree.move_node(redpoint_id, nearest_control.data.uid)
                change_one_redpoint_layer(input_tree, redpoint_id)


def yolo_detect(image):

    model = get_yolo_model()  # 使用缓存的模型，避免每次加载
    results = model(image)  # return a list of Results objects
    for result in results:
        boxes = result.boxes  # Boxes object for bbox outputs
        # 打印 YOLO 模型识别结果到日志
        _logger.info(f"YOLO detection results - classes: {boxes.cls}, confidence: {boxes.conf}")
        return boxes
    return None


def get_redpoint_bubble_by_match(image):
    cv_image = cv2.cvtColor(numpy.asarray(image), cv2.COLOR_RGB2BGR)
    return find_image.find_images(cv_image, path_config.getAssetsImagesDir()+ '/bubble/')

def judge_bubble_by_match(x, y, width, height,bubble_list_by_match):
    for i, elem in enumerate(bubble_list_by_match):
        x1 = elem.x
        y1 = elem.y
        width1 = elem.width
        height1 = elem.height
        result = gen_tree.judge_box2((x, y, width, height), (x1, y1, width1, height1))
        if result >= AREA_THRESHOLD:
            return ai_type_def.AI_TYPE.RED_POINT.value
    return -1


def judge_bubble_by_yolo(x, y, width, height, boxes, item_id, top_bar_height=0):
    if boxes is None:
        return -1
    count = boxes.cls.size()[0]
    for i in range(0, count):
        if boxes.conf[i] > YOLO_THRESHOLD:
            x1 = int(boxes.xyxy[i][0])
            y1 = int(boxes.xyxy[i][1])
            # 当 top_bar_height > 0 时，修正 y1 坐标
            if top_bar_height > 0:
                y1 = y1 - top_bar_height
            width1 = int(boxes.xyxy[i][2] - boxes.xyxy[i][0])
            height1 = int(boxes.xyxy[i][3] - boxes.xyxy[i][1])
            result = gen_tree.judge_box2((x, y, width, height), (x1, y1, width1, height1))
            if result >= AREA_THRESHOLD:
                logging.info('yolo find success,item_id:' + item_id + str(result))
                # 禁用 InferenceMode
                with torch.inference_mode():
                    # 克隆张量
                    cloned_tensor = boxes.conf[i].clone()
                    cloned_tensor = -1 * cloned_tensor
                    boxes.conf[i] = cloned_tensor #将已匹配上的气泡控件打标，避免一个气泡匹配上多个控件
                if int(boxes.cls[i] == 0) :
                    return ai_type_def.AI_TYPE.RED_POINT.value
                elif int(boxes.cls[i] == 1) :
                    return ai_type_def.AI_TYPE.BUBBLE.value
            # 面积匹配不通过时，继续检查下一个元素，而不是直接返回
    return -1

def get_redpoint_bubble_boxes_by_yolo(image):
    import time
    start_time = time.time()
    if image is None:
        return
    w = image.width  # 图片的宽
    h = image.height
    if h / w < FIGMA_DESIGN_HEIGHT / FIGMA_DESIGN_WIDTH:
        image = ImageOps.expand(image, border=(0, 0, 0, int(w / FIGMA_DESIGN_WIDTH * FIGMA_DESIGN_HEIGHT) - h), fill=0)
    boxes = yolo_detect(image)
    elapsed_time = time.time() - start_time
    _logger.info(f"get_redpoint_bubble_boxes_by_yolo elapsed time: {elapsed_time:.3f}s")
    return boxes


def find_redpoint_bubble(input_tree,current_uid, yolo_boxes,bubble_list_by_match,result_list, top_bar_height=0):

    node_data = input_tree.get_node(current_uid).data
    current_x = node_data.x * dp_factor
    current_y = node_data.y * dp_factor
    current_width = node_data.width * dp_factor
    current_height = node_data.height * dp_factor

    match_result = judge_bubble_by_match(current_x, current_y, current_width, current_height,bubble_list_by_match)
    yolo_result = judge_bubble_by_yolo(current_x, current_y, current_width, current_height, yolo_boxes, node_data.uid, top_bar_height)
    find_flag = False
    if match_result >= 0:
        node_data.extra_dict['newId'] = 'match' + str(match_result) + node_data.uid
        node_data.ai_type = match_result
        find_flag = True
    if yolo_result >= 0 and node_data.src.type !=  dsl_enum.ComponentType.TEXT and current_width < REDPOINT_MAX_WIDTH:
        if  yolo_result == ai_type_def.AI_TYPE.RED_POINT.value:
            if abs(current_height - current_height )<= 1 and current_height > MAX_POINT_SIZE: #红点误判过滤
                return
        node_data.extra_dict['newId'] = 'yolo' + str(yolo_result) + node_data.uid
        node_data.ai_type = yolo_result
        find_flag = True
    if find_flag:
        result_list.append(node_data.uid)
    children_list = input_tree.children(current_uid)
    for i, elem in enumerate(children_list):
           find_redpoint_bubble(input_tree, elem.data.uid, yolo_boxes,bubble_list_by_match,result_list, top_bar_height)
    return


# 0 上 1由 2 下，3左

def fill_png(pil_image, fill_color):
    x, y = pil_image.size
    try:
        # 填充白色背景
        p = Image.new('RGBA', pil_image.size, fill_color)
        p.paste(pil_image, (0, 0, x, y), pil_image)
        return p
    except Exception as exc:
        _logger.warning("fill_png failed")
        return None


