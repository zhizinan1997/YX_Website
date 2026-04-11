"""
共享的后台登录与会话权限守卫。

本模块提供后台管理系统的认证和授权功能，是保护后台API安全的第一道防线。

主要功能：
1. 登录状态验证（login_required装饰器）
   - 检查Session中的管理员登录状态
   - 验证会话是否过期（基于admin_login_at和admin_session_ttl）
   - 检查会话schema版本，确保兼容新版本
   - 防止跨站请求伪造（CSRF）

2. 权限控制系统
   - 超级管理员（super_admin）：拥有所有权限
   - 子管理员（sub_admin）：根据分配的权限集合访问特定功能
   - 权限映射表（ADMIN_PERMISSION_KEYS）：定义所有可分配的权限项

3. 会话安全机制
   - 会话超时自动失效（默认8小时，可配置）
   - 会话schema版本校验，防止旧版会话继续使用
   - 同源请求校验，防止跨站API调用

4. 权限校验流程
   - 根据请求路径和HTTP方法解析所需权限
   - 超级管理员跳过权限检查
   - 子管理员验证权限集合中是否包含所需权限
   - 写操作（POST/PUT/PATCH/DELETE）必须通过权限检查

权限项定义（ADMIN_PERMISSION_CATALOG）：
- site-reports: 网站数据查看
- messages: 留言系统管理
- home: 首页设置
- h2-home: 氢气首页设置
- products: 氢气产品管理
- bio-products: 生物产品管理
- hydrogen-solutions: 氢气方案管理
- news-create: 资讯发布
- jobs: 招聘信息管理
- chatbot: AI聊天机器人配置
- site-settings: 站点设置
- settings: 账号设置
- backup: 备份恢复
- changelog: 更新日志查看
- cdn-assets: CDN素材管理
- docker-logs: 后端日志查看

使用方式：
在需要保护的路由函数上添加 @login_required 装饰器，
系统会自动进行完整的认证和权限校验。

作者：元芯传感技术团队
"""

import time
from functools import wraps

from flask import jsonify, redirect, request, session

from app.app_config import ADMIN_SESSION_MAX_AGE_SECONDS, WRITE_METHODS
from app.request_security import is_same_origin_request
from app.routes.admin import (
    ADMIN_PERMISSION_KEYS,
    ADMIN_SESSION_SCHEMA_VERSION,
    is_binding_allowed_path,
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

        if bool(session.get('admin_binding_required', False)) and not is_binding_allowed_path(request.path or ''):
            if is_api:
                return jsonify({'success': False, 'message': '当前账号必须先绑定安全邮箱后才能继续操作。', 'binding_required': True}), 403
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


