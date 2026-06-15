import json
import logging
import os

from mdap_u2c.dsl_processors.layout import tree_projection, tree_rebuild, find_special_control
from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry


@processor_registry.register_decorator(
    name="group by projection",
    description="根据投影进行分组",
    config=ProcessorConfig(priority=60, enabled=True)  # 优先级20，在demo_first之后执行
)
class ProjectionProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("group by projection")
        input_tree = context.tree
        new_pil_img = context.shared_data["pil_image"]
        projection_map = context.shared_data["projection_map"]
        tree_projection.adjust_child_control_recurve(input_tree,input_tree.root)
        tree_projection.calc_children_projection(input_tree, input_tree.root, 20)
        homebar_height = context.shared_data["home_bar_height"]
        find_special_control.bottom_bar_layer_process(input_tree, new_pil_img, projection_map,homebar_height)

        if "debug" in context.shared_data and context.shared_data['debug'] == 1:
            dsl_json_path = os.path.join("tests", "projection_tree.json")
            with open(dsl_json_path, "w", encoding="utf-8") as json_file:
                json_file.write(json.dumps(tree_rebuild.tree_to_json(context.tree,context.tree.root), ensure_ascii=False, indent=2))
        return context
