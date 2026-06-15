import base64
import hashlib
import json
import logging
import time
from io import BytesIO

import numpy
import requests
from PIL import Image

from mdap_u2c.config.http_config import get_http_timeout, get_ssl_verify
from mdap_u2c.core import memory_kv
from mdap_u2c.constant import FIGMA_DESIGN_WIDTH, FIGMA_DESIGN_HEIGHT
from mdap_u2c.dsl_processors.cv_module.vlm_provider import get_vlm_provider, is_vlm_enabled
from mdap_u2c.dsl_processors.layout import gen_tree, ai_type_def
from mdap_u2c.dsl_processors.layout.tree_projection import create_sub_container
from mdap_u2c.enums import dsl_enum
from mdap_u2c.enums.cache_enum import CacheKey
from mdap_u2c.utils.component_style_utils import is_rich_text_container

# 大屏幕阈值
MAX_HEIGHT = FIGMA_DESIGN_HEIGHT  # 单块最大高度
MAX_WIDTH = FIGMA_DESIGN_WIDTH
SPLIT_THRESHOLD_2 = FIGMA_DESIGN_HEIGHT  # 超过此高度切2块
SPLIT_THRESHOLD_3 = 1500  # 超过此高度切3块

_logger = logging.getLogger(__name__)


# You can tweak the flow by adding a tweaks dictionary
# e.g {"xxx": xxx}

def run_flow(tweaks: dict = None) -> dict:
    """
    调用 VLM Provider（由 MDAP_VLM_PROVIDER 环境变量决定后端）。

    :param tweaks: 需包含 BOT_USER_INPUT（提示词）与 image（URL 或 base64 data URI）
    :return: {ret, data: {output}} 格式响应
    """
    tweaks = tweaks or {}
    text = tweaks.get("BOT_USER_INPUT", "")
    image = tweaks.get("image", "")
    if not text or not image:
        return {"ret": -1, "msg": "missing BOT_USER_INPUT or image", "data": {"output": ""}}

    _logger.info("开始调用 VLM API...")
    start_time = time.time()
    result = get_vlm_provider().invoke(text, image)
    elapsed_time = time.time() - start_time
    _logger.info(f"VLM API 调用完成，耗时: {elapsed_time:.2f} 秒")
    return result


def _get_image_by_url(url: str) -> Image.Image:
    """根据图片url获取图片对象"""
    response = requests.get(url, verify=get_ssl_verify(), timeout=get_http_timeout())
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    return image


def _pil_image_to_base64(pil_image: Image.Image, format: str = "PNG") -> str:
    """将PIL图片转换为base64编码字符串"""
    buffer = BytesIO()
    pil_image.save(buffer, format=format)
    img_bytes = buffer.getvalue()
    base64_str = base64.b64encode(img_bytes).decode('utf-8')
    return f"data:image/{format.lower()};base64,{base64_str}"


