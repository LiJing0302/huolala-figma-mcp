import msgspec
from typing import Optional, Union

from mdap_u2c.utils.serializer_utils import SerializerUtils


class Rect(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """矩形"""
    x: Union[float, int] = 0
    y: Union[float, int] = 0
    width: Union[float, int] = 0
    height: Union[float, int] = 0


class BorderWidth(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """边框宽度"""
    top: Optional[float] = msgspec.field(default=0)
    right: Optional[float] = msgspec.field(default=0)
    bottom: Optional[float] = msgspec.field(default=0)
    left: Optional[float] = msgspec.field(default=0)


class OverlapInfo(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """重叠信息"""
    top: bool = msgspec.field(default=False)
    right: bool = msgspec.field(default=False)
    bottom: bool = msgspec.field(default=False)
    left: bool = msgspec.field(default=False)


class UnitInfo(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """单位信息"""
    unit: Optional[str] = msgspec.field(default="")
    value: Union[float, int] = msgspec.field(default=0)

    @classmethod
    def create(cls, value: Union[str, int, float], unit: Optional[str] = None):
        return cls(value=value, unit=unit)


class TokenUserInfo(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """Token用户信息"""
    name_en: str        # 英文名
    name_cn: str        # 中文名
    client_id: str      # 客户端ID

    def to_json(self):
        return SerializerUtils.to_json(self)

    def to_dict(self) -> dict:
        return SerializerUtils.to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TokenUserInfo":
        return cls(
            name_en=data.get("name_en"),
            name_cn=data.get("name_cn"),
            client_id=data.get("client_id"),
        )


