"""进程内 TTL 字符串缓存（替代原 Redis / SQLite KV 调用）。"""
from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()
_data: dict[str, tuple[Optional[float], str]] = {}


def get(key: str) -> Optional[str]:
    with _lock:
        if key not in _data:
            return None
        expires_at, val = _data[key]
        if expires_at is not None and time.time() > expires_at:
            del _data[key]
            return None
        return val


def put(key: str, value: str, ex: Optional[int] = None) -> None:
    """写入缓存；ex 为秒级 TTL，None 表示不过期。"""
    with _lock:
        expires_at = time.time() + ex if ex is not None else None
        _data[key] = (expires_at, value)


def ttl(key: str) -> int:
    """对齐 Redis：不存在 -2，永不过期 -1，否则剩余秒数。"""
    with _lock:
        if key not in _data:
            return -2
        exp, _ = _data[key]
        if exp is None:
            return -1
        remaining = int(exp - time.time())
        if remaining <= 0:
            del _data[key]
            return -2
        return remaining