def _is_row_uniform(row: numpy.ndarray, max_diff_threshold: int = 5,
                    edge_margin: int = 3) -> bool:
    """
    检查一行像素是否颜色基本一致（从左到右）
    
    判断逻辑：每行像素的 R、G、B 各通道的最大值和最小值差值 <= max_diff_threshold 则认为是空隙
    
    :param row: 一行像素数据，shape 为 (width,) 或 (width, channels)
    :param max_diff_threshold: 最大值-最小值差异阈值，默认5
    :param edge_margin: 边缘忽略的像素数，默认3
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


def _find_horizontal_gaps(img_array: numpy.ndarray, min_gap_height: int = 5,
                          max_diff_threshold: int = 5) -> list:
    """
    搜索纵向空隙区域（从左到右颜色基本一致的区域）
    
    :param img_array: 输入图像数组 (RGB 或灰度)
    :param min_gap_height: 最小空隙高度，排除 <= 该值的部分
    :param max_diff_threshold: RGB各通道最大值-最小值差异阈值，默认5
    :return: 空隙区域列表 [(y_start, y_end, height, center_y), ...]
    """
    height = img_array.shape[0]
    
    # 标记每行是否是空隙行
    uniform_rows = []
    for y in range(height):
        row = img_array[y, :]
        uniform_rows.append(_is_row_uniform(row, max_diff_threshold))
    
    # 找到连续的空隙区域
    gaps = []
    in_gap = False
    gap_start = 0
    
    for y in range(height):
        if uniform_rows[y] and not in_gap:
            in_gap = True
            gap_start = y
        elif not uniform_rows[y] and in_gap:
            in_gap = False
            gap_height = y - gap_start
            if gap_height > min_gap_height:
                center_y = (gap_start + y) / 2
                gaps.append((gap_start, y, gap_height, center_y))
    
    # 处理末尾空隙
    if in_gap:
        gap_height = height - gap_start
        if gap_height > min_gap_height:
            center_y = (gap_start + height) / 2
            gaps.append((gap_start, height, gap_height, center_y))
    
    return gaps


def _find_split_points(pil_image: Image.Image, num_splits: int) -> list:
    """
    使用纯图像处理方式寻找分割点
    
    分割点选择逻辑:
    1. 搜索纵向空隙区域（每行像素RGB各通道max-min差值<=5）
    2. 优先选择高度 >= 18 的较大空隙
    3. 根据目标分割数选择最佳空隙位置
    
    :param pil_image: PIL图片对象
    :param num_splits: 需要分割成的块数（2或3）
    :return: 分割点y坐标列表（图片像素坐标）
    """
    # 参数配置
    MIN_GAP_HEIGHT = 5  # 最小空隙高度
    MAX_DIFF_THRESHOLD = 5  # RGB各通道最大差值阈值
    MIN_LARGE_GAP_HEIGHT = 18  # 较大空隙的高度阈值
    
    img_width, img_height = pil_image.size
    
    # 转换为numpy数组
    img_array = numpy.array(pil_image)
    
    # 确保是RGB格式（去掉alpha通道）
    if len(img_array.shape) == 3 and img_array.shape[2] == 4:
        img_array = img_array[:, :, :3]
    
    _logger.info(f"图像尺寸: {img_width}x{img_height}, 目标分割数: {num_splits}")
    
    # 找到所有空隙区域
    gaps = _find_horizontal_gaps(img_array, MIN_GAP_HEIGHT, MAX_DIFF_THRESHOLD)
    _logger.info(f"找到 {len(gaps)} 个空隙区域")
    
    if not gaps:
        _logger.warning("未找到空隙区域，使用均分方式分割")
        # 均分
        if num_splits == 2:
            return [img_height // 2]
        else:
            return [img_height // 3, img_height * 2 // 3]
    
    # 筛选较大的空隙（高度 >= MIN_LARGE_GAP_HEIGHT）
    large_gaps = [g for g in gaps if g[2] >= MIN_LARGE_GAP_HEIGHT]
    
    # 如果较大空隙数量足够，则只从这些较长的空隙中筛选
    min_required = num_splits - 1  # 切n块需要n-1个分割点
    candidates = large_gaps if len(large_gaps) >= min_required else gaps
    _logger.info(f"候选空隙: {len(candidates)} 个 (较大空隙: {len(large_gaps)} 个)")
    
    if num_splits == 2:
        # 切2块：选择最接近 1/2 处的空隙
        target_y = img_height / 2
        sorted_gaps = sorted(candidates, key=lambda g: abs(g[3] - target_y))
        best_gap = sorted_gaps[0]
        split_points = [int(best_gap[3])]
        _logger.info(f"选择空隙: y=[{best_gap[0]}, {best_gap[1]}], 高度={best_gap[2]}, 中心={split_points[0]}")
    else:
        # 切3块：选择最接近 1/3 和 2/3 处的空隙
        target_y_1 = img_height / 3
        target_y_2 = img_height * 2 / 3
        
        # 按距离 1/3 或 2/3 处的最小偏移排序
        def min_distance_to_targets(gap):
            dist_1 = abs(gap[3] - target_y_1)
            dist_2 = abs(gap[3] - target_y_2)
            return min(dist_1, dist_2)
        
        sorted_gaps = sorted(candidates, key=min_distance_to_targets)
        
        # 选取2个分割点
        selected_gaps = []
        for gap in sorted_gaps:
            if len(selected_gaps) >= 2:
                break
            # 确保选择的空隙不会太近（至少相隔100像素）
            if not selected_gaps or abs(gap[3] - selected_gaps[0][3]) > 100:
                selected_gaps.append(gap)
        
        # 按y坐标排序
        selected_gaps.sort(key=lambda g: g[3])
        split_points = [int(g[3]) for g in selected_gaps]
        
        for i, gap in enumerate(selected_gaps):
            _logger.info(f"选择空隙{i+1}: y=[{gap[0]}, {gap[1]}], 高度={gap[2]}, 中心={int(gap[3])}")
    
    return split_points


def _adjust_coordinates(json_data: dict, offset_y: int = 0, scale: float = 1.0) -> dict:
    """
    调整json数据中所有控件的坐标
    
    先进行缩放修正（scale），再加上y偏移量（offset_y）
    
    :param json_data: VLM返回的json数据
    :param offset_y: y坐标偏移量
    :param scale: 缩放因子（用于修正因缩放导致的坐标变化）
    :return: 调整后的json数据
    """
    if not json_data:
        return json_data
    
    result = json_data.copy()
    
    # 先进行缩放修正
    if scale != 1.0:
        if 'x' in result:
            result['x'] = int(result['x'] * scale)
        if 'y' in result:
            result['y'] = int(result['y'] * scale)
        if 'width' in result:
            result['width'] = int(result['width'] * scale)
        if 'height' in result:
            result['height'] = int(result['height'] * scale)
    
    # 再加上y偏移量
    if offset_y != 0 and 'y' in result:
        result['y'] = result['y'] + offset_y
    
    # 递归调整children中的坐标
    if 'children' in result and isinstance(result['children'], list):
        result['children'] = [_adjust_coordinates(child, offset_y, scale) for child in result['children']]
    
    return result


def _merge_vlm_results(results: list, part_infos: list) -> dict:
    """
    合并多部分的VLM结果
    
    :param results: VLM结果列表
    :param part_infos: 每部分的信息列表 [(offset_y, scale), ...]
                       offset_y: 该部分在原图中的起始y坐标
                       scale: 该部分图片的缩放因子（实际高度/缩放后高度）
    :return: 合并后的结果
    """
    if not results:
        return {}
    
    merged = None
    total_height = 0
    
    for i, (result, (offset_y, scale)) in enumerate(zip(results, part_infos)):
        if not result:
            continue
        
        # 调整该部分所有控件的坐标
        adjusted_result = _adjust_coordinates(result, offset_y, scale)
        
        if merged is None:
            merged = adjusted_result
            if 'children' not in merged:
                merged['children'] = []
        else:
            # 合并children
            if 'children' in adjusted_result and isinstance(adjusted_result['children'], list):
                merged['children'].extend(adjusted_result['children'])
        
        # 累加高度
        if 'height' in adjusted_result:
            total_height += int(adjusted_result.get('height', 0) * scale)
    
    if merged and total_height > 0:
        merged['height'] = total_height
    
    return merged or {}


def _call_vlm_api_with_base64(text: str, base64_image: str) -> dict:
    """
    使用base64编码的图片调用VLM API
    
    :param text: 提示文本
    :param base64_image: base64编码的图片
    :return: API返回结果
    """
    input_params = {
        "BOT_USER_INPUT": text,
        "image": base64_image
    }
    return run_flow(tweaks=input_params)


def parse_json_safely(json_str: str) -> dict:
    """
    安全解析JSON字符串，处理VLM返回的非标准JSON格式
    
    :param json_str: JSON字符串
    :return: 解析后的字典
    """
    import re
    
    if not json_str:
        return {}
    
    # 始终先清理非标准JSON格式（注释、尾随逗号等）
    cleaned = json_str
    
    # 移除可能的markdown代码块标记
    cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^```\s*$', '', cleaned, flags=re.MULTILINE)
    
    # 移除 JavaScript 风格的单行注释 // ...
    # 匹配：空白字符后跟 // 及其后的内容（排除 URL 中的 http:// https://）
    cleaned = re.sub(r'\s//[^\n\r]*', '', cleaned)
    
    # 移除 JavaScript 风格的多行注释 /* ... */
    cleaned = re.sub(r'/\*[\s\S]*?\*/', '', cleaned)
    
    # 移除尾随逗号（在 } 或 ] 之前的逗号）
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    
    # 解析清理后的 JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        _logger.warning(f"JSON解析失败: {e}")
        _logger.warning(f"清理后的JSON内容: {cleaned[:500]}...")
        return {}


def _parse_vlm_response(response: dict) -> dict:
    """
    解析VLM API的返回结果
    
    :param response: API原始返回
    :return: 解析后的json数据
    """
    if response.get('ret') == 0:
        json_data = response.get("data", {}).get("output", "{}")
        if isinstance(json_data, str):
            return parse_json_safely(json_data)
        return json_data
    return {}


# 多模态结果进程内缓存：仅成功且 body 为合法 JSON 时写入；TTL 48 小时
VLM_CACHE_TTL_SECONDS = 48 * 60 * 60


def _vlm_api_ret_success(resp) -> bool:
    return isinstance(resp, dict) and resp.get("ret") == 0


def _is_cacheable_vlm_bundle(result) -> bool:
    """
    是否允许缓存：ret==0，且 data.output 为 dict/list，或为可解析为 JSON 对象/数组的字符串。
    """
    if not _vlm_api_ret_success(result):
        return False
    data = result.get("data")
    if not isinstance(data, dict):
        return False
    out = data.get("output")
    if out is None:
        return False
    if isinstance(out, (dict, list)):
        return True
    if isinstance(out, str):
        s = out.strip()
        if not s:
            return False
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            parsed = parse_json_safely(s)
        return isinstance(parsed, (dict, list))
    return False


def _resize_image_if_needed(pil_image: Image.Image, max_height: int) -> tuple:
    """
    如果图片高度超过max_height，则等比缩小到max_height
    
    :param pil_image: PIL图片对象
    :param max_height: 最大高度
    :return: (缩放后的图片, 缩放因子)
            缩放因子 = 原始高度 / 缩放后高度，用于还原坐标
    """
    img_width, img_height = pil_image.size
    
    if img_height <= max_height:
        return pil_image, 1.0
    
    # 等比缩放
    scale = img_height / max_height
    new_width = int(img_width / scale)
    new_height = max_height
    
    resized = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    _logger.info(f"图片缩放: {img_width}x{img_height} -> {new_width}x{new_height}, 缩放因子={scale:.2f}")
    
    return resized, scale


def call_vlm_api(text: str, context) -> dict:
    """
    调用VLM API识别UI结构
    
    分割策略：
    - width >= height（横屏/正方形）：不分割
    - 竖屏且高度 <= FIGMA_DESIGN_HEIGHT（812）：不分割
    - 竖屏且高度 812～1500：切 2 块
    - 竖屏且高度 > 1500：切 3 块
    
    切块后，如果某部分高度 > FIGMA_DESIGN_HEIGHT，会缩放到 FIGMA_DESIGN_HEIGHT 后再送VLM检测，
    返回的坐标会同步修正
    
    :param text: 提示文本
    :param context: 处理上下文
    :return: API返回结果
    """
    if not is_vlm_enabled():
        _logger.info("VLM 未启用，跳过 call_vlm_api")
        return {"ret": -1, "msg": "VLM provider disabled", "data": {"output": ""}}

    height = context.dsl.metadata.height
    width = context.dsl.metadata.width
    image_url = context.dsl.metadata.image_url
    
    # 获取图片二进制数据并计算MD5作为缓存key
    image_bytes = None
    cache_key = None
    try:
        response = requests.get(
            image_url, verify=get_ssl_verify(), timeout=get_http_timeout(default=10)
        )
        image_bytes = response.content
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        cache_key = CacheKey.VLM_API_RESULT.value.format(image_md5=image_hash)
        
        # 尝试从进程内缓存读取
        try:
            cached_result = memory_kv.get(cache_key)
            if cached_result:
                _logger.info(f"VLM API 缓存命中, key: {cache_key}")
                return json.loads(cached_result)
        except Exception as e:
            _logger.warning(f"读取 VLM 缓存失败: {e}")
    except Exception as e:
        _logger.warning(f"获取图片数据用于缓存失败: {e}")
    
    result = None
    split_part_responses = None  # 分割路径下各分片的原始 API 响应（用于判断是否全部成功后再缓存）

    # 竖屏（height > width）且高度超阈值时才分割；横屏/正方形整图送 VLM
    if height > width and height > SPLIT_THRESHOLD_2:
        # 确定分割数量
        if height > SPLIT_THRESHOLD_3:
            num_splits = 3
        else:
            num_splits = 2
        
        _logger.info(f"设计稿尺寸({width}x{height})，分割成 {num_splits} 块")
        
        try:
            # 获取背景图
            if image_bytes:
                pil_image = Image.open(BytesIO(image_bytes))
            else:
                pil_image = _get_image_by_url(image_url)
            img_width, img_height = pil_image.size
            
            # 计算图片与DSL的缩放比例
            dsl_to_img_scale = img_height / height if height > 0 else 1
            
            # 查找分割点
            split_points = _find_split_points(pil_image, num_splits)
            _logger.info(f"图片尺寸: {img_width}x{img_height}, 分割点: {split_points}")
            
            # 根据分割点切割图片
            all_points = [0] + split_points + [img_height]
            image_parts = []
            part_infos = []  # [(offset_y, scale), ...]
            
            import os
            debug_dir = os.path.join(os.getcwd(), "vlm_debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            for i in range(len(all_points) - 1):
                y_start, y_end = all_points[i], all_points[i + 1]
                part = pil_image.crop((0, y_start, img_width, y_end))
                
                # 计算该部分在DSL坐标系中的偏移
                offset_y_dsl = int(y_start / dsl_to_img_scale)
                
                # 如果该部分高度超过MAX_HEIGHT，缩放到MAX_HEIGHT
                part_resized, resize_scale = _resize_image_if_needed(part, MAX_HEIGHT)
                
                image_parts.append(part_resized)
                part_infos.append((offset_y_dsl, resize_scale))
                
                # 保存调试图片
                debug_path = os.path.join(debug_dir, f"image_part{i+1}.png")
                part_resized.save(debug_path, "PNG")
                _logger.info(f"第{i+1}部分: 原始高度={y_end-y_start}, "
                           f"缩放后={part_resized.size[1]}, offset_y={offset_y_dsl}, scale={resize_scale:.2f}")
            
            # 并发调用VLM API处理所有部分
            from concurrent.futures import ThreadPoolExecutor
            
            _logger.info(f"并发调用VLM API处理 {len(image_parts)} 部分...")
            with ThreadPoolExecutor(max_workers=len(image_parts)) as executor:
                futures = []
                for part in image_parts:
                    base64_img = _pil_image_to_base64(part)
                    future = executor.submit(_call_vlm_api_with_base64, text, base64_img)
                    futures.append(future)
                
                responses = [f.result() for f in futures]
            
            _logger.info(f"{len(image_parts)} 部分VLM API调用完成")
            
            # 解析所有结果
            json_results = []
            for i, resp in enumerate(responses):
                json_result = _parse_vlm_response(resp)
                json_results.append(json_result)
                _logger.info(f"第{i+1}部分识别结果: {len(json_result.get('children', []))} 个子元素")
            
            # 合并结果
            merged_result = _merge_vlm_results(json_results, part_infos)
            _logger.info(f"合并后结果: {len(merged_result.get('children', []))} 个子元素")
            
            # 返回与原始API格式一致的结果
            split_part_responses = responses
            result = {
                "ret": 0,
                "data": {
                    "output": json.dumps(merged_result, ensure_ascii=False)
                }
            }
            
        except Exception as e:
            _logger.error(f"分割处理失败: {e}", exc_info=True)
            # 降级为直接调用
            _logger.info("降级为直接调用VLM API")
    
    # 正常调用（不需要分割或分割失败时降级）
    if result is None:
        if image_bytes:
            pil_image = Image.open(BytesIO(image_bytes))
            base64_img = _pil_image_to_base64(pil_image)
            result = _call_vlm_api_with_base64(text, base64_img)
        else:
            result = run_flow(tweaks={"BOT_USER_INPUT": text, "image": image_url})
    
    # 仅成功且返回体为合法 JSON 时缓存 48h；分割路径需每一分片 ret==0
    should_cache = False
    if cache_key and result is not None:
        if split_part_responses is not None:
            if all(_vlm_api_ret_success(r) for r in split_part_responses) and _is_cacheable_vlm_bundle(result):
                should_cache = True
            else:
                _logger.info("VLM 分割调用存在失败分片或响应不可缓存，跳过写入缓存")
        elif _is_cacheable_vlm_bundle(result):
            should_cache = True
        else:
            _logger.info("VLM 单次调用未返回可缓存的成功 JSON（ret!=0 或 data.output 非 JSON），跳过写入缓存")

    if cache_key and should_cache:
        try:
            memory_kv.put(cache_key, json.dumps(result), ex=VLM_CACHE_TTL_SECONDS)
            _logger.info(f"VLM API 结果已缓存（{VLM_CACHE_TTL_SECONDS // 3600}h）, key: {cache_key}")
        except Exception as e:
            _logger.warning(f"写入 VLM 缓存失败: {e}")
    
    return result


def _collect_text_from_rich_container(component) -> str:
    """
    递归收集富文本容器中的所有文本内容
    
    :param component: 富文本容器组件
    :return: 收集到的所有文本内容
    """
    texts = []
    if hasattr(component, 'children') and component.children:
        for child in component.children:
            if child.type == dsl_enum.ComponentType.TEXT:
                if hasattr(child, 'props') and hasattr(child.props, 'text') and child.props.text:
                    texts.append(child.props.text)
            elif is_rich_text_container(child):
                texts.append(_collect_text_from_rich_container(child))
    return ''.join(texts)


