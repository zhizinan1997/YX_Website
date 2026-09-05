"""Runtime feature unlock switches for the admin console."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.app_config import DATA_DIR


ADMIN_FEATURE_UNLOCKS_FILE = DATA_DIR / 'admin_feature_unlocks.json'

DEFAULT_ADMIN_FEATURE_UNLOCKS = {
    'version': 1,
    'default_unlocked': True,
    'features': {},
}

LEGACY_FEATURE_KEY_MAP = {
    'changelog': 'log-records',
    'docker-logs': 'log-records',
}

_LOGGER = logging.getLogger(__name__)
_CACHE_LOCK = threading.RLock()
_CACHE_PATH: Path | None = None
_CACHE_MTIME_NS: int | None = None
_CACHE_SIZE: int | None = None
_CACHE_PAYLOAD: dict | None = None


def normalize_admin_feature_key(key: str) -> str:
    raw = str(key or '').strip()
    return LEGACY_FEATURE_KEY_MAP.get(raw, raw)


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off'}:
            return False
    return bool(default)


def _normalize_payload(raw_payload) -> dict:
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    default_unlocked = _coerce_bool(raw_payload.get('default_unlocked', True), True)
    raw_features = raw_payload.get('features', {})
    if not isinstance(raw_features, dict):
        raw_features = {}

    features = {}
    for raw_key, raw_value in raw_features.items():
        key = normalize_admin_feature_key(raw_key)
        if not key:
            continue
        features[key] = _coerce_bool(raw_value, default_unlocked)

    return {
        'version': 1,
        'default_unlocked': default_unlocked,
        'features': features,
    }


def _load_payload() -> dict:
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_SIZE, _CACHE_PAYLOAD

    path = Path(ADMIN_FEATURE_UNLOCKS_FILE)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return _normalize_payload(DEFAULT_ADMIN_FEATURE_UNLOCKS)
    except OSError as exc:
        _LOGGER.warning('Unable to stat admin feature unlock file %s: %s', path, exc)
        return _normalize_payload(DEFAULT_ADMIN_FEATURE_UNLOCKS)

    mtime_ns = int(stat.st_mtime_ns)
    size = int(stat.st_size)
    resolved_path = path.resolve()
    with _CACHE_LOCK:
        if (
            _CACHE_PAYLOAD is not None
            and _CACHE_PATH == resolved_path
            and _CACHE_MTIME_NS == mtime_ns
            and _CACHE_SIZE == size
        ):
            return dict(_CACHE_PAYLOAD)

    try:
        raw_payload = json.loads(path.read_text(encoding='utf-8'))
        payload = _normalize_payload(raw_payload)
    except Exception as exc:
        _LOGGER.warning('Invalid admin feature unlock file %s: %s', path, exc)
        # 解析失败时优先沿用上一次的缓存（fail-closed 倾向）：文件损坏或
        # stat 与 read 之间被替换的竞态窗口不应让全部受控功能临时放行。
        with _CACHE_LOCK:
            if _CACHE_PAYLOAD is not None and _CACHE_PATH == resolved_path:
                return dict(_CACHE_PAYLOAD)
        payload = _normalize_payload(DEFAULT_ADMIN_FEATURE_UNLOCKS)

    with _CACHE_LOCK:
        _CACHE_PATH = resolved_path
        _CACHE_MTIME_NS = mtime_ns
        _CACHE_SIZE = size
        _CACHE_PAYLOAD = dict(payload)

    return payload


def clear_admin_feature_unlocks_cache():
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_SIZE, _CACHE_PAYLOAD

    with _CACHE_LOCK:
        _CACHE_PATH = None
        _CACHE_MTIME_NS = None
        _CACHE_SIZE = None
        _CACHE_PAYLOAD = None


def is_admin_feature_unlocked(key: str) -> bool:
    feature_key = normalize_admin_feature_key(key)
    if not feature_key:
        return True
    payload = _load_payload()
    features = payload.get('features', {})
    if feature_key in features:
        return bool(features[feature_key])
    return bool(payload.get('default_unlocked', True))


def get_admin_feature_unlocks(keys) -> dict[str, bool]:
    payload = _load_payload()
    features = payload.get('features', {})
    default_unlocked = bool(payload.get('default_unlocked', True))
    output: dict[str, bool] = {}
    for raw_key in keys or []:
        key = normalize_admin_feature_key(raw_key)
        if not key or key in output:
            continue
        output[key] = bool(features.get(key, default_unlocked))
    return output


def filter_unlocked_permission_catalog(catalog) -> list[dict]:
    output = []
    for item in catalog or []:
        if not isinstance(item, dict):
            continue
        key = normalize_admin_feature_key(item.get('key', ''))
        if not key or not is_admin_feature_unlocked(key):
            continue
        row = dict(item)
        row['key'] = key
        output.append(row)
    return output


__all__ = [
    'ADMIN_FEATURE_UNLOCKS_FILE',
    'DEFAULT_ADMIN_FEATURE_UNLOCKS',
    'clear_admin_feature_unlocks_cache',
    'filter_unlocked_permission_catalog',
    'get_admin_feature_unlocks',
    'is_admin_feature_unlocked',
    'normalize_admin_feature_key',
]
