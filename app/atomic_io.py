"""原子文件写入辅助。

后台多处配置保存原先直接 `write_text` 截断重写目标文件，多 worker 并发
保存时可能产生半截 JSON，导致配置静默丢失。统一改用临时文件 + `replace`
的原子写法（与 product_settings/news_content 既有做法保持一致）。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


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
