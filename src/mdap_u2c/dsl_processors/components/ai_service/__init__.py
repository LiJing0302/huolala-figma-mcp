import copy
import logging
import os

from PIL import Image
from mdap_u2c.dsl_processors import processor_registry
from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.utils.download_file import get_image_by_url
from mdap_u2c.dsl_processors.cv_module import find_redpoint_bubble
from mdap_u2c.utils.serializer_utils import SerializerUtils

from mdap_u2c.dsl_processors.cv_module import vlm_process

@processor_registry.register_decorator(
    name="call_ai_server",
    description="调用AI服务",
    config=ProcessorConfig(priority=8, enabled=False)
)

class CallServerProcessor(BaseProcessor):
    def process(self, context: ProcessContext) -> ProcessContext:
        context.shared_data["debug"] = 0
        if "debug" in context.shared_data and context.shared_data['debug'] == 1:
            dsl_json_path = os.path.join("tests", "dsl.json")
            with open(dsl_json_path, "w", encoding="utf-8") as json_file:
                json_file.write(SerializerUtils.to_json(context.dsl))

        logging.info("Starting call vlm server processor execute.")
        # 提交异步任务执行(异步任务不会阻塞主链路执行)
        vlm_task = self.submit_task(
            context,
            func=CallServerProcessor.async_call_vlm_server,
            data=context,
            name="task_list_group"
        )
        context.shared_data["task_list_group"] = vlm_task.task_id

        pil_image = context.shared_data.get("pil_image")
        if pil_image is None:
            pil_image = get_image_by_url(context.dsl.metadata.image_url)
            context.shared_data["pil_image"] = pil_image
        pil_image_copy = copy.deepcopy(pil_image)
        # 提交异步任务执行 yolo 检测红点气泡（在单独进程中执行）
        yolo_task = self.submit_task(
            context,
            func=CallServerProcessor.async_get_redpoint_bubble_boxes_by_yolo,
            data=pil_image_copy,
            name="task_yolo_redpoint_bubble"
        )
        context.shared_data["task_yolo_redpoint_bubble"] = yolo_task.task_id
        return context

    @staticmethod
    def async_call_vlm_server(data:ProcessContext) -> dict:
        """异步执行的函数, 必须是静态方法或普通函数"""
        result_json = vlm_process.call_vlm_api("识别UI结构 ,输出前端可用json结构,要求包含x,y,width,height,type,text(如有),children(如有)字段", data)
        #返回结果(结果不做约束，可自定义)
        return result_json

    @staticmethod
    def async_get_redpoint_bubble_boxes_by_yolo(data: Image):
        """异步执行 yolo 检测红点气泡"""
        boxes = find_redpoint_bubble.get_redpoint_bubble_boxes_by_yolo(data)
        return boxes
