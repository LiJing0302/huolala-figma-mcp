import logging

from mdap_u2c.dsl_processors.layout import tree_rebuild
from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry

@processor_registry.register_decorator(
    name="calc layout",
    description="计算布局",
    config=ProcessorConfig(priority=70, enabled=True)  #
)
class CalcLayoutProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("calc layout.")
        input_tree = context.tree

        root_component = tree_rebuild.tree_to_dsl(input_tree, input_tree.root,context.shared_data)
        context.dsl.components = list()
        context.dsl.components.append(root_component)
        return context
