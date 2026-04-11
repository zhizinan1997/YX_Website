"""
后台认证与管理路由模块。

本模块是元芯传感官网后台管理系统的核心，负责：
1. 管理员身份认证（登录、会话、登出）
2. 账号管理体系（超级管理员、子管理员）
3. 登录安全保护（IP地域限制、Turnstile验证码、暴力破解防护）
4. 后台运维功能（日志查看、更新日志）

主要功能：
1. 管理员登录系统
   - 用户名密码验证
   - Turnstile人机验证（可选Cloudflare验证码）
   - IP地域限制（仅允许中国大陆和港澳台）
   - 登录失败计数和封禁机制
   - 登录延迟机制（防止暴力破解）

2. 会话管理系统
   - Session存储管理员状态
   - 会话过期自动失效（默认8小时）
   - 会话版本校验（防止旧会话攻击）
   - 同源请求验证（防CSRF）

3. 账号权限体系
   - 超级管理员（super_admin）：拥有所有权限
   - 子管理员（sub_admin）：按需分配权限
   - 16种权限项覆盖所有后台功能
   - 权限路径映射自动校验

4. 子管理员CRUD操作
   - 创建子账号（用户名、密码、权限分配）
   - 更新子账号（启用状态、权限调整）
   - 删除子账号
   - 查看所有子账号列表

5. 密码管理
   - 修改当前账号密码
   - 密码强度要求（至少8位）
   - 用户名规则验证（3-32位字母数字下划线）

6. Turnstile配置
   - 启用/关闭人机验证
   - 配置Site Key和Secret Key
   - 后台实时更新

7. 后台运维接口
   - Docker容器日志查看
   - 本地日志文件查看（开发模式）
   - 更新日志构建（支持本地Markdown或Git历史）
   - 登录日志审计

安全特性：
- 登录失败封禁机制（12小时封禁，3次失败触发）
- 登录延迟机制（60秒/180秒渐进延迟）
- IP地域白名单（默认仅CN/HK/MO/TW）
- 会话同源校验
- 审计日志完整记录

API路由清单：
- /admin: 后台登录页
- /admin/login: POST登录请求
- /admin/logout: POST登出请求
- /admin/check: GET会话状态检查
- /admin/change-password: POST修改密码
- /api/admin/subaccounts/*: 子账号管理CRUD
- /api/admin/security/turnstile/*: Turnstile配置
- /api/admin/login-logs: 登录日志查询
- /api/admin/changelog: 更新日志
- /api/admin/docker-logs: 容器日志
- /api/changelog/latest: 公开的更新日志

作者：元芯传感技术团队
"""

import json
import os
import re
import secrets
import smtplib
import subprocess
import threading
import time
import hashlib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import ssl

from flask import jsonify, make_response, request, send_from_directory, session
from app.request_security import get_request_client_ip, is_same_origin_request
from werkzeug.security import check_password_hash, generate_password_hash

BEIJING_TZ = timezone(timedelta(hours=8))

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)

LOGIN_FAIL_WINDOW_SECONDS = 12 * 3600
LOGIN_FAIL_LIMIT = 3
LOGIN_BLOCK_SECONDS = 12 * 3600
LOGIN_ATTEMPTS_LOCK = threading.Lock()
ADMIN_USERS_LOCK = threading.RLock()
EMAIL_AUTH_STATE_LOCK = threading.RLock()
SMTP_REMINDER_THREAD_LOCK = threading.Lock()
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
try:
    ADMIN_SESSION_MAX_AGE_SECONDS = max(300, int((os.environ.get('ADMIN_SESSION_MAX_AGE_SECONDS') or '7200').strip()))
except Exception:
    ADMIN_SESSION_MAX_AGE_SECONDS = 7200
ADMIN_SESSION_SCHEMA_VERSION = 4
LOGIN_DELAY_SECONDS = [60, 180]
ALLOWED_LOGIN_COUNTRIES = {'CN', 'HK', 'MO', 'TW'}
EMAIL_CODE_LENGTH = 6
EMAIL_CODE_EXPIRES_SECONDS = 300
EMAIL_CODE_RESEND_COOLDOWN_SECONDS = 60
EMAIL_CODE_MAX_SENDS = 5
EMAIL_CODE_MAX_VERIFY_FAILURES = 5
PENDING_LOGIN_EXPIRES_SECONDS = 600
SMTP_PASSWORD_VALID_DAYS = 180
SMTP_REMINDER_DAYS = (7, 3, 1)

ADMIN_PERMISSION_CATALOG = [
    {'key': 'site-reports', 'label': '网站数据'},
    {'key': 'messages', 'label': '留言系统'},
    {'key': 'home', 'label': '首页设置'},
    {'key': 'h2-home', 'label': '氢气首页'},
    {'key': 'products', 'label': '氢气产品'},
    {'key': 'bio-products', 'label': '生物产品'},
    {'key': 'hydrogen-solutions', 'label': '氢气方案'},
    {'key': 'news-create', 'label': '添加资讯'},
    {'key': 'jobs', 'label': '招聘信息'},
    {'key': 'chatbot', 'label': 'AI 与知识库'},
    {'key': 'site-settings', 'label': '站点设置'},
    {'key': 'settings', 'label': '账号设置'},
    {'key': 'backup', 'label': '备份恢复'},
    {'key': 'changelog', 'label': '更新日志'},
    {'key': 'cdn-assets', 'label': 'CDN 素材'},
    {'key': 'docker-logs', 'label': '后端日志'},
]
ADMIN_PERMISSION_KEYS = [item['key'] for item in ADMIN_PERMISSION_CATALOG]
USERNAME_RULE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
APP_ENV = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or '').strip().lower()
DEV_ENV_NAMES = {'dev', 'development', 'local', 'test', 'testing'}

try:
    import certifi
    CERTIFI_AVAILABLE = True
except Exception:
    certifi = None
    CERTIFI_AVAILABLE = False


def _normalize_username(raw_value: str) -> str:
    return str(raw_value or '').strip()


def _normalize_email(raw_value: str) -> str:
    return str(raw_value or '').strip().lower()


def _is_development_mode() -> bool:
    return APP_ENV in DEV_ENV_NAMES



def _normalize_permissions(raw_permissions, is_super_admin: bool = False):
    if is_super_admin:
        return list(ADMIN_PERMISSION_KEYS)
    output = []
    source = raw_permissions if isinstance(raw_permissions, (list, tuple, set)) else []
    for item in source:
        key = str(item or '').strip()
        if key in ADMIN_PERMISSION_KEYS and key not in output:
            output.append(key)
    return output


def _get_admin_users_file(project_root: Path) -> Path:
    data_dir = (project_root / 'data').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'admin_users.json'


def _load_admin_users(file_path: Path):
    default_data = {'version': 1, 'users': []}
    if not file_path.exists():
        return default_data
    try:
        data = json.loads(file_path.read_text(encoding='utf-8'))
    except Exception:
        return default_data
    if not isinstance(data, dict):
        return default_data
    users = data.get('users', [])
    if not isinstance(users, list):
        users = []
    return {
        'version': int(data.get('version', 1) or 1),
        'users': [item for item in users if isinstance(item, dict)]
    }


def _save_admin_users(file_path: Path, data):
    payload = data if isinstance(data, dict) else {'version': 1, 'users': []}
    users = payload.get('users', [])
    if not isinstance(users, list):
        users = []
    payload = {'version': int(payload.get('version', 1) or 1), 'users': users}
    tmp = file_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file_path)


def _find_user(users_data, username: str):
    name = _normalize_username(username)
    users = users_data.get('users', []) if isinstance(users_data, dict) else []
    if not isinstance(users, list):
        return None, -1
    for idx, user in enumerate(users):
        if _normalize_username(user.get('username', '')) == name:
            return user, idx
    return None, -1


def _hash_password(password: str) -> str:
    return generate_password_hash(str(password or ''))


def _verify_password(password_hash: str, plain_password: str) -> bool:
    hashed = str(password_hash or '').strip()
    if not hashed:
        return False
    try:
        return bool(check_password_hash(hashed, str(plain_password or '')))
    except Exception:
        return False


def _get_email_auth_state_file(project_root: Path) -> Path:
    data_dir = (project_root / 'data').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'admin_email_auth_state.json'


def _load_email_auth_state(file_path: Path):
    default_state = {
        'version': 1,
        'pending_logins': {},
        'binding_codes': {},
        'smtp_notice_history': {},
    }
    if not file_path.exists():
        return default_state
    try:
        data = json.loads(file_path.read_text(encoding='utf-8'))
    except Exception:
        return default_state
    if not isinstance(data, dict):
        return default_state
    return {
        'version': int(data.get('version', 1) or 1),
        'pending_logins': data.get('pending_logins', {}) if isinstance(data.get('pending_logins'), dict) else {},
        'binding_codes': data.get('binding_codes', {}) if isinstance(data.get('binding_codes'), dict) else {},
        'smtp_notice_history': data.get('smtp_notice_history', {}) if isinstance(data.get('smtp_notice_history'), dict) else {},
    }


def _save_email_auth_state(file_path: Path, data):
    payload = data if isinstance(data, dict) else {}
    safe = {
        'version': int(payload.get('version', 1) or 1),
        'pending_logins': payload.get('pending_logins', {}) if isinstance(payload.get('pending_logins'), dict) else {},
        'binding_codes': payload.get('binding_codes', {}) if isinstance(payload.get('binding_codes'), dict) else {},
        'smtp_notice_history': payload.get('smtp_notice_history', {}) if isinstance(payload.get('smtp_notice_history'), dict) else {},
    }
    tmp = file_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file_path)


def _email_code_hash(code: str, salt: str) -> str:
    return hashlib.sha256(f'{salt}:{str(code or "").strip()}'.encode('utf-8')).hexdigest()


def _generate_email_code() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(EMAIL_CODE_LENGTH))


def _mask_email_address(email: str) -> str:
    normalized = _normalize_email(email)
    if '@' not in normalized:
        return normalized
    local_part, domain = normalized.split('@', 1)
    if len(local_part) <= 1:
        masked_local = '*'
    elif len(local_part) == 2:
        masked_local = f'{local_part[0]}*'
    else:
        masked_local = f'{local_part[0]}***{local_part[-1]}'
    return f'{masked_local}@{domain}'


def _parse_iso_datetime(raw_value: str):
    value = str(raw_value or '').strip()
    if not value:
        return None
    normalized = value.replace('Z', '+00:00')
    try:
        dt_value = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=BEIJING_TZ)
    return dt_value.astimezone(BEIJING_TZ)


def _to_iso_datetime(dt_value):
    if not isinstance(dt_value, datetime):
        return ''
    return dt_value.astimezone(BEIJING_TZ).isoformat(timespec='seconds')


