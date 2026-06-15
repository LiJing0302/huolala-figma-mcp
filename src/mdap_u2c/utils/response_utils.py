# coding=utf-8
"""
HTTP 统一响应格式
定义标准的 HTTP API 响应格式，确保所有接口返回结构一致
"""
from typing import TypeVar, Optional, Any
from enum import Enum
import msgspec

# 泛型类型变量，用于包装任意数据类型
T = TypeVar('T')


class BusinessCode(Enum):
    SUCCESS = (0, "Success")

    # 1xxxx 开头: 服务器内部相关错误
    FAILURE = (10000, "操作失败")
    SERVER_ERROR = (10001, "服务器内部错误，请稍后再试")
    REQUEST_TIMEOUT = (10002, "请求超时")

    # 2xxxx 开头: 账号相关问题
    INVALID_LOGIN = (20000, "登录已失效，请重新登录")
    ACCOUNT_NOT_PERMISSION = (20001, "不好意思，没有操作权限")

    # 3xxxx 开头: 参数和访问资源相关问题
    INVALID_PARAMETER = (30000, "无效的参数")
    RESOURCE_NOT_EXIST = (30001, "资源不存在")
    MISSING_PARAMETER = (30002, "缺少必要参数")
    REQUEST_TOO_FAST_LIMIT = (30003, "请求过快，稍后再试")

    def __init__(self, ret: int, msg: str):
        self._ret = ret
        self._msg = msg

    @property
    def get_ret(self) -> int:
        return self._ret

    @property
    def get_msg(self) -> str:
        return self._msg

    @classmethod
    def from_code(cls, ret: int) -> Optional['BusinessCode']:
        for member in cls:
            if member.code == ret:
                return member
        return None

    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.name}({self.get_ret}: {self.get_msg})"

    def __repr__(self) -> str:
        """调试表示"""
        return f"<ResponseCode.{self.name}: ret={self.get_ret}, msg='{self.get_msg}'>"


class ResponseUtils(msgspec.Struct, kw_only=True):
    ret: int = 0
    msg: str = "Success"
    data: Optional[Any] = None

    @classmethod
    def success(cls, data: Optional[Any] = None, msg: Optional[str] = None) -> dict:
        """成功响应"""
        response = cls(
            ret=BusinessCode.SUCCESS.get_ret,
            msg=msg if msg is not None else BusinessCode.SUCCESS.get_msg,
            data=data
        )
        return response.to_dict()

    @classmethod
    def error(cls, code: BusinessCode = None, msg: Optional[str] = None, data: Optional[Any] = None) -> dict:
        """错误响应"""
        if code is None:
            code = BusinessCode.FAILURE

        response = cls(
            ret=code.get_ret,
            msg=msg if msg is not None else code.get_msg,
            data=data
        )
        return response.to_dict()

    def to_dict(self) -> dict:
        """转换为字典"""
        return msgspec.to_builtins(self)

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        encoder = msgspec.json.Encoder()
        return encoder.encode(self).decode('utf-8')

    def is_success(self) -> bool:
        """判断是否成功"""
        return self.ret == BusinessCode.SUCCESS.get_ret
