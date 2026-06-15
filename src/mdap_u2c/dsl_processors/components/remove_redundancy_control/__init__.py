import logging

from mdap_u2c.dsl_processors.layout import tree_rebuild, find_special_control
from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry

from mdap_u2c.dsl_processors.layout import remove_redundancy


@processor_registry.register_decorator(
    name="remove redundancy control",
    description="去冗余控件",
    config=ProcessorConfig(priority=20, enabled=True)  #
)
class RemoveRedundancyProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("remove redundancy control.")
        pil_img = context.shared_data["pil_image"]
        input_tree = context.tree
        new_pil_img, top_bar_height, real_homebar_height, is_translucent_top_bar = find_special_control.remove_sys_bar(input_tree, pil_img)
        projection_map = remove_redundancy.remove_overlap_control(input_tree)
        context.shared_data["projection_map"] = projection_map
        context.shared_data["pil_image"] = new_pil_img
        context.shared_data['top_bar_height'] = top_bar_height
        context.shared_data['home_bar_height'] = real_homebar_height
        context.shared_data['is_translucent_top_bar'] = is_translucent_top_bar

        # 将 top_bar_height, real_homebar_height, is_translucent_top_bar 写入 Metadata 的 extra_dict
        context.dsl.metadata.extra_dict['top_bar_height'] = top_bar_height
        context.dsl.metadata.extra_dict['real_homebar_height'] = real_homebar_height
        context.dsl.metadata.extra_dict['is_translucent_top_bar'] = is_translucent_top_bar
        
        return context

