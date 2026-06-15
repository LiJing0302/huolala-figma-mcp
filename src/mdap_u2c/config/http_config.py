"""HTTP 客户端 SSL 验证与超时统一配置。"""
from __future__ import annotations

import os
import platform
import ssl
from typing import Union

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_DEFAULT_TIMEOUT = 30


def _system_ca_bundle_candidates() -> list[str]:
    """按操作系统返回常见系统 CA 证书路径（按优先级）。"""
    system = platform.system()
    if system == "Darwin":
        return [
            "/etc/ssl/cert.pem",
            "/private/etc/ssl/cert.pem",
            "/opt/homebrew/etc/openssl@3/cert.pem",
            "/opt/homebrew/etc/ca-certificates/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
            "/usr/local/etc/openssl/cert.pem",
        ]
    if system == "Linux":
        return [
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/ssl/ca-bundle.pem",
            "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
        ]
    return []


def _first_existing_file(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def _resolve_ca_bundle(explicit: str | None = None) -> str | None:
    """解析 CA 证书路径。

    优先级：显式参数 > MDAP_CA_BUNDLE > REQUESTS_CA_BUNDLE > SSL_CERT_FILE
            > certifi > 操作系统默认路径。
    """
    if explicit:
        return explicit

    for env_key in ("MDAP_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        env_path = os.environ.get(env_key, "").strip()
        if env_path:
            return env_path

    try:
        import certifi

        return certifi.where()
    except ImportError:
        pass

    return _first_existing_file(_system_ca_bundle_candidates())


def get_ssl_verify() -> Union[bool, str]:
    """requests 的 verify 参数：True / False / CA bundle 路径。"""
    raw = os.environ.get("MDAP_SSL_VERIFY", "true").strip()
    lowered = raw.lower()
    if lowered in _TRUE_VALUES:
        return _resolve_ca_bundle() or True
    if lowered in _FALSE_VALUES:
        return False
    return raw


def get_http_timeout(default: int = _DEFAULT_TIMEOUT) -> int:
    raw = os.environ.get("MDAP_HTTP_TIMEOUT", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _build_ssl_context(ca_bundle: str | None = None) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    bundle = _resolve_ca_bundle(ca_bundle if isinstance(ca_bundle, str) else None)
    if bundle:
        ctx.load_verify_locations(bundle)
    return ctx


def get_aiohttp_ssl() -> Union[bool, ssl.SSLContext]:
    verify = get_ssl_verify()
    if verify is False:
        return False
    if isinstance(verify, str):
        return _build_ssl_context(verify)
    return _build_ssl_context()


def get_urllib_ssl_context() -> ssl.SSLContext | None:
    """urllib.request.urlopen 的 context 参数。"""
    verify = get_ssl_verify()
    if verify is False:
        return ssl._create_unverified_context()
    if isinstance(verify, str):
        return _build_ssl_context(verify)
    ca_bundle = _resolve_ca_bundle()
    if ca_bundle:
        return _build_ssl_context(ca_bundle)
    return None
