import logging

logger = logging.getLogger(__name__)


class RegisterController:

    @staticmethod
    def register():
        try:
            from . import (http_controller, test_controller)
        except Exception as e:
            logger.warning(f"[MCP] Failed to register REST routes: {e}")
