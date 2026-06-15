"""
UI2Code 服务 - 三层编排层

负责编排三层架构的完整流程：
1. Figma 节点转 DSL 层 (FigmaService)
2. DSL 加工层 (ProcessorPipeline)
3. ZIP 包生成层 (ExportService)
"""
import logging
import time
from typing import List, Optional, Union

from fastmcp import Context
from mdap_u2c.utils import UrlUtils
from mdap_u2c.models import common_model, dsl_model
from mdap_u2c.services import FigmaService, ExportService
from mdap_u2c.dsl_processors import ProcessContext, ProcessorPipeline
from mdap_u2c.enums import common_enum
from treelib import Tree

logger = logging.getLogger(__name__)

# 平台映射表：用户输入 -> 标准 code_type
_PLATFORM_CODE_TYPES = {
    "h5": common_enum.PlatformType.H5.value,
    "vue": common_enum.PlatformType.Vue.value,
    "react": common_enum.PlatformType.React.value,
    "react native": common_enum.PlatformType.ReactNative.value,
    "ios": common_enum.PlatformType.Ios.value,
    "android": common_enum.PlatformType.Android.value
}


def _normalize_image_scales(image_scale: Union[int, List[int]]) -> List[int]:
    """归一化为 int 列表，每个元素 1-4。"""
    if isinstance(image_scale, int):
        return [image_scale] if 1 <= image_scale <= 4 else [2]
    return [s for s in image_scale if 1 <= s <= 4] or [2]


class UI2CodeService:
    _url: str
    _image_scales: List[int]
    _target_platform: Optional[str] = None
    _mcp_context: Context = None

    def __init__(self, url: str, image_scale: Union[int, List[int]] = 2, target_platform: Optional[str] = None):
        if not url:
            raise Exception("缺少必填参数: url")

        self._url = url
        self._image_scales = _normalize_image_scales(image_scale)
        self._target_platform = target_platform

    def set_mcp_context(self, mcp_context: Context):
        self._mcp_context = mcp_context
        return self

    def _parse_file_key_node_id(self, file_key: Optional[str] = None, node_id: Optional[str] = None) -> tuple[str, str]:
        """解析file_key和node_id值"""
        if file_key is None or node_id is None:
            return UrlUtils.get_figma_param_by_url_throw_error(self._url)

        return file_key, node_id.replace("-", ":")

    def _get_user_info(self) -> common_model.TokenUserInfo:
        from mdap_u2c.server import McpContextUtils
        if self._mcp_context:
            return McpContextUtils.get_user_info(self._mcp_context)
        return McpContextUtils.default_user_info()

    async def run(self, file_key: Optional[str] = None, node_id: Optional[str] = None) -> tuple[str, dsl_model.Metadata] | tuple[None, None]:
        from mdap_u2c.server import McpContextUtils
        user_info = self._get_user_info()
        file_key, node_id = self._parse_file_key_node_id(file_key, node_id)
        processor = ProcessorPipeline.get_instance()
        notify_step_total = processor.__len__() + 3

        # ========== 1: Figma 节点转 DSL 层 ==========
        await McpContextUtils.send_progress(context=self._mcp_context, progress=1, total=notify_step_total, message=f"正在转换Figma设计稿为DSL...")
        to_dsl_start_time = time.time()
        logger.info(f"[UI2CodeService] figma to dsl start, fileKey: {file_key}, nodeId: {node_id}")
        primary_scale = self._image_scales[0]
        dsl = FigmaService(url=self._url, file_key=file_key, node_id=node_id, is_export_image=True).to_dsl(image_scale=primary_scale)
        logger.info(f"[UI2CodeService] figma to dsl finish，耗时: {(time.time() - to_dsl_start_time):.3f}s, fileKey: {file_key}, nodeId: {node_id}")

        # ========== 2: DSL 加工层 ==========
        dsl_process_start_time = time.time()
        logger.info(f"[UI2CodeService] dsl processor start execute, fileKey: {file_key}, nodeId: {node_id}")
        
        # 创建 ProcessContext 并设置共享数据
        processor_context = ProcessContext(dsl=dsl, tree=Tree())
        
        # 将 image_scale 传递到 shared_data（布局等用主倍数）
        processor_context.shared_data["image_scale"] = self._image_scales[0]
        
        # 将 code_type 传递到 shared_data（用于平台特定的处理逻辑）
        if self._target_platform:
            code_type = _PLATFORM_CODE_TYPES.get(self._target_platform.lower(), None)
            if code_type:
                processor_context.shared_data["code_type"] = code_type
                logger.info(f"[UI2CodeService] target_platform: {self._target_platform}, code_type: {code_type}")
        
        await processor.execute(context=processor_context, mcp_context=self._mcp_context, start_step=1, notify_step_total=notify_step_total)
        logger.info(f"[UI2CodeService] dsl processor finish，耗时: {(time.time() - dsl_process_start_time):.3f}s, fileKey: {file_key}, nodeId: {node_id}")

        # ========== 3: ZIP 包生成层 ==========
        await McpContextUtils.send_progress(context=self._mcp_context, progress=notify_step_total - 1, total=notify_step_total, message=f"正在生成ZIP包...")
        zip_package_start_time = time.time()
        logger.info(f"[UI2CodeService] zip package start, fileKey: {file_key}, nodeId: {node_id}")
        zip_url = ExportService(image_scale=self._image_scales).generate_pack(
            processor_context.dsl,
            user_info,
            processor_context.shared_data,
        )
        logger.info(f"[UI2CodeService]: zip package finish，耗时: {(time.time() - zip_package_start_time):.3f}s, fileKey: {file_key}, nodeId: {node_id}, url: {zip_url}")
        if zip_url is None:
            raise Exception("Zip包打包失败了，请参考日志排查问题")

        await McpContextUtils.send_progress(context=self._mcp_context, progress=notify_step_total, total=notify_step_total, message=f"MCP服务处理完成，进入cursor代码转换阶段。")
        return zip_url, dsl.metadata
