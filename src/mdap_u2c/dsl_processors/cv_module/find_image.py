import cv2
import time
import numpy as np
import os

from mdap_u2c.dsl_processors.layout import gen_tree


def py_nms(dets, thresh):
    """Pure Python NMS baseline."""
    x1 = dets[:, 0]
    y1 = dets[:, 1]
    x2 = dets[:, 2]
    y2 = dets[:, 3]
    scores = dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= thresh)[0]
        order = order[inds + 1]
    return keep


def find_template(img_gray, template_img, template_threshold):
    '''
    img_gray:待检测的灰度图片格式
    template_img:模板小图，也是灰度化了
    template_threshold:模板匹配的置信度
    '''
    if (img_gray is None or template_img is None):
        print('无效图片，直接返回')
        return
    h, w = template_img.shape[:2]
    target_height, target_width = img_gray.shape
    if target_width < w or target_height < h:
        print('模板图尺寸大于待检测图，直接返回')
        return
    res = cv2.matchTemplate(img_gray, template_img, cv2.TM_CCOEFF_NORMED)
    start_time = time.time()
    loc = np.where(res >= template_threshold)
    score = res[res >= template_threshold]
    xmin = np.array(loc[1])
    ymin = np.array(loc[0])
    xmax = xmin + w
    ymax = ymin + h
    xmin = xmin.reshape(-1, 1)
    xmax = xmax.reshape(-1, 1)
    ymax = ymax.reshape(-1, 1)
    ymin = ymin.reshape(-1, 1)
    score = score.reshape(-1, 1)
    data_hlist = []
    data_hlist.append(xmin)
    data_hlist.append(ymin)
    data_hlist.append(xmax)
    data_hlist.append(ymax)
    data_hlist.append(score)
    data_hstack = np.hstack(data_hlist)
    thresh = 0.3

    keep_dets = py_nms(data_hstack, thresh)
    dets = data_hstack[keep_dets]
    return dets


def find_image_area(img_gray, template_img, image_uid='test'):
    dets = find_template(img_gray, template_img, 0.8)
    if dets is None:
        return None
    image_list = []
    for count, elem in enumerate(dets):
        image_view = gen_tree.UIControl(0, 0, 0, 0, '')
        image_view.x = int(elem[0]) - 1
        image_view.y = int(elem[1]) - 1
        image_view.width = int(elem[2]) - int(elem[0]) + 1 + 2
        image_view.height = int(elem[3]) - int(elem[1]) + 1 + 2
        image_view.typeName = 'BigImageView'
        image_view.uid = image_uid + str(count)
        image_list.append(image_view)
    return image_list


def find_images(input_image, template_dir):
    if isinstance(input_image, str):
        orig_image = cv2.imread(input_image)
        if orig_image.shape[2] == 4:
            orig_image[..., 3] = 255
        img_gray = cv2.cvtColor(orig_image, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)

    image_list = []
    for file_name in os.listdir(template_dir):
        if not (file_name.endswith("jpg") or file_name.endswith("png")):
            continue
        file_path = template_dir + file_name
        template_org = cv2.imread(file_path)
        if template_org.shape[2] == 4:
            template_org[..., 3] = 255
        template_img = cv2.cvtColor(template_org, cv2.COLOR_BGR2GRAY)
        sub_list = find_image_area(img_gray, template_img, file_name)
        if sub_list is not None:
            image_list.extend(sub_list)
    return image_list

