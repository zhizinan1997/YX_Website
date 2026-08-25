"""跨进程持久化限流存储。

提供基于文件的限流计数器，在 Gunicorn 多 worker 部署下保证限流阈值一致。

数据结构（v2）：
    { "<bucket-key>": {"w": <window_seconds>, "ts": [<timestamp>, ...]} }

每个桶记录自己的时间窗口，清理时按各桶自身的 window 判断过期，
避免不同业务（如 60s 的 analytics 与 3600s 的留言限流）共用文件时
被彼此的窗口误清理。旧版纯 list 结构在读取时自动迁移。
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from app.app_config import RATE_LIMIT_FILE

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows fallback
    _fcntl = None

_LOCK = threading.Lock()
_CLEANUP_INTERVAL = 300
_last_cleanup = 0.0
# 旧版 list 结构没有记录 window，清理时按全站最大窗口兜底。
_LEGACY_PRUNE_WINDOW_SECONDS = 86400


@contextmanager
def _storage_lock():
    """同时保护进程内线程和多 worker 进程对限流文件的读写。"""
    with _LOCK:
        lock_file = RATE_LIMIT_FILE.with_suffix('.lock')
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        with lock_file.open('a+', encoding='utf-8') as lock_handle:
            if _fcntl is not None:
                _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_EX)
            try:
                yield
            finally:
                if _fcntl is not None:
                    _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_UN)


def _load() -> dict:
    if not RATE_LIMIT_FILE.exists():
        return {}
    try:
        data = json.loads(RATE_LIMIT_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = RATE_LIMIT_FILE.with_suffix(f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(RATE_LIMIT_FILE)


def _normalize_entry(entry, default_window: int):
    """把任意版本的桶结构规范化为 {'w': window, 'ts': [float]}；无效返回 None。"""
    fallback_window = int(default_window) or _LEGACY_PRUNE_WINDOW_SECONDS
    if isinstance(entry, dict):
        try:
            window = int(entry.get('w', 0) or 0) or fallback_window
        except Exception:
            window = fallback_window
        raw_ts = entry.get('ts', [])
    elif isinstance(entry, list):
        # 旧版结构：未记录 window。
        window = _LEGACY_PRUNE_WINDOW_SECONDS
        raw_ts = entry
    else:
        return None
    timestamps = [float(ts) for ts in raw_ts if isinstance(ts, (int, float))]
    return {'w': window, 'ts': timestamps}


def _prune_expired(data: dict, now: float) -> None:
    """按每个桶自身记录的 window 清理过期时间戳。"""
    keys_to_remove = []
    for key, entry in data.items():
        normalized = _normalize_entry(entry, _LEGACY_PRUNE_WINDOW_SECONDS)
        if normalized is None:
            keys_to_remove.append(key)
            continue
        fresh = [ts for ts in normalized['ts'] if now - ts < normalized['w']]
        if not fresh:
            keys_to_remove.append(key)
        else:
            data[key] = {'w': normalized['w'], 'ts': fresh}
    for key in keys_to_remove:
        data.pop(key, None)


def check_and_record(key: str, *, limit: int, window: int) -> tuple[bool, int, int]:
    """检查并记录一次限流请求。

    返回 (allowed, retry_after_seconds, current_count)。
    文件 IO 异常时拒绝访问，避免限流存储故障变成无限制放行。
    """
    global _last_cleanup
    now = time.time()
    ip_key = str(key or 'unknown').strip() or 'unknown'
    try:
        with _storage_lock():
            data = _load()
            if now - _last_cleanup > _CLEANUP_INTERVAL:
                _prune_expired(data, now)
                _last_cleanup = now
            # 桶首次创建时记录本次调用的 window；此后以桶自身记录为准。
            existing = data.get(ip_key)
            entry = _normalize_entry(existing, window)
            if entry is None:
                entry = {'w': max(1, int(window)), 'ts': []}
            bucket_window = entry['w']
            bucket = [ts for ts in entry['ts'] if now - ts < bucket_window]
            if len(bucket) >= limit:
                data[ip_key] = {'w': bucket_window, 'ts': bucket}
                _save(data)
                retry_after = max(1, int(min(bucket) + bucket_window - now + 1))
                return False, retry_after, len(bucket)
            bucket.append(now)
            data[ip_key] = {'w': bucket_window, 'ts': bucket}
            _save(data)
            return True, 0, len(bucket)
    except Exception:
        return False, 1, 0


def get_snapshot(key: str, window: int) -> tuple[int, int]:
    """获取当前限流快照，不增加计数。

    返回 (current_count, retry_after_seconds)。
    """
    now = time.time()
    ip_key = str(key or 'unknown').strip() or 'unknown'
    try:
        with _storage_lock():
            data = _load()
            entry = _normalize_entry(data.get(ip_key), window)
            if entry is None:
                return 0, 0
            bucket_window = entry['w']
            bucket = [ts for ts in entry['ts'] if now - ts < bucket_window]
            retry_after = max(0, int(min(bucket) + bucket_window - now + 1)) if bucket else 0
            # 快照只读，不增加计数，不写入文件
            return len(bucket), retry_after
    except Exception:
        return 0, 0
