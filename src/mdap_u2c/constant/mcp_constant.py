class McpConstant:
    DEFAULT_USER = {
        "name_en": "anonymous",
        "name_cn": "anonymous",
        "client_id": "default_client",
    }

    MCP_INSTRUCTIONS = """
    该服务提供 Figma 设计稿转代码的能力。
    调用工具 figma_to_code_package 后会得到一个 ZIP 包地址，
    该 ZIP 包中包含一个 index.html 文件，该文件是基于规则转换的 Web 代码，
    客户端拿到该代码后，需要利用 LLM 对其进行目标代码转换。
    """
