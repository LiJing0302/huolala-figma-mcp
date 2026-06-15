
import logging

logger = logging.getLogger(__name__)


class RegisterResources:

    @staticmethod
    def register():
        try:
            from . import (
                skills_resource
            )
        except Exception as e:
            logger.warning(f"[MCP] Failed to register resources: {e}")
