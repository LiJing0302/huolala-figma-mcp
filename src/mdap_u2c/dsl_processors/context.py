"""
处理上下文 - 统一的输入输出数据结构
所有处理器共享同一个 Context 对象
"""
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from treelib import Tree

from mdap_u2c.dsl_processors.event_bus import EventBus, event_bus as default_event_bus
from mdap_u2c.models import dsl_model


@dataclass
class ProcessContext:
    dsl: dsl_model.DSL                                                      # DSL 数据结构（核心数据）
    tree: Tree                                                              # DSL 树结构(不推荐使用，由加工厂自行创建和维护)
    event_bus: EventBus = field(default_factory=lambda: default_event_bus)  # 事件总线（用于事件发布订阅和异步任务管理）
    shared_data: Dict[str, Any] = field(default_factory=dict)               # 处理器之间共享的临时数据

    def __post_init__(self):
        """初始化时确保 DSL 结构正确"""
        if not isinstance(self.dsl, dsl_model.DSL):
            raise ValueError("DSL must be a DSL model")

    def to_dict(self) -> Dict[str, Any]:
        from mdap_u2c.utils.serializer_utils import SerializerUtils
        return {
            "dsl": SerializerUtils.to_dict(self.dsl),
            "shared_data": self.shared_data
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], event_bus: Optional[EventBus] = None) -> "ProcessContext":
        return cls(
            dsl=data.get("dsl", {}),
            tree=Tree(),
            shared_data=data.get("shared_data", {}),
            event_bus=event_bus or default_event_bus
        )

    """克隆上下文（深拷贝）"""
    def clone(self) -> "ProcessContext":
        import copy
        return ProcessContext(
            dsl=copy.deepcopy(self.dsl),
            tree=self.tree,
            shared_data=copy.deepcopy(self.shared_data),
            event_bus=self.event_bus  # event_bus 不需要拷贝，使用同一个实例
        )


