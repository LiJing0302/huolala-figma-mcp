import logging

logger = logging.getLogger(__name__)


class RegisterTools:

    @staticmethod
    def register():
        try:
            from . import (
                get_code_package,
            )
        except Exception as e:
            logger.warning(f"[MCP] Failed to register tools: {e}")
