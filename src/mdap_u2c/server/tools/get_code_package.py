import logging
from typing import Annotated, List, Optional
from pydantic import Field
from fastmcp import Context
from mdap_u2c.services import UI2CodeService
from mdap_u2c.utils import UrlUtils
from ..mcp_instance import McpInstanceManager
from ..mcp_context_utils import McpContextUtils

logger = logging.getLogger(__name__)
mcp = McpInstanceManager.get_instance().get_mcp()


@mcp.tool(
    name="figma_to_code_package",
    description="""功能1:将figma url转成对应的UI代码。返回结果为zip地址，zip解压后包含：index.html（H5代码），images（图标资源），vlm_result.json（控件分类数据），fonts（字体）。功能2:获取figma链接对应的UI属性、样式、字体、宽高颜色等，下载链接的zip的压缩包读取index.html获取。file key 从 URL 路径 /file/{file_key}/ 或 /design/{file_key}/ 解析；node id 从 ?node-id= 查询参数解析。""",
)
async def get_code_package(
        context: Context,
        figma_url: Annotated[
            str,
            Field(
                description="Figma 设计稿完整链接，需含路径中的 file key（如 /file/xxx/ 或 /design/xxx/）及 ?node-id= 节点参数"
            ),
        ],
        image_scale: Annotated[
            List[int],
            Field(
                default=[3],
                description="图片导出倍数列表，如 [3,2] 同时导出 3x、2x切图",
            ),
        ],
        target_platform: Annotated[Optional[str], Field(default=None, description="""
目标代码平台，支持：h5/vue/react/react native/ios/android
""")],
):
    user = McpContextUtils.get_user_info(context)
    if not figma_url or len(figma_url) < 1:
        raise TypeError("设计稿参数不能为空")

    file_key, node_id = UrlUtils.get_figma_param_by_url_throw_error(figma_url)
    logger.info(
        f"[MCP] Execute tool figma_to_code_package, user: {user} | file_key:{file_key} | node_id:{node_id} | image_scale:{image_scale} | url:{figma_url}"
    )

    if not image_scale:
        image_scale = [3]
    for s in image_scale:
        if s < 1 or s > 4:
            raise TypeError("图片导出倍数值必须在1-4之间")

    zip_url, metadata = await UI2CodeService(url=figma_url, image_scale=image_scale, target_platform=target_platform).set_mcp_context(context)\
        .run(file_key=file_key, node_id=node_id)
    if not zip_url:
        raise RuntimeError("Figma 设计稿转换失败, zip_url为空")

    return {
        "zip_url": zip_url,
        "metadata": metadata.to_dict(),
        "message": "zip_url 可直接下载"
    }
