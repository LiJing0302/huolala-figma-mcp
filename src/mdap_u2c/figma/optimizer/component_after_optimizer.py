import logging
from typing import Optional

from mdap_u2c.models import dsl_model, common_model
from mdap_u2c.enums import dsl_enum
from mdap_u2c.utils.generator_utils import GeneratorUtils
from mdap_u2c.utils import StyleValueUtils

logger = logging.getLogger(__name__)


class ComponentAfterOptimizer:
    # 需要检测类型列表
    _check_types = [dsl_enum.ComponentType.CONTAINER]

    @classmethod
    def optimize(cls, dsl: dsl_model.DSL):
        try:
            if not dsl.components:
                return

            cls._traversal_dsl(component=dsl.components[0])
        except Exception as e:
            logger.error(f"Border support gradient process failed. url: {dsl.metadata.url} | err: {str(e)}", exc_info=True)

    @classmethod
    def _traversal_dsl(cls, component: dsl_model.AbstractComponent):
        stack = [component]
        while stack:
            current = stack.pop()

            if current.type not in cls._check_types:
                continue

            if cls._is_border_contain_gradient_color(style=current.style):
                border_width = cls._get_border_width_info(current.style)
                if border_width:
                    cls._adjust_layout_structure(current, border_width)

            for child in current.children:
                stack.append(child)

    @classmethod
    def _adjust_layout_structure(cls, current: dsl_model.AbstractComponent, border_width: common_model.BorderWidth):
        # ------------------[新组件处理]--------------------
        new_component_id = GeneratorUtils.get_instance().generate_component_id()
        new_component = dsl_model.ContainerComponent.create_with_custom(
            component_id=new_component_id,
            layout=cls._get_new_component_layout(current.layout, border_width),
            style=cls._get_new_component_style(current.style),
            props=dsl_model.ContainerComponentProps(),
            parent_id=current.id
        )
        for child in current.children:
            child.parent_id = new_component_id
            new_component.children.append(child)

        # ------------------[旧组件处理]--------------------
        current.style.background = current.style.border_color
        current.style.background_color = None
        current.style.border_color = None
        current.style.border_width = None
        current.style.border_top_width = None
        current.style.border_right_width = None
        current.style.border_bottom_width = None
        current.style.border_left_width = None
        current.style.border_style = None

        current.children = [new_component]

    @classmethod
    def _get_new_component_layout(cls, layout: dsl_model.Layout, border_width_info: common_model.BorderWidth):
        if layout is None:
            return None

        result = layout.deep_copy()
        # 原来宽和高度需要减去边框宽度
        result.size.width = layout.size.width - border_width_info.left - border_width_info.right
        result.size.height = layout.size.height - border_width_info.top - border_width_info.bottom

        # 位置的x,y也需要减去边框的宽度
        result.position.x = layout.position.x + border_width_info.left
        result.position.y = layout.position.y + border_width_info.top

        return result

    @classmethod
    def _get_new_component_style(cls, style: dsl_model.Style):
        if style is None:
            return dsl_model.Style()

        result = style.deep_copy()
        result.border_color = None
        result.border_width = None
        result.border_top_width = None
        result.border_right_width = None
        result.border_bottom_width = None
        result.border_left_width = None
        result.border_style = None

        return result

    @classmethod
    def _is_border_contain_gradient_color(cls, style: dsl_model.Style) -> bool:
        if style.border_color is None:
            return False

        if style.border_color.startswith("background_"):
            # 移除background_前缀
            style.border_color = style.border_color[len("background_"):]
            return True

        return False

    @classmethod
    def _get_border_width_info(cls, style: dsl_model.Style) -> common_model.BorderWidth | None:
        """该方法，我想判断样式属性中是否包含边框宽度值，需要返回清晰的结构，结构包含四个方向的值"""
        border_width = common_model.BorderWidth()
        border_width_value = cls._check_width_value_px(style.border_width)
        if border_width_value:
            border_width.bottom = border_width_value.value
            border_width.left = border_width_value.value
            border_width.right = border_width_value.value
            border_width.top = border_width_value.value

        border_top_width_value = cls._check_width_value_px(style.border_top_width)
        if border_top_width_value:
            border_width.top = border_top_width_value.value

        border_right_width_value = cls._check_width_value_px(style.border_right_width)
        if border_right_width_value:
            border_width.right = border_right_width_value.value

        border_bottom_width_value = cls._check_width_value_px(style.border_bottom_width)
        if border_bottom_width_value:
            border_width.bottom = border_bottom_width_value.value

        border_left_width_value = cls._check_width_value_px(style.border_left_width)
        if border_left_width_value:
            border_width.left = border_left_width_value.value

        if border_width.bottom > 0 or border_width.left > 0 or border_width.right > 0 or border_width.top > 0:
            return border_width

        return None

    @classmethod
    def _check_width_value_px(cls, width_value: any) -> Optional[common_model.UnitInfo]:
        unit_info = StyleValueUtils.parse_value_and_unit(width_value)
        if unit_info and isinstance(unit_info, common_model.UnitInfo) and unit_info.unit == "px" and unit_info.value > 0:
            return unit_info
