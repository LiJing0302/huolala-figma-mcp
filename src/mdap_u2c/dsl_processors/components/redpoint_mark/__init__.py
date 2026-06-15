import logging
import traceback

from mdap_u2c.dsl_processors.cv_module import find_redpoint_bubble

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry


@processor_registry.register_decorator(
    name="readpoint_mark",
    description="识别气泡",
    config=ProcessorConfig(priority=29, enabled=True)  # 优先级20，在demo_first之后执行
)
class RedpointMarkProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("Starting redpoint mark.")
        pil_image = context.shared_data.get("pil_image")
        input_tree = context.tree
        redpoint_bubble_list = list()
        yolo_boxes = None
        try:
        # 等待 ai_service 中提交的 yolo 异步任务完成
            yolo_task_id = context.shared_data.get("task_yolo_redpoint_bubble")
            if yolo_task_id:
                logging.info("Waiting for yolo redpoint bubble task to complete...")
                yolo_boxes = self.wait_for_task(context, yolo_task_id, timeout=15.0)
                logging.info("Yolo redpoint bubble task completed.")
        except TimeoutError:
            logging.error("异步任务处理超时")
        except Exception as e:
            logging.error(f"异步任务处理失败: " + traceback.format_exc())
        # 获取 match bubble list
        bubble_list_by_match = find_redpoint_bubble.get_redpoint_bubble_by_match(pil_image)
        
        # 获取 top_bar_height 用于修正 yolo 坐标
        top_bar_height = context.shared_data.get("top_bar_height", 0)
        if top_bar_height is None:
            top_bar_height = 0
        
        # 调用更新后的 find_redpoint_bubble 函数
        if yolo_boxes is not None or len(bubble_list_by_match) > 0 :
            find_redpoint_bubble.find_redpoint_bubble(input_tree, input_tree.root, yolo_boxes, bubble_list_by_match, redpoint_bubble_list, top_bar_height)
        context.shared_data["redpoint_bubble_list"] = redpoint_bubble_list
        find_redpoint_bubble.change_redpoint_layer(context.tree, redpoint_bubble_list)
        return context
