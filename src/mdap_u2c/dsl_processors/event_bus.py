"""
事件总线 - 支持事件发布订阅和异步任务管理
"""
import logging
import asyncio
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
import uuid

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """事件优先级"""
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Event:
    """事件对象"""
    name: str  # 事件名称
    data: Any  # 事件数据
    source: str = None  # 事件源（哪个处理器发出的）
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: EventPriority = EventPriority.NORMAL

    def __repr__(self):
        return f"<Event name='{self.name}' source='{self.source}' id='{self.event_id[:8]}...'>"


@dataclass
class AsyncTask:
    """异步任务对象"""
    task_id: str
    name: str
    future: Union[Future, asyncio.Future]
    created_by: str  # 创建任务的处理器名称

    def is_done(self) -> bool:
        """任务是否完成"""
        return self.future.done()

    def result(self, timeout: Optional[float] = None) -> Any:
        """获取任务结果"""
        if isinstance(self.future, asyncio.Future):
            # asyncio.Future 需要在事件循环中获取
            return self.future.result()
        else:
            # concurrent.futures.Future
            return self.future.result(timeout=timeout)

    def __repr__(self):
        status = "done" if self.is_done() else "running"
        return f"<AsyncTask name='{self.name}' status='{status}' id='{self.task_id[:8]}...'>"


