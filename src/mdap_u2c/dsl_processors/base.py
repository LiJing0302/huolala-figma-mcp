"""
处理器基类 - 定义所有处理器的标准接口

所有 DSL 处理器都必须继承这个基类，确保：
1. 统一的接口
2. 统一的入参和出参
3. 可选执行
4. 错误处理
"""
import logging
import traceback
from abc import ABC, abstractmethod
from typing import Optional, Any, Callable

import msgspec

from mdap_u2c.dsl_processors.context import ProcessContext
from mdap_u2c.dsl_processors.event_bus import AsyncTask, Event

logger = logging.getLogger(__name__)


class ProcessorConfig(msgspec.Struct, kw_only=True):
    enabled: bool = True            # 是否启用
    skip_on_error: bool = True      # 出错时是否跳过继续执行
    priority: int = 100             # 优先级（数字越小越先执行）
    config: dict = None             # 自定义配置


class BaseProcessor(ABC):
    """处理基类（抽象层，不要直接使用）"""
    def __init__(self, description: str = None, config: Optional[ProcessorConfig] = None):
        self.config = config or ProcessorConfig()
        self.name = self.__class__.__name__
        self.description = description

    @abstractmethod
    def process(self, context: ProcessContext) -> ProcessContext:
        """需要子类实现具体逻辑，并且返回处理上下文"""
        pass
    
    def execute(self, context: ProcessContext) -> ProcessContext:
        # 检查是否启用
        if not self.config.enabled:
            logger.info(f"['{self.name}'] processor is disabled, skipping")
            return context
        try:
            result = self.process(context)
            logger.info(f"['{self.name}'] processor successfully")
            return result
        except Exception as e:
            error_trace_msg = traceback.format_exc()
            logger.error(f"['{self.name}'] processor failed, err: {error_trace_msg}")
            # 根据配置决定是否跳过错误
            if self.config.skip_on_error:
                logger.warning(f"['{self.name}'] processor skipping error, continuing pipeline")
                return context
            else:
                raise


    def wait_for_event(self, context: ProcessContext, event_name: str, timeout: Optional[float] = None) -> Optional[Event]:
        """等待事件"""
        return context.event_bus.wait_for_event(event_name, timeout=timeout)

    def submit_task(self, context: ProcessContext, func: Callable, *args, name: str = None, **kwargs) -> AsyncTask:
        """提交异步任务"""
        return context.event_bus.submit_task(func, *args, name=name, created_by=self.name, **kwargs)

    def wait_for_task(
        self,
        context: ProcessContext,
        task_id: str,
        timeout: Optional[float] = None,
        *,
        on_wait_tick: Optional[Callable[[float], None]] = None,
        tick_interval: float = 10.0,
    ) -> Any:
        """等待任务完成；长耗时任务可传入 on_wait_tick 做周期性通知（如 MCP 进度）。"""
        return context.event_bus.wait_for_task(
            task_id,
            timeout=timeout,
            on_wait_tick=on_wait_tick,
            tick_interval=tick_interval,
        )

    def __repr__(self) -> str:
        return f"<{self.name} enabled={self.config.enabled} priority={self.config.priority}>"
