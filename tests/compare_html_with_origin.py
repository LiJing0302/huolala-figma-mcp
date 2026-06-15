"""
Tool: 比较 HTML 渲染结果与原始设计稿的相似度

依赖（`tests/ui2code_auto_test.py` 使用）：
  pip install ".[ui2code-test]"
  playwright install chromium
"""
import io
import json
import base64
import logging
import os
import tempfile
import zipfile
from urllib.parse import urlparse

import cv2
import numpy as np
from PIL import Image

from mdap_u2c.config.http_config import get_http_timeout, get_ssl_verify
from mdap_u2c.dsl_processors.cv_module.calc_similarity import calc_ssim

logger = logging.getLogger(__name__)

# iOS 状态栏高度
IOS_STATUS_HEIGHT = 44


def calc_absdiff(image1: Image.Image, image2: Image.Image) -> float:
    """
    使用 cv2.absdiff 计算两张图片的相似度
    
    Args:
        image1: PIL Image 对象
        image2: PIL Image 对象
    
    Returns:
        相似度值 (0-1)，值越大表示越相似
    """
    # 确保两张图片尺寸一致
    img_size = image1.size
    image2 = image2.resize(img_size)
    
    # 转换为 RGB 模式（如果有 alpha 通道则去除）
    if image1.mode == 'RGBA':
        image1 = image1.convert('RGB')
    if image2.mode == 'RGBA':
        image2 = image2.convert('RGB')
    
    # PIL Image 转换为 OpenCV 格式 (BGR)
    cv_img1 = cv2.cvtColor(np.array(image1), cv2.COLOR_RGB2BGR)
    cv_img2 = cv2.cvtColor(np.array(image2), cv2.COLOR_RGB2BGR)
    
    # 计算像素差异
    residual = cv2.absdiff(cv_img1, cv_img2)
    gray_residual = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
    
    # 计算完全相同的像素比例
    height, width = gray_residual.shape
    zero_count = np.sum(gray_residual == 0)
    similarity = zero_count / (height * width)
    
    return similarity


def generate_diff_image(image1: Image.Image, image2: Image.Image) -> Image.Image:
    """
    生成两张图片的 diff 图像，差异部分用红色高亮显示
    
    Args:
        image1: PIL Image 对象 (原始图片)
        image2: PIL Image 对象 (渲染图片)
    
    Returns:
        diff 图像 (PIL Image 对象)
    """
    # 确保两张图片尺寸一致
    img_size = image1.size
    image2 = image2.resize(img_size)
    
    # 转换为 RGB 模式（如果有 alpha 通道则去除）
    if image1.mode == 'RGBA':
        image1 = image1.convert('RGB')
    if image2.mode == 'RGBA':
        image2 = image2.convert('RGB')
    
    # PIL Image 转换为 OpenCV 格式 (BGR)
    cv_img1 = cv2.cvtColor(np.array(image1), cv2.COLOR_RGB2BGR)
    cv_img2 = cv2.cvtColor(np.array(image2), cv2.COLOR_RGB2BGR)
    
    # 计算像素差异
    residual = cv2.absdiff(cv_img1, cv_img2)
    gray_residual = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
    
    # 创建差异掩码 (差异大于阈值的像素)
    threshold = 10  # 差异阈值
    _, diff_mask = cv2.threshold(gray_residual, threshold, 255, cv2.THRESH_BINARY)
    
    # 创建输出图像 (以原始图片为基础)
    diff_output = cv_img1.copy()
    
    # 将差异区域用红色高亮显示
    diff_output[diff_mask > 0] = [0, 0, 255]  # BGR 格式的红色
    
    # 转换回 PIL Image
    diff_image = Image.fromarray(cv2.cvtColor(diff_output, cv2.COLOR_BGR2RGB))
    
    return diff_image


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的 URL scheme: {parsed.scheme}")


def download_image(image_url: str) -> Image.Image:
    """下载图片并返回 PIL Image 对象"""
    import requests

    _validate_http_url(image_url)
    logger.info(f"Downloading image from: {image_url[:100]}...")

    response = requests.get(
        image_url,
        verify=get_ssl_verify(),
        timeout=get_http_timeout(default=60),
    )
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))


