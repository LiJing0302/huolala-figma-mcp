"""
移除重复图片资源服务
遍历 images 文件夹，识别并删除重复图片，同时更新 dsl.json 和 index.html 中的引用路径。
同时会删除备用图片文件夹 images_{number} 下的同名重复文件。
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _is_safe_filename(name: str) -> bool:
    base = os.path.basename(name)
    return bool(base) and base == name and base not in (".", "..") and ".." not in base


def _safe_child_path(base_dir: str, filename: str) -> Path | None:
    if not _is_safe_filename(filename):
        return None
    base = Path(base_dir).resolve()
    resolved = (base / filename).resolve()
    if not resolved.is_relative_to(base):
        return None
    return resolved


def get_image_info(image_path: str) -> Tuple[int, int, np.ndarray] | None:
    """
    获取图片的宽、高和 cv2 图像数据
    
    Args:
        image_path: 图片路径
        
    Returns:
        (width, height, cv_image) 或 None（如果读取失败）
    """
    try:
        cv_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if cv_image is None:
            logger.warning(f"无法读取图片: {image_path}")
            return None
        height, width = cv_image.shape[:2]
        return width, height, cv_image
    except Exception as e:
        logger.error(f"读取图片失败: {image_path}, 错误: {e}")
        return None


def _bgra_to_bgr_composite(cv_bgra: np.ndarray) -> np.ndarray:
    """
    若图片含透明通道，根据非透明部分的平均亮度决定透明区域的填充色（与 PIL 合成逻辑一致）：
    非透明偏暗则透明区填白，偏亮则填黑，再按 alpha 合成到 RGB，避免直接丢 alpha 导致相似度误判。
    cv2 读入为 BGRA。
    """
    if len(cv_bgra.shape) != 3 or cv_bgra.shape[2] != 4:
        return cv_bgra
    alpha_channel = cv_bgra[:, :, 3]
    bgr = cv_bgra[:, :, :3]
    non_transparent_mask = alpha_channel > 0
    if np.any(non_transparent_mask):
        non_transparent_pixels = bgr[non_transparent_mask]
        avg_brightness = np.mean(non_transparent_pixels)
        fill_bgr = (255, 255, 255) if avg_brightness < 128 else (0, 0, 0)
    else:
        fill_bgr = (255, 255, 255)
    a = alpha_channel.astype(np.float32) / 255.0
    fill = np.array(fill_bgr, dtype=np.float32).reshape(1, 1, 3)
    composited = bgr.astype(np.float32) * a[..., np.newaxis] + fill * (1.0 - a[..., np.newaxis])
    return np.clip(np.round(composited), 0, 255).astype(np.uint8)


def calc_image_similarity(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    使用 cv2.absdiff 计算两张图片的相似度
    
    Args:
        img1: 第一张图片 (cv2 格式)
        img2: 第二张图片 (cv2 格式)
        
    Returns:
        相似度 (0.0 - 1.0)，1.0 表示完全相同
    """
    try:
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # 统一转换为 3 通道；含 alpha 时先按亮度填底再合成，避免透明 PNG 与 cv2 直接丢 alpha 导致误判
        if len(img1.shape) == 2:
            img1 = cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR)
        elif img1.shape[2] == 4:
            img1 = _bgra_to_bgr_composite(img1)

        if len(img2.shape) == 2:
            img2 = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
        elif img2.shape[2] == 4:
            img2 = _bgra_to_bgr_composite(img2)

        # 确保两张图片尺寸一致，将 img2 resize 到 img1 的尺寸
        if (w1, h1) != (w2, h2):
            img2 = cv2.resize(img2, (w1, h1))
        
        # 计算差异
        residual = cv2.absdiff(img1, img2)
        gray_diff = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
        
        # 统计相同像素的比例 (差异为0的像素)
        total_pixels = gray_diff.shape[0] * gray_diff.shape[1]
        same_pixels = np.sum(gray_diff == 0)
        
        similarity = same_pixels / total_pixels
        return similarity
        
    except Exception as e:
        logger.error(f"计算图片相似度失败: {e}")
        return 0.0


