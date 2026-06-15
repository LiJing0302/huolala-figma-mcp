"""
处理器管道 - 编排和执行处理器链

负责按顺序执行所有处理器，特点：
1. 按优先级执行
2. 支持跳过失败的处理器
"""
import asyncio
import logging
from fastmcp import Context
from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.registry import processor_registry
from mdap_u2c.core import SingletonClass

logger = logging.getLogger(__name__)


class ProcessorPipeline(metaclass=SingletonClass):
    def __init__(self):
        self.stop_on_error = False
        self.processors = processor_registry.get_sorted_processors(enabled_only=True)

        processor_names = [p.name for p in self.processors]
        logger.info(f"Initialized pipeline with {len(self.processors)} processors: {processor_names}")

    @staticmethod
    def get_instance():
        return ProcessorPipeline()

    async def execute(self, context: ProcessContext, mcp_context: Context, start_step: int, notify_step_total: int) -> ProcessContext:
        from mdap_u2c.server import McpContextUtils
        # 主线程事件循环：供工作线程里 run_coroutine_threadsafe 上报 MCP 进度（同步 execute 会阻塞 loop，导致进度协程永远不执行）
        context.shared_data["_mcp_asyncio_loop"] = asyncio.get_running_loop()
        for i, processor in enumerate(self.processors, 1):
            logger.debug(f"Pipeline step {i}/{len(self.processors)}: {processor.name}")
            try:
                await McpContextUtils.send_progress(context=mcp_context, progress=i + start_step, total=notify_step_total, message=f"正在进行DSL加工处理({processor.description})...")
                # 供长耗时步骤（如多模态等待）内通过 MCP 续报进度
                context.shared_data["_mcp_context"] = mcp_context
                context.shared_data["_mcp_progress"] = i + start_step
                context.shared_data["_mcp_notify_step_total"] = notify_step_total
                context: ProcessContext = await asyncio.to_thread(processor.execute, context)
            except Exception as e:
                logger.error(f"Pipeline failed at processor '{processor.name}', err: {e}", exc_info=True)
                if self.stop_on_error:
                    raise
                else:
                    # 继续执行下一个处理器
                    logger.warning(f"Continuing pipeline after error")
                    continue

        return context

    def __len__(self) -> int:
        """返回处理器数量"""
        return len(self.processors)

    def __repr__(self) -> str:
        return f"<ProcessorPipeline processors={len(self.processors)}>"
