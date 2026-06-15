"""
Figma 服务
- 从 Figma 获取设计稿转换为 DSL
https://developers.figma.com/docs/rest-api/file-property-types/#typestyle-type
"""
import json
import logging
from typing import Any, Dict, Optional, List

from mdap_u2c.core import memory_kv
from mdap_u2c.figma import client_figma
from mdap_u2c.models import dsl_model
from mdap_u2c.figma.component_converters import CoordinateResolver
from mdap_u2c.enums import dsl_enum, cache_enum, figma_enum
from mdap_u2c.figma.component_converters.factory import ComponentFactory
from mdap_u2c.figma.optimizer.component_after_optimizer import ComponentAfterOptimizer

logger = logging.getLogger(__name__)

FIGMA_MAX_SUPPORT_NODE_WIDTH = 1500
# 与 VLM 一致：进程内 TTL 缓存成功结果，48 小时
FIGMA_CACHE_TTL_SECONDS = 48 * 60 * 60


def _cached_figma_entry_valid(info: Any) -> bool:
    """进程内缓存条目是否可用：含 version 且 node 为带 type 的非空对象。"""
    if not isinstance(info, dict):
        return False
    node = info.get("node")
    if not isinstance(node, dict) or not node.get("type"):
        return False
    return bool(info.get("version"))


def _figma_nodes_response_cacheable(full_data: dict, node_id: str) -> bool:
    """
    仅当 Figma /v1/files/.../nodes 返回体为成功结构时才允许缓存：
    无 err；nodes[node_id].document 为非空对象且含 type（有效节点 JSON）。
    """
    if not isinstance(full_data, dict):
        return False
    if full_data.get("err"):
        return False
    status = full_data.get("status")
    if status is not None and status != 200:
        return False
    entry = (full_data.get("nodes") or {}).get(node_id)
    if not isinstance(entry, dict):
        return False
    doc = entry.get("document")
    if not isinstance(doc, dict) or not doc:
        return False
    if not doc.get("type"):
        return False
    return True