def find_duplicate_images(images_dir: str) -> Dict[str, str]:
    """
    查找重复图片
    
    Args:
        images_dir: 图片目录路径
        
    Returns:
        重复图片映射关系 {重复图片路径: 保留图片路径}
    """
    # 获取所有图片文件
    image_extensions = {'.png', '.jpg', '.jpeg'}
    image_files = []
    
    for filename in os.listdir(images_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in image_extensions:
            image_files.append(filename)
    
    if not image_files:
        logger.info("未找到图片文件")
        return {}
    
    logger.info(f"共找到 {len(image_files)} 个图片文件")
    
    # 获取所有图片的信息
    image_info_list: List[Tuple[str, int, int, np.ndarray]] = []
    for filename in image_files:
        if not _is_safe_filename(filename):
            logger.warning("跳过非法文件名: %s", filename)
            continue
        image_path = os.path.join(images_dir, filename)
        info = get_image_info(image_path)
        if info:
            width, height, cv_image = info
            image_info_list.append((filename, width, height, cv_image))
    
    # 查找重复图片
    duplicate_map: Dict[str, str] = {}  # {重复图片文件名: 保留图片文件名}
    processed = set()  # 已处理的图片
    
    for i, (filename1, w1, h1, img1) in enumerate(image_info_list):
        if filename1 in processed:
            continue
            
        for j, (filename2, w2, h2, img2) in enumerate(image_info_list):
            if i >= j or filename2 in processed:
                continue
            
            # 检查宽高差值是否 <= 1
            if abs(w1 - w2) <= 1 and abs(h1 - h2) <= 1:
                # 计算相似度
                similarity = calc_image_similarity(img1, img2)
                
                if similarity >= 0.99:
                    logger.info(f"发现重复图片: {filename2} 与 {filename1} 相似度: {similarity:.4f}")
                    duplicate_map[filename2] = filename1
                    processed.add(filename2)
    
    return duplicate_map


def update_dsl_references(dsl_path: str, duplicate_map: Dict[str, str], image_folder: str = "images") -> bool:
    """
    更新 dsl.json 文件中的图片引用路径
    
    Args:
        dsl_path: dsl.json 文件路径
        duplicate_map: 重复图片映射关系 {重复图片文件名: 保留图片文件名}
        image_folder: 图片目录名（如 images 或 images_2），用于匹配引用路径
        
    Returns:
        是否更新成功
    """
    try:
        with open(dsl_path, 'r', encoding='utf-8') as f:
            dsl_content = f.read()
        
        original_content = dsl_content
        
        # 替换所有重复图片的引用
        for duplicate_file, keep_file in duplicate_map.items():
            if not _is_safe_filename(duplicate_file) or not _is_safe_filename(keep_file):
                logger.warning("跳过非法文件名引用: %s -> %s", duplicate_file, keep_file)
                continue
            # 替换 props.src 格式: "./images/xxx.png" 或 "./images_2/xxx.png"
            # 替换 style.background_image 格式: "url(./images/xxx.png)"
            patterns = [
                f'./{image_folder}/{duplicate_file}',
                f'{image_folder}/{duplicate_file}',
            ]
            
            for pattern in patterns:
                replacement = pattern.replace(duplicate_file, keep_file)
                dsl_content = dsl_content.replace(pattern, replacement)
        
        if dsl_content != original_content:
            with open(dsl_path, 'w', encoding='utf-8') as f:
                f.write(dsl_content)
            logger.info(f"已更新 dsl.json 文件: {dsl_path}")
            return True
        else:
            logger.info("dsl.json 文件无需更新")
            return True
            
    except Exception as e:
        logger.error(f"更新 dsl.json 文件失败: {e}")
        return False


def update_html_references(html_path: str, duplicate_map: Dict[str, str], image_folder: str = "images") -> bool:
    """
    更新 index.html 文件中的图片引用路径
    
    Args:
        html_path: index.html 文件路径
        duplicate_map: 重复图片映射关系 {重复图片文件名: 保留图片文件名}
        image_folder: 图片目录名（如 images 或 images_2），用于匹配引用路径
        
    Returns:
        是否更新成功
    """
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        original_content = html_content
        
        # 替换所有重复图片的引用
        for duplicate_file, keep_file in duplicate_map.items():
            if not _is_safe_filename(duplicate_file) or not _is_safe_filename(keep_file):
                logger.warning("跳过非法文件名引用: %s -> %s", duplicate_file, keep_file)
                continue
            # 替换各种可能的引用格式
            # ./images/xxx.png, images/xxx.png, /images/xxx.png（或 images_2 等）
            patterns = [
                f'./{image_folder}/{duplicate_file}',
                f'{image_folder}/{duplicate_file}',
                f'/{image_folder}/{duplicate_file}',
            ]
            
            for pattern in patterns:
                replacement = pattern.replace(duplicate_file, keep_file)
                html_content = html_content.replace(pattern, replacement)
        
        if html_content != original_content:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"已更新 index.html 文件: {html_path}")
            return True
        else:
            logger.info("index.html 文件无需更新")
            return True
            
    except Exception as e:
        logger.error(f"更新 index.html 文件失败: {e}")
        return False


