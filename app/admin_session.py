"""Admin session expiry and activity-refresh helpers."""

import time

from app.app_config import (
    ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
)

ADMIN_SESSION_ACTIVE_HEADER = 'X-Admin-User-Active'
ADMIN_SESSION_REFRESH_THROTTLE_SECONDS = 60


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
    sess['admin_session_ttl'] = ADMIN_SESSION_IDLE_TIMEOUT_SECONDS
    sess['admin_session_absolute_ttl'] = ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS
    return True
