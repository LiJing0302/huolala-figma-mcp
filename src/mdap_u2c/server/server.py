"""
MCP 服务器
https://gofastmcp.com/getting-started/welcome
"""
import logging

from fastmcp import FastMCP, settings
from mdap_u2c.config import AppConfig
from .controller import RegisterController
from .resources import RegisterResources
from .prompts import RegisterPrompts
from .tools import RegisterTools
from .mcp_instance import McpInstanceManager
from .object_starter_utils import ObjectStarterUtils
from ..constant import McpConstant


# 防止记录大量请求日志，对FASTMCP内部日志级别设置为WARNING，业务日志保存INFO级别
settings.log_level = "WARNING"
config = AppConfig.get_instance().CONFIG

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name=config.APP_ID,
    instructions=McpConstant.MCP_INSTRUCTIONS,
    on_duplicate_tools="error",
    on_duplicate_prompts="error",
    on_duplicate_resources="error",
)
McpInstanceManager.get_instance().set_mcp(mcp)

RegisterTools.register()
RegisterResources.register()
RegisterController.register()
RegisterPrompts.register()

# 提前加载耗时旧的对象(提高执行速度)
ObjectStarterUtils.run()


def create_app():
    """创建独立的MCP应用实例"""
    return mcp.http_app(transport="streamable-http", path="/mcp", stateless_http=True)


def run_server():
    """运行 MCP 服务器(该方式为直接运行，适合本地开发环境)"""
    from mdap_u2c.core import LoggingApplication
    logger = logging.getLogger(__name__)
    try:
        logger.info(
            f"The server run info. appId: {config.APP_ID}, port: {config.PORT}"
        )
        mcp.run(transport="streamable-http", host=config.HOST, port=config.PORT, path="/mcp", stateless_http=True, show_banner=False)
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
    finally:
        # 关闭日志系统，确保所有日志都被写入
        LoggingApplication.shutdown()
