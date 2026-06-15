"""
Huolala Figma MCP 转 H5 code 转换 Prompt（含 SKILL 步骤）
"""
from pathlib import Path

from ..mcp_instance import McpInstanceManager

mcp = McpInstanceManager.get_instance().get_mcp()

# 从项目根目录的 assets/prompts 读取内容
_PROMPT_FILE = Path(__file__).resolve().parents[4] / "assets" / "prompts" / "ui2code_with_skills.md"


@mcp.prompt(
    name="ui2code_with_skills",
    description="Huolala Figma MCP 转 code 流程，包含获取 ZIP 包、解压、调用 adjust-list-group 和 u2c-code-convert 等 SKILL 的完整步骤",
)
def ui2code_with_skills() -> str:
    """
    返回 ui2code_with_skills.md 的完整内容
    """
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8")
    return "[Error] ui2code_with_skills.md 文件不存在"
