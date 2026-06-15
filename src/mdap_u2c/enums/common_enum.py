"""
通用枚举定义

跨领域共享的枚举类型，如来源类型、资源格式等
"""

from enum import Enum


class PlatformType(str, Enum):
    """平台类型"""
    H5 = "h5"
    Vue = "vue"
    React = "react"
    ReactNative = "rn"
    Ios = "ios"
    Android = "android"


