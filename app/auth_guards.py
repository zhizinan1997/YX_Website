"""共享的后台登录与会话权限守卫。"""

import time
from functools import wraps

from flask import jsonify, redirect, request, session

from app.app_config import ADMIN_SESSION_MAX_AGE_SECONDS, WRITE_METHODS
from app.request_security import is_same_origin_request
from app.routes.admin import (
    ADMIN_PERMISSION_KEYS,
    ADMIN_SESSION_SCHEMA_VERSION,
    resolve_permission_for_path,
)


def login_required(f):
    """要求管理员登录后才能访问目标视图。"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_api = (request.path or '').startswith('/api/')
        if not session.get('admin_logged_in'):
            if is_api:
                return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
            return redirect('/admin')
        now_ts = int(time.time())
        try:
            login_at = int(session.get('admin_login_at') or 0)
        except Exception:
            login_at = 0
        try:
            ttl = int(session.get('admin_session_ttl') or ADMIN_SESSION_MAX_AGE_SECONDS)
        except Exception:
            ttl = ADMIN_SESSION_MAX_AGE_SECONDS
        if ttl <= 0:
            ttl = ADMIN_SESSION_MAX_AGE_SECONDS
        if login_at <= 0 or now_ts - login_at > ttl:
            session.clear()
            if is_api:
                return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
            return redirect('/admin')

        # 旧版会话结构创建的登录态直接失效，避免兼容状态继续混用。
        if session.get('admin_session_schema') != ADMIN_SESSION_SCHEMA_VERSION:
            session.clear()
            if is_api:
                return jsonify({'success': False, 'message': '会话版本已更新，请重新登录'}), 401
            return redirect('/admin')

        if (request.method or 'GET').upper() in WRITE_METHODS and not is_same_origin_request(request):
            if is_api:
                return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403
            return redirect('/admin')

        is_super_admin = bool(session.get('admin_is_super_admin', False))
        if is_super_admin:
            return f(*args, **kwargs)

        raw_permissions = session.get('admin_permissions', [])
        permissions = []
        if isinstance(raw_permissions, (list, tuple, set)):
            for item in raw_permissions:
                key = str(item or '').strip()
                if key in ADMIN_PERMISSION_KEYS and key not in permissions:
                    permissions.append(key)
        session['admin_permissions'] = permissions

        method = (request.method or 'GET').upper()
        is_write_method = method in WRITE_METHODS

        if is_write_method:
            required_permission = resolve_permission_for_path(request.path or '', method)
            denied = (
                required_permission == '__unknown__'
                or (required_permission and required_permission not in permissions)
            )
            if denied:
                if is_api:
                    return jsonify({'success': False, 'message': '当前账号无权限执行该操作'}), 403
                return redirect('/admin')

        return f(*args, **kwargs)
    return decorated_function


def _current_admin_is_super_admin() -> bool:
    return bool(session.get('admin_logged_in')) and bool(session.get('admin_is_super_admin', False))


def require_super_admin_api():
    if _current_admin_is_super_admin():
        return None
    return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403


