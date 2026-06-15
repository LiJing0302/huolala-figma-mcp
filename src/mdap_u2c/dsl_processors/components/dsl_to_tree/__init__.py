import logging
import os

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.layout.dsl_preprocess_and_to_tree import TreeExtraInfo, dsl_to_tree
from mdap_u2c.dsl_processors.registry import processor_registry
from mdap_u2c.utils.serializer_utils import SerializerUtils

from mdap_u2c.utils.download_file import get_image_by_url


@processor_registry.register_decorator(
    name="dsl_to_tree",
    description="DSL转树结构",
    config=ProcessorConfig(priority=10, enabled=True)  # 优先级20，在demo_first之后执行
)
class DSL2TreeProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("Starting dsl to tree execute.")
        share_tree_info = TreeExtraInfo()
        components = context.dsl.components
        if len(components) == 1:
            root_component = components[0]
            share_tree_info.root_height = root_component.layout.size.height
            share_tree_info.root_width = root_component.layout.size.width
            dsl_to_tree(root_component, context.tree, None, share_tree_info)
            context.shared_data["figma_width"] = share_tree_info.root_width
            context.shared_data["figma_height"] = share_tree_info.root_height
        return context
