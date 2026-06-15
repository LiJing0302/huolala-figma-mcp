from typing import Dict, Any, Set

from mdap_u2c.enums import figma_enum
from mdap_u2c.figma.check.check_utils import FigmaCheckUtils


class ImageMergeCheck:
    _ICON_MAX_WIDTH = 80        # 图标检测最大宽度和高度
    _ICON_MAX_SIZE = 120         # 装饰性元素最大尺寸（比图标稍大）
    
    # 可能包含图标的容器节点类型
    _ICON_CONTAINER_TYPES: Set[str] = {
        figma_enum.FigmaNodeType.FrameNode,
        figma_enum.FigmaNodeType.GroupNode,
        figma_enum.FigmaNodeType.InstanceNode,
        figma_enum.FigmaNodeType.ComponentNode,
        figma_enum.FigmaNodeType.BooleanOperationNode,
    }
    
    # 可能是图标的节点类型
    _ICON_CANDIDATE_TYPES: Set[str] = {
        figma_enum.FigmaNodeType.VectorNode,
        figma_enum.FigmaNodeType.BooleanOperationNode,
        figma_enum.FigmaNodeType.EllipseNode,
        figma_enum.FigmaNodeType.RectangleNode,
        figma_enum.FigmaNodeType.RegularPolygonNode,
        figma_enum.FigmaNodeType.StarNode,
    }

    @classmethod
    def check(cls, node: Dict[str, Any]) -> bool:
        """
        检测节点是否满足图片导出，主要有以下逻辑

        1. 如果节点本身就是text类型，则不导出图片，导出text
        2. 如果节点有图片填充，则导出图片
        3. 如果节点有发生非(0/90/180/-90/-180/-0)这种特殊角度的旋转，也需要导出图片
        4. 判断节点的名称是否包含icon，并且节点的宽度和高度都小于等于阈值，如果是导出图片
        5. 判断该节点及子节点，以及子节点的子节点类型
            5.1. 如果有text类型，则停止判断，不导出图片
            5.2. 如果整个子树都没有text类型，且节点尺寸较小，可能是图标/装饰元素，导出图片
            5.3. 如果节点类型是图标候选类型（VectorNode、BooleanOperationNode等）且尺寸小，导出图片

        :param node: Figma 节点
        :return: True 表示应该导出为图片，False 表示不应该导出为图片
        """
        node_type = node.get("type", "")

        # 4. 检查名称是否包含 icon 且尺寸合适
        if cls._check_icon_by_name(node):
            return True

        # 5. 递归检查子节点
        # 5.0. 特殊场景：当节点只有两个子节点时（一个文本节点和一个其他类型节点），
        #      检查这个其他类型节点是否应该导出为图片
        children = node.get("children", [])
        if children and len(children) == 2:
            # 检查是否是一个文本节点 + 一个其他类型节点的组合
            text_child = None
            other_child = None
            
            for child in children:
                if child.get("type") == figma_enum.FigmaNodeType.TextNode:
                    text_child = child
                else:
                    other_child = child
            
            # 如果确实是一个文本节点 + 一个其他类型节点
            if text_child and other_child:
                # 检查这个其他类型节点是否应该导出为图片
                if cls._should_export_sibling_node_as_image(other_child):
                    # 如果应该导出为图片，当前节点不应该导出为图片
                    # （因为子节点会分别导出：文本节点导出为文本，其他节点导出为图片）
                    return False
        
        # 5.1. 如果子树中有文本节点，不导出为图片
        if cls._has_text_node_in_subtree(node):
            return False

        # 5.2. 检查节点尺寸和类型，判断是否为图标/装饰元素
        absolute_render_bounds = node.get("absoluteRenderBounds")
        if absolute_render_bounds is None:
            return False

        width = absolute_render_bounds.get("width", 0)
        height = absolute_render_bounds.get("height", 0)

        # 如果节点尺寸过大，不太可能是图标
        if width > cls._ICON_MAX_SIZE or height > cls._ICON_MAX_SIZE:
            return False

        # 4.5. 检查节点及其所有子节点是否都是 VectorNode 类型
        # 如果节点及其所有子节点（递归）都是 VectorNode，存在过度合并 case，故不单独处理

        # 5.3. 如果节点类型是图标候选类型，且尺寸较小，导出为图片
        # 注意：排除矩形节点，因为矩形通常不是图标
        if node_type in cls._ICON_CANDIDATE_TYPES:
            # 排除矩形节点（矩形通常不是图标，除非有特殊标识）
            if node_type == figma_enum.FigmaNodeType.RectangleNode:
                # 矩形节点需要特殊判断，比如名称包含 icon
                if not cls._check_icon_by_name(node):
                    # 如果不是通过名称识别的图标，不导出为图片
                    pass
                else:
                    # 如果名称包含 icon，且尺寸小，可能是图标
                    if width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                        return True
            else:
                # 非矩形节点，尺寸小就是图标
                if width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                    return True
        
        # 5.4. 如果是容器类型节点，且整个子树都没有文本，尺寸较小，可能是图标容器
        if node_type in cls._ICON_CONTAINER_TYPES:
            # 检查是否有子节点
            children = node.get("children", [])
            if children:
                # 关键：检查直接子节点中，有多少个可能独立导出为图标的节点
                # 如果直接子节点中有多个独立图标，不应该合并父节点，应该让子节点分别导出
                independent_icon_count = cls._count_independent_icon_children(children)
                
                # 如果直接子节点中有多个（>=2）独立图标，不导出父节点，让子节点分别处理
                if independent_icon_count >= 2:
                    return False
                
                # 如果尺寸较小，且子树中没有文本，可能是图标
                if width <= cls._ICON_MAX_SIZE and height <= cls._ICON_MAX_SIZE:
                    # 如果只有一个独立图标子节点，或者没有独立图标子节点，可以考虑导出父节点
                    # 进一步检查：如果子树中主要是矢量节点或布尔运算节点，更可能是图标
                    vector_or_boolean_count = sum(
                        1 for child in children 
                        if child.get("type") in (figma_enum.FigmaNodeType.VectorNode, 
                                                figma_enum.FigmaNodeType.BooleanOperationNode)
                    )
                    if vector_or_boolean_count > 0:
                        return True

        return False

    @classmethod
    def _check_icon(cls, node: Dict[str, Any]) -> bool:
        """icon检测（通过名称）"""
        name = node.get("name", "").lower()
        if "icon" not in name:
            return False

        absolute_render_bounds = node.get("absoluteRenderBounds")
        if absolute_render_bounds is None:
            return False

        width = absolute_render_bounds.get("width", 0)
        height = absolute_render_bounds.get("height", 0)
        
        if width > cls._ICON_MAX_WIDTH or height > cls._ICON_MAX_WIDTH:
            return False

        return True

    @classmethod
    def _check_icon_by_name(cls, node: Dict[str, Any]) -> bool:
        """通过名称检测是否为图标"""
        return cls._check_icon(node)

    @classmethod
    def _has_text_node_in_subtree(cls, node: Dict[str, Any]) -> bool:
        """
        递归检查子树中是否有文本节点
        
        :param node: 要检查的节点
        :return: True 表示子树中有文本节点，False 表示没有
        """
        stack = [node]
        visited = set()
        
        while stack:
            current_node = stack.pop()
            node_id = current_node.get("id")
            
            # 避免循环引用
            if node_id and node_id in visited:
                continue
            if node_id:
                visited.add(node_id)
            
            current_type = current_node.get("type", "")
            
            # 检测到文本节点，返回 True
            if current_type == figma_enum.FigmaNodeType.TextNode:
                return True
            
            # 添加子节点到栈中
            children = current_node.get("children", [])
            for child_node in children:
                stack.append(child_node)
        
        return False

    @classmethod
    def _count_independent_icon_children(cls, children: list) -> int:
        """
        统计直接子节点中可能独立导出为图标的节点数量
        
        判断标准：
        1. 节点类型是图标候选类型（VectorNode、BooleanOperationNode等）且尺寸小
        2. 节点名称包含 icon
        3. 节点是 GroupNode/FrameNode 等容器类型，但尺寸小且可能包含图标
        
        :param children: 子节点列表
        :return: 可能独立导出的图标数量
        """
        count = 0
        
        for child in children:
            child_type = child.get("type", "")
            
            # 跳过文本节点
            if child_type == figma_enum.FigmaNodeType.TextNode:
                continue
            
            # 检查是否有图片填充或非垂直旋转（这些肯定要导出）
            if FigmaCheckUtils.has_image_fill(child):
                count += 1
                continue
            
            if FigmaCheckUtils.is_vertical_horizontal_rotation(child.get("rotation", None)) is False:
                count += 1
                continue
            
            # 检查名称是否包含 icon
            if cls._check_icon_by_name(child):
                count += 1
                continue
            
            # 检查节点尺寸和类型
            absolute_render_bounds = child.get("absoluteRenderBounds")
            if absolute_render_bounds is None:
                continue
            
            width = absolute_render_bounds.get("width", 0)
            height = absolute_render_bounds.get("height", 0)
            
            # 如果节点类型是图标候选类型，且尺寸较小，可能是独立图标
            # 注意：排除矩形节点（除非名称包含 icon），因为矩形通常不是图标
            if child_type in cls._ICON_CANDIDATE_TYPES:
                # 排除矩形节点（除非通过名称识别为图标）
                if child_type == figma_enum.FigmaNodeType.RectangleNode:
                    # 矩形节点需要特殊判断
                    if cls._check_icon_by_name(child):
                        # 如果名称包含 icon，且尺寸小，可能是图标
                        if width > 0 and height > 0 and width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                            count += 1
                            continue
                else:
                    # 非矩形节点，尺寸小就是图标
                    if width > 0 and height > 0 and width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                        count += 1
                        continue
            
            # 如果是容器类型（Group、Frame等），且尺寸较小，检查是否可能是图标容器
            if child_type in cls._ICON_CONTAINER_TYPES:
                # 检查子节点的子节点，如果主要是矢量节点或布尔运算节点，可能是图标
                child_children = child.get("children", [])
                if child_children:
                    # 检查是否有文本节点
                    has_text = False
                    vector_or_boolean_count = 0
                    for grandchild in child_children:
                        if grandchild.get("type") == figma_enum.FigmaNodeType.TextNode:
                            has_text = True
                            break
                        if grandchild.get("type") in (figma_enum.FigmaNodeType.VectorNode, 
                                                      figma_enum.FigmaNodeType.BooleanOperationNode):
                            vector_or_boolean_count += 1
                    
                    # 如果没有文本节点，且有矢量或布尔运算节点，且尺寸小，可能是独立图标
                    if not has_text and vector_or_boolean_count > 0:
                        if width > 0 and height > 0 and width <= cls._ICON_MAX_SIZE and height <= cls._ICON_MAX_SIZE:
                            count += 1
                            continue
                    # 如果尺寸很小，且没有文本，也可能是独立图标
                    if not has_text and width > 0 and height > 0 and width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                        count += 1
                        continue
        
        return count

    @classmethod
    def _is_all_vector_nodes(cls, node: Dict[str, Any]) -> bool:
        """
        递归检查节点及其所有子节点是否都是 VectorNode 类型
        
        注意：VectorNode 本身不能包含子节点，只有容器类型节点才能包含子节点
        容器类型包括：InstanceNode/FrameNode/ComponentNode/GroupNode/ComponentSetNode/BooleanOperationNode
        
        :param node: 要检查的节点
        :return: True 表示节点及其所有子节点（递归）都是 VectorNode，False 表示不是
        """
        node_type = node.get("type", "")
        
        # 如果当前节点是 VectorNode，返回 True（VectorNode 是叶子节点，不能包含子节点）
        if node_type == figma_enum.FigmaNodeType.VectorNode:
            return True
        
        # 如果当前节点不是容器类型，返回 False
        # 容器类型：InstanceNode/FrameNode/ComponentNode/GroupNode/ComponentSetNode/BooleanOperationNode
        container_types = {
            figma_enum.FigmaNodeType.InstanceNode,
            figma_enum.FigmaNodeType.FrameNode,
            figma_enum.FigmaNodeType.ComponentNode,
            figma_enum.FigmaNodeType.GroupNode,
            figma_enum.FigmaNodeType.ComponentSetNode,
            figma_enum.FigmaNodeType.BooleanOperationNode,
        }
        
        if node_type not in container_types:
            return False
        
        # 检查所有子节点
        children = node.get("children", [])
        if not children:
            # 容器节点但没有子节点，返回 False（至少需要一个 VectorNode 子节点）
            return False
        
        # 递归检查所有子节点，必须全部是 VectorNode
        for child in children:
            if not cls._is_all_vector_nodes(child):
                return False
        
        # 所有子节点（递归）都是 VectorNode，返回 True
        return True

    @classmethod
    def _should_export_sibling_node_as_image(cls, node: Dict[str, Any]) -> bool:
        """
        判断与文本节点同级的其他类型节点是否应该导出为图片
        
        判断标准：
        1. 节点自身及所有子节点都没有 text 类型
        2. 节点的宽和高相等（通常是图标）
        3. 节点的宽和高都小于指定阈值
        
        :param node: 要检查的节点
        :return: True 表示应该导出为图片，False 表示不应该导出为图片
        """
        # 1. 检查节点自身及所有子节点是否都没有 text 类型
        if cls._has_text_node_in_subtree(node):
            return False
        
        # 2. 检查节点尺寸
        absolute_render_bounds = node.get("absoluteRenderBounds")
        if absolute_render_bounds is None:
            return False
        
        width = absolute_render_bounds.get("width", 0)
        height = absolute_render_bounds.get("height", 0)
        
        # 尺寸必须大于0
        if width <= 0 or height <= 0:
            return False
        
        # 3. 检查宽和高是否相等（通常是图标）
        # 允许一定的误差（比如 1px 的差异）
        width_height_diff = abs(width - height)
        is_square = width_height_diff <= 1.0
        
        # 4. 检查宽和高是否都小于指定阈值
        if width > cls._ICON_MAX_SIZE or height > cls._ICON_MAX_SIZE:
            return False
        
        # 5. 判断逻辑：
        #    - 如果宽高相等，且小于阈值，更可能是图标
        #    - 如果宽高不相等，但尺寸很小（小于 _ICON_MAX_WIDTH），也可能是图标
        if is_square:
            # 宽高相等，且小于阈值，是图标
            if width <= cls._ICON_MAX_SIZE and height <= cls._ICON_MAX_SIZE:
                # 进一步检查节点类型
                node_type = node.get("type", "")
                # 排除矩形节点（除非名称包含 icon）
                if node_type == figma_enum.FigmaNodeType.RectangleNode:
                    if cls._check_icon_by_name(node):
                        return True
                    return False
                # 其他类型，宽高相等且小于阈值，认为是图标
                return True
        else:
            # 宽高不相等，但尺寸很小，也可能是图标（比如矩形图标）
            if width <= cls._ICON_MAX_WIDTH and height <= cls._ICON_MAX_WIDTH:
                # 进一步检查节点类型
                node_type = node.get("type", "")
                # 排除矩形节点（除非名称包含 icon）
                if node_type == figma_enum.FigmaNodeType.RectangleNode:
                    if cls._check_icon_by_name(node):
                        return True
                    return False
                # 其他类型，尺寸很小，认为是图标
                return True
        
        return False
