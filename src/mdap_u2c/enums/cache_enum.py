from enum import Enum


class CacheKey(Enum):
    """ 缓存Key定义，所有缓存相关key必须在这里统一定义，并且必须添加前缀(mdap_u2c) """
    FIGMA_NODE_DATA = "mdap_u2c:figma_node:{file_key}:{node_id}"       # figma节点数据
    VLM_API_RESULT = "mdap_u2c:vlm_result:{image_md5}"                 # VLM API调用结果缓存
