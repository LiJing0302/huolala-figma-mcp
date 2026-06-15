import logging

logger = logging.getLogger(__name__)


class RegisterPrompts:
    """注册所有 MCP Prompts"""

    @staticmethod
    def register():
        from . import get_figma_property
        from . import ui2code_with_skills

