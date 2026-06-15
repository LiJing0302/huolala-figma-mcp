"""
REST API 控制器
使用 FastMCP 的 custom_route 添加 REST API 端点
"""
import logging
from starlette.responses import JSONResponse

from starlette.requests import Request
from mdap_u2c.services import FigmaService, UI2CodeService
from mdap_u2c.utils import UrlUtils
from mdap_u2c.utils.response_utils import ResponseUtils, BusinessCode
from ..mcp_instance import McpInstanceManager

# 获取 MCP 实例
logger = logging.getLogger(__name__)
mcp = McpInstanceManager.get_instance().get_mcp()


@mcp.custom_route('/test/to_dsl', methods=['GET'])
async def test_to_dsl(request: Request):
    # 从GET请求中获取参数
    design_url = request.query_params.get('design_url')
    is_export_image = request.query_params.get('is_export_image', None)
    if not design_url:
        return ResponseUtils.error(code=BusinessCode.FAILURE, msg="参数错误(design_url)")

    file_key, node_id = UrlUtils.get_figma_param_by_url_throw_error(design_url)

    dsl = FigmaService(
        url=design_url,
        file_key=file_key,
        node_id=node_id,
        is_export_image=is_export_image == "true"
    ).to_dsl()
    return JSONResponse(ResponseUtils.success(data=dsl.to_dict()))


@mcp.custom_route('/test/generator', methods=['GET'])
async def test_generator(request: Request):
    design_url = request.query_params.get("design_url")
    if not design_url:
        return ResponseUtils.error(code=BusinessCode.FAILURE, msg="参数错误(design_url)")

    url, _ = await UI2CodeService(url=design_url).run()
    return JSONResponse(ResponseUtils.success(data={
        "design_url": design_url,
        "zip": url
    }))