def crop_image(image: Image.Image, top_crop: int = 0, bottom_crop: int = 0) -> Image.Image:
    """
    裁剪图片的顶部和底部
    
    Args:
        image: PIL Image 对象
        top_crop: 顶部裁剪高度
        bottom_crop: 底部裁剪高度
    
    Returns:
        裁剪后的 PIL Image 对象
    """
    width, height = image.size
    new_top = top_crop
    new_bottom = height - bottom_crop
    
    if new_top >= new_bottom:
        raise ValueError(f"Invalid crop parameters: top={top_crop}, bottom={bottom_crop}, height={height}")
    
    cropped = image.crop((0, new_top, width, new_bottom))
    logger.info(f"Cropped image from {width}x{height} to {cropped.size[0]}x{cropped.size[1]} (top={top_crop}, bottom={bottom_crop})")
    return cropped


def render_html_to_image_local(html_zip_base64: str, width: int, height: int) -> Image.Image:
    """
    使用本地 Playwright 将 HTML 渲染为图片
    
    Args:
        html_zip_base64: HTML ZIP 文件的 base64 编码
        width: 渲染宽度
        height: 渲染高度
    
    Returns:
        PIL Image 对象
    """
    from playwright.sync_api import sync_playwright
    
    logger.info(f"Rendering HTML to image locally: width={width}, height={height}")
    
    # 创建临时目录解压 ZIP
    with tempfile.TemporaryDirectory() as temp_dir:
        # 解码并解压 ZIP
        zip_data = base64.b64decode(html_zip_base64)
        zip_buffer = io.BytesIO(zip_data)
        
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            zf.extractall(temp_dir)
        
        # 查找 index.html
        html_path = os.path.join(temp_dir, 'index.html')
        if not os.path.exists(html_path):
            # 尝试在子目录中查找
            for root, dirs, files in os.walk(temp_dir):
                if 'index.html' in files:
                    html_path = os.path.join(root, 'index.html')
                    break
        
        if not os.path.exists(html_path):
            raise FileNotFoundError(f"index.html not found in ZIP")
        
        # 使用 Playwright 渲染
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': width, 'height': height})
                
                # 加载本地 HTML 文件
                file_url = f"file://{html_path}"
                page.goto(file_url, wait_until='networkidle')
                
                # 等待页面渲染完成
                page.wait_for_timeout(500)
                
                # 截图
                screenshot_bytes = page.screenshot(type='png')
                
                # 转换为 PIL Image
                image = Image.open(io.BytesIO(screenshot_bytes))
                logger.info(f"HTML rendered to image: {image.size[0]}x{image.size[1]}")
                
                return image
            finally:
                browser.close()


def render_html_dir_to_image(html_dir: str, width: int, height: int) -> Image.Image:
    """
    使用本地 Playwright 将 HTML 目录渲染为图片
    
    Args:
        html_dir: 包含 index.html 的目录路径
        width: 渲染宽度
        height: 渲染高度
    
    Returns:
        PIL Image 对象
    """
    from playwright.sync_api import sync_playwright
    
    logger.info(f"Rendering HTML directory to image: {html_dir}, width={width}, height={height}")
    
    # 查找 index.html
    html_path = os.path.join(html_dir, 'index.html')
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"index.html not found in {html_dir}")
    
    # 使用 Playwright 渲染
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': width, 'height': height})
            
            # 加载本地 HTML 文件
            file_url = f"file://{html_path}"
            page.goto(file_url, wait_until='networkidle')
            
            # 等待页面渲染完成
            page.wait_for_timeout(500)
            
            # 截图
            screenshot_bytes = page.screenshot(type='png')
            
            # 转换为 PIL Image
            image = Image.open(io.BytesIO(screenshot_bytes))
            logger.info(f"HTML rendered to image: {image.size[0]}x{image.size[1]}")
            
            return image
        finally:
            browser.close()


def parse_dsl_json(dsl_json_content: str) -> dict:
    """
    解析 dsl.json 内容，提取所需字段
    
    Returns:
        包含 top_bar_height, real_homebar_height, is_translucent_top_bar, width, height, image_url 的字典
    """
    dsl_data = json.loads(dsl_json_content)
    metadata = dsl_data.get('metadata', {})
    extra_dict = metadata.get('extra_dict', {})
    
    return {
        'top_bar_height': extra_dict.get('top_bar_height', 0),
        'real_homebar_height': extra_dict.get('real_homebar_height', 0),
        'is_translucent_top_bar': extra_dict.get('is_translucent_top_bar', False),
        'width': metadata.get('width', 375),
        'height': metadata.get('height', 812),
        'image_url': metadata.get('image_url', ''),
    }


