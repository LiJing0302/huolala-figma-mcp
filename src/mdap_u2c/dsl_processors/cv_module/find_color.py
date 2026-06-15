from collections import Counter
def count_colors_pil(pil_image):
    # 转换为 RGB 模式
    img = pil_image.convert('RGB')
    # 获取所有像素颜色
    pixels = list(img.getdata())
    # 统计颜色出现次数
    color_count = Counter(pixels)
    return color_count

def is_colorful_image(pil_image):
    color_stats = count_colors_pil(pil_image)
    for color, count in color_stats.most_common(5):
        if abs(color[1] - color[0]) >= 5 or abs(color[2] - color[1]) >= 5:
            return True
    return False