def _get_email_auth_settings(config):
    safe = config if isinstance(config, dict) else {}
    host = str(safe.get('smtp_host', '') or '').strip()
    username = str(safe.get('smtp_username', '') or '').strip()
    password = str(safe.get('smtp_password_or_app_code', '') or '').strip()
    from_name = str(safe.get('smtp_from_name', '') or '').strip()
    from_email = _normalize_email(safe.get('smtp_from_email', ''))
    notice_email = _normalize_email(safe.get('smtp_notice_email', ''))
    password_set_at = str(safe.get('smtp_password_set_at', '') or '').strip()
    password_expires_at = str(safe.get('smtp_password_expires_at', '') or '').strip()
    try:
        port = int(str(safe.get('smtp_port', 465) or 465).strip())
    except Exception:
        port = 465
    use_ssl = _parse_bool(safe.get('smtp_use_ssl', True), True)
    use_tls = _parse_bool(safe.get('smtp_use_tls', False), False)
    enabled = _parse_bool(safe.get('email_auth_enabled', False), False)

    missing_fields = []
    if not host:
        missing_fields.append('smtp_host')
    if port <= 0:
        missing_fields.append('smtp_port')
    if not username:
        missing_fields.append('smtp_username')
    if not password:
        missing_fields.append('smtp_password_or_app_code')
    if not from_email:
        missing_fields.append('smtp_from_email')

    set_dt = _parse_iso_datetime(password_set_at)
    expires_dt = _parse_iso_datetime(password_expires_at)
    if expires_dt is None and set_dt is not None:
        expires_dt = set_dt + timedelta(days=SMTP_PASSWORD_VALID_DAYS)

    now_dt = now_beijing()
    remaining_days = None
    if expires_dt is not None:
        remaining_seconds = int((expires_dt - now_dt).total_seconds())
        remaining_days = max(0, (remaining_seconds + 86399) // 86400)

    expired = expires_dt is not None and expires_dt <= now_dt
    configured = not missing_fields

    return {
        'enabled': enabled,
        'smtp_host': host,
        'smtp_port': port,
        'smtp_username': username,
        'smtp_password_or_app_code': password,
        'smtp_use_ssl': use_ssl,
        'smtp_use_tls': use_tls,
        'smtp_from_name': from_name,
        'smtp_from_email': from_email,
        'smtp_notice_email': notice_email,
        'smtp_password_set_at': password_set_at,
        'smtp_password_expires_at': _to_iso_datetime(expires_dt) if expires_dt else '',
        'smtp_password_masked': ('***' if password else ''),
        'configured': configured,
        'missing_fields': missing_fields,
        'expired': expired,
        'remaining_days': remaining_days,
    }


def _smtp_ready_for_email_auth(settings) -> bool:
    return bool(settings.get('configured')) and not bool(settings.get('expired'))


def _build_smtp_status_payload(config):
    settings = _get_email_auth_settings(config)
    return {
        'email_auth_enabled': settings['enabled'],
        'smtp_host': settings['smtp_host'],
        'smtp_port': settings['smtp_port'],
        'smtp_username': settings['smtp_username'],
        'smtp_use_ssl': settings['smtp_use_ssl'],
        'smtp_use_tls': settings['smtp_use_tls'],
        'smtp_from_name': settings['smtp_from_name'],
        'smtp_from_email': settings['smtp_from_email'],
        'smtp_notice_email': settings['smtp_notice_email'],
        'smtp_password_masked': settings['smtp_password_masked'],
        'smtp_password_set_at': settings['smtp_password_set_at'],
        'smtp_password_expires_at': settings['smtp_password_expires_at'],
        'smtp_password_remaining_days': settings['remaining_days'],
        'smtp_password_expired': settings['expired'],
        'smtp_configured': settings['configured'],
        'smtp_missing_fields': settings['missing_fields'],
    }


def _send_smtp_mail(settings, *, to_email: str, subject: str, html_body: str, text_body: str = ''):
    recipient = _normalize_email(to_email)
    if not recipient:
        raise ValueError('missing recipient')
    if not _smtp_ready_for_email_auth(settings):
        raise RuntimeError('SMTP 配置不可用')

    message = EmailMessage()
    from_name = str(settings.get('smtp_from_name') or '').strip()
    from_email = _normalize_email(settings.get('smtp_from_email', ''))
    message['From'] = f'{from_name} <{from_email}>' if from_name else from_email
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(text_body or '请使用支持 HTML 的邮箱客户端查看邮件。')
    message.add_alternative(html_body, subtype='html')

    host = settings['smtp_host']
    port = int(settings['smtp_port'])
    username = settings['smtp_username']
    password = settings['smtp_password_or_app_code']

    if settings.get('smtp_use_ssl'):
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    try:
        server.ehlo()
        if settings.get('smtp_use_tls') and not settings.get('smtp_use_ssl'):
            server.starttls()
            server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def resolve_permission_for_path(path: str, method: str = 'GET'):
    p = str(path or '').strip()
    m = str(method or 'GET').upper()
    if not p:
        return None

    # 公开页、登录页、会话检查和 IP 预检接口在别处处理。
    if p in {
        '/admin',
        '/admin/login',
        '/admin/login/start',
        '/admin/login/send-email-code',
        '/admin/login/verify-email-code',
        '/admin/logout',
        '/admin/check',
        '/api/admin/ip-preflight',
    }:
        return None

    # 历史登录日志为全管理员只读审计信息，不绑定单一侧栏权限，避免子账号误拦截。
    if p.startswith('/api/admin/login-logs'):
        return None
    if p.startswith('/api/admin/subaccounts') or p.startswith('/admin/change-password'):
        return 'settings'
    if p.startswith('/api/admin/account/email-binding'):
        return 'settings'
    if p.startswith('/api/admin/email-auth'):
        return 'site-settings'
    if p.startswith('/api/admin/security/turnstile') or p.startswith('/api/cdn/'):
        return 'site-settings'
    if p.startswith('/api/admin/site-reports'):
        return 'site-reports'
    if p.startswith('/api/admin/changelog'):
        return 'changelog'
    if p.startswith('/api/admin/docker-logs'):
        return 'docker-logs'
    if p.startswith('/api/cdn/assets'):
        return 'cdn-assets'
    if p.startswith('/api/backup/'):
        return 'backup'
    if p.startswith('/api/recommendations'):
        return 'products'
    if p.startswith('/api/measurement-targets'):
        return 'products'
    if p.startswith('/api/messages'):
        return 'messages'
    if p.startswith('/api/jobs'):
        return 'jobs'
    if p.startswith('/api/chatbot') or p.startswith('/api/product-ai'):
        return 'chatbot'
    if p.startswith('/api/h2-home'):
        return 'h2-home'
    if p.startswith('/api/nav-industry-categories'):
        return 'products'
    if p.startswith('/api/admin/hydrogen-solutions') or p.startswith('/api/solutions/all'):
        return 'hydrogen-solutions'
    if p.startswith('/api/solutions/featured'):
        return 'home'
    if p.startswith('/api/solutions'):
        return 'hydrogen-solutions'
    if p.startswith('/api/news/featured'):
        return 'home'
    if p.startswith('/api/news'):
        return 'news-create'
    if p.startswith('/api/products/featured'):
        return 'home'
    if p.startswith('/api/bio-products'):
        return 'bio-products'
    if p.startswith('/api/products') or p.startswith('/api/cases/gassensing'):
        return 'products'
    if p.startswith('/api/home/section-visibility') or p.startswith('/api/hero') or p.startswith('/api/partners'):
        return 'home'
    if p.startswith('/api/search/rebuild'):
        return 'settings'

    # 对子账号而言，未识别的受保护 API 默认拒绝访问。
    if p.startswith('/api/'):
        return '__unknown__'
    return None


def _sanitize_user_record(user, fallback_username: str = '', is_super_admin: bool = False, force_hidden=None):
    now_iso = now_beijing().isoformat(timespec='seconds')
    username = _normalize_username(user.get('username') if isinstance(user, dict) else fallback_username)
    if not username:
        username = fallback_username
    enabled = bool(user.get('enabled', True)) if isinstance(user, dict) else True
    role = 'super_admin' if is_super_admin else 'sub_admin'
    hidden = bool((user or {}).get('hidden', False)) if isinstance(user, dict) else False
    if force_hidden is not None:
        hidden = bool(force_hidden)
    permissions = _normalize_permissions((user or {}).get('permissions', []), is_super_admin=is_super_admin)
    if is_super_admin:
        enabled = True
    else:
        hidden = False
    password_hash = str((user or {}).get('password_hash', '') or '').strip()
    created_at = str((user or {}).get('created_at', '') or '').strip() or now_iso
    updated_at = str((user or {}).get('updated_at', '') or '').strip() or now_iso
    last_login_at = str((user or {}).get('last_login_at', '') or '').strip()
    last_login_ip = str((user or {}).get('last_login_ip', '') or '').strip()
    email = _normalize_email((user or {}).get('email', ''))
    email_bound_at = str((user or {}).get('email_bound_at', '') or '').strip()
    email_verified = bool(email and (user or {}).get('email_verified', False))
    two_factor_enabled = True if (user or {}).get('two_factor_enabled', True) is not False else False
    return {
        'username': username,
        'password_hash': password_hash,
        'role': role,
        'enabled': enabled,
        'hidden': hidden,
        'permissions': permissions,
        'created_at': created_at,
        'updated_at': updated_at,
        'last_login_at': last_login_at,
        'last_login_ip': last_login_ip,
        'email': email,
        'email_bound_at': email_bound_at,
        'email_verified': email_verified,
        'two_factor_enabled': two_factor_enabled,
    }


def _public_user_profile(user):
    record = user if isinstance(user, dict) else {}
    return {
        'username': _normalize_username(record.get('username', '')),
        'role': str(record.get('role') or 'sub_admin'),
        'enabled': bool(record.get('enabled', True)),
        'permissions': _normalize_permissions(record.get('permissions', []), is_super_admin=bool(record.get('role') == 'super_admin')),
        'created_at': str(record.get('created_at') or ''),
        'updated_at': str(record.get('updated_at') or ''),
        'last_login_at': str(record.get('last_login_at') or ''),
        'last_login_ip': str(record.get('last_login_ip') or ''),
        'email': _normalize_email(record.get('email', '')),
        'email_verified': bool(record.get('email_verified', False)),
        'email_bound_at': str(record.get('email_bound_at') or ''),
        'two_factor_enabled': record.get('two_factor_enabled', True) is not False,
    }


def _is_hidden_admin_record(user) -> bool:
    return bool(
        isinstance(user, dict)
        and str(user.get('role') or '') == 'super_admin'
        and bool(user.get('hidden', False))
    )


def _is_hidden_admin_session(sess) -> bool:
    return bool(sess.get('admin_logged_in')) and bool(sess.get('admin_is_hidden', False))


def _get_hidden_admin_config(config):
    safe = config if isinstance(config, dict) else {}
    username = _normalize_username(safe.get('hidden_admin_username', ''))
    password_hash = str(safe.get('hidden_admin_password_hash', '') or '').strip()
    password_plain = str(safe.get('hidden_admin_password', '') or '').strip()
    return {
        'enabled': bool(username or password_hash or password_plain),
        'username': username,
        'password_hash': password_hash,
        'password_plain': password_plain,
    }


def _hidden_admin_username_unavailable_response():
    return jsonify({'success': False, 'message': '用户名不可用，请更换'}), 400


def _hidden_admin_not_found_response():
    return jsonify({'success': False, 'message': '子账号不存在'}), 404


def _is_super_admin_session(sess) -> bool:
    return bool(sess.get('admin_is_super_admin', False))


def _has_verified_email(user) -> bool:
    return bool(_normalize_email((user or {}).get('email', '')) and bool((user or {}).get('email_verified', False)))


def _is_binding_required_session(sess) -> bool:
    return bool(sess.get('admin_logged_in')) and bool(sess.get('admin_binding_required', False))


def is_binding_allowed_path(path: str) -> bool:
    p = str(path or '').strip()
    if not p:
        return False
    if p in {'/admin', '/admin/', '/admin/index.html', '/admin/check', '/admin/logout'}:
        return True
    if p.startswith('/api/admin/account/email-binding'):
        return True
    return False


def _clear_pending_login_session(sess):
    for key in (
        'admin_pending_login_id',
        'admin_pending_username',
        'admin_pending_started_at',
        'admin_pending_ip',
    ):
        sess.pop(key, None)


def _clear_admin_session(sess):
    for key in (
        'admin_logged_in',
        'admin_username',
        'admin_is_super_admin',
        'admin_is_hidden',
        'admin_permissions',
        'admin_login_at',
        'admin_session_ttl',
        'admin_session_schema',
        'admin_binding_required',
    ):
        sess.pop(key, None)
    _clear_pending_login_session(sess)


def _set_pending_login_session(sess, *, pending_login_id: str, username: str, ip_addr: str):
    _clear_admin_session(sess)
    sess['admin_pending_login_id'] = pending_login_id
    sess['admin_pending_username'] = username
    sess['admin_pending_started_at'] = int(time.time())
    sess['admin_pending_ip'] = ip_addr


def _set_logged_in_session(sess, *, user, permissions, is_super_admin: bool, is_hidden_admin: bool, binding_required: bool = False):
    _clear_pending_login_session(sess)
    sess['admin_logged_in'] = True
    sess['admin_username'] = _normalize_username((user or {}).get('username', ''))
    sess['admin_is_super_admin'] = bool(is_super_admin)
    sess['admin_is_hidden'] = bool(is_hidden_admin)
    sess['admin_permissions'] = list(permissions or [])
    sess['admin_login_at'] = int(time.time())
    sess['admin_session_ttl'] = ADMIN_SESSION_MAX_AGE_SECONDS
    sess['admin_session_schema'] = ADMIN_SESSION_SCHEMA_VERSION
    sess['admin_binding_required'] = bool(binding_required)


def _save_login_success(root: Path, get_config, update_config, username: str, ip_addr: str):
    prev_last_login_at = ''
    prev_last_login_ip = ''
    current_login_at = now_beijing().isoformat(timespec='seconds')
    with ADMIN_USERS_LOCK:
        users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
        user_ref, idx = _find_user(users_data, username)
        if user_ref is not None and idx >= 0:
            user_ref = dict(user_ref)
            prev_last_login_at = str(user_ref.get('last_login_at', '') or '').strip()
            prev_last_login_ip = str(user_ref.get('last_login_ip', '') or '').strip()
            user_ref['last_login_at'] = current_login_at
            user_ref['last_login_ip'] = ip_addr
            user_ref['updated_at'] = current_login_at
            users_data['users'][idx] = _sanitize_user_record(
                user_ref,
                fallback_username=username,
                is_super_admin=bool(str(user_ref.get('role') or '') == 'super_admin'),
                force_hidden=bool(user_ref.get('hidden', False)),
            )
            _save_admin_users(users_file, users_data)
    return prev_last_login_at, prev_last_login_ip, current_login_at


def _find_user_by_email(users_data, email: str, exclude_username: str = ''):
    normalized = _normalize_email(email)
    exclude_name = _normalize_username(exclude_username)
    users = users_data.get('users', []) if isinstance(users_data, dict) else []
    for item in users if isinstance(users, list) else []:
        if _normalize_username(item.get('username', '')) == exclude_name:
            continue
        if _normalize_email(item.get('email', '')) == normalized:
            return item
    return None


def _prune_email_auth_state(state, now_ts: int):
    pending = state.get('pending_logins', {}) if isinstance(state, dict) else {}
    if isinstance(pending, dict):
        for key in list(pending.keys()):
            item = pending.get(key)
            expires_at = int((item or {}).get('expires_at', 0) or 0) if isinstance(item, dict) else 0
            if expires_at <= now_ts:
                pending.pop(key, None)
    binding_codes = state.get('binding_codes', {}) if isinstance(state, dict) else {}
    if isinstance(binding_codes, dict):
        for key in list(binding_codes.keys()):
            item = binding_codes.get(key)
            expires_at = int((item or {}).get('expires_at', 0) or 0) if isinstance(item, dict) else 0
            if expires_at <= now_ts:
                binding_codes.pop(key, None)


def _build_login_email_subject():
    return '管理员登录邮箱验证码'


def _build_login_email_content(username: str, code: str):
    safe_username = _normalize_username(username) or '管理员'
    html_body = f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.7;color:#1f2937;">
      <h2 style="margin:0 0 12px;">后台登录验证码</h2>
      <p>账号 <strong>{safe_username}</strong> 正在登录管理后台。</p>
      <p>本次验证码为：</p>
      <div style="font-size:28px;font-weight:700;letter-spacing:6px;color:#0f2f5f;margin:16px 0;">{code}</div>
      <p>验证码 5 分钟内有效，若非本人操作，请立即修改后台密码。</p>
    </div>
    """
    text_body = f'账号 {safe_username} 正在登录管理后台，本次验证码：{code}，5 分钟内有效。'
    return html_body, text_body


def _build_binding_email_content(username: str, code: str):
    safe_username = _normalize_username(username) or '管理员'
    html_body = f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.7;color:#1f2937;">
      <h2 style="margin:0 0 12px;">邮箱绑定验证码</h2>
      <p>账号 <strong>{safe_username}</strong> 正在绑定后台安全邮箱。</p>
      <p>本次验证码为：</p>
      <div style="font-size:28px;font-weight:700;letter-spacing:6px;color:#0f2f5f;margin:16px 0;">{code}</div>
      <p>验证码 5 分钟内有效。完成绑定后，后续后台登录将通过邮箱二次校验。</p>
    </div>
    """
    text_body = f'账号 {safe_username} 正在绑定后台安全邮箱，本次验证码：{code}，5 分钟内有效。'
    return html_body, text_body


def _build_smtp_notice_content(remaining_days: int, expires_at: str):
    html_body = f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.7;color:#1f2937;">
      <h2 style="margin:0 0 12px;">SMTP 授权码即将到期</h2>
      <p>后台使用的 SMTP 授权码预计还剩 <strong>{remaining_days}</strong> 天到期。</p>
      <p>预计到期时间：<strong>{expires_at or '未知'}</strong></p>
      <p>请尽快前往后台“站点设置”更新 163 邮箱授权码，避免管理员无法收到登录验证码。</p>
    </div>
    """
    text_body = f'SMTP 授权码预计还剩 {remaining_days} 天到期，到期时间：{expires_at or "未知"}。请尽快更新后台 SMTP 授权码。'
    return html_body, text_body


def _filter_admin_login_logs_for_session(items, sess):
    logs = [item for item in (items or []) if isinstance(item, dict)]
    if _is_hidden_admin_session(sess):
        return logs
    return [item for item in logs if not bool(item.get('hidden_account', False))]


def _should_conceal_hidden_admin(target_user, sess) -> bool:
    return bool(target_user is not None and _is_hidden_admin_record(target_user) and not _is_hidden_admin_session(sess))


def _ensure_admin_users_store(project_root: Path, get_config, update_config):
    with ADMIN_USERS_LOCK:
        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        users_file = _get_admin_users_file(root)
        users_data = _load_admin_users(users_file)
        users = users_data.get('users', [])
        if not isinstance(users, list):
            users = []

        config = get_config() or {}
        config_admin_username = _normalize_username(config.get('admin_username', '')) or 'admin'
        config_admin_hash = str(config.get('admin_password_hash', '') or '').strip()
        config_admin_plain = str(config.get('admin_password', '') or '').strip()
        if not config_admin_plain and _is_development_mode():
            config_admin_plain = 'admin123'
        hidden_admin_cfg = _get_hidden_admin_config(config)

        if not USERNAME_RULE.match(config_admin_username):
            raise RuntimeError('主超级管理员用户名格式不合法')
        if hidden_admin_cfg['enabled']:
            if not hidden_admin_cfg['username']:
                raise RuntimeError('启用隐藏超级管理员时必须配置 hidden_admin_username')
            if not USERNAME_RULE.match(hidden_admin_cfg['username']):
                raise RuntimeError('隐藏超级管理员用户名格式不合法')
            if hidden_admin_cfg['username'] == config_admin_username:
                raise RuntimeError('隐藏超级管理员用户名不能与主超级管理员相同')
            if not hidden_admin_cfg['password_hash'] and not hidden_admin_cfg['password_plain']:
                raise RuntimeError('隐藏超级管理员缺少初始化凭据')

        now_iso = now_beijing().isoformat(timespec='seconds')

        normalized_existing = []
        seen_names = set()
        for raw_user in users:
            if not isinstance(raw_user, dict):
                continue
            username = _normalize_username(raw_user.get('username', ''))
            if not username or username in seen_names:
                continue
            is_super = str(raw_user.get('role') or '') == 'super_admin'
            item = _sanitize_user_record(
                raw_user,
                fallback_username=username,
                is_super_admin=is_super,
                force_hidden=bool(raw_user.get('hidden', False)) if is_super else False,
            )
            if not item['password_hash']:
                continue
            seen_names.add(username)
            normalized_existing.append(item)

        configured_specs = [{
            'kind': 'primary',
            'username': config_admin_username,
            'password_hash': config_admin_hash,
            'password_plain': config_admin_plain,
            'hidden': False,
        }]
        if hidden_admin_cfg['enabled']:
            configured_specs.append({
                'kind': 'hidden',
                'username': hidden_admin_cfg['username'],
                'password_hash': hidden_admin_cfg['password_hash'],
                'password_plain': hidden_admin_cfg['password_plain'],
                'hidden': True,
            })

        configured_names = [spec['username'] for spec in configured_specs]
        if len(configured_names) != len(set(configured_names)):
            raise RuntimeError('配置的超级管理员用户名冲突')

        existing_lookup = {'users': normalized_existing}
        for spec in configured_specs:
            existing_user, _ = _find_user(existing_lookup, spec['username'])
            if spec['kind'] == 'hidden' and existing_user is not None and not _is_hidden_admin_record(existing_user):
                raise RuntimeError(f"隐藏超级管理员用户名与现有账号冲突：{spec['username']}")
            if spec['kind'] == 'primary' and existing_user is not None and _is_hidden_admin_record(existing_user):
                raise RuntimeError(f"主超级管理员用户名与隐藏账号冲突：{spec['username']}")

        normalized_users = []
        for spec in configured_specs:
            existing_user, _ = _find_user(existing_lookup, spec['username'])
            password_hash = spec['password_hash']
            if not password_hash and spec['password_plain']:
                password_hash = _hash_password(spec['password_plain'])
            if not password_hash and existing_user is not None:
                password_hash = str(existing_user.get('password_hash', '') or '').strip()
            if not password_hash:
                if spec['kind'] == 'hidden':
                    raise RuntimeError('缺少隐藏超级管理员初始化凭据，无法创建或修复账号')
                raise RuntimeError('缺少主超级管理员初始化凭据，无法创建或修复账号')

            base_user = dict(existing_user or {})
            base_user.update({
                'username': spec['username'],
                'password_hash': password_hash,
                'permissions': list(ADMIN_PERMISSION_KEYS),
                'created_at': str(base_user.get('created_at', '') or '').strip() or now_iso,
                'updated_at': now_iso,
            })
            normalized_users.append(_sanitize_user_record(
                base_user,
                fallback_username=spec['username'],
                is_super_admin=True,
                force_hidden=spec['hidden'],
            ))

        for item in normalized_existing:
            username = _normalize_username(item.get('username', ''))
            if not username or username in configured_names:
                continue
            if _is_hidden_admin_record(item):
                continue
            normalized_users.append(item)

        users_data = {'version': 1, 'users': normalized_users}
        _save_admin_users(users_file, users_data)

        config_updates = {}
        primary_user = next((u for u in normalized_users if str(u.get('role') or '') == 'super_admin' and not _is_hidden_admin_record(u)), None)
        hidden_user = next((u for u in normalized_users if _is_hidden_admin_record(u)), None)
        if primary_user is not None:
            if _normalize_username(config.get('admin_username', '')) != primary_user.get('username', ''):
                config_updates['admin_username'] = primary_user.get('username', '')
            if str(config.get('admin_password_hash', '') or '').strip() != str(primary_user.get('password_hash', '') or '').strip():
                config_updates['admin_password_hash'] = str(primary_user.get('password_hash', '') or '').strip()
            if str(config.get('admin_password', '') or '').strip():
                config_updates['admin_password'] = ''
        if hidden_admin_cfg['enabled'] and hidden_user is not None:
            if _normalize_username(config.get('hidden_admin_username', '')) != hidden_user.get('username', ''):
                config_updates['hidden_admin_username'] = hidden_user.get('username', '')
            if str(config.get('hidden_admin_password_hash', '') or '').strip() != str(hidden_user.get('password_hash', '') or '').strip():
                config_updates['hidden_admin_password_hash'] = str(hidden_user.get('password_hash', '') or '').strip()
            if str(config.get('hidden_admin_password', '') or '').strip():
                config_updates['hidden_admin_password'] = ''
        if config_updates:
            update_config(config_updates)

        return users_data, users_file

def _run_git_command(args, cwd: Path) -> str:
    """安全执行 git 命令并返回去除首尾空白后的标准输出。"""
    try:
        proc = subprocess.run(
            ['git', *args],
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except Exception:
        return ''

    if proc.returncode != 0:
        return ''
    return (proc.stdout or '').strip()


def _get_login_attempts_file(project_root: Path) -> Path:
    data_dir = (project_root / 'data').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'admin_login_attempts.json'


def _load_login_attempts(file_path: Path):
    default_state = {'ips': {}}
    if not file_path.exists():
        return default_state
    try:
        data = json.loads(file_path.read_text(encoding='utf-8'))
        if isinstance(data, dict) and isinstance(data.get('ips'), dict):
            return data
    except Exception:
        pass
    _start_smtp_reminder_worker_once(app=app, root=root, get_config=get_config)
    return default_state


def _save_login_attempts(file_path: Path, state):
    safe_state = state if isinstance(state, dict) else {'ips': {}}
    if not isinstance(safe_state.get('ips'), dict):
        safe_state['ips'] = {}
    tmp = file_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file_path)


def _get_request_ip(req):
    return get_request_client_ip(
        req,
        default_ip=((req.remote_addr or 'unknown').strip() or 'unknown'),
        trust_proxy_headers_default=False,
        public_ip_header_names=('CF-Connecting-IP', 'CDN-Real-IP', 'Ali-CDN-Real-IP'),
    )


def _prune_login_attempts(state, now_ts: int):
    ips = state.get('ips') if isinstance(state, dict) else {}
    if not isinstance(ips, dict):
        state['ips'] = {}
        return
    to_delete = []
    for ip, item in ips.items():
        if not isinstance(item, dict):
            to_delete.append(ip)
            continue
        failures = item.get('failures', [])
        failures = [int(ts) for ts in failures if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
        blocked_until = int(item.get('blocked_until', 0) or 0)
        if blocked_until <= now_ts:
            blocked_until = 0
        if not failures and blocked_until <= 0:
            to_delete.append(ip)
        else:
            item['failures'] = failures
            item['blocked_until'] = blocked_until
            ips[ip] = item
    for ip in to_delete:
        ips.pop(ip, None)


def _register_login_failure(state, ip_addr: str, now_ts: int):
    ips = state.setdefault('ips', {})
    item = ips.get(ip_addr, {}) if isinstance(ips.get(ip_addr), dict) else {}
    failures = [int(ts) for ts in item.get('failures', []) if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
    failures.append(now_ts)
    blocked_until = int(item.get('blocked_until', 0) or 0)

    is_blocked_now = False
    if len(failures) >= LOGIN_FAIL_LIMIT:
        blocked_until = now_ts + LOGIN_BLOCK_SECONDS
        failures = []
        is_blocked_now = True

    item['failures'] = failures
    item['blocked_until'] = blocked_until
    ips[ip_addr] = item
    remaining = max(0, LOGIN_FAIL_LIMIT - len(failures))
    return is_blocked_now, blocked_until, remaining


def _get_login_delay_seconds(state, ip_addr: str, now_ts: int) -> int:
    """根据连续失败次数返回所需延迟秒数；无需延迟时返回 0。"""
    ips = state.get('ips') if isinstance(state, dict) else {}
    item = ips.get(ip_addr, {}) if isinstance(ips.get(ip_addr), dict) else {}
    failures = [int(ts) for ts in item.get('failures', []) if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
    delay_until = int(item.get('delay_until', 0) or 0)
    if delay_until > now_ts:
        return delay_until - now_ts
    failure_count = len(failures)
    if failure_count == 1 and LOGIN_DELAY_SECONDS[0] > 0:
        return LOGIN_DELAY_SECONDS[0]
    if failure_count >= 2 and LOGIN_DELAY_SECONDS[1] > 0:
        return LOGIN_DELAY_SECONDS[1]
    return 0


def _set_login_delay(state, ip_addr: str, now_ts: int):
    """根据连续失败次数为当前 IP 设置登录延迟。"""
    ips = state.setdefault('ips', {})
    item = ips.get(ip_addr, {}) if isinstance(ips.get(ip_addr), dict) else {}
    failures = [int(ts) for ts in item.get('failures', []) if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
    delay_seconds = 0
    failure_count = len(failures)
    if failure_count == 1 and LOGIN_DELAY_SECONDS[0] > 0:
        delay_seconds = LOGIN_DELAY_SECONDS[0]
    elif failure_count >= 2 and LOGIN_DELAY_SECONDS[1] > 0:
        delay_seconds = LOGIN_DELAY_SECONDS[1]
    if delay_seconds > 0:
        item['delay_until'] = now_ts + delay_seconds
    ips[ip_addr] = item


def _reset_login_attempts_for_ip(state, ip_addr: str):
    ips = state.get('ips') if isinstance(state, dict) else {}
    if isinstance(ips, dict):
        ips.pop(ip_addr, None)


def _format_blocked_until(ts_value: int) -> str:
    ts = int(ts_value or 0)
    if ts <= 0:
        return ''
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def _parse_datetime_safe(raw_value: str):
    """尝试按多种常见格式解析日期时间。"""
    value = (raw_value or '').strip()
    if not value:
        return None
    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_bool(raw, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    value = str(raw or '').strip().lower()
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _is_ip_country_allowed(ip: str, allowed_countries: set, resolve_country_code_func) -> tuple:
    """检查 IP 所属国家是否在允许列表中，返回（是否允许，原因）。"""
    if not ip:
        return True, ''
    try:
        import ipaddress as ipaddress_module
        ip_obj = ipaddress_module.ip_address(ip)
        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_reserved:
            return True, ''
    except ValueError:
        return True, ''
    country_code = resolve_country_code_func(ip)
    if not country_code:
        return False, '无法获取IP归属地，已拒绝登录'
    if country_code not in allowed_countries:
        location = ''
        try:
            from app.admin_audit import resolve_ip_location
            location = resolve_ip_location(ip)
        except Exception:
            location = ''
        return False, f'您的登录IP归属地({location})被禁止登录'
    return True, ''


def _get_turnstile_settings(config):
    enabled = _parse_bool(config.get('turnstile_enabled', False), False)
    site_key = str(config.get('turnstile_site_key', '') or '').strip()
    secret_key = str(config.get('turnstile_secret_key', '') or '').strip()
    if enabled and (not site_key or not secret_key):
        enabled = False
    return {
        'enabled': enabled,
        'site_key': site_key,
        'secret_key': secret_key,
    }


def _verify_turnstile_token(secret_key: str, token: str, remote_ip: str = ''):
    payload = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    req = Request(
        TURNSTILE_VERIFY_URL,
        data=urlencode(payload).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    ssl_context = None
    if CERTIFI_AVAILABLE and certifi is not None:
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_context = None

    try:
        with urlopen(req, timeout=30, context=ssl_context) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
        result = json.loads(body) if body else {}
    except Exception as exc:
        return False, f'验证码服务请求失败: {exc}'

    if bool(result.get('success')):
        return True, ''

    codes = result.get('error-codes') or []
    if isinstance(codes, list):
        code_text = ','.join(str(x) for x in codes if x)
    else:
        code_text = str(codes or '').strip()
    if code_text:
        return False, f'验证码校验未通过({code_text})'
    return False, '验证码校验未通过'


def get_turnstile_settings(config):
    """读取公共流程与后台流程共用的 Turnstile 配置。"""
    return _get_turnstile_settings(config)


def verify_turnstile_token(secret_key: str, token: str, remote_ip: str = ''):
    """校验公共流程与后台流程共用的 Turnstile 令牌。"""
    return _verify_turnstile_token(secret_key=secret_key, token=token, remote_ip=remote_ip)


def _create_pending_login(root: Path, username: str, ip_addr: str):
    now_ts = int(time.time())
    pending_login_id = secrets.token_urlsafe(24)
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        state.setdefault('pending_logins', {})[pending_login_id] = {
            'username': _normalize_username(username),
            'ip_addr': str(ip_addr or '').strip(),
            'created_at': now_ts,
            'expires_at': now_ts + PENDING_LOGIN_EXPIRES_SECONDS,
            'send_count': 0,
            'verify_fail_count': 0,
            'last_sent_at': 0,
            'code_hash': '',
            'code_salt': '',
            'code_expires_at': 0,
            'used': False,
        }
        _save_email_auth_state(state_file, state)
    return pending_login_id


def _load_pending_login(root: Path, pending_login_id: str):
    now_ts = int(time.time())
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        item = (state.get('pending_logins') or {}).get(str(pending_login_id or '').strip())
        _save_email_auth_state(state_file, state)
    return item


def _delete_pending_login(root: Path, pending_login_id: str):
    state_file = _get_email_auth_state_file(root)
    pending_key = str(pending_login_id or '').strip()
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        pending = state.get('pending_logins', {})
        if isinstance(pending, dict):
            pending.pop(pending_key, None)
        _save_email_auth_state(state_file, state)


def _send_pending_login_code(root: Path, *, pending_login_id: str, email: str, smtp_settings):
    pending_key = str(pending_login_id or '').strip()
    state_file = _get_email_auth_state_file(root)
    now_ts = int(time.time())
    code_to_send = ''
    username = ''

    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        item = (state.get('pending_logins') or {}).get(pending_key)
        if not isinstance(item, dict):
            _save_email_auth_state(state_file, state)
            return False, '待验证登录已失效，请重新输入账号密码登录。', {}
        if int(item.get('expires_at', 0) or 0) <= now_ts:
            state.get('pending_logins', {}).pop(pending_key, None)
            _save_email_auth_state(state_file, state)
            return False, '待验证登录已过期，请重新登录。', {}
        last_sent_at = int(item.get('last_sent_at', 0) or 0)
        if last_sent_at > 0 and (now_ts - last_sent_at) < EMAIL_CODE_RESEND_COOLDOWN_SECONDS:
            resend_after = EMAIL_CODE_RESEND_COOLDOWN_SECONDS - (now_ts - last_sent_at)
            _save_email_auth_state(state_file, state)
            return False, f'验证码发送过于频繁，请 {resend_after} 秒后再试。', {'resend_after': resend_after}
        send_count = int(item.get('send_count', 0) or 0)
        if send_count >= EMAIL_CODE_MAX_SENDS:
            state.get('pending_logins', {}).pop(pending_key, None)
            _save_email_auth_state(state_file, state)
            return False, '验证码发送次数已达上限，请重新登录后再试。', {}

        code_to_send = _generate_email_code()
        code_salt = secrets.token_hex(8)
        item['code_salt'] = code_salt
        item['code_hash'] = _email_code_hash(code_to_send, code_salt)
        item['code_expires_at'] = now_ts + EMAIL_CODE_EXPIRES_SECONDS
        item['last_sent_at'] = now_ts
        item['send_count'] = send_count + 1
        item['verify_fail_count'] = 0
        username = _normalize_username(item.get('username', ''))
        state['pending_logins'][pending_key] = item
        _save_email_auth_state(state_file, state)

    html_body, text_body = _build_login_email_content(username, code_to_send)
    _send_smtp_mail(
        smtp_settings,
        to_email=email,
        subject=_build_login_email_subject(),
        html_body=html_body,
        text_body=text_body,
    )
    return True, '验证码已发送，请查收邮箱。', {
        'expires_in': EMAIL_CODE_EXPIRES_SECONDS,
        'resend_after': EMAIL_CODE_RESEND_COOLDOWN_SECONDS,
        'email_masked': _mask_email_address(email),
    }


def _verify_pending_login_code(root: Path, *, pending_login_id: str, code: str):
    pending_key = str(pending_login_id or '').strip()
    now_ts = int(time.time())
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        item = (state.get('pending_logins') or {}).get(pending_key)
        if not isinstance(item, dict):
            _save_email_auth_state(state_file, state)
            return False, '待验证登录已失效，请重新登录。', None
        if int(item.get('expires_at', 0) or 0) <= now_ts:
            state.get('pending_logins', {}).pop(pending_key, None)
            _save_email_auth_state(state_file, state)
            return False, '待验证登录已过期，请重新登录。', None
        if int(item.get('code_expires_at', 0) or 0) <= now_ts or not item.get('code_hash'):
            _save_email_auth_state(state_file, state)
            return False, '验证码已过期，请重新发送。', None
        if bool(item.get('used', False)):
            _save_email_auth_state(state_file, state)
            return False, '该验证码已使用，请重新登录。', None
        expected_hash = str(item.get('code_hash', '') or '').strip()
        code_salt = str(item.get('code_salt', '') or '').strip()
        if _email_code_hash(code, code_salt) != expected_hash:
            item['verify_fail_count'] = int(item.get('verify_fail_count', 0) or 0) + 1
            if item['verify_fail_count'] >= EMAIL_CODE_MAX_VERIFY_FAILURES:
                state.get('pending_logins', {}).pop(pending_key, None)
                _save_email_auth_state(state_file, state)
                return False, '验证码连续输错次数过多，请重新登录。', None
            state['pending_logins'][pending_key] = item
            _save_email_auth_state(state_file, state)
            return False, '邮箱验证码错误，请重新输入。', None
        item['used'] = True
        state['pending_logins'][pending_key] = item
        payload = dict(item)
        _save_email_auth_state(state_file, state)
        return True, '', payload


def _send_binding_code(root: Path, *, username: str, email: str, smtp_settings):
    normalized_username = _normalize_username(username)
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return False, '请先输入邮箱地址。', {}
    now_ts = int(time.time())
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        item = (state.get('binding_codes') or {}).get(normalized_username, {})
        if not isinstance(item, dict):
            item = {}
        last_sent_at = int(item.get('last_sent_at', 0) or 0)
        if last_sent_at > 0 and (now_ts - last_sent_at) < EMAIL_CODE_RESEND_COOLDOWN_SECONDS:
            resend_after = EMAIL_CODE_RESEND_COOLDOWN_SECONDS - (now_ts - last_sent_at)
            _save_email_auth_state(state_file, state)
            return False, f'验证码发送过于频繁，请 {resend_after} 秒后再试。', {'resend_after': resend_after}
        send_count = int(item.get('send_count', 0) or 0)
        if send_count >= EMAIL_CODE_MAX_SENDS:
            state.get('binding_codes', {}).pop(normalized_username, None)
            _save_email_auth_state(state_file, state)
            return False, '邮箱验证码发送次数已达上限，请稍后重试。', {}

        code = _generate_email_code()
        salt = secrets.token_hex(8)
        state.setdefault('binding_codes', {})[normalized_username] = {
            'email': normalized_email,
            'code_hash': _email_code_hash(code, salt),
            'code_salt': salt,
            'send_count': send_count + 1,
            'verify_fail_count': 0,
            'last_sent_at': now_ts,
            'expires_at': now_ts + EMAIL_CODE_EXPIRES_SECONDS,
        }
        _save_email_auth_state(state_file, state)

    html_body, text_body = _build_binding_email_content(normalized_username, code)
    _send_smtp_mail(
        smtp_settings,
        to_email=normalized_email,
        subject='后台邮箱绑定验证码',
        html_body=html_body,
        text_body=text_body,
    )
    return True, '绑定验证码已发送，请查收邮箱。', {
        'expires_in': EMAIL_CODE_EXPIRES_SECONDS,
        'resend_after': EMAIL_CODE_RESEND_COOLDOWN_SECONDS,
        'email_masked': _mask_email_address(normalized_email),
    }


def _verify_binding_code(root: Path, *, username: str, email: str, code: str):
    normalized_username = _normalize_username(username)
    normalized_email = _normalize_email(email)
    now_ts = int(time.time())
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        _prune_email_auth_state(state, now_ts)
        item = (state.get('binding_codes') or {}).get(normalized_username)
        if not isinstance(item, dict):
            _save_email_auth_state(state_file, state)
            return False, '绑定验证码已失效，请重新发送。'
        if _normalize_email(item.get('email', '')) != normalized_email:
            _save_email_auth_state(state_file, state)
            return False, '当前邮箱与发送验证码的邮箱不一致，请重新发送验证码。'
        if int(item.get('expires_at', 0) or 0) <= now_ts:
            state.get('binding_codes', {}).pop(normalized_username, None)
            _save_email_auth_state(state_file, state)
            return False, '绑定验证码已过期，请重新发送。'
        if _email_code_hash(code, str(item.get('code_salt', '') or '').strip()) != str(item.get('code_hash', '') or '').strip():
            item['verify_fail_count'] = int(item.get('verify_fail_count', 0) or 0) + 1
            if item['verify_fail_count'] >= EMAIL_CODE_MAX_VERIFY_FAILURES:
                state.get('binding_codes', {}).pop(normalized_username, None)
                _save_email_auth_state(state_file, state)
                return False, '验证码连续输错次数过多，请重新发送。'
            state['binding_codes'][normalized_username] = item
            _save_email_auth_state(state_file, state)
            return False, '邮箱验证码错误，请重新输入。'
        state.get('binding_codes', {}).pop(normalized_username, None)
        _save_email_auth_state(state_file, state)
    return True, ''


def _clear_smtp_notice_history(root: Path):
    state_file = _get_email_auth_state_file(root)
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        state['smtp_notice_history'] = {}
        _save_email_auth_state(state_file, state)


def _maybe_send_smtp_expiry_notice(*, root: Path, get_config):
    config = get_config() or {}
    settings = _get_email_auth_settings(config)
    notice_email = _normalize_email(settings.get('smtp_notice_email', ''))
    remaining_days = settings.get('remaining_days')
    if not notice_email or remaining_days is None or not settings.get('smtp_password_expires_at', ''):
        return
    if remaining_days not in SMTP_REMINDER_DAYS:
        return
    if not settings.get('configured') or settings.get('expired'):
        return

    today = now_beijing().strftime('%Y-%m-%d')
    state_file = _get_email_auth_state_file(root)
    key = str(remaining_days)
    should_send = False
    with EMAIL_AUTH_STATE_LOCK:
        state = _load_email_auth_state(state_file)
        history = state.setdefault('smtp_notice_history', {})
        last_sent = str(history.get(key, '') or '').strip()
        if last_sent != today:
            history[key] = today
            should_send = True
            _save_email_auth_state(state_file, state)
    if not should_send:
        return
    html_body, text_body = _build_smtp_notice_content(remaining_days, settings.get('smtp_password_expires_at', ''))
    _send_smtp_mail(
        settings,
        to_email=notice_email,
        subject='后台 SMTP 授权码即将到期提醒',
        html_body=html_body,
        text_body=text_body,
    )


def _start_smtp_reminder_worker_once(*, app, root: Path, get_config):
    if getattr(app, '_admin_smtp_reminder_started', False):
        return
    with SMTP_REMINDER_THREAD_LOCK:
        if getattr(app, '_admin_smtp_reminder_started', False):
            return

        def worker():
            last_run_date = ''
            while True:
                try:
                    today = now_beijing().strftime('%Y-%m-%d')
                    if today != last_run_date:
                        _maybe_send_smtp_expiry_notice(root=root, get_config=get_config)
                        last_run_date = today
                except Exception:
                    pass
                time.sleep(3600)

        thread = threading.Thread(target=worker, name='admin-smtp-expiry-reminder', daemon=True)
        thread.start()
        app._admin_smtp_reminder_started = True


def _is_admin_session_expired(sess) -> bool:
    if not sess.get('admin_logged_in'):
        return True
    now_ts = int(time.time())
    try:
        login_at = int(sess.get('admin_login_at') or 0)
    except Exception:
        login_at = 0
    try:
        ttl = int(sess.get('admin_session_ttl') or ADMIN_SESSION_MAX_AGE_SECONDS)
    except Exception:
        ttl = ADMIN_SESSION_MAX_AGE_SECONDS
    if ttl <= 0:
        ttl = ADMIN_SESSION_MAX_AGE_SECONDS
    if login_at <= 0:
        return True
    return (now_ts - login_at) > ttl


def _is_same_origin_request(req) -> bool:
    """后台写操作使用的基础同源校验。"""
    return is_same_origin_request(req, trust_proxy_headers_default=False)


def _to_display_time(dt_value):
    """将日期时间对象格式化为统一展示字符串。"""
    if not isinstance(dt_value, datetime):
        return ''
    return dt_value.strftime('%Y-%m-%d %H:%M:%S')


def _get_changelog_dir(project_root: Path) -> Path:
    """从环境变量或默认目录中获取更新日志目录。"""
    explicit = (os.environ.get('APP_CHANGELOG_DIR') or '').strip()
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        return p
    return (project_root / 'update_logs').resolve()


def _find_local_update_logs(project_root: Path):
    """定位更新日志目录下的本地 Markdown 日志文件。"""
    explicit_file = (os.environ.get('APP_CHANGELOG_FILE') or '').strip()
    if explicit_file:
        p = Path(explicit_file).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if p.exists() and p.is_file():
            return [p]
        return []

    changelog_dir = _get_changelog_dir(project_root)
    if not changelog_dir.exists() or not changelog_dir.is_dir():
        return []

    files = [p for p in changelog_dir.glob('*.md') if p.is_file()]
    return sorted(files, key=lambda p: p.name, reverse=True)


def _extract_updates_from_markdown(text: str, limit: int):
    """从 Markdown 中提取逻辑上的更新条目，并合并嵌套子项。"""
    items = []
    current = ''
    in_code_block = False

    for raw in text.splitlines():
        line = (raw or '').rstrip()
        stripped = line.strip()

        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            continue

        bullet_match = re.match(r'^(\s*)[-*]\s+(.+)$', line)
        if bullet_match:
            indent = len((bullet_match.group(1) or '').expandtabs(4))
            value = re.sub(r'\s+', ' ', (bullet_match.group(2) or '').strip())
            if not value:
                continue

            # 一级列表项会开启一条新的更新记录。
            if indent <= 1 or not current:
                if current:
                    items.append(current.strip())
                    if len(items) >= limit:
                        return items[:limit]
                current = value
            else:
                # 二级列表项归属到上一条一级更新记录。
                current = f"{current}\n• {value}".strip()
            continue

        numbered_match = re.match(r'^(\s*)\d+[.)]\s+(.+)$', line)
        if numbered_match:
            indent = len((numbered_match.group(1) or '').expandtabs(4))
            value = re.sub(r'\s+', ' ', (numbered_match.group(2) or '').strip())
            if not value:
                continue

            if indent > 1 and current:
                current = f"{current}\n• {value}".strip()
            else:
                if current:
                    items.append(current.strip())
                    if len(items) >= limit:
                        return items[:limit]
                current = value
            continue

        # 连续文本追加到当前记录，不新建列表项。
        if current and not stripped.startswith('#'):
            continuation = re.sub(r'\s+', ' ', stripped)
            if continuation:
                current = f"{current} {continuation}".strip()

    if current and len(items) < limit:
        items.append(current.strip())
    return items[:limit]


def _extract_markdown_field(text: str, patterns):
    """使用正则模式提取单行字段值。"""
    for raw in text.splitlines():
        line = (raw or '').strip()
        if not line:
            continue
        for pattern in patterns:
            m = re.search(pattern, line, flags=re.IGNORECASE)
            if m:
                value = (m.group(1) or '').strip().strip('`')
                if value:
                    return value
    return ''


def _normalize_version_text(raw: str):
    value = (raw or '').strip()
    if not value:
        return ''
    if value.lower().startswith('v'):
        return value
    return f'v{value}'


def _extract_release_from_markdown(log_file: Path, item_limit: int):
    """从单个 Markdown 文件构建一条结构化发布记录。"""
    try:
        text = log_file.read_text(encoding='utf-8')
    except Exception:
        return None

    version = _normalize_version_text(_extract_markdown_field(
        text,
        (
            r'版本(?:号)?\s*[:：]\s*(.+)$',
            r'VERSION\s*[:：]\s*(.+)$',
        ),
    ))
    if not version:
        m_version = re.search(r'v(\d+(?:\.\d+)*)', log_file.name, flags=re.IGNORECASE)
        if m_version:
            version = f"v{m_version.group(1)}"

    build_time_raw = _extract_markdown_field(
        text,
        (
            r'构建时间\s*[:：]\s*(.+)$',
            r'更新时间\s*[:：]\s*(.+)$',
            r'BUILD(?:_TIME)?\s*[:：]\s*(.+)$',
            r'DATE\s*[:：]\s*(.+)$',
        ),
    )
    build_dt = _parse_datetime_safe(build_time_raw)
    if not build_dt:
        m_date = re.search(r'(\d{4}-\d{2}-\d{2})', log_file.name)
        if m_date:
            build_dt = _parse_datetime_safe(m_date.group(1))
    if not build_dt:
        try:
            build_dt = datetime.fromtimestamp(log_file.stat().st_mtime, tz=BEIJING_TZ)
        except OSError:
            build_dt = now_beijing()

    if not version:
        version = f"v{build_dt.strftime('%Y.%m.%d')}"

    updates = _extract_updates_from_markdown(text, item_limit)
    if not updates:
        updates = [f'已读取本地更新日志：{log_file.name}']

    return {
        'version': version,
        'build_time': _to_display_time(build_dt),
        'updates': updates[:item_limit],
        '_sort_key': build_dt.timestamp(),
    }


def _build_local_changelog_history(project_root: Path, release_limit: int, item_limit: int):
    """根据本地 Markdown 文件构建结构化更新历史。"""
    files = _find_local_update_logs(project_root)
    if not files:
        return []

    history = []
    for log_file in files:
        release = _extract_release_from_markdown(log_file, item_limit)
        if release:
            history.append(release)

    if not history:
        return []

    history.sort(key=lambda item: item.get('_sort_key', 0), reverse=True)
    normalized = []
    for item in history[:release_limit]:
        normalized.append({
            'version': item.get('version', 'v1.0.0'),
            'build_time': item.get('build_time', ''),
            'updates': item.get('updates', []),
        })
    return normalized


def build_admin_changelog_payload(project_root=None):
    """根据本地日志、环境变量或 Git 元数据构建后台更新日志载荷。"""
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]

    release_limit_raw = (os.environ.get('APP_CHANGELOG_LIMIT') or '20').strip()
    item_limit_raw = (os.environ.get('APP_CHANGELOG_ITEM_LIMIT') or '12').strip()
    try:
        release_limit = max(1, min(int(release_limit_raw), 50))
    except ValueError:
        release_limit = 20
    try:
        item_limit = max(1, min(int(item_limit_raw), 50))
    except ValueError:
        item_limit = 12

    history = _build_local_changelog_history(root, release_limit, item_limit)
    if history:
        latest = history[0]
        return {
            'version': latest.get('version', 'v1.0.0'),
            'build_time': latest.get('build_time', ''),
            'updates': latest.get('updates', []),
            'history': history,
        }

    version = (os.environ.get('APP_VERSION') or '').strip()
    build_time = (os.environ.get('APP_BUILD_TIME') or '').strip()

    if not version:
        rev = _run_git_command(['rev-parse', '--short', 'HEAD'], root)
        if rev:
            version = f'v{rev}'

    if not build_time:
        build_time = _run_git_command(
            ['show', '-s', '--format=%cd', '--date=format:%Y-%m-%d %H:%M:%S', 'HEAD'],
            root,
        )

    updates_text = _run_git_command(['log', f'-n{item_limit}', '--pretty=%s'], root)
    updates = [line.strip() for line in updates_text.splitlines() if line.strip()] if updates_text else []

    if not version:
        version = 'v1.0.0'
    if not build_time:
        build_time = now_beijing().strftime('%Y-%m-%d %H:%M:%S')
    if not updates:
        updates = ['新增后台「更新日志」菜单，可查看版本号、构建时间与更新内容。']

    return {
        'version': version,
        'build_time': build_time,
        'updates': updates[:item_limit],
        'history': [{
            'version': version,
            'build_time': build_time,
            'updates': updates[:item_limit],
        }],
    }



# 路由注册入口。
def register_admin_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
    append_admin_login_log,
    load_admin_login_logs,
    admin_login_log_lock,
    project_root=None,
    resolve_ip_location=None,
    resolve_ip_country_code=None,
):
    """向 Flask 应用注册后台管理相关路由。"""
    _resolve_ip_location = resolve_ip_location if resolve_ip_location else lambda ip: '未知'
    _resolve_ip_country_code = resolve_ip_country_code if resolve_ip_country_code else lambda ip: ''
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    try:
        _ensure_admin_users_store(root, get_config, update_config)
    except Exception:
        # 即使初始化迁移暂时异常，也尽量保持路由可用。
        pass
    _start_smtp_reminder_worker_once(app=app, root=root, get_config=get_config)

    def _build_admin_html_response(directory: str, filename: str = 'index.html'):
        resp = make_response(send_from_directory(directory, filename))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'same-origin'
        return resp

    @app.route('/admin/index.html')
    @app.route('/admin', strict_slashes=False)
    def admin_page():
        """后台登录页与控制台入口页面。"""
        return _build_admin_html_response('admin')

    @app.route('/api/admin/ip-preflight', methods=['GET'])
    def admin_ip_preflight():
        """登录前 IP 预检：返回客户端 IP、归属地和是否允许登录。"""
        ip_addr = _get_request_ip(request)
        location = _resolve_ip_location(ip_addr)
        country_code = _resolve_ip_country_code(ip_addr)
        allowed, reason = _is_ip_country_allowed(
            ip_addr, ALLOWED_LOGIN_COUNTRIES, _resolve_ip_country_code
        )
        return jsonify({
            'ip': ip_addr,
            'location': location,
            'country_code': country_code,
            'allowed': allowed,
            'reason': reason,
        })

    @app.route('/api/admin/security/turnstile/public', methods=['GET'])
    def admin_turnstile_public_config():
        """获取登录页 Turnstile 组件使用的公开配置。"""
        config = get_config()
        settings = _get_turnstile_settings(config)
        return jsonify({
            'enabled': settings['enabled'],
            'site_key': settings['site_key'] if settings['enabled'] else ''
        })

    @app.route('/api/admin/security/turnstile', methods=['GET'])
    @login_required
    def admin_turnstile_config():
        """获取后台面板使用的 Turnstile 配置。"""
        settings = _get_turnstile_settings(get_config())
        secret_masked = ''
        if settings['secret_key']:
            secret = settings['secret_key']
            secret_masked = f"{secret[:6]}...{secret[-4:]}" if len(secret) > 12 else '***'
        return jsonify({
            'enabled': settings['enabled'],
            'site_key': settings['site_key'],
            'secret_key': secret_masked
        })

    @app.route('/api/admin/security/turnstile', methods=['POST'])
    @login_required
    def admin_turnstile_update():
        """更新后台登录保护使用的 Turnstile 配置。"""
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403
        data = request.get_json(silent=True) or {}
        enabled = _parse_bool(data.get('enabled', False), False)
        site_key = str(data.get('site_key', '') or '').strip()
        secret_key_input = str(data.get('secret_key', '') or '').strip()

        config = get_config()
        existing_secret = str(config.get('turnstile_secret_key', '') or '').strip()
        # 提交的是掩码值或空值时，保留现有密钥。
        if secret_key_input and not secret_key_input.startswith('***'):
            secret_key = secret_key_input
        else:
            secret_key = existing_secret

        if enabled and (not site_key or not secret_key):
            return jsonify({'success': False, 'message': '启用 Turnstile 时必须填写站点密钥和服务端密钥'}), 400

        update_config({
            'turnstile_enabled': bool(enabled),
            'turnstile_site_key': site_key,
            'turnstile_secret_key': secret_key
        })
        return jsonify({'success': True, 'message': '登录验证设置已保存'})

    @app.route('/api/admin/email-auth/public', methods=['GET'])
    def admin_email_auth_public():
        settings = _get_email_auth_settings(get_config() or {})
        return jsonify({
            'email_auth_enabled': bool(settings.get('enabled', False)),
            'smtp_ready': bool(_smtp_ready_for_email_auth(settings)),
            'smtp_password_expired': bool(settings.get('expired', False)),
        })

    @app.route('/api/admin/email-auth/config', methods=['GET'])
    @login_required
    def admin_email_auth_config():
        config = get_config() or {}
        return jsonify(_build_smtp_status_payload(config))

    @app.route('/api/admin/email-auth/config', methods=['POST'])
    @login_required
    def admin_email_auth_config_update():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        data = request.get_json(silent=True) or {}
        config = get_config() or {}
        existing_password = str(config.get('smtp_password_or_app_code', '') or '').strip()
        password_input = str(data.get('smtp_password_or_app_code', '') or '').strip()
        password_value = password_input if password_input and not password_input.startswith('***') else existing_password

        updates = {
            'email_auth_enabled': _parse_bool(data.get('email_auth_enabled', False), False),
            'smtp_host': str(data.get('smtp_host', '') or '').strip(),
            'smtp_port': int(data.get('smtp_port') or 465),
            'smtp_username': str(data.get('smtp_username', '') or '').strip(),
            'smtp_password_or_app_code': password_value,
            'smtp_use_ssl': _parse_bool(data.get('smtp_use_ssl', True), True),
            'smtp_use_tls': _parse_bool(data.get('smtp_use_tls', False), False),
            'smtp_from_name': str(data.get('smtp_from_name', '') or '').strip(),
            'smtp_from_email': _normalize_email(data.get('smtp_from_email', '')),
            'smtp_notice_email': _normalize_email(data.get('smtp_notice_email', '')),
        }
        if password_input and not password_input.startswith('***'):
            now_iso = now_beijing().isoformat(timespec='seconds')
            updates['smtp_password_set_at'] = now_iso
            updates['smtp_password_expires_at'] = (now_beijing() + timedelta(days=SMTP_PASSWORD_VALID_DAYS)).isoformat(timespec='seconds')

        merged = dict(config)
        merged.update(updates)
        smtp_settings = _get_email_auth_settings(merged)
        if updates['email_auth_enabled'] and not smtp_settings['configured']:
            return jsonify({'success': False, 'message': '启用邮箱验证前，请先完整填写 SMTP 配置。'}), 400

        update_config(updates)
        if password_input and not password_input.startswith('***'):
            _clear_smtp_notice_history(root)
        return jsonify({
            'success': True,
            'message': 'SMTP 与邮箱验证设置已保存。',
            'config': _build_smtp_status_payload(get_config() or {}),
        })

    @app.route('/api/admin/email-auth/test', methods=['POST'])
    @login_required
    def admin_email_auth_test():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        smtp_settings = _get_email_auth_settings(get_config() or {})
        target_email = _normalize_email(data.get('target_email') or smtp_settings.get('smtp_notice_email') or smtp_settings.get('smtp_from_email'))
        if not target_email:
            return jsonify({'success': False, 'message': '请先设置 SMTP 通知邮箱或发件邮箱。'}), 400
        if not smtp_settings['configured']:
            return jsonify({'success': False, 'message': 'SMTP 配置不完整，无法发送测试邮件。'}), 400
        try:
            _send_smtp_mail(
                smtp_settings,
                to_email=target_email,
                subject='后台 SMTP 测试邮件',
                html_body='<div style="font-family:Arial,Microsoft YaHei,sans-serif;line-height:1.7;"><h2>SMTP 测试成功</h2><p>这是一封来自后台站点设置的测试邮件，说明当前 SMTP 配置可用。</p></div>',
                text_body='SMTP 测试成功，这是一封来自后台站点设置的测试邮件。',
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'SMTP 测试失败：{exc}'}), 400
        return jsonify({'success': True, 'message': f'测试邮件已发送到 {target_email}'})

    def _finalize_login_success(login_user, ip_addr: str, *, binding_required: bool = False, detail_suffix: str = ''):
        is_hidden_admin = _is_hidden_admin_record(login_user)
        is_super_admin = bool((login_user or {}).get('role') == 'super_admin')
        permissions = _normalize_permissions((login_user or {}).get('permissions', []), is_super_admin=is_super_admin)
        login_username = _normalize_username((login_user or {}).get('username', ''))
        _set_logged_in_session(
            session,
            user=login_user,
            permissions=permissions,
            is_super_admin=is_super_admin,
            is_hidden_admin=is_hidden_admin,
            binding_required=binding_required,
        )
        prev_last_login_at, prev_last_login_ip, current_login_at = _save_login_success(
            root, get_config, update_config, login_username, ip_addr
        )
        append_admin_login_log(
            operation='admin_login',
            success=True,
            username=login_username,
            detail=detail_suffix or ('凭据校验通过；role: super_admin' if is_super_admin else '凭据校验通过；role: sub_admin'),
            hidden_account=is_hidden_admin,
        )
        return jsonify({
            'success': True,
            'binding_required': bool(binding_required),
            'last_login_at': prev_last_login_at,
            'last_login_ip': prev_last_login_ip,
            'current_login_at': current_login_at,
            'current_login_ip': ip_addr,
        })

    def _perform_login_start():
        data = request.form if request.form else request.get_json(silent=True) or {}
        username = str(data.get('username', '') or '').strip()
        password = str(data.get('password', '') or '')
        turnstile_token = str(data.get('turnstileToken', '') or data.get('cf_turnstile_response', '') or '').strip()
        ip_addr = _get_request_ip(request)
        now_ts = int(time.time())
        attempts_file = _get_login_attempts_file(root)
        config = get_config() or {}
        turnstile_settings = _get_turnstile_settings(config)
        smtp_settings = _get_email_auth_settings(config)

        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user, _ = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)

        is_hidden_admin = _is_hidden_admin_record(login_user)
        country_allowed, country_reason = _is_ip_country_allowed(ip_addr, ALLOWED_LOGIN_COUNTRIES, _resolve_ip_country_code)
        if not country_allowed:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=username,
                detail=country_reason,
                hidden_account=is_hidden_admin,
            )
            return jsonify({'success': False, 'message': country_reason}), 403

        turnstile_ok = True
        turnstile_fail_reason = ''
        if turnstile_settings['enabled']:
            if not turnstile_token:
                turnstile_ok = False
                turnstile_fail_reason = '请先完成人机验证。'
            else:
                turnstile_ok, detail = _verify_turnstile_token(
                    secret_key=turnstile_settings['secret_key'],
                    token=turnstile_token,
                    remote_ip=ip_addr,
                )
                if not turnstile_ok:
                    turnstile_fail_reason = detail or '人机验证失败，请重试。'

        user_enabled = bool(login_user and login_user.get('enabled', True))
        user_password_hash = str((login_user or {}).get('password_hash', '') or '').strip()
        password_ok = bool(login_user) and user_enabled and _verify_password(user_password_hash, password)
        credentials_ok = bool(turnstile_ok and password_ok)
        login_username = _normalize_username((login_user or {}).get('username', '') or username)

        if not username and not password:
            fail_reason = '用户名和密码不能为空。'
        elif not username:
            fail_reason = '请输入用户名。'
        elif not password:
            fail_reason = '请输入密码。'
        elif turnstile_settings['enabled'] and not turnstile_ok:
            fail_reason = turnstile_fail_reason or '人机验证失败，请重试。'
        elif login_user and not user_enabled:
            fail_reason = '该账号已被停用，请联系管理员。'
        else:
            fail_reason = '用户名或密码错误。'

        failed_payload = None
        failed_status = 401
        failed_detail = ''
        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            blocked_until = int(ip_item.get('blocked_until', 0) or 0) if isinstance(ip_item, dict) else 0
            delay_seconds = _get_login_delay_seconds(attempts_state, ip_addr, now_ts)
            if blocked_until > now_ts:
                _save_login_attempts(attempts_file, attempts_state)
                blocked_at = _format_blocked_until(blocked_until)
                failed_payload = {'success': False, 'message': f'当前登录 IP 已被封禁至 {blocked_at}，请稍后再试。'}
                failed_status = 429
                failed_detail = f'IP 已封禁至 {blocked_at or blocked_until}'
            elif delay_seconds > 0:
                wait_hint = f'{delay_seconds // 60}m {delay_seconds % 60}s' if delay_seconds >= 60 else f'{delay_seconds}s'
                failed_payload = {'success': False, 'message': f'失败次数过多，请等待 {wait_hint} 后再试。'}
                failed_status = 429
                failed_detail = f'登录已触发延迟保护，等待 {wait_hint}'
                _save_login_attempts(attempts_file, attempts_state)
            elif credentials_ok:
                _reset_login_attempts_for_ip(attempts_state, ip_addr)
                _save_login_attempts(attempts_file, attempts_state)
            else:
                _set_login_delay(attempts_state, ip_addr, now_ts)
                is_blocked_now, blocked_until, _remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
                if is_blocked_now:
                    blocked_at = _format_blocked_until(blocked_until)
                    failed_payload = {'success': False, 'message': f'{fail_reason} 同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'}
                    failed_status = 429
                    failed_detail = f'{fail_reason}；已封禁至 {blocked_at or blocked_until}'
                else:
                    failed_payload = {'success': False, 'message': f'{fail_reason} 已触发延迟保护，请稍后再试。'}
                    failed_status = 400 if fail_reason != '用户名或密码错误。' else 401
                    failed_detail = f'{fail_reason}；已触发延迟保护'

        if failed_payload is not None:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=username,
                detail=failed_detail,
                hidden_account=is_hidden_admin,
            )
            return jsonify(failed_payload), failed_status

        if smtp_settings['enabled'] and not _smtp_ready_for_email_auth(smtp_settings):
            return jsonify({'success': False, 'message': '邮箱验证已启用，但 SMTP 配置不可用或已过期，请联系管理员更新。'}), 503

        if smtp_settings['enabled'] and _has_verified_email(login_user):
            pending_login_id = _create_pending_login(root, login_username, ip_addr)
            _set_pending_login_session(session, pending_login_id=pending_login_id, username=login_username, ip_addr=ip_addr)
            return jsonify({
                'success': True,
                'requires_email_code': True,
                'pending_login_id': pending_login_id,
                'email_masked': _mask_email_address(login_user.get('email', '')),
                'message': '账号密码已验证，请发送邮箱验证码。',
            })

        return _finalize_login_success(
            login_user,
            ip_addr,
            binding_required=bool(smtp_settings['enabled'] and not _has_verified_email(login_user)),
            detail_suffix='凭据校验通过；已进入后台' + ('；需绑定安全邮箱' if smtp_settings['enabled'] and not _has_verified_email(login_user) else ''),
        )

    @app.route('/admin/login/start', methods=['POST'])
    def admin_login_start():
        return _perform_login_start()

    @app.route('/admin/login/send-email-code', methods=['POST'])
    def admin_login_send_email_code():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        pending_login_id = str(data.get('pending_login_id') or session.get('admin_pending_login_id') or '').strip()
        pending_login = _load_pending_login(root, pending_login_id)
        if not isinstance(pending_login, dict):
            _clear_pending_login_session(session)
            return jsonify({'success': False, 'message': '待验证登录已失效，请重新输入账号密码。'}), 401
        username = _normalize_username(pending_login.get('username', ''))
        if username != _normalize_username(session.get('admin_pending_username', '')):
            return jsonify({'success': False, 'message': '待验证登录信息不匹配，请重新登录。'}), 401

        smtp_settings = _get_email_auth_settings(get_config() or {})
        if not smtp_settings['enabled'] or not _smtp_ready_for_email_auth(smtp_settings):
            return jsonify({'success': False, 'message': '当前邮箱验证不可用，请联系管理员。'}), 503
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user, _ = _find_user(users_data, username)
        if login_user is None or not _has_verified_email(login_user):
            return jsonify({'success': False, 'message': '当前账号未绑定可用邮箱，请联系管理员。'}), 400

        try:
            ok, message, payload = _send_pending_login_code(
                root,
                pending_login_id=pending_login_id,
                email=login_user.get('email', ''),
                smtp_settings=smtp_settings,
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'验证码邮件发送失败：{exc}'}), 400
        if not ok:
            return jsonify({'success': False, 'message': message, **payload}), 400
        return jsonify({'success': True, 'message': message, **payload})

    @app.route('/admin/login/verify-email-code', methods=['POST'])
    def admin_login_verify_email_code():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        pending_login_id = str(data.get('pending_login_id') or session.get('admin_pending_login_id') or '').strip()
        code = str(data.get('code', '') or '').strip()
        if not code:
            return jsonify({'success': False, 'message': '请输入邮箱验证码。'}), 400
        ok, message, pending_login = _verify_pending_login_code(root, pending_login_id=pending_login_id, code=code)
        if not ok:
            return jsonify({'success': False, 'message': message}), 400

        username = _normalize_username((pending_login or {}).get('username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user, _ = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)
        if login_user is None or not _has_verified_email(login_user):
            _delete_pending_login(root, pending_login_id)
            return jsonify({'success': False, 'message': '账号邮箱状态已变化，请重新登录。'}), 400

        _delete_pending_login(root, pending_login_id)
        return _finalize_login_success(login_user, str((pending_login or {}).get('ip_addr', '') or ''), detail_suffix='凭据校验通过；邮箱验证码通过')

    @app.route('/api/admin/account/email-binding', methods=['GET'])
    @login_required
    def admin_email_binding_status():
        current_admin = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            current_user, _ = _find_user(users_data, current_admin)
        if current_user is None:
            return jsonify({'success': False, 'message': '当前登录状态已失效，请重新登录。'}), 401
        return jsonify({
            'success': True,
            'username': current_admin,
            'email': _normalize_email(current_user.get('email', '')),
            'email_masked': _mask_email_address(current_user.get('email', '')),
            'email_verified': bool(current_user.get('email_verified', False)),
            'binding_required': _is_binding_required_session(session),
        })

    @app.route('/api/admin/account/email-binding/send-code', methods=['POST'])
    @login_required
    def admin_email_binding_send_code():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        target_email = _normalize_email(data.get('email', ''))
        if not target_email or '@' not in target_email:
            return jsonify({'success': False, 'message': '请输入有效的邮箱地址。'}), 400
        smtp_settings = _get_email_auth_settings(get_config() or {})
        if not smtp_settings['enabled'] or not _smtp_ready_for_email_auth(smtp_settings):
            return jsonify({'success': False, 'message': '当前邮箱绑定不可用，请联系管理员。'}), 503

        current_admin = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            duplicated = _find_user_by_email(users_data, target_email, exclude_username=current_admin)
            if duplicated is not None:
                return jsonify({'success': False, 'message': '该邮箱已绑定其他后台账号，请更换邮箱。'}), 400

        try:
            ok, message, payload = _send_binding_code(
                root,
                username=current_admin,
                email=target_email,
                smtp_settings=smtp_settings,
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'绑定验证码发送失败：{exc}'}), 400
        if not ok:
            return jsonify({'success': False, 'message': message, **payload}), 400
        return jsonify({'success': True, 'message': message, **payload})

    @app.route('/api/admin/account/email-binding/verify', methods=['POST'])
    @login_required
    def admin_email_binding_verify():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        target_email = _normalize_email(data.get('email', ''))
        code = str(data.get('code', '') or '').strip()
        if not target_email or '@' not in target_email:
            return jsonify({'success': False, 'message': '请输入有效的邮箱地址。'}), 400
        if not code:
            return jsonify({'success': False, 'message': '请输入邮箱验证码。'}), 400

        current_admin = _normalize_username(session.get('admin_username', ''))
        ok, message = _verify_binding_code(root, username=current_admin, email=target_email, code=code)
        if not ok:
            return jsonify({'success': False, 'message': message}), 400

        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            duplicated = _find_user_by_email(users_data, target_email, exclude_username=current_admin)
            if duplicated is not None:
                return jsonify({'success': False, 'message': '该邮箱已绑定其他后台账号，请更换邮箱。'}), 400
            current_user, idx = _find_user(users_data, current_admin)
            if current_user is None or idx < 0:
                return jsonify({'success': False, 'message': '当前登录状态已失效，请重新登录。'}), 401
            updated_user = dict(current_user)
            now_iso = now_beijing().isoformat(timespec='seconds')
            updated_user['email'] = target_email
            updated_user['email_verified'] = True
            updated_user['email_bound_at'] = now_iso
            updated_user['updated_at'] = now_iso
            users_data['users'][idx] = _sanitize_user_record(
                updated_user,
                fallback_username=current_admin,
                is_super_admin=bool(str(current_user.get('role') or '') == 'super_admin'),
                force_hidden=bool(current_user.get('hidden', False)),
            )
            _save_admin_users(users_file, users_data)

        session['admin_binding_required'] = False
        append_admin_login_log(
            operation='admin_email_binding',
            success=True,
            username=current_admin,
            detail=f'已绑定邮箱：{target_email}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': '安全邮箱绑定成功。', 'email_masked': _mask_email_address(target_email)})

    @app.route('/admin/login', methods=['POST'])
    def admin_login():
        return _perform_login_start()
        """Handle admin login."""
        data = request.form if request.form else request.get_json(silent=True) or {}
        username = str(data.get('username', '') or '').strip()
        password = str(data.get('password', '') or '')
        turnstile_token = str(data.get('turnstileToken', '') or data.get('cf_turnstile_response', '') or '').strip()
        ip_addr = _get_request_ip(request)
        now_ts = int(time.time())
        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        attempts_file = _get_login_attempts_file(root)
        config = get_config() or {}
        turnstile_settings = _get_turnstile_settings(config)

        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user, _ = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)

        is_hidden_admin = _is_hidden_admin_record(login_user)

        country_allowed, country_reason = _is_ip_country_allowed(
            ip_addr, ALLOWED_LOGIN_COUNTRIES, _resolve_ip_country_code
        )
        if not country_allowed:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=username,
                detail=country_reason,
                hidden_account=is_hidden_admin,
            )
            return jsonify({'success': False, 'message': country_reason}), 403

        turnstile_ok = True
        turnstile_fail_reason = ''
        if turnstile_settings['enabled']:
            if not turnstile_token:
                turnstile_ok = False
                turnstile_fail_reason = '请先完成人机验证。'
            else:
                turnstile_ok, detail = _verify_turnstile_token(
                    secret_key=turnstile_settings['secret_key'],
                    token=turnstile_token,
                    remote_ip=ip_addr,
                )
                if not turnstile_ok:
                    turnstile_fail_reason = detail or '人机验证失败，请重试。'

        user_enabled = bool(login_user and login_user.get('enabled', True))
        user_password_hash = str((login_user or {}).get('password_hash', '') or '').strip()
        password_ok = bool(login_user) and user_enabled and _verify_password(user_password_hash, password)
        credentials_ok = bool(turnstile_ok and password_ok)

        is_super_admin = bool((login_user or {}).get('role') == 'super_admin')
        user_permissions = _normalize_permissions((login_user or {}).get('permissions', []), is_super_admin=is_super_admin)
        login_username = _normalize_username((login_user or {}).get('username', '') or username)

        if not username and not password:
            fail_reason = '用户名和密码不能为空。'
        elif not username:
            fail_reason = '请输入用户名。'
        elif not password:
            fail_reason = '请输入密码。'
        elif turnstile_settings['enabled'] and not turnstile_ok:
            fail_reason = turnstile_fail_reason or '人机验证失败，请重试。'
        elif login_user and not user_enabled:
            fail_reason = '该账号已被停用，请联系管理员。'
        else:
            fail_reason = '用户名或密码错误。'

        failed_payload = None
        failed_status = 401
        failed_detail = ''

        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            blocked_until = int(ip_item.get('blocked_until', 0) or 0) if isinstance(ip_item, dict) else 0
            delay_seconds = _get_login_delay_seconds(attempts_state, ip_addr, now_ts)

            if blocked_until > now_ts:
                _save_login_attempts(attempts_file, attempts_state)
                blocked_at = _format_blocked_until(blocked_until)
                failed_payload = {
                    'success': False,
                    'message': f'当前登录 IP 已被封禁至 {blocked_at}，请稍后再试。'
                }
                failed_status = 429
                failed_detail = f'IP 已封禁至 {blocked_at or blocked_until}'
            elif delay_seconds > 0:
                delay_minutes = delay_seconds // 60
                delay_secs = delay_seconds % 60
                if delay_minutes > 0:
                    wait_hint = f'{delay_minutes}m {delay_secs}s'
                else:
                    wait_hint = f'{delay_secs}s'
                failed_payload = {
                    'success': False,
                    'message': f'失败次数过多，请等待 {wait_hint} 后再试。'
                }
                failed_status = 429
                failed_detail = f'登录已触发延迟保护，等待 {wait_hint}'
                _save_login_attempts(attempts_file, attempts_state)
            elif credentials_ok:
                _reset_login_attempts_for_ip(attempts_state, ip_addr)
                _save_login_attempts(attempts_file, attempts_state)
            else:
                _set_login_delay(attempts_state, ip_addr, now_ts)
                is_blocked_now, blocked_until, remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
                if is_blocked_now:
                    blocked_at = _format_blocked_until(blocked_until)
                    failed_payload = {
                        'success': False,
                        'message': f'{fail_reason} 同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'
                    }
                    failed_status = 429
                    failed_detail = f'{fail_reason}；已封禁至 {blocked_at or blocked_until}'
                else:
                    fail_count = remaining - 1
                    if fail_count > 0:
                        fail_payload_msg = f'{fail_reason} 已触发保护延迟，请稍后再试。'
                    else:
                        fail_payload_msg = f'{fail_reason} 已触发保护延迟，请等待 3 分钟后再试。'
                    failed_payload = {
                        'success': False,
                        'message': fail_payload_msg
                    }
                    failed_status = 400 if fail_reason != '用户名或密码错误。' else 401
                    failed_detail = f'{fail_reason}；已失败 {fail_count + 1} 次，已触发延迟保护'

        if failed_payload is not None:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=username,
                detail=failed_detail,
                hidden_account=is_hidden_admin,
            )
            return jsonify(failed_payload), failed_status

        session.clear()
        session['admin_logged_in'] = True
        session['admin_username'] = login_username
        session['admin_is_super_admin'] = bool(is_super_admin)
        session['admin_is_hidden'] = bool(is_hidden_admin)
        session['admin_permissions'] = list(user_permissions)
        session['admin_login_at'] = now_ts
        session['admin_session_ttl'] = ADMIN_SESSION_MAX_AGE_SECONDS
        session['admin_session_schema'] = ADMIN_SESSION_SCHEMA_VERSION

        prev_last_login_at = ''
        prev_last_login_ip = ''
        current_login_at = now_beijing().isoformat(timespec='seconds')
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            user_ref, idx = _find_user(users_data, login_username)
            if user_ref is not None and idx >= 0:
                user_ref = dict(user_ref)
                prev_last_login_at = str(user_ref.get('last_login_at', '') or '').strip()
                prev_last_login_ip = str(user_ref.get('last_login_ip', '') or '').strip()
                user_ref['last_login_at'] = current_login_at
                user_ref['last_login_ip'] = ip_addr
                user_ref['updated_at'] = current_login_at
                users_data['users'][idx] = user_ref
                _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='admin_login',
            success=True,
            username=login_username,
            detail=('凭据校验通过；人机验证通过' if turnstile_settings['enabled'] else '凭据校验通过')
            + ('; role: super_admin' if is_super_admin else '; role: sub_admin'),
            hidden_account=is_hidden_admin,
        )
        return jsonify({
            'success': True,
            'last_login_at': prev_last_login_at,
            'last_login_ip': prev_last_login_ip,
            'current_login_at': current_login_at,
            'current_login_ip': ip_addr,
        })
    @app.route('/admin/change-password', methods=['POST'])
    @login_required
    def change_password():
        """Update the current admin username and password."""
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        data = request.get_json(silent=True) or {}
        old_password = str(data.get('oldPassword', '') or '')
        new_username = str(data.get('newUsername', '') or '').strip()
        new_password = str(data.get('newPassword', '') or '').strip()

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        current_admin = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            current_user, current_index = _find_user(users_data, current_admin)

        if current_user is None or current_index < 0:
            session.clear()
            return jsonify({'success': False, 'message': '当前登录状态已失效，请重新登录。'}), 401

        current_is_hidden = _is_hidden_admin_record(current_user)

        if not _verify_password(str(current_user.get('password_hash', '') or ''), old_password):
            append_admin_login_log(
                operation='admin_profile_update',
                success=False,
                username=current_admin,
                detail='当前密码校验失败',
                hidden_account=current_is_hidden,
            )
            return jsonify({'success': False, 'message': '当前密码不正确。'}), 400

        if not new_username or not new_password:
            append_admin_login_log(
                operation='admin_profile_update',
                success=False,
                username=current_admin,
                detail='缺少新用户名或新密码',
                hidden_account=current_is_hidden,
            )
            return jsonify({'success': False, 'message': '用户名和新密码不能为空。'}), 400

        if not USERNAME_RULE.match(new_username):
            return jsonify({'success': False, 'message': '用户名需为 3 到 32 位，仅支持字母、数字、下划线、点和短横线。'}), 400
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': '新密码至少需要 8 位。'}), 400

        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            current_user, current_index = _find_user(users_data, current_admin)
            if current_user is None or current_index < 0:
                session.clear()
                return jsonify({'success': False, 'message': '当前登录状态已失效，请重新登录。'}), 401

            current_is_hidden = _is_hidden_admin_record(current_user)
            existing, existing_idx = _find_user(users_data, new_username)
            if existing is not None and existing_idx != current_index:
                if _should_conceal_hidden_admin(existing, session):
                    return _hidden_admin_username_unavailable_response()
                return jsonify({'success': False, 'message': '用户名已存在，请更换。'}), 400

            now_iso = now_beijing().isoformat(timespec='seconds')
            updated_user = dict(current_user)
            updated_user['username'] = new_username
            updated_user['password_hash'] = _hash_password(new_password)
            updated_user['updated_at'] = now_iso
            users_data['users'][current_index] = _sanitize_user_record(
                updated_user,
                fallback_username=new_username,
                is_super_admin=bool(str(current_user.get('role') or '') == 'super_admin'),
                force_hidden=bool(current_user.get('hidden', False)),
            )
            _save_admin_users(users_file, users_data)

            config_updates = {}
            if str(current_user.get('role') or '') == 'super_admin':
                if current_is_hidden:
                    config_updates.update({
                        'hidden_admin_username': new_username,
                        'hidden_admin_password_hash': users_data['users'][current_index]['password_hash'],
                        'hidden_admin_password': ''
                    })
                else:
                    config_updates.update({
                        'admin_username': new_username,
                        'admin_password_hash': users_data['users'][current_index]['password_hash'],
                        'admin_password': ''
                    })
            if config_updates:
                update_config(config_updates)

        session['admin_username'] = new_username
        session['admin_is_hidden'] = bool(current_is_hidden)
        append_admin_login_log(
            operation='admin_profile_update',
            success=True,
            username=new_username,
            detail='账号资料已更新',
            hidden_account=current_is_hidden,
        )

        return jsonify({'success': True, 'message': '账号信息已更新。'})

    def _forbidden_subaccount_manage():
        return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403

    @app.route('/api/admin/subaccounts/permissions', methods=['GET'])
    @login_required
    def admin_permissions_catalog():
        return jsonify({
            'success': True,
            'permission_catalog': ADMIN_PERMISSION_CATALOG,
            'is_super_admin': bool(_is_super_admin_session(session)),
        })

    @app.route('/api/admin/subaccounts', methods=['GET'])
    @login_required
    def admin_subaccounts_list():
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            users = users_data.get('users', [])
            items = [_public_user_profile(user) for user in users if str(user.get('role') or '') != 'super_admin']
        return jsonify({
            'success': True,
            'items': items,
            'permission_catalog': ADMIN_PERMISSION_CATALOG,
        })

    @app.route('/api/admin/subaccounts', methods=['POST'])
    @login_required
    def admin_subaccounts_create():
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        data = request.get_json(silent=True) or {}
        username = _normalize_username(data.get('username', ''))
        password = str(data.get('password', '') or '')
        enabled = bool(data.get('enabled', True))
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)

        if not USERNAME_RULE.match(username):
            return jsonify({'success': False, 'message': '用户名需为 3 到 32 位，仅支持字母、数字、下划线、点和短横线。'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': '密码至少需要 8 位。'}), 400
        if not permissions:
            return jsonify({'success': False, 'message': '请至少选择 1 项权限。'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            existing, _ = _find_user(users_data, username)
            if existing is not None:
                if _should_conceal_hidden_admin(existing, session):
                    return _hidden_admin_username_unavailable_response()
                return jsonify({'success': False, 'message': '用户名已存在。'}), 400
            now_iso = now_beijing().isoformat(timespec='seconds')
            user = _sanitize_user_record({
                'username': username,
                'password_hash': _hash_password(password),
                'role': 'sub_admin',
                'enabled': enabled,
                'permissions': permissions,
                'created_at': now_iso,
                'updated_at': now_iso,
                'last_login_at': '',
            }, fallback_username=username, is_super_admin=False)
            users_data.setdefault('users', []).append(user)
            _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='subaccount_manage',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'创建子账号：{username}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': '子账号创建成功。'})
    @app.route('/api/admin/subaccounts/<username>', methods=['PUT'])
    @login_required
    def admin_subaccounts_update(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        target_name = _normalize_username(username)
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get('enabled', True))
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)
        reset_password = str(data.get('password', '') or '')

        if not permissions:
            return jsonify({'success': False, 'message': '请至少选择 1 项权限。'}), 400
        if reset_password and len(reset_password) < 8:
            return jsonify({'success': False, 'message': '密码至少需要 8 位。'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            target_user, idx = _find_user(users_data, target_name)
            if target_user is None or idx < 0:
                return jsonify({'success': False, 'message': '未找到该子账号。'}), 404
            if _is_hidden_admin_record(target_user):
                return _hidden_admin_not_found_response()
            if str(target_user.get('role') or '') == 'super_admin':
                return jsonify({'success': False, 'message': '不能在此处编辑超级管理员账号。'}), 400

            now_iso = now_beijing().isoformat(timespec='seconds')
            updated = dict(target_user)
            updated['enabled'] = enabled
            updated['permissions'] = permissions
            if reset_password:
                updated['password_hash'] = _hash_password(reset_password)
            updated['updated_at'] = now_iso
            users_data['users'][idx] = _sanitize_user_record(updated, fallback_username=target_name, is_super_admin=False)
            _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='subaccount_manage',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'更新子账号：{target_name}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': '子账号更新成功。'})
    @app.route('/api/admin/subaccounts/<username>', methods=['DELETE'])
    @login_required
    def admin_subaccounts_delete(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        target_name = _normalize_username(username)
        current_name = _normalize_username(session.get('admin_username', ''))
        if target_name == current_name:
            return jsonify({'success': False, 'message': '不能删除当前登录账号。'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            target_user, idx = _find_user(users_data, target_name)
            if target_user is None or idx < 0:
                return jsonify({'success': False, 'message': '未找到该子账号。'}), 404
            if _is_hidden_admin_record(target_user):
                return _hidden_admin_not_found_response()
            if str(target_user.get('role') or '') == 'super_admin':
                return jsonify({'success': False, 'message': '不能在此处删除超级管理员账号。'}), 400

            users = users_data.get('users', [])
            users.pop(idx)
            users_data['users'] = users
            _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='subaccount_manage',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'删除子账号：{target_name}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': '子账号已删除。'})
    @app.route('/admin/logout', methods=['POST'])
    def admin_logout():
        """Handle admin logout."""
        username = session.get('admin_username') or ''
        is_hidden = bool(session.get('admin_is_hidden', False))
        if session.get('admin_logged_in'):
            append_admin_login_log(
                operation='admin_logout',
                success=True,
                username=username,
                detail='手动退出登录',
                hidden_account=is_hidden,
            )
        _clear_admin_session(session)
        return jsonify({'success': True})
    @app.route('/admin/check')
    def admin_check():
        """Check whether an admin session is still valid."""
        logged_in = bool(session.get('admin_logged_in', False))
        if logged_in and _is_admin_session_expired(session):
            session.clear()
            logged_in = False
        if not logged_in:
            return jsonify({
                'logged_in': False,
                'username': '',
                'is_super_admin': False,
                'is_hidden_admin': False,
                'binding_required': False,
                'permissions': [],
                'permission_catalog': ADMIN_PERMISSION_CATALOG,
            })

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        current_name = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            user, _ = _find_user(users_data, current_name)

        if user is None or not bool(user.get('enabled', True)):
            session.clear()
            return jsonify({
                'logged_in': False,
                'username': '',
                'is_super_admin': False,
                'is_hidden_admin': False,
                'binding_required': False,
                'permissions': [],
                'permission_catalog': ADMIN_PERMISSION_CATALOG,
            })

        is_super_admin = bool(str(user.get('role') or '') == 'super_admin')
        is_hidden_admin = _is_hidden_admin_record(user)
        permissions = _normalize_permissions(user.get('permissions', []), is_super_admin=is_super_admin)
        session['admin_is_super_admin'] = is_super_admin
        session['admin_is_hidden'] = is_hidden_admin
        session['admin_permissions'] = permissions
        session['admin_username'] = _normalize_username(user.get('username', current_name))
        session['admin_binding_required'] = bool((get_config() or {}).get('email_auth_enabled', False) and not _has_verified_email(user))

        return jsonify({
            'logged_in': True,
            'username': session.get('admin_username', ''),
            'is_super_admin': is_super_admin,
            'is_hidden_admin': is_hidden_admin,
            'binding_required': bool(session.get('admin_binding_required', False)),
            'permissions': permissions,
            'permission_catalog': ADMIN_PERMISSION_CATALOG,
            'last_login_at': str(user.get('last_login_at') or ''),
            'last_login_ip': str(user.get('last_login_ip') or ''),
            'email': _normalize_email(user.get('email', '')),
            'email_masked': _mask_email_address(user.get('email', '')),
            'email_verified': bool(user.get('email_verified', False)),
        })
    @app.route('/api/admin/login-logs')
    @login_required
    def admin_login_logs():
        """Return immutable admin audit/login logs with hidden-account filtering."""
        limit_raw = request.args.get('limit')
        page_raw = request.args.get('page')
        page_size_raw = request.args.get('page_size')
        if limit_raw and page_raw is None and page_size_raw is None:
            try:
                limit = int(limit_raw)
            except (TypeError, ValueError):
                limit = 200
            limit = max(1, min(limit, 1000))

            with admin_login_log_lock:
                items = _filter_admin_login_logs_for_session(load_admin_login_logs(), session)

            output = list(reversed(items))[:limit]
            return jsonify({'items': output, 'count': len(output)})

        try:
            page = int(page_raw or '1')
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(page_size_raw or '20')
        except (TypeError, ValueError):
            page_size = 20

        page = max(1, page)
        page_size = max(5, min(page_size, 200))

        with admin_login_log_lock:
            items = list(reversed(_filter_admin_login_logs_for_session(load_admin_login_logs(), session)))

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        start = (page - 1) * page_size
        end = start + page_size
        output = items[start:end]

        return jsonify({
            'items': output,
            'count': len(output),
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        })
    @app.route('/api/admin/changelog')
    @login_required
    def admin_changelog():
        """获取当前版本、构建信息与最近更新记录。"""
        return jsonify(build_admin_changelog_payload(project_root=project_root))

    @app.route('/api/admin/docker-logs')
    @login_required
    def admin_docker_logs():
        """获取两个后端容器的 Docker 日志；Docker 不可用时回退到本地日志文件。"""
        container1_name = os.environ.get('DOCKER_CONTAINER_1_NAME', 'yx-website-app')
        container2_name = os.environ.get('DOCKER_CONTAINER_2_NAME', 'yx-website-nginx')
        lines = request.args.get('lines', default=200, type=int)
        lines = max(10, min(lines, 1000))

        def get_container_logs(container_name):
            try:
                result = subprocess.run(
                    ['docker', 'logs', '--tail', str(lines), container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                stdout = result.stdout or ''
                stderr = result.stderr or ''
                combined = (stdout + stderr).strip()
                if not combined:
                    return '暂无日志记录'
                return combined
            except subprocess.TimeoutExpired:
                return '日志获取超时'
            except FileNotFoundError:
                return None
            except Exception as e:
                return f'获取日志失败: {str(e)}'

        def get_local_log_lines():
            try:
                log_file = os.environ.get('FLASK_LOG_FILE', '').strip()
                if not log_file:
                    log_file = os.path.join(project_root, 'data', 'app.log')
                if not os.path.exists(log_file):
                    fallback = os.path.join(project_root, 'app.log')
                    if os.path.exists(fallback):
                        log_file = fallback
                    else:
                        return None
                with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                    all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if all_lines else []
                return ''.join(tail_lines).strip() or None
            except Exception:
                return None

        logs1 = get_container_logs(container1_name)
        logs2 = get_container_logs(container2_name)

        is_docker_available = logs1 is not None and logs2 is not None

        if logs1 is None:
            local_logs = get_local_log_lines()
            if local_logs:
                logs1 = f'[本地开发模式] Flask 应用日志:\n{local_logs}'
            else:
                logs1 = '暂无日志记录（当前为本地开发模式，日志文件尚未生成）'

        if logs2 is None:
            if is_docker_available:
                logs2 = '暂无 Nginx 日志记录'
            else:
                logs2 = '[本地开发模式] Nginx 日志仅在 Docker 部署时可用'

        return jsonify({
            'container1': {
                'name': container1_name,
                'logs': logs1
            },
            'container2': {
                'name': container2_name,
                'logs': logs2
            }
        })

    @app.route('/api/admin/docker-logs/clear', methods=['POST'])
    @login_required
    def admin_docker_logs_clear():
        """清理 Docker 容器日志或本地日志文件。"""
        try:
            data = request.get_json() or {}
            container = data.get('container', 'all')
            
            def clear_container_logs(container_name):
                try:
                    subprocess.run(
                        ['docker', 'logs', '--truncate', container_name],
                        capture_output=True,
                        timeout=10,
                    )
                    return True
                except Exception:
                    return False
            
            def clear_local_log():
                try:
                    log_file = os.environ.get('FLASK_LOG_FILE', '').strip()
                    if not log_file:
                        log_file = os.path.join(project_root, 'data', 'app.log')
                    if os.path.exists(log_file):
                        open(log_file, 'w').close()
                        return True
                    fallback = os.path.join(project_root, 'app.log')
                    if os.path.exists(fallback):
                        open(fallback, 'w').close()
                        return True
                    return False
                except Exception:
                    return False
            
            container1_name = os.environ.get('DOCKER_CONTAINER_1_NAME', 'yx-website-app')
            container2_name = os.environ.get('DOCKER_CONTAINER_2_NAME', 'yx-website-nginx')
            
            docker_available = True
            try:
                subprocess.run(['docker', 'ps'], capture_output=True, timeout=5)
            except FileNotFoundError:
                docker_available = False
            except Exception:
                docker_available = False
            
            if docker_available:
                if container == 'all' or container == 'container1':
                    clear_container_logs(container1_name)
                if container == 'all' or container == 'container2':
                    clear_container_logs(container2_name)
            else:
                clear_local_log()
            
            return jsonify({'success': True, 'message': '日志已清除'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/changelog/latest')
    def public_changelog_latest():
        """提供给首页测试版本弹窗使用的公开更新日志接口。"""
        payload = build_admin_changelog_payload(project_root=project_root)
        history_raw = payload.get('history') if isinstance(payload, dict) else []
        history = []
        if isinstance(history_raw, list):
            for item in history_raw:
                if not isinstance(item, dict):
                    continue
                updates_raw = item.get('updates', [])
                updates = [str(x).strip() for x in updates_raw if str(x or '').strip()]
                history.append({
                    'version': str(item.get('version', '')).strip() or 'v1.0.0',
                    'build_time': str(item.get('build_time', '')).strip(),
                    'updates': updates,
                })

        if not history:
            updates_raw = payload.get('updates') if isinstance(payload, dict) else []
            updates = [str(item).strip() for item in updates_raw if str(item or '').strip()]
            history = [{
                'version': str(payload.get('version', 'v1.0.0')),
                'build_time': str(payload.get('build_time', '')),
                'updates': updates,
            }]

        latest = history[0] if history else {'version': 'v1.0.0', 'build_time': '', 'updates': []}
        latest_updates = latest.get('updates') if isinstance(latest.get('updates'), list) else []
        latest_update = latest_updates[0] if latest_updates else '暂无更新内容'
        return jsonify({
            'version': str(latest.get('version', 'v1.0.0')),
            'build_time': str(latest.get('build_time', '')),
            'latest_update': latest_update,
            'history': history,
        })
