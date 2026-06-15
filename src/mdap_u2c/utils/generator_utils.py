"""
ID 生成器工具类
"""
import uuid
from typing import Optional
from enum import Enum
from mdap_u2c.core import SingletonClass


class IdType(Enum):
    """ID 类型枚举"""
    COMPONENT = "comp"      # 组件 ID
    IMAGE = "img"           # 图片 ID
    FONT = "font"           # 字体 ID
    CUSTOM = "custom"       # 自定义 ID


class GeneratorUtils(metaclass=SingletonClass):
    _default_length: int = 10  # 默认长度

    @staticmethod
    def get_instance():
        return GeneratorUtils()

    def generate_component_id(self) -> str:
        return self.generate_with_type(id_type=IdType.COMPONENT)

    def generate_with_type(self, id_type: IdType, length: Optional[int] = None):
        return self.generate(id_type=id_type, length=length)


    def generate(self, id_type: Optional[IdType] = None, prefix: Optional[str] = None, length: Optional[int] = None):
        final_prefix = prefix or id_type.value
        return f"{final_prefix}:{uuid.uuid4().hex[:length or self._default_length]}"

