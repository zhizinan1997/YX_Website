"""原子文件写入与跨进程锁辅助。

后台多处配置保存原先直接 `write_text` 截断重写目标文件，多 worker 并发
保存时可能产生半截 JSON，导致配置静默丢失。统一改用临时文件 + `replace`
的原子写法（与 product_settings/news_content 既有做法保持一致）。

原子写只保证“单次写不撕裂”，不保证“读改写不丢更新”——后者还需要跨进程
互斥（gunicorn 多 worker 部署下两个进程同时读旧值会互相覆盖）。本模块同时
提供 `cross_process_file_lock`：线程锁 + flock 的可重入组合锁，供配置、
留言统计等共享 JSON 的读改写临界区使用。
"""

from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows 开发环境无 fcntl，退化为仅线程锁
    _fcntl = None

# 同一线程内对同一路径的可重入深度：进入深度 0→1 时才真正 flock，
# 避免嵌套临界区对第二个 fd 重复 flock 造成自死锁（flock 按 fd 计，不像
# POSIX 记录锁按进程计）。
_LOCK_THREAD_STATE = threading.local()
_LOCK_THREAD_GUARDS: dict[str, threading.RLock] = {}
_LOCK_THREAD_GUARDS_GUARD = threading.Lock()


@contextmanager
def cross_process_file_lock(lock_path):
    """对指定锁文件建立线程 + 跨进程互斥；同线程嵌套进入安全。"""
    resolved = Path(lock_path)
    key = str(resolved)
    with _LOCK_THREAD_GUARDS_GUARD:
        thread_guard = _LOCK_THREAD_GUARDS.setdefault(key, threading.RLock())
    depths = getattr(_LOCK_THREAD_STATE, 'depths', None)
    if depths is None:
        depths = {}
        _LOCK_THREAD_STATE.depths = depths
    with thread_guard:
        depths[key] = depths.get(key, 0) + 1
        try:
            if depths[key] > 1 or _fcntl is None:
                yield
                return
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with resolved.open('a+', encoding='utf-8') as handle:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
        finally:
            depths[key] = depths.get(key, 1) - 1


def atomic_write_text(path, text: str, *, encoding: str = 'utf-8') -> None:
    """把文本原子地写入目标路径：先写同目录临时文件，再 replace 覆盖。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f'{target.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}')
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(target)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(path, payload, *, encoding: str = 'utf-8', indent: int = 2) -> None:
    """把可 JSON 序列化对象原子地写入目标路径。"""
    import json

    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=indent),
        encoding=encoding,
    )
