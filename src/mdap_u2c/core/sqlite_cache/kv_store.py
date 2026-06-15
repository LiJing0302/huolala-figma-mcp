"""
本地 SQLite KV 缓存，接口对齐原 Redis 客户端常用方法（get / set / ttl）。
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# 可通过环境变量覆盖，默认 ~/.mdap_u2c/kv_cache.sqlite
_DEFAULT_DB_PATH = Path.home() / ".mdap_u2c" / "kv_cache.sqlite"


class SqliteKVCache:
    """线程安全的本地 SQLite 缓存，语义接近 redis-py（decode_responses=True）。"""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        path = Path(db_path or os.environ.get("MDAP_U2C_SQLITE_CACHE", str(_DEFAULT_DB_PATH)))
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_cache (
                k TEXT PRIMARY KEY NOT NULL,
                v TEXT NOT NULL,
                expires_at REAL
            )
            """
        )
        self._conn.commit()

    def _maybe_expire(self, key: str, expires_at: Optional[float]) -> bool:
        """若已过期则删除并返回 True（表示条目无效）。"""
        if expires_at is None:
            return False
        if time.time() > expires_at:
            self._conn.execute("DELETE FROM kv_cache WHERE k = ?", (key,))
            self._conn.commit()
            return True
        return False

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT v, expires_at FROM kv_cache WHERE k = ?", (key,)
            )
            row = cur.fetchone()
            if not row:
                return None
            v, exp = row[0], row[1]
            if self._maybe_expire(key, exp):
                return None
            return v

    def set(
        self,
        name: Optional[str] = None,
        value: Optional[Any] = None,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        **kwargs: Any,
    ) -> bool:
        """写入缓存。对齐 redis set(name, value, ex=秒, px=毫秒)。"""
        if name is None or value is None:
            raise TypeError("set() requires name and value")

        if isinstance(value, bytes):
            val_str = value.decode("utf-8", errors="replace")
        else:
            val_str = value if isinstance(value, str) else str(value)

        expires_at: Optional[float] = None
        if px is not None:
            expires_at = time.time() + px / 1000.0
        elif ex is not None:
            expires_at = time.time() + float(ex)

        with self._lock:
            self._conn.execute(
                "INSERT INTO kv_cache(k, v, expires_at) VALUES(?,?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v, expires_at=excluded.expires_at",
                (name, val_str, expires_at),
            )
            self._conn.commit()
        return True

    def ttl(self, key: str) -> int:
        """返回剩余秒数；无 key 为 -2；永不过期为 -1（对齐 Redis）。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT expires_at FROM kv_cache WHERE k = ?", (key,)
            )
            row = cur.fetchone()
            if not row:
                return -2
            exp = row[0]
            if exp is None:
                return -1
            remaining = int(exp - time.time())
            if remaining <= 0:
                self._conn.execute("DELETE FROM kv_cache WHERE k = ?", (key,))
                self._conn.commit()
                return -2
            return remaining


_instance: Optional[SqliteKVCache] = None
_instance_lock = threading.Lock()


def get_sqlite_kv_cache() -> SqliteKVCache:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SqliteKVCache()
                logger.info("本地 SQLite 缓存已初始化: %s", _instance._db_path)
    return _instance
