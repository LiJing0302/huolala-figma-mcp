"""
MCP 实例管理模块
提供统一的 MCP 实例获取方法（单例模式）
"""
import logging
from typing import Optional
from fastmcp import FastMCP
from mdap_u2c.core import SingletonClass

logger = logging.getLogger(__name__)


class McpInstanceManager(metaclass=SingletonClass):
    """MCP实例管理工具"""
    _mcp: Optional[FastMCP] = None

    def set_mcp(self, instance: FastMCP) -> None:
        self._mcp = instance
        logger.info("[MCP] MCP 实例已设置")
    
    def get_mcp(self) -> FastMCP:
        if self._mcp is None:
            raise RuntimeError("MCP 实例未初始化。请确保在导入其他模块之前先初始化 MCP 实例。")
        
        return self._mcp
    
    def is_initialized(self) -> bool:
        return self._mcp is not None

    @staticmethod
    def get_instance():
        return McpInstanceManager()
