"""
从 Figma 链接获取设计属性：ZIP 下载、解压、读取 index.html 等步骤说明
"""
from pathlib import Path

from ..mcp_instance import McpInstanceManager

mcp = McpInstanceManager.get_instance().get_mcp()

_PROMPT_FILE = Path(__file__).resolve().parents[4] / "assets" / "prompts" / "get_figma_property.md"


@mcp.prompt(
    name="get_figma_property",
    description="获取 Figma 设计属性：使用完整 Figma URL 调用 figma_to_code_package、下载解压 ZIP、从 index.html 读取文字与样式等",
)
def get_figma_property() -> str:
    """返回 get_figma_property.md 的完整内容"""
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8")
    return "[Error] get_figma_property.md 文件不存在"
