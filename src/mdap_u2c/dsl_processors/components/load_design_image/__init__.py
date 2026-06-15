import logging

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry
from mdap_u2c.utils.download_file import get_image_by_url

logger = logging.getLogger(__name__)


@processor_registry.register_decorator(
    name="load_design_image",
    description="加载设计稿图片",
    config=ProcessorConfig(priority=8, enabled=True),
)
class LoadDesignImageProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        if context.shared_data.get("pil_image") is not None:
            return context

        image_url = context.dsl.metadata.image_url
        if not image_url:
            logger.warning("load_design_image: metadata.image_url is empty, skip")
            return context

        logger.info("Loading design image from metadata.image_url")
        context.shared_data["pil_image"] = get_image_by_url(image_url)
        return context
