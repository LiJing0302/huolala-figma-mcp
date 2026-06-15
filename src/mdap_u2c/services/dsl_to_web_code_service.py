from typing import Optional
from mdap_u2c.models import dsl_model
from mdap_u2c.enums import dsl_enum


class DslToWebCodeService:
    _dsl: dsl_model.DSL
    _fonts: Optional[dict[str, str]] = None

    def __init__(self, dsl: dsl_model.DSL, fonts: Optional[dict[str, str]] = None):
        self._dsl = dsl
        self._fonts = fonts or {}

    def to_web_code(self) -> str:
        """将 DSL 转换为 HTML"""
        if self._dsl is None:
            raise ValueError("DSL cannot be None")

        if self._dsl.components is None or len(self._dsl.components) == 0:
            raise ValueError("DSL components cannot be None or empty")

        return self._generate_html()

    def _generate_html(self) -> str:
        """生成完整的 HTML 内容"""
        html = []

        html.append("<!DOCTYPE html>")
        html.append('<html lang="zh-CN">')
        html.append("<head>")
        html.append('    <meta charset="UTF-8">')
        html.append('    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
        html.append(f'    <title>{self._dsl.metadata.name if self._dsl.metadata.name else "Huolala Figma MCP"}</title>')
        html.append("    <style>")

        # 字体注册
        for font_name, font_url in self._fonts.items():
            html.append(f'        @font-face {{')
            html.append(f'          font-family: "{font_name}";')
            html.append(f'          src: url("./fonts/{font_url}");')
            html.append("         }")

        html.append("        * { margin: 0; padding: 0; box-sizing: border-box; }")
        html.append("        ul,ol { padding-inline-start: 16px; }")
        html.append("        body { font-family: Arial, sans-serif; }")

        body_content = []
        if self._dsl.components:
            for component in self._dsl.components:
                body_content.append(self._convert_component(component, indent=4))

        html.append("    </style>")
        html.append("</head>")
        html.append("<body>")
        html.extend(body_content)
        html.append("</body>")
        html.append("</html>")
        
        return "\n".join(html)
    
    def _convert_component(self, component: dsl_model.AbstractComponent, indent: int = 0) -> str:
        """转换组件为 HTML"""
        indent_str = " " * indent
        component_type = component.type
        
        if component_type == dsl_enum.ComponentType.TEXT.value:
            return self._convert_text_component(component, indent)
        elif component_type == dsl_enum.ComponentType.IMAGE.value:
            return self._convert_image_component(component, indent)
        elif component_type == dsl_enum.ComponentType.BR.value:
            return f"{indent_str}<br />"
        elif component_type in [dsl_enum.ComponentType.ORDERED_LIST.value, dsl_enum.ComponentType.UNORDERED_LIST.value]:
            return self._convert_list_component(component, indent)
        else:
            return self._convert_container_component(component, indent)
    
    def _convert_container_component(self, component: dsl_model.AbstractComponent, indent: int = 0) -> str:
        """转换容器组件"""
        indent_str = " " * indent
        tag = "div"
        
        # 构建属性
        attrs = []
        if component.id:
            attrs.append(f'id="{component.id}"')

        style_str = self._build_style(component.style)
        if style_str:
            attrs.append(f'style="{style_str}"')
        attrs_str = " " + " ".join(attrs) if attrs else ""

        # 处理子组件
        children_html = []
        if component.children:
            for child in component.children:
                children_html.append(self._convert_component(child, indent + 4))
        
        if children_html:
            html_parts = [f"{indent_str}<{tag}{attrs_str}>"]
            html_parts.extend(children_html)
            html_parts.append(f"{indent_str}</{tag}>")
            return "\n".join(html_parts)
        else:
            return f"{indent_str}<{tag}{attrs_str}></{tag}>"
    
    def _convert_text_component(self, component: dsl_model.AbstractComponent, indent: int = 0) -> str:
        """转换文本组件"""
        indent_str = " " * indent

        # 构建属性
        attrs = []
        if component.id:
            attrs.append(f'id="{component.id}"')

        style_str = self._build_style(component.style)
        if style_str:
            attrs.append(f'style="{style_str}"')
        attrs_str = " " + " ".join(attrs) if attrs else ""
        
        # 获取文本内容
        text = ""
        if component.props and hasattr(component.props, "text"):
            text = str(component.props.text)
        
        # HTML 转义
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        return f"{indent_str}<span{attrs_str}>{text}</span>"
    
    def _convert_image_component(self, component: dsl_model.AbstractComponent, indent: int = 0) -> str:
        """转换图片组件"""
        indent_str = " " * indent
        
        # 构建属性
        attrs = []
        if component.id:
            attrs.append(f'id="{component.id}"')

        # 图片属性
        if component.props and hasattr(component.props, "src"):
            attrs.append(f'src="{component.props.src}"')
        
        if component.props and hasattr(component.props, "alt"):
            alt = component.props.alt or ""
            attrs.append(f'alt="{alt}"')

        style_str = self._build_style(component.style)
        if style_str:
            attrs.append(f'style="{style_str}"')
        attrs_str = " " + " ".join(attrs) if attrs else ""
        
        return f"{indent_str}<img{attrs_str} />"

    def _convert_list_component(self, component: dsl_model.AbstractComponent, indent: int = 0) -> str:
        """转换列表组件，根据 level 构建嵌套结构"""
        indent_str = " " * indent
        
        # 判断是有序列表还是无序列表
        if component.type == dsl_enum.ComponentType.ORDERED_LIST.value:
            tag = "ol"
        else:
            tag = "ul"
        
        # 构建属性
        attrs = []
        if component.id:
            attrs.append(f'id="{component.id}"')

        # 有序列表的起始序号
        if tag == "ol" and component.props and hasattr(component.props, "start_index") and component.props.start_index:
            attrs.append(f'start="{component.props.start_index}"')
        
        style_str = self._build_style(component.style)
        if style_str:
            attrs.append(f'style="{style_str}"')
        
        attrs_str = " " + " ".join(attrs) if attrs else ""
        
        # 处理子组件（列表项），根据 level 构建嵌套结构
        children = component.children or []
        
        # 过滤出列表项
        list_items = [child for child in children if child.type == dsl_enum.ComponentType.LIST_ITEM.value]
        other_children = [child for child in children if child.type != dsl_enum.ComponentType.LIST_ITEM.value]
        
        if not list_items:
            # 如果没有列表项，只处理其他子组件
            children_html = []
            for child in other_children:
                children_html.append(self._convert_component(child, indent + 4))
            
            if children_html:
                html_parts = [f"{indent_str}<{tag}{attrs_str}>"]
                html_parts.extend(children_html)
                html_parts.append(f"{indent_str}</{tag}>")
                return "\n".join(html_parts)
            else:
                return f"{indent_str}<{tag}{attrs_str}></{tag}>"
        
        # 根据 level 构建嵌套结构
        html_parts = [f"{indent_str}<{tag}{attrs_str}>"]
        html_parts.extend(self._build_nested_list_items(list_items, indent + 4, component.type))
        html_parts.append(f"{indent_str}</{tag}>")
        
        return "\n".join(html_parts)
    
    def _build_nested_list_items(self, list_items: list, indent: int, list_type: str, parent_level: int = -1) -> list:
        """根据 level 构建嵌套的列表项"""
        if not list_items:
            return []
        
        html_parts = []
        i = 0
        
        while i < len(list_items):
            item = list_items[i]
            # 获取列表项的 level
            current_level = 0
            if item.props and hasattr(item.props, "level"):
                current_level = item.props.level
            
            # 如果当前项的 level 小于等于父级 level，说明不属于当前层级，应该停止
            if parent_level >= 0 and current_level <= parent_level:
                break
            
            # 查找当前项下的所有嵌套项（level > current_level 的项）
            nested_items = []
            j = i + 1
            while j < len(list_items):
                next_item = list_items[j]
                next_level = 0
                if next_item.props and hasattr(next_item.props, "level"):
                    next_level = next_item.props.level
                
                # 如果下一个项的 level 等于当前项的 level，说明是同级项，停止
                if next_level == current_level:
                    break
                # 如果下一个项的 level 小于当前项的 level，说明回到了上一级，停止
                if next_level < current_level:
                    break
                # 如果下一个项的 level 大于当前项的 level，说明是嵌套项（直接子项或更深层的嵌套）
                if next_level > current_level:
                    nested_items.append(next_item)
                    j += 1
                else:
                    break
            
            # 转换当前列表项，并包含嵌套列表（如果有）
            item_html = self._convert_list_item_with_nested(
                item, nested_items, indent, list_type, current_level
            )
            html_parts.append(item_html)
            
            # 移动到下一个同级项（跳过所有嵌套项，因为它们已经被处理了）
            i = j
        
        return html_parts
    
    def _convert_list_item_with_nested(self, item: dsl_model.AbstractComponent, nested_items: list, indent: int, list_type: str, current_level: int) -> str:
        """转换列表项，包含嵌套列表（如果有）"""
        indent_str = " " * indent
        tag = "li"
        
        # 构建属性
        attrs = []
        if item.id:
            attrs.append(f'id="{item.id}"')
        
        style_str = self._build_style(item.style)
        if style_str:
            attrs.append(f'style="{style_str}"')
        
        attrs_str = " " + " ".join(attrs) if attrs else ""
        
        # 处理列表项的直接子组件（不包括嵌套的列表项）
        children_html = []
        if item.children:
            for child in item.children:
                # 跳过列表项类型的子组件（嵌套列表会单独处理）
                if child.type != dsl_enum.ComponentType.LIST_ITEM.value:
                    children_html.append(self._convert_component(child, indent + 4))
        
        # 构建嵌套列表（如果有）
        nested_list_html = ""
        if nested_items:
            nested_tag = "ol" if list_type == dsl_enum.ComponentType.ORDERED_LIST.value else "ul"
            nested_indent_str = " " * (indent + 4)
            
            nested_html_parts = [f"{nested_indent_str}<{nested_tag}>"]
            nested_html_parts.extend(self._build_nested_list_items(nested_items, indent + 8, list_type, current_level))
            nested_html_parts.append(f"{nested_indent_str}</{nested_tag}>")
            nested_list_html = "\n".join(nested_html_parts)
        
        # 组合所有内容
        html_parts = [f"{indent_str}<{tag}{attrs_str}>"]
        if children_html:
            html_parts.extend(children_html)
        if nested_list_html:
            html_parts.append(nested_list_html)
        html_parts.append(f"{indent_str}</{tag}>")
        
        return "\n".join(html_parts)
    

    @classmethod
    def _is_text_gradient(cls, value: str) -> bool:
        """判断是否为渐变值（CSS color 不支持渐变，需用 background + background-clip: text 实现）"""
        if not value or not isinstance(value, str):
            return False
        v = value.strip()
        return v.startswith("linear-gradient(") or v.startswith("radial-gradient(") or v.startswith("conic-gradient(")

    @classmethod
    def _build_style(cls, style: Optional[dsl_model.Style]) -> str:
        """构建 CSS 样式字符串"""
        styles = []

        if style:
            # 使用反射机制遍历 Style 对象的所有字段
            for field_name in style.__struct_fields__:
                value = getattr(style, field_name, None)
                if value is None:
                    continue
                
                # 跳过不需要处理的字段（如 deep_copy 方法等）
                if field_name.startswith('_') or callable(value):
                    continue
                
                # 文本渐变色：color 不能直接写 linear-gradient，需用 background + background-clip: text + color: transparent
                if field_name == "color" and cls._is_text_gradient(value):
                    styles.append(f"background: {value}")
                    styles.append("background-clip: text")
                    styles.append("color: transparent")
                    continue
                
                # 将下划线属性名转换为连字符 CSS 属性名
                css_property = field_name.replace('_', '-')

                # 处理webkit开头属性
                if css_property.startswith('webkit'):
                    css_property = f"-{css_property}"

                styles.append(f"{css_property}: {value}")

        return "; ".join(styles) if styles else ""

