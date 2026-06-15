"""
REST API 控制器
使用 FastMCP 的 custom_route 添加 REST API 端点
"""
import logging
import re
from pathlib import Path
from starlette.responses import JSONResponse, PlainTextResponse, FileResponse

from starlette.requests import Request
from mdap_u2c.utils.response_utils import ResponseUtils
from mdap_u2c.config.path_config import PathConfig
from ..mcp_instance import McpInstanceManager

# 获取 MCP 实例
_logger = logging.getLogger(__name__)
_mcp = McpInstanceManager.get_instance().get_mcp()

# Skills 目录路径
SKILLS_DIR = Path(PathConfig.get_assets_dir()) / "skills"
_SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _resolve_skill_md(skill_name: str) -> Path | None:
    if not _SKILL_NAME_PATTERN.match(skill_name):
        return None
    skill_dir = (SKILLS_DIR / skill_name).resolve()
    if not skill_dir.is_relative_to(SKILLS_DIR.resolve()):
        return None
    return skill_dir / "SKILL.md"


@_mcp.custom_route("/", methods=["GET"])
async def health_check(request: Request):
    """健康检查端点"""
    return PlainTextResponse("Welcome mdap u2c")


@_mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    """健康检查端点"""
    return JSONResponse(ResponseUtils.success())


@_mcp.custom_route('/api/skills/{skill_name}/download', methods=['GET'])
async def download_skill(request: Request):
    """下载指定 skill 的 SKILL.md 文件"""
    try:
        skill_name = request.path_params.get('skill_name')
        if not skill_name:
            return JSONResponse({"error": "skill_name 参数缺失"}, status_code=400)

        skill_md = _resolve_skill_md(skill_name)
        if skill_md is None:
            return JSONResponse({"error": "非法 skill_name"}, status_code=403)

        if not skill_md.exists():
            return JSONResponse({"error": f"skill '{skill_name}' 不存在"}, status_code=404)
        
        return FileResponse(
            path=str(skill_md),
            filename=f"{skill_name}_SKILL.md",
            media_type="text/markdown"
        )
    except Exception as e:
        _logger.error(f"下载 skill 文件失败: {e}", exc_info=True)
        return JSONResponse({"error": f"下载失败: {str(e)}"}, status_code=500)
