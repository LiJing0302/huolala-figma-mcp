"""
DSL 加工处理器
新增处理器步骤：
    1. 在 processors/components/ 下创建新的处理器文件
    2. 定义处理器类，继承 BaseProcessor
    3. 使用 @processor_registry.register_decorator() 装饰器注册
    4. 在本文件中添加一行: from . import your_processor

关键：
    导入模块会触发装饰器执行，从而自动注册处理器到 registry！
    不需要导出类，处理器会通过 registry 访问。
"""
# ============================================================================
# 导入所有处理器模块（触发装饰器注册）
# 添加新处理器时，只需在这里添加一行
# ============================================================================
from . import (
    load_design_image,
    ai_service,
    image_merge,
    dsl_to_tree,
    remove_redundancy_control,
    group_by_projection,
    redpoint_mark,
    re_calc_layout,
    remove_transparent,
    vlm_result_process
)
