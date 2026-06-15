from mdap_u2c.enums import dsl_enum
from typing import Optional, Union
from mdap_u2c.models import common_model


class StyleValueUtils:
    """样式值格式化与解析工具类"""

    @classmethod
    def format_number(cls, value: Optional[Union[int, float]] = None) -> Optional[Union[int, float]]:
        """
        格式化数值
        1. 如果参数为浮点类型，并且小数位为0，则会转换成int类型
        2. 如果参数为浮点类型，并且小数位不为0，则最多保留两位小数
        """
        if value is None:
            return

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if value.is_integer():
                return int(value)

        value = float(f"{value:.2f}")
        return int(value) if value.is_integer() else value

    @classmethod
    def format_value_with_unit(cls, value: Optional[Union[str, int, float]] = None, unit: dsl_enum.StyleUnit = dsl_enum.StyleUnit.PX) -> Optional[str]:
        """
        格式化值和单位
        """
        if value is None:
            return None

        if isinstance(value, str):
            return value

        value = cls.format_number(value)
        if unit is None:
            return str(value)

        return str(value) + unit.value

    @classmethod
    def parse_value_and_unit(cls, value: Optional[Union[str, int, float]]) -> Optional[Union["common_model.UnitInfo", str]]:
        """
        解析值和单位
        :param value:
        :return:
        """
        if value is None:
            return value

        # 如果是数字类型，单位为空
        if isinstance(value, int) or isinstance(value, float):
            return common_model.UnitInfo.create(cls.format_number(value), "")

        # 如果是字符串类型
        if isinstance(value, str):
            import re
            # 匹配以数字开头的字符串，提取数字和单位
            match = re.match(r'^(\d+(?:\.\d+)?)(.*)$', value.strip())
            if match:
                # 数字开头，解析出数字和单位
                number_str = match.group(1)
                unit = match.group(2) if match.group(2) else ''
                try:
                    number = float(number_str) if '.' in number_str else int(number_str)
                    return common_model.UnitInfo.create(cls.format_number(number), unit)
                except ValueError:
                    return value
            else:
                return value

        return value


