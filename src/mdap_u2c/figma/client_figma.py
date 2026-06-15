import logging
import os
from typing import List, Dict, Any
from urllib.parse import urlencode

from mdap_u2c.utils.http_utils import HttpUtils
from mdap_u2c.core import SingletonClass

logger = logging.getLogger(__name__)


def get_figma_token() -> str:
    token = os.environ.get("MDAP_FIGMA_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "未配置 Figma API Token，请设置环境变量 MDAP_FIGMA_TOKEN。"
            "可在 Figma → Settings → Security → Personal access tokens 创建。"
        )
    return token


class FigmaClient(metaclass=SingletonClass):
    def __init__(self):
        self.client = HttpUtils(
            base_url="https://api.figma.com/v1",
            headers={"X-Figma-Token": get_figma_token()},
            pool_maxsize=30,
            retry_times= 1  # 仅重试 1 次，避免导图等请求等待过久
        )

    @staticmethod
    def get_instance():
        return FigmaClient()

    def get_nodes(self, file_key: str, node_id: str, depth: int = None) -> Dict[str, Any]:
        """
        获取节点信息
        :param file_key: 文件 key
        :param node_id: 节点 id
        :param depth: 节点深度，默认获取全部
        :return: 节点信息
        """
        params = {"ids": node_id}
        if depth is not None:
            params["depth"] = depth

        response = self.client.get(f"/files/{file_key}/nodes?{urlencode(params)}")
        if response is None:
            raise Exception("Get nodes error, response is None")

        if response.status_code != 200:
            raise Exception(f"Get nodes error, status: {response.status_code}, error: {response.text}")

        return response.json()


    def get_file_meta(self, file_key: str) -> dict:
        response = self.client.get(f"/files/{file_key}/meta")
        if response is None:
            raise Exception("Get file meta error, response is None")

        if response.status_code != 200:
            raise Exception(f"Get file meta error, status: {response.status_code}, error: {response.text}")

        return response.json()

    def get_image_fills(self, file_key: str) -> Dict[str, str]:
        """获取文件所有图片填充列表"""
        res_str = self.client.get(f"/files/{file_key}/images")
        res = res_str.json()
        error = res.get("error", False)
        status = res.get("status", 200)
        if error or status != 200:
            logger.error(f"Get file image fill list error, file_key: {file_key}, error: {res.get('err')}")
            return {}

        return res.get("meta", {}).get("images", {})

    def export_images(self, file_key: str, node_ids: List[str], scale: float = 1) -> dict:
        try:
            params = {
                "ids": ",".join(node_ids),
                "scale": scale,
                "format": "png",
                "use_absolute_bounds": "true"
            }
            images = self._request_images(file_key=file_key, params=params)
            failed_node_ids = []
            for node_id, image_url in images.items():
                if image_url is None:
                    failed_node_ids.append(node_id)

            if len(failed_node_ids) > 0:
                params["ids"] = ",".join(failed_node_ids)
                params["use_absolute_bounds"] = "false"
                failed_images = self._request_images(file_key=file_key, params=params)
                for node_id, image_url in failed_images.items():
                    if image_url and node_id in images:
                        images[node_id] = image_url

            return images
        except Exception as e:
            logger.error(f"[figma_client]node is to export image error, file_key: {file_key}, node_ids: {node_ids}, error: {str(e)}")
            return {}

    def _request_images(self, file_key: str, params: Dict[str, Any]) -> dict:
        query_str = urlencode(params)
        ids_str = params.get("ids", "")
        ids_count = len([x for x in ids_str.split(",") if x.strip()]) if isinstance(ids_str, str) else 0
        # ids 个数 > 1 时不重试，且超时 15 秒
        timeout = 15
        client = self.client
        if ids_count > 1:
            client = HttpUtils(
                base_url=self.client.base_url,
                headers=dict(self.client.session.headers),
                retry_times=0,
                timeout=timeout,
            )
        try:
            res = client.get(f"/images/{file_key}?{query_str}", timeout=timeout)
            response = res.json()
            is_err = response.get("err")
            if is_err:
                logger.error(f"[figma_client]node is to export image error, file_key: {file_key}, params: {query_str}, error: {is_err}")
                return {}

            return response.get("images", {})
        except Exception as e:
            logger.error(f"[figma_client]node is to export image error, file_key: {file_key}, params: {query_str}, error: {str(e)}")
            return {}