class EventBus:
    """
    事件总线 - 支持事件发布订阅和异步任务管理

    Features:
    1. 事件发布/订阅（同步和异步）
    2. 异步任务管理（线程池/进程池）
    3. 等待特定事件或任务完成
    4. 事件优先级
    """

    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: 线程池最大工作线程数
        """
        self._listeners: Dict[str, List[Callable]] = {}  # 事件监听器
        self._tasks: Dict[str, AsyncTask] = {}  # 异步任务
        self._event_queue: List[Event] = []  # 事件队列
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        logger.info(f"EventBus initialized with {max_workers} workers")

    # ==================== 事件发布订阅 ====================

    def subscribe(self, event_name: str, callback: Callable[[Event], None]):
        """
        订阅事件

        Args:
            event_name: 事件名称
            callback: 回调函数，接收 Event 对象

        Example:
            def on_task_complete(event: Event):
                print(f"Task completed: {event.data}")

            event_bus.subscribe("task_complete", on_task_complete)
        """
        with self._lock:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            self._listeners[event_name].append(callback)
            logger.debug(f"Subscribed to event '{event_name}', total listeners: {len(self._listeners[event_name])}")

    def unsubscribe(self, event_name: str, callback: Callable[[Event], None]):
        """取消订阅"""
        with self._lock:
            if event_name in self._listeners:
                self._listeners[event_name].remove(callback)
                logger.debug(f"Unsubscribed from event '{event_name}'")

    def publish(self, event_name: str, data: Any = None, source: str = None,
                priority: EventPriority = EventPriority.NORMAL):
        """
        发布事件（同步执行监听器）

        Args:
            event_name: 事件名称
            data: 事件数据
            source: 事件源
            priority: 事件优先级

        Example:
            event_bus.publish("data_processed", {"result": result}, source="DataProcessor")
        """
        event = Event(name=event_name, data=data, source=source, priority=priority)
        logger.info(f"Publishing event: {event}")

        with self._lock:
            listeners = self._listeners.get(event_name, []).copy()

        # 执行所有监听器
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error executing listener for event '{event_name}': {e}")


    def _safe_execute_listener(self, listener: Callable, event: Event):
        """安全执行监听器（捕获异常）"""
        try:
            listener(event)
        except Exception as e:
            logger.error(f"Error executing async listener for event '{event.name}': {e}")

    def wait_for_event(self, event_name: str, timeout: Optional[float] = None,
                       predicate: Optional[Callable[[Event], bool]] = None) -> Optional[Event]:
        """
        等待特定事件发生

        Args:
            event_name: 事件名称
            timeout: 超时时间（秒）
            predicate: 判断函数，返回 True 表示是期望的事件

        Returns:
            Event 对象，如果超时返回 None

        Example:
            # 等待任务完成事件
            event = event_bus.wait_for_event("task_complete", timeout=30)
            if event:
                result = event.data
        """
        event_received = threading.Event()
        received_event = [None]

        def listener(event: Event):
            if predicate is None or predicate(event):
                received_event[0] = event
                event_received.set()

        self.subscribe(event_name, listener)

        try:
            if event_received.wait(timeout=timeout):
                return received_event[0]
            else:
                logger.warning(f"Timeout waiting for event '{event_name}'")
                return None
        finally:
            self.unsubscribe(event_name, listener)

    # ==================== 异步任务管理 ====================

    def submit_task(self, func: Callable, *args, name: str = None, created_by: str = None, **kwargs) -> AsyncTask:
        """
        提交异步任务到线程池

        Args:
            func: 要执行的函数
            name: 任务名称
            created_by: 创建任务的处理器名称
            *args, **kwargs: 函数参数

        Returns:
            AsyncTask 对象

        Example:
            def heavy_computation(x, y):
                return x + y

            task = event_bus.submit_task(heavy_computation, 1, 2, name="computation")
            result = task.result()  # 等待结果
        """
        task_id = str(uuid.uuid4())
        task_name = name or f"task_{task_id[:8]}"

        future = self._executor.submit(func, *args, **kwargs)
        task = AsyncTask(
            task_id=task_id,
            name=task_name,
            future=future,
            created_by=created_by or "unknown"
        )

        with self._lock:
            self._tasks[task_id] = task

        logger.info(f"Submitted task: {task}")

        # 任务完成后自动发布事件
        def on_complete(f: Future):
            try:
                result = f.result()
                self.publish(f"task_complete:{task_id}",
                             data={"task_id": task_id, "result": result},
                             source=created_by)
                logger.info(f"Task {task.name} completed successfully")
            except Exception as e:
                self.publish(f"task_error:{task_id}",
                             data={"task_id": task_id, "error": str(e)},
                             source=created_by)
                logger.error(f"Task {task.name} failed: {e}")

        future.add_done_callback(on_complete)

        return task

    def get_task(self, task_id: str) -> Optional[AsyncTask]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None,
        *,
        on_wait_tick: Optional[Callable[[float], None]] = None,
        tick_interval: float = 10.0,
    ) -> Any:
        """
        等待任务完成并获取结果

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            on_wait_tick: 在等待期间按 tick_interval 周期回调，参数为已等待秒数（浮点）
            tick_interval: 轮询间隔（秒），用于长耗时任务时触发 on_wait_tick（如 MCP 进度推送）

        Returns:
            任务结果

        Raises:
            TimeoutError: 如果超时
            Exception: 如果任务执行失败
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        future = task.future
        if not on_wait_tick or tick_interval <= 0:
            return future.result(timeout=timeout)

        start = time.monotonic()
        while True:
            if future.done():
                return future.result()

            elapsed = time.monotonic() - start
            if timeout is not None and elapsed >= timeout:
                raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

            remaining = timeout - elapsed if timeout is not None else tick_interval
            chunk = min(tick_interval, remaining) if remaining > 0 else 0.0
            if chunk <= 0:
                raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

            try:
                return future.result(timeout=chunk)
            except FuturesTimeoutError:
                on_wait_tick(time.monotonic() - start)


    # ==================== 工具方法 ====================

    def shutdown(self, wait: bool = True):
        """关闭事件总线"""
        logger.info("Shutting down EventBus...")
        self._executor.shutdown(wait=wait)

    def __del__(self):
        """析构时关闭线程池"""
        try:
            self.shutdown(wait=False)
        except:
            pass

    def __repr__(self):
        return f"<EventBus listeners={len(self._listeners)} tasks={len(self._tasks)}>"


# 全局单例
event_bus = EventBus()