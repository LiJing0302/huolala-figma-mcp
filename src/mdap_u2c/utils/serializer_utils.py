"""
序列化工具
提供 msgspec 对象的序列化/反序列化功能
"""
import msgspec
from typing import Any, Type, TypeVar


T = TypeVar('T')


class SerializerUtils:
    """序列化器，用于 msgspec 对象的 JSON 转换"""
    @staticmethod
    def to_json(obj: Any, indent: int = 0, omit_defaults: bool = True) -> str:
        if indent > 0:
            # 格式化输出（可读性好，但性能稍差）
            encoder = msgspec.json.Encoder()
            json_bytes = encoder.encode(obj)
            # 使用标准库格式化，并过滤 None 值
            import json
            data = json.loads(json_bytes)
            if omit_defaults:
                data = SerializerUtils._remove_none_values(data)
            return json.dumps(data, ensure_ascii=False, indent=indent)
        else:
            # 紧凑输出（性能最优）
            if omit_defaults:
                # 先转换为字典，过滤 None，再序列化
                data = msgspec.to_builtins(obj)
                data = SerializerUtils._remove_none_values(data)
                import json
                return json.dumps(data, ensure_ascii=False)
            else:
                encoder = msgspec.json.Encoder()
                return encoder.encode(obj).decode('utf-8')
    
    @staticmethod
    def to_dict(obj: Any, omit_defaults: bool = True) -> dict:
        data = msgspec.to_builtins(obj)
        if omit_defaults:
            return SerializerUtils._remove_none_values(data)
        return data
    
    @staticmethod
    def _remove_none_values(data: Any) -> Any:
        if isinstance(data, dict):
            return {
                key: SerializerUtils._remove_none_values(value)
                for key, value in data.items()
                if value is not None and value != [] and value != {}
            }
        elif isinstance(data, list):
            return [
                SerializerUtils._remove_none_values(item)
                for item in data
                if item is not None
            ]
        else:
            return data
    
    @staticmethod
    
    @staticmethod
    def from_dict(data: dict, type_: Type[T]) -> T:
        return msgspec.convert(data, type_)
