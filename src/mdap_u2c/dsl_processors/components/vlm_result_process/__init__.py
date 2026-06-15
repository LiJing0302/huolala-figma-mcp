import asyncio
import logging
import traceback
from typing import Callable

from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry

from mdap_u2c.dsl_processors.cv_module import vlm_process
from mdap_u2c.dsl_processors.cv_module.vlm_provider import get_vlm_timeout

logger = logging.getLogger(__name__)


@processor_registry.register_decorator(
    name="vlm_result_process",
    description="调用多模态大模型",
    config=ProcessorConfig(priority=71, enabled=False)  #61，60是根据投影进行分组
)
class CallVLMProcessor(BaseProcessor):
    def _make_vlm_mcp_tick(self, context: ProcessContext) -> Callable[[float], None]:
        """在等待 VLM 异步任务期间，按间隔向 MCP 客户端上报已等待时长（需在 async 工具调用链下才有 event loop）。"""

        def on_tick(elapsed_sec: float) -> None:
            mcp_ctx = context.shared_data.get("_mcp_context")
            if not mcp_ctx:
                return
            # pipeline 在 asyncio.to_thread 中执行 processor 时，本回调在工作线程，无 running loop，必须用 pipeline 注入的主循环
            loop = context.shared_data.get("_mcp_asyncio_loop")
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    logger.debug("VLM MCP 进度跳过：无可用事件循环")
                    return
            from mdap_u2c.server.mcp_context_utils import McpContextUtils

            progress = int(context.shared_data.get("_mcp_progress", 1))
            total = int(context.shared_data.get("_mcp_notify_step_total", 1))
            msg = f"多模态大模型分析中，已等待 {int(elapsed_sec)}s，请稍候..."
            fut = asyncio.run_coroutine_threadsafe(
                McpContextUtils.send_progress(mcp_ctx, progress, total, msg),
                loop,
            )
            try:
                fut.result(timeout=30.0)
            except Exception as e:
                logger.warning("VLM MCP 进度推送失败: %s", e, exc_info=True)

        return on_tick

    def process(self, context: ProcessContext) -> ProcessContext:
        logging.info("Starting list group processor execute.")

        task_id = context.shared_data.get("task_list_group")
        if not task_id:
            logging.error("Task test id not found.")
            return context
        
        
        logging.info(f"存在异步任务，需要等待结果，也可以选择不用等待，自行选择")
        wait_timeout = get_vlm_timeout()
        try:
            # 等待异步任务返回结果（长耗时，定时通过 MCP 推送已等待时间）
            result = self.wait_for_task(
                context,
                task_id,
                timeout=wait_timeout,
                on_wait_tick=self._make_vlm_mcp_tick(context),
                tick_interval=3.0,
            )
            if result['ret'] == 0:
                json_data = result["data"]["output"]
                json_dict = vlm_process.parse_json_safely(json_data)
                
                if json_dict:
                    # 将VLM返回结果保存到context.dsl.vlm_result
                    context.dsl.vlm_result = json_dict
                    logging.info(f"VLM结果已保存到context.dsl.vlm_result")
                else:
                    logging.warning("VLM返回结果解析为空")
            else:
                logging.error(f"后端接口报错: {result}")
        except TimeoutError:
            logging.error("异步任务处理超时（MDAP_VLM_TIMEOUT=%ss）", wait_timeout)
        except Exception as e:
            logging.error(f"异步任务处理失败: " + traceback.format_exc())

        return context


