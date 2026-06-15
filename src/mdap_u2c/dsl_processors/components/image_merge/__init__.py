import logging
import traceback

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.cv_module import find_redpoint_bubble
from mdap_u2c.dsl_processors.layout import image_merge
from mdap_u2c.dsl_processors.registry import processor_registry


@processor_registry.register_decorator(
    name="image_merge",
    description="图片合并",
    config=ProcessorConfig(priority=9, enabled=True)  # 优先级20，在demo_first之后执行
)
class ImageMergeProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("Starting icon_merge processor execute.")
       
        components = context.dsl.components
        if len(components) >= 1:
            root_component = components[0]
        else:
            return context
        image_merge.dsl_to_map(root_component,context.shared_data)
        image_merge.icon_merge(root_component, context.shared_data)
        context.shared_data["dsl_map"] = {}

        return context

