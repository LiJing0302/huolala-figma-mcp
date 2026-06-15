"""
Export 服务 - ZIP 打包层
负责将处理后的 DSL 打包成 ZIP 文件
"""
import asyncio
import hashlib
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Literal, Union, Any, Optional

import aiohttp

from mdap_u2c.config.http_config import get_aiohttp_ssl
from mdap_u2c.utils.serializer_utils import SerializerUtils
from mdap_u2c.utils.local_export_http import build_download_url, get_export_dir
from mdap_u2c.config.font_config import FontConfig

from mdap_u2c.enums import dsl_enum
from mdap_u2c.models import dsl_model, common_model
from mdap_u2c.config import path_config
from mdap_u2c.figma.client_figma import FigmaClient

from .del_same_img import remove_same_image_resource
from .dsl_to_web_code_service import DslToWebCodeService

logger = logging.getLogger(__name__)

_IMAGE_BASENAME_MAX_LEN = 200


def _sanitize_image_basename(name: str) -> str:
    base = os.path.basename(name)
    safe = re.sub(r"[^\w\-]", "_", base, flags=re.ASCII).strip("._")
    if not safe:
        return "image"
    return safe[:_IMAGE_BASENAME_MAX_LEN]

# 批量导图：单次请求最多节点数；超过则拆成多批，最多 6 批并行
EXPORT_IMAGE_BATCH_SIZE = 36
EXPORT_IMAGE_MAX_PARALLEL = 6
# 某批失败时，先按 6 个节点一批重试；仍失败再按 1 个节点一批重试
EXPORT_IMAGE_RETRY_BATCH_SIZE = 6


def _chunk_list(lst: List[str], size: int) -> List[List[str]]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def _run_async_safely(coro):
    """
    安全地运行异步函数，无论是否在已有的事件循环中
    如果已有事件循环，在新线程中创建新的事件循环运行；否则使用 asyncio.run()
    """
    try:
        # 尝试获取当前运行的事件循环
        asyncio.get_running_loop()
        # 如果成功获取到，说明在已有事件循环中，需要在新线程中运行
        import concurrent.futures
        import threading
        
        future = concurrent.futures.Future()
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            finally:
                new_loop.close()
        
        thread = threading.Thread(target=run_in_thread, daemon=False)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # 没有运行的事件循环，使用 asyncio.run()
        return asyncio.run(coro)


