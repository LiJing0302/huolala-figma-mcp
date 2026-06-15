from typing import Dict, Any, Optional, List

from mdap_u2c.models import dsl_model
from .style.text_style import TextStyleConverter
from mdap_u2c.utils.generator_utils import GeneratorUtils


class RichTextResolver:
    """富文本解析器"""

    @classmethod
    def create_component(
            cls,
            node: Dict[str, Any],
            layout: dsl_model.Layout,
            style: dsl_model.Style,
            component_id: str,
            figma_info: dsl_model.FigmaInfo,
            parent_component: Optional[dsl_model.AbstractComponent] = None,
    ) -> dsl_model.ContainerComponent:
        component = dsl_model.ContainerComponent.create_rich_container(
            node=node,
            layout=layout,
            style=TextStyleConverter.get_style_with_node(style, node, parent_component),
            component_id=component_id,
            figma_info=figma_info,
            parent_component=parent_component,
        )

        component.children = cls._resolve_rich_text(node, component_id)
        return component

    @classmethod
    def _resolve_rich_text(cls, node: Dict[str, Any], parent_component_id: str) -> List[dsl_model.AbstractComponent]:
        characters = node.get("characters", "")
        if not characters:
            return []

        line_types = node.get("lineTypes", [])
        line_indentations = node.get("lineIndentations", [])
        if line_types and any(lt != "NONE" for lt in line_types):
            return cls._resolve_rich_text_with_lists(node, parent_component_id, line_types, line_indentations)
        
        # 普通文本解析
        return cls._resolve_plain_text(node, parent_component_id)

    @classmethod
    def _resolve_plain_text(cls, node: Dict[str, Any], parent_component_id: str) -> List[dsl_model.AbstractComponent]:
        """解析普通文本"""
        components = []
        characters = node.get("characters", "")
        default_style = node.get("style", {})
        style_override_table = node.get("styleOverrideTable", {})
        character_style_overrides = node.get("characterStyleOverrides", [])

        current_text = ""
        current_style_id = None
        current_merged_style = None
        generator = GeneratorUtils.get_instance()
        
        for i, char in enumerate(characters):
            # 获取当前字符的样式ID（0表示使用默认样式）
            style_id = character_style_overrides[i] if i < len(character_style_overrides) else 0
            
            # 处理换行符
            if char == '\n':
                if current_text:
                    components.append(cls._create_text_component(current_text, current_merged_style or default_style, generator, parent_component_id))
                    current_text = ""
                
                components.append(dsl_model.BrComponent(
                    id=generator.generate_component_id(),
                    parent_id=parent_component_id,
                    style=dsl_model.Style(),
                    props=dsl_model.BrComponentProps()
                ))
                continue

            if style_id != current_style_id:
                if current_text:
                    components.append(cls._create_text_component(current_text, current_merged_style or default_style, generator, parent_component_id))
                    current_text = ""
                
                current_style_id = style_id
                current_merged_style = cls._merge_style(default_style, style_override_table, style_id)

            current_text += char
        
        # 处理最后的文本段
        if current_text:
            components.append(cls._create_text_component(current_text, current_merged_style or default_style, generator, parent_component_id))
        
        return components

    @classmethod
    def _resolve_rich_text_with_lists(
        cls,
        node: Dict[str, Any],
        parent_component_id: str,
        line_types: List[str],
        line_indentations: List[int]
    ) -> List[dsl_model.AbstractComponent]:
        """解析包含列表的富文本"""
        characters = node.get("characters", "")
        default_style = node.get("style", {})
        style_override_table = node.get("styleOverrideTable", {})
        character_style_overrides = node.get("characterStyleOverrides", [])
        generator = GeneratorUtils.get_instance()
        
        # 按行分割文本
        lines = cls._split_into_lines(characters, line_types, line_indentations)
        
        # 解析每行的内容
        parsed_lines = []
        for line_info in lines:
            line_text = line_info["text"]
            line_type = line_info["line_type"]
            indentation = line_info["indentation"]
            
            # 解析行内的文本组件（处理样式变化）
            line_components = cls._parse_line_text(
                line_text,
                line_info["start_index"],
                default_style,
                style_override_table,
                character_style_overrides,
                generator,
                parent_component_id
            )
            
            parsed_lines.append({
                "components": line_components,
                "line_type": line_type,
                "indentation": indentation,
                "text": line_text
            })
        
        # 构建组件列表（处理列表分组和嵌套）
        return cls._build_components_from_lines(parsed_lines, generator, parent_component_id)

    @classmethod
    def _split_into_lines(
        cls,
        characters: str,
        line_types: List[str],
        line_indentations: List[int]
    ) -> List[Dict[str, Any]]:
        """将文本按行分割，并记录每行的类型和缩进"""
        lines = []
        char_index = 0
        
        # 按换行符分割
        text_lines = characters.split('\n')
        
        for line_idx, text_line in enumerate(text_lines):
            line_type = line_types[line_idx] if line_idx < len(line_types) else "NONE"
            indentation = line_indentations[line_idx] if line_idx < len(line_indentations) else 0
            
            lines.append({
                "text": text_line,
                "line_type": line_type,
                "indentation": indentation,
                "start_index": char_index
            })
            
            char_index += len(text_line) + 1  # +1 for newline
        
        return lines

    @classmethod
    def _parse_line_text(
        cls,
        line_text: str,
        start_char_index: int,
        default_style: Dict[str, Any],
        style_override_table: Dict[str, Any],
        character_style_overrides: List[int],
        generator: GeneratorUtils,
        parent_component_id: str
    ) -> List[dsl_model.AbstractComponent]:
        """解析单行文本，处理样式变化"""
        if not line_text:
            return []
        
        components = []
        current_text = ""
        current_style_id = None
        current_merged_style = None
        
        for i, char in enumerate(line_text):
            char_index = start_char_index + i
            style_id = character_style_overrides[char_index] if char_index < len(character_style_overrides) else 0
            
            if style_id != current_style_id:
                if current_text:
                    components.append(cls._create_text_component(
                        current_text,
                        current_merged_style or default_style,
                        generator,
                        parent_component_id
                    ))
                    current_text = ""
                
                current_style_id = style_id
                current_merged_style = cls._merge_style(default_style, style_override_table, style_id)
            
            current_text += char
        
        # 处理最后的文本段
        if current_text:
            components.append(cls._create_text_component(
                current_text,
                current_merged_style or default_style,
                generator,
                parent_component_id
            ))
        
        return components

    @classmethod
    def _build_components_from_lines(
        cls,
        parsed_lines: List[Dict[str, Any]],
        generator: GeneratorUtils,
        parent_component_id: str
    ) -> List[dsl_model.AbstractComponent]:
        """从解析后的行构建组件列表，处理列表分组和嵌套"""
        components = []
        i = 0
        
        while i < len(parsed_lines):
            line = parsed_lines[i]
            line_type = line["line_type"]
            
            if line_type == "NONE":
                # 普通文本行，直接添加组件
                components.extend(line["components"])
                # 如果不是最后一行，添加换行
                if i < len(parsed_lines) - 1:
                    components.append(dsl_model.BrComponent(
                        id=generator.generate_component_id(),
                        parent_id=parent_component_id,
                        style=dsl_model.Style(),
                        props=dsl_model.BrComponentProps()
                    ))
                i += 1
            else:
                # 列表行，收集所有连续的相同类型的列表行（不管缩进级别）
                list_type = "ordered" if line_type == "ORDERED" else "unordered"
                list_lines = []
                
                # 收集所有连续的相同类型的列表行（包括不同缩进级别）
                while i < len(parsed_lines):
                    current_line = parsed_lines[i]
                    if current_line["line_type"] == line_type:
                        list_lines.append(current_line)
                        i += 1
                    else:
                        break
                
                # 构建列表组件（包含所有嵌套层级）
                list_component = cls._build_list_component(
                    list_lines,
                    list_type,
                    generator,
                    parent_component_id
                )
                components.append(list_component)
        
        return components

    @classmethod
    def _build_list_component(
        cls,
        list_lines: List[Dict[str, Any]],
        list_type: str,
        generator: GeneratorUtils,
        parent_component_id: str
    ) -> dsl_model.AbstractComponent:
        """
        构建列表组件（扁平化结构，通过level属性表示嵌套深度）
        
        这种方式更简单，符合HTML列表结构：
        - 一个完整的列表组件包含所有列表项
        - 每个列表项通过level属性表示嵌套深度
        - 不需要嵌套的ListComponent
        """
        # 创建列表组件
        if list_type == "ordered":
            list_comp = dsl_model.ListComponent.create_ordered_list(
                component_id=generator.generate_component_id(),
                parent_id=parent_component_id
            )
        else:
            list_comp = dsl_model.ListComponent.create_unordered_list(
                component_id=generator.generate_component_id(),
                parent_id=parent_component_id
            )
        
        # 找到最小缩进级别（作为基准）
        min_indentation = min(line["indentation"] for line in list_lines) if list_lines else 0
        
        # 将所有列表行转换为列表项，使用level属性表示嵌套深度
        for line in list_lines:
            # 计算相对缩进级别（相对于最小缩进）
            relative_level = line["indentation"] - min_indentation
            
            # 创建列表项
            list_item = dsl_model.ListItemComponent.create(
                component_id=generator.generate_component_id(),
                parent_id=list_comp.id,
                level=relative_level
            )
            
            # 添加行内容到列表项
            list_item.children.extend(line["components"])
            
            list_comp.children.append(list_item)
        
        return list_comp

    @classmethod
    def _merge_style(cls, default_style: Dict[str, Any], style_override_table: Dict[str, Any], style_id: int) -> Dict[str, Any]:
        """
        合并默认样式和覆盖样式
        
        Args:
            default_style: 默认样式
            style_override_table: 样式覆盖表
            style_id: 样式ID（0表示使用默认样式）
            
        Returns:
            合并后的样式字典
        """
        if style_id == 0 or str(style_id) not in style_override_table:
            return default_style.copy()
        
        # 从默认样式开始
        merged = default_style.copy()
        # 应用覆盖样式
        override = style_override_table[str(style_id)]
        merged.update(override)
        
        return merged
    
    @classmethod
    def _create_text_component(
        cls,
        text: str,
        figma_style: Dict[str, Any],
        generator: GeneratorUtils,
        parent_component_id: str
    ) -> dsl_model.TextComponent:
        # 构建DSL Style对象
        return dsl_model.TextComponent(
            id=generator.generate_component_id(),
            parent_id=parent_component_id,
            style=TextStyleConverter.get_style_with_style(dsl_model.Style(), figma_style),
            props=dsl_model.TextComponentProps(text=text)
        )
