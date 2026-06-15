import logging
import traceback

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.cv_module import find_redpoint_bubble
from mdap_u2c.dsl_processors.layout import remove_redundancy
from mdap_u2c.dsl_processors.registry import processor_registry

@processor_registry.register_decorator(
    name="remove_transparent",
    description="去透明控件",
    config=ProcessorConfig(priority=30, enabled=True)  # 优先级20，在demo_first之后执行
)
class RemoveTransparentProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("Starting remove_transparent processor execute.")
        remove_redundancy.remove_transparent_control(context.tree)
        return context