def compare_html_with_origin_local(dsl_file: str, output_base_dir: str, save_images: bool = True) -> dict:
    """
    本地版本的 compare_html_with_origin，直接读取文件并使用本地 Playwright 渲染
    
    Args:
        dsl_file: dsl.json 文件路径
        output_base_dir: 包含 index.html 和 images 文件夹的目录
        save_images: 是否保存中间结果图片
    
    Returns:
        比较结果字典
    """
    # 1. 读取并解析 dsl.json
    with open(dsl_file, 'r', encoding='utf-8') as f:
        dsl_content = f.read()
    
    metadata = parse_dsl_json(dsl_content)
    
    top_bar_height = metadata['top_bar_height']
    real_homebar_height = metadata['real_homebar_height']
    is_translucent_top_bar = metadata['is_translucent_top_bar']
    width = metadata['width']
    height = metadata['height']
    image_url = metadata['image_url']
    
    logger.info(f"Parsed metadata: top_bar_height={top_bar_height}, real_homebar_height={real_homebar_height}, "
                f"is_translucent_top_bar={is_translucent_top_bar}, width={width}, height={height}")
    
    if not image_url:
        raise ValueError("image_url 不能为空")
    
    # 2. 下载并裁剪原始设计稿图片
    origin_image = download_image(image_url)
    
    # 计算顶部裁剪高度
    if is_translucent_top_bar:
        top_crop = IOS_STATUS_HEIGHT
    elif top_bar_height > 0:
        top_crop = top_bar_height
    else:
        top_crop = 0
    
    # 底部裁剪高度
    bottom_crop = real_homebar_height if real_homebar_height > 0 else 0
    
    # 裁剪原始图片
    image1 = crop_image(origin_image, top_crop=top_crop, bottom_crop=bottom_crop)
    
    # 3. 计算渲染高度
    new_height = height - top_bar_height - real_homebar_height
    new_height = int(new_height)
    width = int(width)
    
    logger.info(f"Calculated render dimensions: width={width}, new_height={new_height}")
    
    # 4. 使用本地 Playwright 渲染 HTML
    image2 = render_html_dir_to_image(output_base_dir, width, new_height)
    
    # 如果是半透明状态栏，需要额外裁剪 image2
    if is_translucent_top_bar:
        image2 = crop_image(image2, top_crop=IOS_STATUS_HEIGHT)
    
    # 4.1 屏幕拉伸渲染图：将渲染宽度拉伸为 width 的 1.5 倍
    stretched_width = int(width * 1.5)
    image2_stretched = render_html_dir_to_image(output_base_dir, stretched_width, new_height)
    if is_translucent_top_bar:
        image2_stretched = crop_image(image2_stretched, top_crop=IOS_STATUS_HEIGHT)
    
    # 5. 比较图像相似度
    ssim_similarity = calc_ssim(image1, image2)
    absdiff_similarity = calc_absdiff(image1, image2)
    
    # 6. 生成 diff 图像
    diff_image = generate_diff_image(image1, image2)
    
    logger.info(f"Image similarity - SSIM: {ssim_similarity:.4f}, absdiff: {absdiff_similarity:.4f}")
    
    # 7. 保存中间结果图片（可选）
    if save_images:
        compare_output_dir = os.path.join(output_base_dir, "compare")
        os.makedirs(compare_output_dir, exist_ok=True)
        image1.save(os.path.join(compare_output_dir, "origin_cropped.png"))
        image2.save(os.path.join(compare_output_dir, "rendered.png"))
        image2_stretched.save(os.path.join(compare_output_dir, "rendered_stretched.png"))
        diff_image.save(os.path.join(compare_output_dir, "diff.png"))
        logger.info(f"Saved comparison images to: {compare_output_dir}")
    
    return {
        "ssim": round(ssim_similarity, 4),
        "absdiff": round(absdiff_similarity, 4),
        "origin_size": {"width": image1.size[0], "height": image1.size[1]},
        "rendered_size": {"width": image2.size[0], "height": image2.size[1]},
        "metadata": {
            "top_bar_height": top_bar_height,
            "real_homebar_height": real_homebar_height,
            "is_translucent_top_bar": is_translucent_top_bar,
            "original_width": width,
            "original_height": height,
            "render_height": new_height,
            "top_crop": top_crop,
            "bottom_crop": bottom_crop,
        }
    }
