"""Admin session expiry and activity-refresh helpers."""

import time

from app.app_config import (
    ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
    ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS,
)

ADMIN_SESSION_ACTIVE_HEADER = 'X-Admin-User-Active'
ADMIN_SESSION_REFRESH_THROTTLE_SECONDS = 60
# 会话档位标记。登录页勾选「N 天内免登录」时为 True，写进会话（cookie 是签名的，
# 客户端改不了）。缺省（缺失）等同于 False，也就是改动前的默认档行为。
ADMIN_SESSION_PERSISTENT_KEY = 'admin_session_persistent'


def session_ttls_for(persistent: bool) -> tuple:
    """返回 (空闲上限, 绝对上限)。免登录档两者都是同一时长，等于 30 天内不再要求重新登录。"""
    if persistent:
        ttl = ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS
        return ttl, ttl
    return ADMIN_SESSION_IDLE_TIMEOUT_SECONDS, ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS


def is_persistent_admin_session(sess) -> bool:
    return bool(sess.get(ADMIN_SESSION_PERSISTENT_KEY, False))


def _safe_positive_int(value, fallback):
    try:
        parsed = int(value or 0)
    except Exception:
        parsed = 0
    return parsed if parsed > 0 else fallback


def _session_times(sess):
    login_at = _safe_positive_int(sess.get('admin_login_at'), 0)
    last_active_at = _safe_positive_int(sess.get('admin_last_active_at'), login_at)
    idle_ttl = _safe_positive_int(sess.get('admin_session_ttl'), ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)
    absolute_ttl = _safe_positive_int(
        sess.get('admin_session_absolute_ttl'),
        ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    )
    return login_at, last_active_at, idle_ttl, absolute_ttl


def is_admin_session_expired(sess, *, now_ts=None) -> bool:
    if not sess.get('admin_logged_in'):
        return True
    now_value = int(time.time()) if now_ts is None else int(now_ts)
    login_at, last_active_at, idle_ttl, absolute_ttl = _session_times(sess)
    if login_at <= 0 or last_active_at <= 0:
        return True
    if now_value - login_at > absolute_ttl:
        return True
    return now_value - last_active_at > idle_ttl


def has_admin_activity_signal(req) -> bool:
    return str(req.headers.get(ADMIN_SESSION_ACTIVE_HEADER, '') or '').strip() == '1'


def maybe_refresh_admin_session(sess, req, *, now_ts=None) -> bool:
    if not has_admin_activity_signal(req):
        return False
    now_value = int(time.time()) if now_ts is None else int(now_ts)
    if is_admin_session_expired(sess, now_ts=now_value):
        return False
    login_at, last_active_at, _, _ = _session_times(sess)
    if login_at <= 0 or now_value - last_active_at < ADMIN_SESSION_REFRESH_THROTTLE_SECONDS:
        return False
    sess['admin_last_active_at'] = now_value
    # 按会话自身的档位重新套用，不能写死默认档：免登录会话一旦被重置成 2 小时，
    # 「N 天内免登录」会静默失效——表现为勾了之后照样几小时就掉线。
    idle_ttl, absolute_ttl = session_ttls_for(is_persistent_admin_session(sess))
    sess['admin_session_ttl'] = idle_ttl
    sess['admin_session_absolute_ttl'] = absolute_ttl
    return True