class ExportService:
    _image_node_ids: List[str]                                          # 需要导出图片的figma节点id列表
    _image_node_id_type_map: Dict[str, Literal["image", "background"]]  # 图片类型(图片组件，背景图片)
    _node_id_to_component_id: Dict[str, str]                            # figma节点id和组件id的映射map
    _component_id_to_component: Dict[str, dsl_model.AbstractComponent]  # 组件id和组件的映射map
    _image_name_map: Dict[str, int]                                     # 图片名称出现次数映射关系
    _export_font_map: Dict[str, str]                                    # 需要导出的字体列表(key -> font file name)
    _image_scales: List[int]                                             # 图片导出倍数列表；仅一种倍数时文件夹为 images，多种时为 images_2、images_3 等
    _node_id_crop_info: Dict[str, Dict[str, Any]]                       # 需要按 render_bounds 裁剪的节点信息
    _node_id_expand_info: Dict[str, Dict[str, Any]]                     # 需要按 render_bounds 扩展的节点信息

    def __init__(self, image_scale: Union[int, List[int]] = 2):
        if isinstance(image_scale, int):
            self._image_scales = [image_scale] if 1 <= image_scale <= 4 else [2]
        else:
            self._image_scales = [s for s in image_scale if 1 <= s <= 4] or [2]
        self._image_node_ids = []
        self._image_name_map = {}
        self._export_font_map = {}
        self._image_node_id_type_map = {}
        self._node_id_to_component_id = {}
        self._component_id_to_component = {}
        self._node_id_crop_info = {}
        self._node_id_expand_info = {}
        self._http_session = None

    def _get_image_folder_name(self, scale: int, is_primary: bool = False) -> str:
        """仅一种倍数时返回 images；多种倍数时全部为 images_{倍数}，index.html 默认使用第一个倍数目录。"""
        if len(self._image_scales) == 1:
            return "images"
        return f"images_{scale}"

    def generate_pack(
        self,
        dsl: dsl_model.DSL,
        user_info: common_model.TokenUserInfo,
        shared_data: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        if dsl is None:
            raise Exception("DSL cannot be None")

        if dsl.components is None or len(dsl.components) == 0:
            raise Exception("DSL components cannot be None or empty")

        # 遍历DSL树
        self._traversal_component(dsl)

        key = hashlib.sha256(f"{dsl.metadata.file_key}_{dsl.metadata.node_id}".encode("utf-8")).hexdigest()
        temp_dir = f"{path_config.PathConfig.get_temp_dir()}/{user_info.client_id}/{key}/"
        resource_dir = os.path.join(temp_dir, dsl.metadata.name)
        self._clean_temp_folder(temp_dir)
        try:
            os.makedirs(resource_dir, exist_ok=True)
            _run_async_safely(self._prepare_resources(resource_dir, dsl))
            self._generate_dsl_json_file(resource_dir, dsl)
            self._generate_design_png_file(resource_dir, shared_data)
            self._copy_font_files(resource_dir)
            self._generate_index_html_file(resource_dir, DslToWebCodeService(dsl, self._export_font_map).to_web_code())
            remove_same_image_resource(resource_dir, self._image_scales)
            zip_path = shutil.make_archive(base_name=temp_dir + "/data",
                                           format="zip",
                                           root_dir=os.path.join(temp_dir, dsl.metadata.name),
                                           base_dir="")
            # 写入固定本地目录并启动本地 HTTP，返回可下载的 http 地址（temp 在 finally 中清理）
            local_root = get_export_dir()
            os.makedirs(local_root, exist_ok=True)
            filename = f"{key}.zip"
            local_zip = os.path.join(local_root, filename)
            shutil.copy2(zip_path, local_zip)
            url = build_download_url(filename)
            logger.info("ZIP 已导出: %s -> %s", local_zip, url)
            return url
        finally:
            _run_async_safely(self._close_http_session())
            self._clean_temp_folder(temp_dir)

    def _traversal_component(self, dsl: dsl_model.DSL):
        stack = list(dsl.components or [])
        while stack:
            component = stack.pop()
            if not component:
                continue

            self._component_id_to_component[component.id] = component
            if component.figma is not None and component.figma.node_id:
                self._node_id_to_component_id[component.figma.node_id] = component.id

            self._check_image_node(component)   # 检测组件是否为图片类型
            self._check_text_node(component)    # 检测文本节点

            # 清理冗余信息
            component.figma = None
            component.layout = None
            component.parent_id = None
            component.extensions = None

            if hasattr(component, "children") and isinstance(component.children, list):
                stack.extend(component.children)

    async def _prepare_resources(self, resource_dir: str, dsl: dsl_model.DSL):
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=get_aiohttp_ssl(), limit=100)
            )

        # 多倍数切图：仅一种倍数时文件夹为 images；多种时全部为 images_2、images_3 等，主倍数写入组件路径（index.html 默认加载第一个倍数目录）
        # 先按 node_id 固定顺序生成命名映射，保证各 images_{scale} 目录下文件名一致
        node_id_to_image_name = self._build_node_id_to_image_name()
        primary_scale = self._image_scales[0]
        image_tasks = [
            self._download_images(
                resource_dir,
                dsl.metadata.file_key,
                scale,
                update_component_paths=(scale == primary_scale),
                image_folder=self._get_image_folder_name(scale, is_primary=(scale == primary_scale)),
                node_id_to_image_name=node_id_to_image_name,
            )
            for scale in self._image_scales
        ]
        tasks = [
            *image_tasks,
            asyncio.to_thread(self._generate_dsl_json_file, resource_dir, dsl),
            asyncio.to_thread(self._generate_vlm_result_json_file, resource_dir, dsl),
        ]
        await asyncio.gather(*tasks)

    def _copy_font_files(self, save_prefix):
        if self._export_font_map is None or len(self._export_font_map) == 0:
            return

        save_path = os.path.join(save_prefix, "fonts")
        os.makedirs(save_path, exist_ok=True)
        font_path = f"{path_config.PathConfig.get_assets_dir()}/fonts"

        def copy_font(font_file):
            src = f"{font_path}/{font_file}"
            dst = f"{save_path}/{font_file}"
            if not os.path.isfile(src):
                return
            try:
                os.link(src, dst)
            except OSError:
                shutil.copyfile(src, dst)

        with ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(copy_font, self._export_font_map.values())

    async def _export_images_batched(self, file_key: str, scale: int) -> Dict[str, str]:
        """
        批量导出图片：若 node_ids 超过 36 则拆成多批，最多 6 个请求并行。
        若某批失败则将该批拆成每批 6 个重试；仍失败则拆成每批 1 个重试。
        scale: 导出倍数，如 2、3、4。
        """
        node_ids = self._image_node_ids
        if not node_ids:
            return {}
        figma = FigmaClient.get_instance()
        sem = asyncio.Semaphore(EXPORT_IMAGE_MAX_PARALLEL)

        async def do_batch(chunk: List[str]) -> Dict[str, str]:
            async with sem:
                return await asyncio.to_thread(figma.export_images, file_key, chunk, scale)

        all_results: Dict[str, str] = {}

        # 1. 按 36 拆分，最多 6 批并行
        chunks = _chunk_list(node_ids, EXPORT_IMAGE_BATCH_SIZE)
        logger.info(f"开始figma节点导图请求，共{len(self._image_node_ids)}个图片节点，拆成{len(chunks)}批（每批最多{EXPORT_IMAGE_BATCH_SIZE}个，最多{EXPORT_IMAGE_MAX_PARALLEL}批并行）")
        batch_results = await asyncio.gather(*[do_batch(c) for c in chunks])
        failed_chunks = [c for c, r in zip(chunks, batch_results) if not r]
        for r in batch_results:
            if r:
                all_results.update(r)

        if not failed_chunks:
            return all_results

        # 2. 失败批次按每批 6 个重试，最多 6 批并行
        retry_chunks: List[List[str]] = []
        for c in failed_chunks:
            retry_chunks.extend(_chunk_list(c, EXPORT_IMAGE_RETRY_BATCH_SIZE))
        logger.warning(f"有{len(failed_chunks)}批导图失败，按每批{EXPORT_IMAGE_RETRY_BATCH_SIZE}个重试，共{len(retry_chunks)}批")
        retry_results = await asyncio.gather(*[do_batch(c) for c in retry_chunks])
        failed_again = [c for c, r in zip(retry_chunks, retry_results) if not r]
        for r in retry_results:
            if r:
                all_results.update(r)

        if not failed_again:
            return all_results

        # 3. 仍失败的按每批 1 个重试，最多 6 批并行
        single_chunks = [[nid] for c in failed_again for nid in c]
        logger.warning(f"仍有{len(single_chunks)}个节点导图失败，按单节点重试")
        single_results = await asyncio.gather(*[do_batch(c) for c in single_chunks])
        for r in single_results:
            if r:
                all_results.update(r)

        return all_results

    def _build_node_id_to_image_name(self) -> Dict[str, str]:
        """
        按 node_id 固定顺序（排序）生成 node_id -> 图片文件名 的映射，保证多倍数导图时
        images 与 images_2 等目录下同名文件对应同一节点。
        """
        node_id_to_image_name: Dict[str, str] = {}
        for node_id in sorted(self._image_node_ids):
            if node_id not in self._node_id_to_component_id:
                continue
            component_id = self._node_id_to_component_id[node_id]
            component = self._component_id_to_component.get(component_id)
            if component is None:
                continue
            image_name = self._get_image_name(component)
            node_id_to_image_name[node_id] = image_name
        return node_id_to_image_name

    async def _download_images(
        self,
        save_prefix: str,
        file_key: str,
        scale: int,
        update_component_paths: bool = True,
        image_folder: str | None = None,
        node_id_to_image_name: Dict[str, str] | None = None,
    ):
        """
        按指定倍数从 Figma 导图并保存到指定文件夹（仅一种倍数时为 images，多种时全部为 images_{scale}）。
        update_component_paths: 是否更新组件中的图片路径（仅主倍数设为 True，index.html 默认加载该目录）。
        node_id_to_image_name: 可选，node_id -> 文件名映射，传入时与各目录命名保持一致。
        """
        if not self._image_node_ids or len(self._image_node_ids) == 0:
            return

        images_data = await self._export_images_batched(file_key, scale)
        if not images_data:
            logger.warning("从figma导图失败，请检测日志进行排查")
            return

        if image_folder is None:
            image_folder = self._get_image_folder_name(scale, is_primary=update_component_paths)
        image_save_path = os.path.join(save_prefix, image_folder)
        os.makedirs(image_save_path, exist_ok=True)
        semaphore = asyncio.Semaphore(10)

        async def fetch_and_save(node_id, image_url):
            if not image_url:
                return False

            async with semaphore:
                if node_id in self._node_id_to_component_id:
                    component_id = self._node_id_to_component_id[node_id]
                    component = self._component_id_to_component[component_id]
                    if node_id_to_image_name is not None and node_id in node_id_to_image_name:
                        image_name = node_id_to_image_name[node_id]
                    else:
                        image_name = self._get_image_name(component)
                    file_path = f"{image_save_path}/{image_name}"
                    is_success = await self._download_file(image_url, file_path)
                    if is_success and (node_id in self._node_id_crop_info or node_id in self._node_id_expand_info):
                        await asyncio.to_thread(self.edit_image_by_render_bounds, file_path, node_id, scale)
                    if update_component_paths:
                        image_type = self._image_node_id_type_map[node_id]
                        path = f"./{image_folder}/{image_name}" if is_success else image_url
                        if image_type == "background":
                            component.style.background_image = f"url({path})" if is_success else image_url
                        elif image_type == "image":
                            component.props.src = path if is_success else image_url
                    return is_success
            return False

        tasks = [fetch_and_save(node_id, image_url) for node_id, image_url in images_data.items()]
        await asyncio.gather(*tasks)

    def _record_crop_info_if_needed(self, node_id: str, component: dsl_model.AbstractComponent) -> None:
        """若 render_bounds_size < bounding_box_size，则标记该节点图片需要按 render_bounds 裁剪。"""
        if not component.figma:
            return
        fi = component.figma
        rb_size = fi.render_bounds_size
        bb_size = fi.bounding_box_size
        rb_pos = fi.render_bounds_position
        bb_pos = fi.bounding_box_position
        if not rb_size or not bb_size or not rb_pos:
            return
        rw = rb_size.width if rb_size.width is not None else 0
        rh = rb_size.height if rb_size.height is not None else 0
        bw = bb_size.width if bb_size.width is not None else 0
        bh = bb_size.height if bb_size.height is not None else 0
        if rw >= bw and rh >= bh:
            return
        self._node_id_crop_info[node_id] = {
            "render_bounds_position": {"x": rb_pos.x - bb_pos.x, "y": rb_pos.y - bb_pos.y},
            "render_bounds_size": {"width": rw, "height": rh},
            "bounding_box_size": {"width": bw, "height": bh},
            "control_size": {"width": component.layout.size.width, "height": component.layout.size.height}
        }

    def _record_expand_info_if_needed(self, node_id: str, component: dsl_model.AbstractComponent) -> None:
        """当 render_bounds_size > bounding_box_size 时，标记该节点图片可能需要扩展。"""
        if not component.figma:
            return
        fi = component.figma
        rb_size = fi.render_bounds_size
        bb_size = fi.bounding_box_size
        rb_pos = fi.render_bounds_position
        bb_pos = fi.bounding_box_position
        if not rb_size or not bb_size or not rb_pos or not bb_pos:
            return
        rw = rb_size.width if rb_size.width is not None else 0
        rh = rb_size.height if rb_size.height is not None else 0
        bw = bb_size.width if bb_size.width is not None else 0
        bh = bb_size.height if bb_size.height is not None else 0
        if rw <= bw and rh <= bh:
            return
        self._node_id_expand_info[node_id] = {
            "bounding_box_position_in_render_bounds": {"x": bb_pos.x - rb_pos.x, "y": bb_pos.y - rb_pos.y},
            "render_bounds_size": {"width": rw, "height": rh},
            "bounding_box_size": {"width": bw, "height": bh},
            "control_size": {"width": component.layout.size.width, "height": component.layout.size.height}
        }

    def _get_image_name(self, component: dsl_model.AbstractComponent):
        if component.props and component.props.class_name and len(component.props.class_name) > 0:
            name = _sanitize_image_basename(component.props.class_name)
        else:
            name = "image"

        if name in self._image_name_map:
            self._image_name_map[name] += 1
            return f"{name}_{self._image_name_map[name]}.png"
        else:
            self._image_name_map[name] = 1
            return f"{name}.png"

    def _check_text_node(self, component: dsl_model.AbstractComponent):
        if not component.is_instance_of(dsl_enum.ComponentType.TEXT):
            return

        post_script_name = getattr(component.figma, "font_post_script_name", None)
        if post_script_name is None:
            return

        if post_script_name not in self._export_font_map:
            font_file = FontConfig.get_font_file(post_script_name)
            if font_file:
                self._export_font_map[post_script_name] = font_file

        if post_script_name in self._export_font_map:
            component.style.font_family = post_script_name

    def _check_image_node(self, component: dsl_model.AbstractComponent):
        if component.is_instance_of(dsl_enum.ComponentType.IMAGE) and component.figma:
            node_id = component.figma.node_id
            self._image_node_ids.append(node_id)
            self._image_node_id_type_map[node_id] = "image"
            self._record_crop_info_if_needed(node_id, component)
            self._record_expand_info_if_needed(node_id, component)  # render_bounds_size > bounding_box_size 时标记可能需要扩展
        elif component.style and component.style.background_image:
            # 判断样式中是否有background图片（此处为图片的 figma node_id）
            node_id = component.style.background_image
            self._image_node_ids.append(node_id)
            self._image_node_id_type_map[node_id] = "background"
            self._record_crop_info_if_needed(node_id, component)
            self._record_expand_info_if_needed(node_id, component)
            # background 对应的 IMAGE 组件可能尚未遍历到，裁剪信息在遍历到该 IMAGE 时由 _record_crop_info_if_needed 记录

    async def _close_http_session(self):
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    def _crop_image_by_render_bounds(self, file_path: str, node_id: str, scale: int) -> bool:
        """
        若图片尺寸满足 int(width/scale)==int(bounding_box_size.width) 且 int(height/scale)==int(bounding_box_size.height)，
        则按 render_bounds_position 与 render_bounds_size 裁剪后覆盖原文件。
        """
        if node_id not in self._node_id_crop_info:
            return True
        try:
            from PIL import Image
        except ImportError:
            logger.warning("PIL 未安装，跳过图片裁剪")
            return True
        info = self._node_id_crop_info[node_id]
        bbox = info["bounding_box_size"]
        rb_pos = info["render_bounds_position"]
        rb_size = info["render_bounds_size"]
        try:
            img = Image.open(file_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"打开图片失败，跳过裁剪: {file_path}, err: {e}")
            return True
        w, h = img.size
        bbox_w, bbox_h = bbox["width"], bbox["height"]
        design_w, design_h = w *1.0/ scale, h*1.0 / scale
        expected_w, expected_h = bbox_w, bbox_h
        # 多倍图导出时 Figma 各倍数舍入可能不同，用 1 像素容差保证各倍数一致地执行裁剪
        if abs(design_w - expected_w) > 1 or abs(design_h - expected_h) > 1:
            return True
        left = int(rb_pos["x"] * scale)
        top = int(rb_pos["y"] * scale)
        cw = int(rb_size["width"] * scale)
        ch = int(rb_size["height"] * scale)
        # 避免裁剪后宽高过小（如 1x1）：若裁剪区域宽或高 ≤ 1 像素则跳过裁剪，保留原图
        if cw <= 1 or ch <= 1:
            return True
        left = max(0, min(left, w - 1))
        top = max(0, min(top, h - 1))
        right = min(w, left + cw)
        bottom = min(h, top + ch)
        if right <= left or bottom <= top:
            return True
        cropped = img.crop((left, top, right, bottom))
        logger.info(f"执行图片越界裁剪:{file_path}")
        try:
            cropped.save(file_path)
        except Exception as e:
            logger.warning(f"裁剪后保存失败: {file_path}, err: {e}")
            return True
        return True

    def _expand_image_by_render_bounds(self, file_path: str, node_id: str, scale: int) -> bool:
        """
        当标记为需要扩展的图片尺寸满足 abs(bounding_box_size.width - width/scale) <= 1 且
        abs(bounding_box_size.height - height/scale) <= 1 时，根据 render_bounds_size 与坐标扩展 PNG 边缘，扩展区域填充全透明。
        """
        if node_id not in self._node_id_expand_info:
            return True
        try:
            from PIL import Image
        except ImportError:
            logger.warning("PIL 未安装，跳过图片扩展")
            return True
        info = self._node_id_expand_info[node_id]
        rb_size = info["render_bounds_size"]
        bb_pos_in_rb = info["bounding_box_position_in_render_bounds"]
        try:
            img = Image.open(file_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"打开图片失败，跳过扩展: {file_path}, err: {e}")
            return True
        w, h = img.size
        control_size = info["control_size"]
        control_w, control_h = control_size["width"], control_size["height"]
        file_w, file_h = w * 1.0 / scale, h * 1.0 / scale

        if abs(control_w - file_w) <= 1 and abs(control_h - file_h) <= 1:
            return True
        new_w = int(rb_size["width"] * scale)
        new_h = int(rb_size["height"] * scale)
        if new_w <= 0 or new_h <= 0:
            return True
        paste_x = int(bb_pos_in_rb["x"] * scale)
        paste_y = int(bb_pos_in_rb["y"] * scale)
        new_img = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
        new_img.paste(img, (paste_x, paste_y))
        logger.info(f"执行图片扩展: {file_path}")
        try:
            new_img.save(file_path)
        except Exception as e:
            logger.warning(f"扩展后保存失败: {file_path}, err: {e}")
            return True
        return True

    def edit_image_by_render_bounds(self, file_path: str, node_id: str, scale: int) -> None:
        """根据节点所属的 crop/expand 信息，对图片进行裁剪或扩展。"""
        if node_id in self._node_id_crop_info:
            self._crop_image_by_render_bounds(file_path, node_id, scale)
        elif node_id in self._node_id_expand_info:
            self._expand_image_by_render_bounds(file_path, node_id, scale)

    async def _download_file(self, url: str, file_path: str) -> bool:
        try:
            async with self._http_session.get(url) as response:
                if response.status == 200:
                    with open(file_path, 'wb') as f:
                        f.write(await response.read())
                        return True
        except Exception as e:
            logger.error(f"异步文件下载失败, url: {url}, err: {e}", exc_info=True)

        return False

    @staticmethod
    def _generate_dsl_json_file(resource_dir: str, dsl: dsl_model.DSL):
        dsl_json_path = os.path.join(resource_dir, "dsl.json")
        with open(dsl_json_path, "w", encoding="utf-8") as json_file:
            json_file.write(SerializerUtils.to_json(dsl))

    @staticmethod
    def _generate_vlm_result_json_file(resource_dir: str, dsl: dsl_model.DSL):
        """
        导出VLM多模态大模型返回的UI结构识别结果为vlm_result.json文件
        """
        if dsl.vlm_result is None:
            logger.info("vlm_result为空，跳过导出vlm_result.json")
            return
        
        import json
        vlm_result_path = os.path.join(resource_dir, "vlm_result.json")
        with open(vlm_result_path, "w", encoding="utf-8") as json_file:
            json_file.write(json.dumps(dsl.vlm_result, ensure_ascii=False, indent=2))
        logger.info(f"vlm_result.json已导出到: {vlm_result_path}")

    @staticmethod
    def _generate_design_png_file(resource_dir: str, shared_data: Optional[Dict[str, Any]]) -> None:
        """
        将处理链路中的原始设计图导出为 design.png，随 ZIP 一起打包。
        """
        if not shared_data:
            return
        pil_image = shared_data.get("pil_image")
        if pil_image is None:
            return

        design_png_path = os.path.join(resource_dir, "design.png")
        try:
            pil_image.save(design_png_path, format="PNG")
            logger.info(f"design.png已导出到: {design_png_path}")
        except Exception as e:
            logger.warning(f"导出design.png失败: {e}", exc_info=True)

    @staticmethod
    def _generate_index_html_file(resource_dir: str, html_value: str):
        dsl_json_path = os.path.join(resource_dir, "index.html")
        with open(dsl_json_path, "w", encoding="utf-8") as json_file:
            json_file.write(html_value)

    @staticmethod
    def _clean_temp_folder(path: str):
        """删除指定目录"""
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
        except Exception as e:
            logger.error(f"删除目录失败, path: {path}, err: {e}", exc_info=True)
