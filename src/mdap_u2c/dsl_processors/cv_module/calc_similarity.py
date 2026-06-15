from PIL import Image
from skimage import metrics
import cv2
import numpy as np


def calc_ssim(image1, image2):
    img_size = image1.size
    image2 = image2.resize(img_size)

    image1_gray = image1.convert("L")
    image2_gray = image2.convert("L")

    image1_array = np.array(image1_gray)
    image2_array = np.array(image2_gray)

    similarity = metrics.structural_similarity(image1_array, image2_array)
    similarity = (similarity + 1) / 2
    return similarity

if __name__ == "__main__":
    image1 = Image.open('1.png')
    image2 = Image.open('2.png')
    result = calc_ssim(image1, image2)
    print(result)

    cur_poi_img = cv2.imread('1.png')
    cur_clean_img = cv2.imread('2.png')

    residual = cv2.absdiff(cur_poi_img, cur_clean_img)
    gray_image = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
    cv2.imwrite('diff_gray.png', gray_image)

    height = gray_image.shape[0]
    width = gray_image.shape[1]
    dst = np.zeros((height, width, 3))
    none_zero_cnt = 0
    for h in range(0, height):
        for w in range(0, width):
            color = gray_image[h, w]
            if color == 0:
                none_zero_cnt = none_zero_cnt + 1
    result2 = none_zero_cnt / (height * width)
    print(result2)