def get_backup_images_dirs(folder_path: str) -> List[str]:
    """
    获取备用图片文件夹列表 images_{number}（如 images_2, images_3）
    与 images 目录同级的、匹配 images_数字 的目录。
    
    Args:
        folder_path: 包含 images 的目录路径
        
    Returns:
        备用图片目录绝对路径列表（已排序）
    """
    backup_dirs: List[str] = []
    pattern = re.compile(r"^images_(\d+)$")
    try:
        for name in os.listdir(folder_path):
            if pattern.match(name):
                full_path = os.path.join(folder_path, name)
                if os.path.isdir(full_path):
                    backup_dirs.append(full_path)
    except Exception as e:
        logger.warning(f"列举备用图片目录失败: {folder_path}, 错误: {e}")
    return sorted(backup_dirs)


def get_primary_and_backup_images_dirs(
    folder_path: str, image_scales: List[int] | None = None
) -> Tuple[str | None, List[str]]:
    """
    获取主图片目录与备用图片目录列表。
    若传入 image_scales：
      - 仅一个数字时：主目录为 images，backup_images_dirs 为空；
      - 多个数字时：主目录名为 images_ 与 image_scales[0] 的拼接，其余为备用图片目录。
    未传入 image_scales 时：若存在 images 目录则以其为主目录，其余 images_{factor} 为备用；
    若不存在 images 则从 images_{factor} 中取第一个为主目录，其余为备用。
    
    Args:
        folder_path: 根目录路径
        image_scales: 用户输入的图片倍数列表，如 [2] 或 [2, 3]；为 None 时按目录存在情况推断。
        
    Returns:
        (主目录绝对路径, 备用目录绝对路径列表)；无任何图片目录时主目录为 None。
    """
    if image_scales is not None:
        if len(image_scales) == 1:
            primary_dir = os.path.join(folder_path, "images")
            return primary_dir if os.path.isdir(primary_dir) else None, []
        if len(image_scales) > 1:
            primary_name = f"images_{image_scales[0]}"
            primary_dir = os.path.join(folder_path, primary_name)
            backup_dirs = [
                os.path.join(folder_path, f"images_{s}")
                for s in image_scales[1:]
            ]
            return primary_dir if os.path.isdir(primary_dir) else None, backup_dirs

    images_dir = os.path.join(folder_path, "images")
    factor_dirs = get_backup_images_dirs(folder_path)
    if os.path.isdir(images_dir):
        return images_dir, factor_dirs
    if not factor_dirs:
        return None, []
    return factor_dirs[0], factor_dirs[1:]


def remove_duplicate_images(images_dir: str, duplicate_map: Dict[str, str]) -> int:
    """
    删除重复的图片文件（仅 images 目录）
    
    Args:
        images_dir: 图片目录路径
        duplicate_map: 重复图片映射关系
        
    Returns:
        删除的图片数量
    """
    removed_count = 0
    
    for duplicate_file in duplicate_map.keys():
        safe_path = _safe_child_path(images_dir, duplicate_file)
        if safe_path is None:
            logger.warning("跳过非法删除路径: %s", duplicate_file)
            continue
        file_path = str(safe_path)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"已删除重复图片: {duplicate_file}")
                removed_count += 1
        except Exception as e:
            logger.error(f"删除图片失败: {file_path}, 错误: {e}")
    
    return removed_count


def remove_duplicate_images_from_backup_dirs(
    backup_dirs: List[str], duplicate_map: Dict[str, str]
) -> int:
    """
    根据 images 中得到的重复图片名称，删除各 images_{number} 目录下的同名文件。
    不重复搜索，仅按文件名删除。
    
    Args:
        backup_dirs: 备用图片目录路径列表（images_1, images_2 等）
        duplicate_map: 重复图片映射关系 {重复图片文件名: 保留图片文件名}
        
    Returns:
        删除的图片数量
    """
    removed_count = 0
    duplicate_filenames = set(duplicate_map.keys())
    
    for backup_dir in backup_dirs:
        for duplicate_file in duplicate_filenames:
            safe_path = _safe_child_path(backup_dir, duplicate_file)
            if safe_path is None:
                logger.warning("跳过非法删除路径: %s", duplicate_file)
                continue
            file_path = str(safe_path)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logger.info(f"已删除备用目录中的重复图片: {os.path.basename(backup_dir)}/{duplicate_file}")
                    removed_count += 1
            except Exception as e:
                logger.error(f"删除备用目录图片失败: {file_path}, 错误: {e}")
    
    return removed_count


