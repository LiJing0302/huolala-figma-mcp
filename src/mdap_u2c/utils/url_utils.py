import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)


class UrlUtils:
    """URL 工具类"""

    # Figma 文件键：路径 /file/{key}/、/design/{key}/、/proto/{key}/ 中的片段
    _FIGMA_FILE_KEY_PATH_RE = re.compile(
        r"/(?:file|design|proto)/([a-zA-Z0-9]+)(?:/|$)", re.IGNORECASE
    )


    @staticmethod
    def get_figma_param_by_url_throw_error(figma_url: str) -> (str, str):
        """
        从 Figma 设计稿 URL 中解析 file_key 与 node_id（会抛出异常）。

        - file_key：路径中 https://www.figma.com/file/{file_key}/... 或 design/proto 同位置片段
        - node_id：查询参数 node-id=...（Figma 常用连字符，解析后转为 API 所需的冒号形式）
        """
        if not figma_url or not str(figma_url).strip():
            raise TypeError("figma设计稿地址不能为空")
        parsed = urlparse(figma_url.strip())
        path = parsed.path or ""

        m = UrlUtils._FIGMA_FILE_KEY_PATH_RE.search(path)
        if not m:
            raise TypeError(
                f"无法从 figma URL 路径解析 file key，请使用含 /file/{{key}}/ 或 /design/{{key}}/ 的链接，url: {figma_url}"
            )
        file_key = m.group(1)

        qs = parse_qs(parsed.query)
        node_raw = None
        if qs.get("node-id"):
            node_raw = qs["node-id"][0]
        if not node_raw and parsed.fragment:
            frag_qs = parse_qs(parsed.fragment)
            if frag_qs.get("node-id"):
                node_raw = frag_qs["node-id"][0]
        if not node_raw:
            raise TypeError(
                f"无法从 figma URL 解析 node-id，请使用带 ?node-id= 的链接（选中画板/节点后复制链接），url: {figma_url}"
            )

        node_id = unquote(node_raw).replace("-", ":")
        if not file_key or not node_id:
            raise TypeError(f"无法解析 figma 地址, url: {figma_url}")

        return file_key, node_id
