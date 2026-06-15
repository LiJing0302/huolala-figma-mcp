"""
Skills 资源模块
提供下载 assets/skills 目录中 md 文件的能力
"""
import logging
from pathlib import Path
from fastmcp import Context
from ...config.path_config import PathConfig
from ...config import AppConfig
from ..mcp_instance import McpInstanceManager

logger = logging.getLogger(__name__)
mcp = McpInstanceManager.get_instance().get_mcp()

# Skills 目录路径
SKILLS_DIR = Path(PathConfig.get_assets_dir()) / "skills"


@mcp.resource(
    uri="skills://{skill_name}",
    description="获取指定 skill 的 SKILL.md 文件内容，可通过 MCP 协议读取。",
    mime_type="text/markdown"
)
def get_skill_content(skill_name: str) -> str:
    """
    获取指定 skill 的 SKILL.md 文件内容

    Args:
        skill_name: skill 目录名，如 adjust-list-group

    Returns:
        str: SKILL.md 的文本内容，若不存在则返回错误信息
    """
    try:
        skill_dir = SKILLS_DIR / skill_name
        skill_md = skill_dir / "SKILL.md"

        if not skill_dir.exists():
            return f"[Error] Skill '{skill_name}' 不存在"
        if not skill_md.exists():
            return f"[Error] Skill '{skill_name}' 目录中不存在 SKILL.md 文件"

        return skill_md.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[MCP] Failed to read skill {skill_name}: {e}", exc_info=True)
        return f"[Error] 读取 skill 失败: {str(e)}"


def _get_base_url() -> str:
    """
    获取服务器的基础 URL
    
    Returns:
        str: 服务器的基础 URL
    """
    try:
        return AppConfig.get_public_app_base_url()
    except Exception as e:
        logger.warning(f"[MCP] Failed to get base URL, using default: {e}")
        config = AppConfig.get_instance().CONFIG
        return f"http://localhost:{config.PORT}"


@mcp.resource(
    uri="skills://list",
    description="列出所有可用的 skills 列表"
)
def list_skills(context: Context) -> str:
    """
    列出所有可用的 skills
    
    Returns:
        str: JSON 格式的 skills 列表，包含每个 skill 的名称和 URI
    """
    try:
        if not SKILLS_DIR.exists():
            return '{"error": "Skills 目录不存在", "skills": []}'
        
        skills = []
        base_url = _get_base_url()
        for item in SKILLS_DIR.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    # 生成网络下载地址
                    download_url = f"{base_url}/api/skills/{item.name}/download"
                    # MCP resource URI，可通过 fetch_mcp_resource 或 read 获取内容
                    resource_uri = f"skills://{item.name}"
                    skills.append({
                        "name": item.name,
                        "path": download_url,
                        "resource_uri": resource_uri
                    })
        
        import json
        return json.dumps({
            "skills": skills,
            "count": len(skills)
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[MCP] Failed to list skills: {e}", exc_info=True)
        return f'{{"error": "列出 skills 失败: {str(e)}"}}'