class FigmaService:
    _feature_iteration_version: int = 2                                 # 功能迭代版本(该版本会影响缓存的失效策略，如果调整了缓存数据逻辑，需要修改(规则：原有值 + 1))
    _coordinate: CoordinateResolver = None                              # 坐标系计算对象
    _component_factory: ComponentFactory = None                         # 组件工厂对象
    _image_nodes: List[str] = []                                        # 需要导图片的节点id
    _node_id_to_component: Dict[str, dsl_model.AbstractComponent] = {}  # figma id和组件对象的映射map
    _node_id_map: Dict[str, Dict[str, Any]] = {}                        # figma节点id和节点数据映射

    _file_key: str          # figma文件key
    _node_id: str           # figma节点id
    _figma_url: str         # figma设计稿链接
    _cache_key: str         # figma节点数据缓存key
    _is_export_image: bool  # 是否导出图片(默认不导出)

    def __init__(self, file_key: str, node_id: str, url: Optional[str], is_export_image: Optional[bool] = False):
        """初始化 Figma 服务"""
        self._file_key = file_key
        self._node_id = node_id
        self._figma_url = url
        self._image_nodes = []
        self._node_id_map = {}
        self._node_id_to_component = {}
        self._is_export_image = is_export_image if is_export_image else False
        self._cache_key = cache_enum.CacheKey.FIGMA_NODE_DATA.value.format(file_key=file_key, node_id=node_id)

        self._component_factory = ComponentFactory()

    def check_node(self):
        """检查节点"""
        figma_client = client_figma.FigmaClient.get_instance()
        figma_node = self._get_figma_node(figma_client)
        if figma_node is None:
            raise TypeError("从Figma查找该节点失败，可能不是一个合法的Figma设计稿地址")

    def to_dsl(self, image_scale: int = 2) -> dsl_model.DSL:
        # 获取 Figma 数据
        figma_client = client_figma.FigmaClient.get_instance()
        figma_node = self._get_figma_node(figma_client)

        # 初始化坐标系对象
        self._coordinate = CoordinateResolver(figma_node)

        # 转换为 DSL 组件树
        components = self._to_components(figma_node)

        # 构建 DSL 对象
        dsl = dsl_model.DSL(
            version="1.0.0",
            metadata=dsl_model.Metadata(
                url=self._figma_url,
                node_id=figma_node.get("id", self._node_id),
                width=self._coordinate.get_page_size().width,
                height=self._coordinate.get_page_size().height,
                name=figma_node.get("name", ""),
                image_url=self._handle_export_image(figma_client),
                file_key=self._file_key,
                image_scale=image_scale,
                extra_dict=dict()
            ),
            components=components
        )

        # 后置优化器( 支持边框渐变色 & 图片合并再次优化)
        ComponentAfterOptimizer.optimize(dsl)

        return dsl

    def _to_components(self, node: Dict[str, Any]) -> List[dsl_model.AbstractComponent]:
        """遍历figma节点转换为component组件"""
        stack = [(node, None)]  # (当前节点, 父组件)
        root_component = None
        while stack:
            current_node, parent_component = stack.pop()
            current_node_id = current_node.get("id", "")

            self._node_id_map[current_node_id] = current_node
            component = self._component_factory.of(node=current_node, coordinate=self._coordinate, parent_component=parent_component, node_id_map=self._node_id_map)
            if component is None:
                continue

            self._node_id_to_component[current_node_id] = component
            if parent_component is None:
                root_component = component
            if parent_component:
                parent_component.children.append(component)

            if component.type == dsl_enum.ComponentType.IMAGE:
                if self._is_export_image is True:
                    self._image_nodes.append(current_node_id)
                continue

            children = current_node.get("children", [])
            for child_node in reversed(children):
                stack.append((child_node, component))

        return [root_component]

    def _handle_export_image(self, figma_client: client_figma.FigmaClient):
        if self._image_nodes and len(self._image_nodes) > 0:
            logger.debug(f"开始导出 {len(self._image_nodes)} 个图片节点")
            images_data = figma_client.export_images(file_key=self._file_key, node_ids=self._image_nodes, scale=2)
            # 循环遍历image_data，并且把值更新到对应的组件上
            for node_id, image_data in images_data.items():
                if node_id in self._node_id_to_component:
                    component = self._node_id_to_component[node_id]
                    if component.type == dsl_enum.ComponentType.IMAGE:
                        component.props.src = image_data

        root_image_data = figma_client.export_images(file_key=self._file_key, node_ids=[self._node_id], scale=1)
        return root_image_data.get(self._node_id, "")

    def _get_figma_node(self, figma_client: client_figma.FigmaClient):
        # 获取深度为0的节点信息(本动作两个作用：1. 判断当前选择节点是否合理；2. 判断缓存节点是否为最新)
        simple_data = figma_client.get_nodes(file_key=self._file_key, node_id=self._node_id, depth=0)
        simple_node = simple_data.get("nodes", {}).get(self._node_id, {}).get("document", {})
        if simple_node and simple_node.get("type", "") == figma_enum.FigmaNodeType.CanvasNode:
            raise Exception(
                "当前选择节点可能是页面节点，不支持导出，请选择有效的 UI 节点"
                "（Frame / Component / Instance 等），不要选择 Page / Canvas 节点。"
            )

        # 判断节点的宽度是否小于允许的最大宽度
        max_support_width = FIGMA_MAX_SUPPORT_NODE_WIDTH
        if simple_node and simple_node.get("width", 0) > max_support_width:
            raise Exception(f"当前选择节点的宽度大于1500，可能不是一个合法的节点，请选择小于1500的节点进行导出。")

        cache_info = self._get_figma_data_from_cache()
        if cache_info and _cached_figma_entry_valid(cache_info):
            try:
                if not _figma_nodes_response_cacheable(simple_data, self._node_id):
                    logger.info(
                        "Figma 浅层 nodes 响应非成功结构，忽略缓存, fileKey=%s nodeId=%s",
                        self._file_key,
                        self._node_id,
                    )
                else:
                    last_update_version = self._get_node_version(simple_data)
                    if last_update_version == cache_info.get("version"):
                        return cache_info.get("node")
            except Exception as e:
                logger.warning(f"从缓存获取节点数据失败，fileKey: {self._file_key}, nodeId: {self._node_id}, err: {str(e)}", exc_info=True)

        # Not found in cache, get from Figma api
        full_node = None
        full_data = figma_client.get_nodes(file_key=self._file_key, node_id=self._node_id)
        try:
            full_node = full_data.get("nodes", {}).get(self._node_id, {}).get("document", {})
        except Exception as e:
            logger.error(f"从Figma api获取节点数据失败，fileKey: {self._file_key}, nodeId: {self._node_id}, err: {str(e)}", exc_info=True)
        if full_node:
            node = self._filter_invisible_node_before_cache(node=full_node)
            if _figma_nodes_response_cacheable(full_data, self._node_id) and isinstance(node, dict) and node.get("type"):
                self._set_figma_data_to_cache(node=node, version=self._get_node_version(full_data))
            else:
                logger.info(
                    "Figma 全量节点响应未满足缓存条件（非成功 JSON 或过滤后无有效 type），跳过本地缓存, fileKey=%s nodeId=%s",
                    self._file_key,
                    self._node_id,
                )

        return full_node

    def _filter_invisible_node_before_cache(self, node: Dict[str, Any]):
        """过滤不可见节点(注意：调整了此处逻辑后，需要修改_feature_iteration_version字段的值，否则缓存不是最新)"""
        stack = [([node], None)]  # (当前节点列表, 父节点列表)
        while stack:
            current_list, parent = stack.pop()

            # 从后往前遍历，方便删除
            for i in range(len(current_list) - 1, -1, -1):
                child_node = current_list[i]
                if not self._check_visible(child_node):
                    current_list.pop(i)
                    continue

                children = child_node.get("children", [])
                if len(children) > 0:
                    stack.append((children, current_list))

        return node

    @staticmethod
    def _check_visible(node: Dict[str, Any]) -> bool:
        """判断节点是否可见"""
        visible = node.get("visible", True)
        if visible is False:
            return False

        # 检测节点透明度是否为0
        if node.get("opacity", 1) == 0:
            return False

        absolute_bounding_box = node.get("absoluteBoundingBox", None)
        absolute_render_bounds = node.get("absoluteRenderBounds", None)
        if absolute_render_bounds is None:
            return False

        if absolute_bounding_box is None and absolute_render_bounds is None:
            return False

        if absolute_render_bounds:
            if absolute_render_bounds.get("width", 0) == 0 and absolute_render_bounds.get("height", 0) == 0:
                return False

        # 矩形:如果没有背景色和边框，则不导出
        if node.get("type", "") == "RECTANGLE":
            fills = node.get("fills", [])
            strokes = node.get("strokes", [])
            if not fills and not strokes:
                return False

            is_has_visible_fill = [fill for fill in fills if fill.get("visible", True) is True]
            is_has_visible_stroke = [stroke for stroke in strokes if stroke.get("visible", True) is True]
            if not is_has_visible_fill and not is_has_visible_stroke:
                return False

        return True

    def _get_figma_data_from_cache(self):
        value = memory_kv.get(self._cache_key)
        if value:
            return json.loads(value)

        return None

    def _set_figma_data_to_cache(self, node: Dict[str, Any], version: str):
        memory_kv.put(
            self._cache_key,
            json.dumps({"version": version, "node": node}),
            ex=FIGMA_CACHE_TTL_SECONDS,
        )
        logger.info(
            "Figma 节点数据已缓存（%sh）, fileKey=%s nodeId=%s",
            FIGMA_CACHE_TTL_SECONDS // 3600,
            self._file_key,
            self._node_id,
        )

    def _get_node_version(self, data: Dict[str, Any]):
        """获取缓存数据版本号"""
        from datetime import datetime, timedelta

        last_modified = data.get("lastModified")
        if last_modified is not None:
            date_str = datetime.strptime(last_modified, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=8)
            value = date_str.strftime("%Y%m%d%H%M%S")
        else:
            value = data.get("version", "")

        return f"{value}:{self._feature_iteration_version}"


