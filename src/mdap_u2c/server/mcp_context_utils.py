import logging
from typing import Optional

from fastmcp.server.middleware import MiddlewareContext
from fastmcp import Context

from mdap_u2c.constant import McpConstant
from mdap_u2c.models import common_model

logger = logging.getLogger(__name__)


class McpContextUtils:
    """MCP上下文工具类"""

    @staticmethod
    def default_user_info() -> common_model.TokenUserInfo:
        return common_model.TokenUserInfo.from_dict(McpConstant.DEFAULT_USER)

    @staticmethod
    async def send_progress(context: Context, progress: int, total: int, message: str):
        """安全地报告进度，如果 Context 已关闭或不存在则忽略错误"""
        if not context:
            return
        try:
            await context.report_progress(progress=progress, total=total, message=message)
        except Exception as e:
            logger.warning(
                f"[mcp_tool_call] Failed to report progress: {e}, progress={progress}/{total}, message={message}",
                exc_info=True,
            )

    @staticmethod
    def get_user_info(context: Context | MiddlewareContext | None = None) -> common_model.TokenUserInfo:
        """获取用户信息；无 MCP 上下文时返回默认匿名用户。"""
        if context is None:
            return McpContextUtils.default_user_info()

        if isinstance(context, MiddlewareContext):
            user_info = context.fastmcp_context.get_state("login_user_info")
        elif isinstance(context, Context):
            user_info = context.get_state("login_user_info")
        else:
            raise TypeError("context must be MiddlewareContext or Context")

        if user_info:
            return common_model.TokenUserInfo.from_dict(user_info)
        return McpContextUtils.default_user_info()