def remove_same_image_resource(
    folder_path: str, image_scales: List[int] | None = None
) -> Dict:
    """
    移除重复图片资源的主函数。
    若传入 image_scales，则按 get_primary_and_backup_images_dirs 的规则确定主目录与备用目录；
    否则若存在 images 目录则以其为主目录做去重；若不存在则使用 images_{factor} 中第一个为主目录，
    去重后记录删除的文件名，再按同名删除其他倍数目录中的文件。
    
    Args:
        folder_path: 包含 images 或 images_{factor} 的目录路径（dsl.json 和 index.html 可选）
        image_scales: 用户输入的图片倍数列表，与导出时一致；为 None 时按目录存在情况推断。
        
    Returns:
        处理结果 {
            'success': bool,
            'duplicate_count': int,
            'removed_count': int,
            'duplicate_map': Dict[str, str]
        }
    """
    result = {
        'success': False,
        'duplicate_count': 0,
        'removed_count': 0,
        'duplicate_map': {}
    }
    
    # 验证路径
    if not os.path.isdir(folder_path):
        logger.error(f"目录不存在: {folder_path}")
        return result
    
    primary_dir, backup_dirs = get_primary_and_backup_images_dirs(
        folder_path, image_scales
    )
    if primary_dir is None:
        logger.error(f"未找到 images 或 images_{{factor}} 目录: {folder_path}")
        return result
    
    image_folder_name = os.path.basename(primary_dir)
    dsl_path = os.path.join(folder_path, 'dsl.json')
    html_path = os.path.join(folder_path, 'index.html')
    
    logger.info(f"开始处理目录: {folder_path}，主图片目录: {image_folder_name}")
    
    # 在主目录中查找重复图片
    duplicate_map = find_duplicate_images(primary_dir)
    result['duplicate_count'] = len(duplicate_map)
    result['duplicate_map'] = duplicate_map
    
    if not duplicate_map:
        logger.info("未发现重复图片")
        result['success'] = True
        return result
    
    logger.info(f"发现 {len(duplicate_map)} 个重复图片，删除的文件名: {list(duplicate_map.keys())}")
    
    # 更新 dsl.json 引用（如果存在）
    if os.path.isfile(dsl_path):
        if not update_dsl_references(dsl_path, duplicate_map, image_folder=image_folder_name):
            logger.error("更新 dsl.json 引用失败")
            return result
    else:
        logger.info(f"dsl.json 不存在，跳过更新: {dsl_path}")
    
    # 更新 index.html 引用（如果存在）
    if os.path.isfile(html_path):
        if not update_html_references(html_path, duplicate_map, image_folder=image_folder_name):
            logger.error("更新 index.html 引用失败")
            return result
    else:
        logger.info(f"index.html 不存在，跳过更新: {html_path}")
    
    # 删除主目录下的重复图片
    removed_count = remove_duplicate_images(primary_dir, duplicate_map)
    result['removed_count'] = removed_count

    # 用记录下的删除文件名，删除其他倍数目录中的同名文件
    if backup_dirs:
        backup_removed = remove_duplicate_images_from_backup_dirs(backup_dirs, duplicate_map)
        result['removed_count'] += backup_removed
        logger.info(f"其他倍数图片目录中共删除 {backup_removed} 个重复文件")
    else:
        logger.info("未发现其他 images_{factor} 目录，跳过")

    result['success'] = True
    total_removed = result['removed_count']
    logger.info(f"处理完成: 发现 {len(duplicate_map)} 个重复图片，共删除 {total_removed} 个")
    
    return result


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("用法: python remove_same_image_resource.py <folder_path>")
    else:
        folder_path = sys.argv[1]
    result = remove_same_image_resource(folder_path)
    
    print(f"\n处理结果:")
    print(f"  成功: {result['success']}")
    print(f"  发现重复图片: {result['duplicate_count']} 个")
    print(f"  已删除图片: {result['removed_count']} 个")
    
    if result['duplicate_map']:
        print(f"\n重复图片映射关系:")
        for dup, keep in result['duplicate_map'].items():
            print(f"  {dup} -> {keep}")
