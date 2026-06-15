"""
处理器注册中心
"""
import logging
from typing import Dict, List, Type, Optional
from mdap_u2c.dsl_processors.base import BaseProcessor, ProcessorConfig

logger = logging.getLogger(__name__)

_VLM_PROCESSOR_NAMES = ("call_ai_server", "vlm_result_process")


class ProcessorRegistry:
    def __init__(self):
        self._processors: Dict[str, BaseProcessor] = {}
        self._config_map: Dict[str, ProcessorConfig] = {}
        self._loaded: bool = False  # 标记是否已加载

    def register_decorator(self, name: str, description: Optional[str] = None, config: Optional[ProcessorConfig] = None):
        """
        装饰器方式注册处理器
        Example:
            @processor_registry.register_decorator(name="my_processor", description="这里的内容会下发给用户显示")
            class MyProcessor(BaseProcessor):
                def process(self, context):
                    return context
        """
        def decorator(processor_class: Type[BaseProcessor]):
            self._register(name, processor_class, description, config)
            return processor_class
        return decorator

    def get_sorted_processors(self, enabled_only: bool = True) -> List[BaseProcessor]:
        if not self._loaded:
            self._load_processors()
        
        processors = self._get_all_processors(enabled_only)
        # 按优先级排序（数字越小优先级越高）
        return sorted(processors.values(), key=lambda p: p.config.priority)

    def _get_all_processors(self, enabled_only: bool = True) -> Dict[str, BaseProcessor]:
        if enabled_only:
            return {
                name: processor
                for name, processor in self._processors.items()
                if processor.config.enabled
            }

        return self._processors.copy()

    
    def _load_processors(self):
        """自动加载处理器"""
        if self._loaded:
            return
        
        try:
            from mdap_u2c.dsl_processors import components as _  # noqa: F401
        except ImportError as e:
            logger.error(f"Auto load processors failed, err: {e}")
            raise
        self._loaded = True
        self._apply_env_processor_overrides()

    def _apply_env_processor_overrides(self) -> None:
        """根据环境变量动态启用可选处理器（如 VLM 多模态）。"""
        from mdap_u2c.config.env_loader import load_env
        from mdap_u2c.dsl_processors.cv_module.vlm_provider import is_vlm_enabled

        load_env()
        vlm_enabled = is_vlm_enabled()
        for name in _VLM_PROCESSOR_NAMES:
            processor = self._processors.get(name)
            if processor is None:
                logger.warning("VLM 处理器 %s 未注册", name)
                continue
            processor.config.enabled = vlm_enabled

        if vlm_enabled:
            logger.info(
                "VLM 已启用（MDAP_VLM_PROVIDER），自动开启处理器: %s",
                ", ".join(_VLM_PROCESSOR_NAMES),
            )

    def _register(self, name: str, processor_class: Type[BaseProcessor], description: int = None, config: Optional[ProcessorConfig] = None,
                  override: bool = False):
        if name in self._processors and not override:
            raise ValueError(f"Processor '{name}' already registered. Use override=True to replace.")

        self._config_map[name] = config or ProcessorConfig()
        processor_instance = processor_class(description=description, config=self._config_map[name])
        self._processors[name] = processor_instance

    def __contains__(self, name: str) -> bool:
        """检查处理器是否已注册"""
        return name in self._processors

    def __len__(self) -> int:
        """返回已注册处理器数量"""
        return len(self._processors)


# 全局单例
processor_registry = ProcessorRegistry()


