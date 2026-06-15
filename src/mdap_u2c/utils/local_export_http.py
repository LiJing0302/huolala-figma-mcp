"""
ZIP 导出目录的本地只读 HTTP 服务，用于返回可下载的 http:// 地址（替代 OSS CDN）。
"""
from __future__ import annotations

import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

logger = logging.getLogger(__name__)

_server: ThreadingHTTPServer | None = None
_server_lock = threading.Lock()
_started = False


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def get_export_dir() -> str:
    """导出 ZIP 的根目录，与 MDAP_EXPORT_LOCAL_DIR 或默认 runtime/exports 一致。"""
    custom = os.environ.get("MDAP_EXPORT_LOCAL_DIR", "").strip()
    if custom:
        return os.path.abspath(custom)
    from mdap_u2c.config import path_config

    return os.path.abspath(os.path.join(path_config.PathConfig.get_runtime_dir(), "exports"))


def get_http_host() -> str:
    return os.environ.get("MDAP_EXPORT_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"


def get_http_port() -> int:
    return int(os.environ.get("MDAP_EXPORT_HTTP_PORT", "18081"))


def _handler_class(directory: str):
    class _ExportHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt: str, *args) -> None:
            logger.debug("export-http %s - " + fmt, self.address_string(), *args)

    return _ExportHandler


def ensure_local_export_server() -> None:
    """在首次导出时启动后台线程中的 HTTP 服务（幂等）。"""
    global _server, _started
    with _server_lock:
        if _started:
            return
        directory = get_export_dir()
        os.makedirs(directory, exist_ok=True)
        host = get_http_host()
        port = get_http_port()
        handler = _handler_class(directory)
        try:
            _server = _ReusableThreadingHTTPServer((host, port), handler)
        except OSError as e:
            raise RuntimeError(
                f"无法启动本地导出 HTTP 服务（{host}:{port}）：{e}。"
                f"请更换端口：环境变量 MDAP_EXPORT_HTTP_PORT"
            ) from e
        thread = threading.Thread(
            target=_server.serve_forever,
            name="mdap-local-export-http",
            daemon=True,
        )
        thread.start()
        _started = True
        logger.info(
            "本地导出 HTTP 已监听 http://%s:%s/ （根目录: %s）",
            host,
            port,
            directory,
        )


def build_download_url(filename: str) -> str:
    """返回形如 http://127.0.0.1:18081/xxx.zip 的下载地址。"""
    ensure_local_export_server()
    host = get_http_host()
    port = get_http_port()
    safe = quote(filename, safe="")
    return f"http://{host}:{port}/{safe}"
