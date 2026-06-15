import logging
import time
from typing import Optional, Dict, Any, Callable, List
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    RequestException,
    Timeout,
    ConnectionError,
    HTTPError,
    TooManyRedirects,
)
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ========== 自定义异常 ==========

class HttpClientError(Exception):
    """HTTP 客户端基础异常"""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[requests.Response] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class HttpTimeoutError(HttpClientError):
    """请求超时异常"""
    pass


class HttpConnectionError(HttpClientError):
    """连接错误异常"""
    pass


class HttpServerError(HttpClientError):
    """服务器错误异常 (5xx)"""
    pass


class HttpClientRequestError(HttpClientError):
    """客户端请求错误异常 (4xx)"""
    pass


# ========== HTTP 客户端 ==========
class HttpUtils:
    def __init__(self,
                 base_url: Optional[str] = None,
                 timeout: int = 30,
                 retry_times: int = 3,
                 retry_backoff_factor: float = 0.3,
                 headers: Optional[Dict[str, str]] = None,
                 verify_ssl: bool = True,
                 pool_connections: int = 10,
                 pool_maxsize: int = 10):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # 创建 Session（支持连接池）
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)

        # 配置重试策略
        retry_strategy = Retry(
            total=retry_times,
            backoff_factor=retry_backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],  # 对这些状态码进行重试
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"],
        )

        # 配置连接池适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 请求/响应拦截器
        self._request_interceptors: List[Callable] = []
        self._response_interceptors: List[Callable] = []

    def _build_url(self, url: str) -> str:
        """构建完整 URL"""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if self.base_url:
            return urljoin(self.base_url + "/", url.lstrip("/"))
        return url

    def _apply_request_interceptors(self, **kwargs) -> Dict[str, Any]:
        """应用请求拦截器"""
        for interceptor in self._request_interceptors:
            kwargs = interceptor(**kwargs)
        return kwargs

    def _apply_response_interceptors(self, response: requests.Response) -> requests.Response:
        """应用响应拦截器"""
        for interceptor in self._response_interceptors:
            response = interceptor(response)
        return response


    def _handle_error(self, e: Exception, url: str, method: str) -> None:
        """统一错误处理"""
        if isinstance(e, Timeout):
            raise HttpTimeoutError(f"Request timeout: {method} {url}") from e

        elif isinstance(e, ConnectionError):
            raise HttpConnectionError(f"Connection error: {method} {url} - {str(e)}") from e

        elif isinstance(e, HTTPError):
            response = e.response
            status_code = response.status_code if response else None

            if status_code and 500 <= status_code < 600:
                raise HttpServerError(f"Server error ({status_code}): {method} {url}", status_code=status_code,
                                      response=response) from e

            elif status_code and 400 <= status_code < 500:
                raise HttpClientRequestError(f"Client error ({status_code}): {method} {url}", status_code=status_code,
                                             response=response) from e

            else:
                raise HttpClientError(f"HTTP error ({status_code}): {method} {url}", status_code=status_code,
                                      response=response) from e

        elif isinstance(e, TooManyRedirects):
            raise HttpClientError(f"Too many redirects: {method} {url}") from e

        else:
            raise HttpClientError(f"Request failed: {method} {url} - {str(e)}") from e

    def request(self,
                method: str,
                url: str,
                params: Optional[Dict[str, Any]] = None,
                data: Optional[Any] = None,
                json: Optional[Dict[str, Any]] = None,
                headers: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None,
                **kwargs) -> requests.Response:
        full_url = self._build_url(url)
        timeout = timeout or self.timeout

        # 合并请求头
        merged_headers = self.session.headers.copy()
        if headers:
            merged_headers.update(headers)

        # 准备请求参数
        request_kwargs = {
            "method": method,
            "url": full_url,
            "params": params,
            "data": data,
            "json": json,
            "headers": merged_headers,
            "timeout": timeout,
            "verify": self.verify_ssl,
            **kwargs
        }

        request_kwargs = self._apply_request_interceptors(**request_kwargs)
        start_time = time.time()
        try:
            response = self.session.request(**request_kwargs)
            elapsed = time.time() - start_time
            logger.info(
                f"HTTP {method.upper()} {full_url} - "
                f"Status: {response.status_code} - "
                f"Time: {elapsed:.3f}s"
            )

            response.raise_for_status()
            return self._apply_response_interceptors(response)

        except RequestException as e:
            elapsed = time.time() - start_time
            logger.error(
                f"HTTP {method.upper()} {full_url} failed - "
                f"Time: {elapsed:.3f}s - Error: {str(e)}",
                exc_info=True
            )
            self._handle_error(e, full_url, method.upper())

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        return self.request("GET", url, params=params, **kwargs)

    def post(self, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None,
             **kwargs) -> requests.Response:
        return self.request("POST", url, data=data, json=json, **kwargs)

    def download(self, url: str, save_path: str, chunk_size: int = 8192, **kwargs) -> None:
        full_url = self._build_url(url)
        logger.info(f"Downloading file from {full_url} to {save_path}")
        try:
            response = self.get(url, stream=True, **kwargs)
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
            logger.info(f"File downloaded successfully: {save_path}")
        except Exception as e:
            logger.error(f"Failed to download file: {str(e)}", exc_info=True)
            raise

    def close(self):
        if hasattr(self, 'session'):
            self.session.close()
            try:
                logger.debug("HTTP client session closed")
            except (ImportError, AttributeError):
                pass

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __del__(self):
        try:
            if hasattr(self, 'session'):
                self.session.close()
        except Exception:
            pass


# ========== 全局单例实例 ==========
_default_client: Optional[HttpUtils] = None


