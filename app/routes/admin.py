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
   - 会话过期自动失效（默认2小时空闲超时、24小时绝对超时）
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

import html
import json
import os
import re
import secrets
import smtplib
import socket
import subprocess
import threading
import time
import hashlib
import hmac
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener, urlopen
import ssl

# 多 worker 文件锁支持；非 POSIX 平台退化为纯线程锁。
try:
    import fcntl as _FCNTL
except ImportError:  # pragma: no cover - Windows fallback
    _FCNTL = None

from flask import jsonify, make_response, request, send_from_directory, session
from app.admin_feature_unlocks import (
    filter_unlocked_permission_catalog,
    get_admin_feature_unlocks,
    is_admin_feature_unlocked,
)
from app.admin_session import is_admin_session_expired, maybe_refresh_admin_session
from app.rate_limit_store import check_and_record
from app.app_config import (
    ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
)
from app.admin_geo import (
    ADMIN_GEO_CONTINENTS,
    build_admin_login_geo_catalog_payload,
    build_admin_login_geo_settings_payload,
    extract_admin_login_geo_updates,
    get_country_continent_key,
    is_country_code_allowed,
    normalize_admin_login_geo_settings,
)
from app.request_security import get_request_client_ip, is_same_origin_request, normalize_origin
from app.request_security import CSRF_SESSION_KEY
from app.passkeys import PasskeyStore, load_passkey_config, require_webauthn
from werkzeug.security import check_password_hash, generate_password_hash

BEIJING_TZ = timezone(timedelta(hours=8))

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)

LOGIN_FAIL_WINDOW_SECONDS = 12 * 3600
LOGIN_FAIL_LIMIT = 3
LOGIN_BLOCK_SECONDS = 12 * 3600


class _CrossProcessStateLock:
    """线程锁 + 跨进程 flock 的组合锁。

    登录失败计数、邮箱验证码状态、管理员账号数据均采用
    “读文件 → 修改 → 整体覆盖写回”的保存方式。Gunicorn 多 worker 部署下
    仅靠进程内线程锁会出现两个 worker 同时读到旧值并互相覆盖：
    失败计数丢失（暴力破解阈值被稀释）、验证码 used 标记丢失导致重放。
    本锁在原线程锁基础上，对数据目录下的同名 .lock 文件追加排他 flock，
    使 `with LOCK:` 临界区同时跨线程与跨进程互斥。
    """

    def __init__(self, lock_file_name: str, *, reentrant: bool = False):
        self._thread_lock = threading.RLock() if reentrant else threading.Lock()
        self._lock_file_name = lock_file_name
        self._base_dir = None

    def set_base_dir(self, data_dir) -> None:
        """由路由注册入口注入实际的数据目录（随部署/测试环境变化）。"""
        self._base_dir = Path(data_dir) if data_dir else None

    def __enter__(self):
        self._thread_lock.acquire()
        self._handle = None
        try:
            if self._base_dir is not None:
                self._base_dir.mkdir(parents=True, exist_ok=True)
                handle = (self._base_dir / self._lock_file_name).open('a+', encoding='utf-8')
                try:
                    if _FCNTL is not None:
                        _FCNTL.flock(handle.fileno(), _FCNTL.LOCK_EX)
                except Exception:
                    handle.close()
                    raise
                self._handle = handle
            return self
        except Exception:
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._handle is not None:
                try:
                    if _FCNTL is not None:
                        _FCNTL.flock(self._handle.fileno(), _FCNTL.LOCK_UN)
                finally:
                    self._handle.close()
                    self._handle = None
        finally:
            self._thread_lock.release()
        return False


LOGIN_ATTEMPTS_LOCK = _CrossProcessStateLock('admin_login_attempts.lock')
ADMIN_USERS_LOCK = _CrossProcessStateLock('admin_users.lock', reentrant=True)
EMAIL_AUTH_STATE_LOCK = _CrossProcessStateLock('admin_email_auth_state.lock', reentrant=True)
SMTP_REMINDER_THREAD_LOCK = threading.Lock()
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
TURNSTILE_DIRECT_TIMEOUT_SECONDS = 6
TURNSTILE_PROXY_TIMEOUT_SECONDS = 15
TURNSTILE_CONNECTIVITY_TEST_TOKEN = 'yx-connectivity-test'
ADMIN_SESSION_MAX_AGE_SECONDS = ADMIN_SESSION_IDLE_TIMEOUT_SECONDS
ADMIN_SESSION_SCHEMA_VERSION = 4
LOGIN_DELAY_SECONDS = [60, 180]
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
    {'key': 'promotion-links', 'label': '推广链接'},
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
    {'key': 'cdn-assets', 'label': 'CDN 素材'},
    {'key': 'image-seo', 'label': '图片 SEO'},
    {'key': 'log-records', 'label': '系统日志'},
]
ADMIN_PERMISSION_KEYS = [item['key'] for item in ADMIN_PERMISSION_CATALOG]


def _admin_feature_response_fields():
    feature_unlocks = get_admin_feature_unlocks(ADMIN_PERMISSION_KEYS)
    return {
        'permission_catalog': filter_unlocked_permission_catalog(ADMIN_PERMISSION_CATALOG),
        'unlocked_features': [key for key in ADMIN_PERMISSION_KEYS if feature_unlocks.get(key, True)],
        'feature_unlocks': feature_unlocks,
    }


def _filter_unlocked_permissions(permissions):
    return [key for key in permissions if is_admin_feature_unlocked(key)]


def _locked_permissions(permissions):
    return [key for key in permissions if not is_admin_feature_unlocked(key)]


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
    legacy_permission_map = {
        'changelog': 'log-records',
        'docker-logs': 'log-records',
    }
    for item in source:
        key = legacy_permission_map.get(str(item or '').strip(), str(item or '').strip())
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
        # 解析失败（文件损坏/半写）时保留现场返回空表，由调用方决定是否重建，
        # 避免读取路径直接破坏既有账号数据。
        return default_data
    if not isinstance(data, dict):
        return default_data
    users = data.get('users', [])
    if not isinstance(users, list):
        users = []
    try:
        version = int(data.get('version', 1) or 1)
    except (TypeError, ValueError):
        version = 1
    return {
        'version': version,
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
    try:
        # 管理员账号数据含密码哈希与登录 IP，仅允许属主读取。
        os.chmod(file_path, 0o600)
    except OSError:
        pass


# ── 服务端会话吊销（min_session_at）────────────────────────────────
# 登出/改密时推进账号的 min_session_at 时间戳；login_required 校验会话中的
# admin_login_at 不早于该时间戳，使被窃取的旧 cookie 在登出后立即失效。

_MIN_SESSION_AT_CACHE: dict = {}
_MIN_SESSION_AT_CACHE_LOCK = threading.Lock()
_users_file_for_revocation = None


def _set_users_file_for_revocation(file_path):
    """由路由注册入口注入管理员数据文件路径，供鉴权守卫查询。"""
    global _users_file_for_revocation
    _users_file_for_revocation = Path(file_path) if file_path else None
    with _MIN_SESSION_AT_CACHE_LOCK:
        _MIN_SESSION_AT_CACHE.clear()


def _build_user_session_cache_entry(users_file: Path, mtime: int):
    """构建 (mtime, min_session_at映射, 已知用户名集合) 缓存项；读取失败返回 None。"""
    mapping = {}
    known_names = set()
    try:
        for user in _load_admin_users(users_file).get('users', []):
            key = _normalize_username(user.get('username', ''))
            if key:
                known_names.add(key)
                try:
                    mapping[key] = int(user.get('min_session_at', 0) or 0)
                except Exception:
                    mapping[key] = 0
    except Exception:
        return None
    return (mtime, mapping, known_names)


def query_user_min_session_at(username) -> int:
    """读取用户的最小有效会话时间戳；带 mtime 缓存避免每请求解析 JSON。"""
    name = _normalize_username(username)
    users_file = _users_file_for_revocation
    if not name or users_file is None:
        return 0
    try:
        mtime = users_file.stat().st_mtime_ns
    except OSError:
        return 0
    with _MIN_SESSION_AT_CACHE_LOCK:
        cached = _MIN_SESSION_AT_CACHE.get('entry')
        if not cached or cached[0] != mtime:
            entry = _build_user_session_cache_entry(users_file, mtime)
            if entry is None:
                return 0
            _MIN_SESSION_AT_CACHE.clear()
            _MIN_SESSION_AT_CACHE['entry'] = entry
            cached = entry
        return int(cached[1].get(name, 0) or 0)


def query_admin_user_exists(username) -> bool:
    """判断用户名是否仍存在于管理员账号存储。

    供会话守卫吊销“账号已被删除”的残留会话；存储缺失或读取失败时返回
    True（fail-open），避免瞬时 IO 故障把全部在线管理员登出。
    """
    name = _normalize_username(username)
    users_file = _users_file_for_revocation
    if not name or users_file is None:
        return True
    try:
        mtime = users_file.stat().st_mtime_ns
    except OSError:
        return True
    with _MIN_SESSION_AT_CACHE_LOCK:
        cached = _MIN_SESSION_AT_CACHE.get('entry')
        if not cached or cached[0] != mtime:
            entry = _build_user_session_cache_entry(users_file, mtime)
            if entry is None:
                return True
            _MIN_SESSION_AT_CACHE.clear()
            _MIN_SESSION_AT_CACHE['entry'] = entry
            cached = entry
        return name in cached[2]


def bump_user_min_session_at(root, username) -> None:
    """推进指定账号的最小有效会话时间戳，使其现有全部会话失效。"""
    name = _normalize_username(username)
    if root is None or not name:
        return
    users_file = _get_admin_users_file(Path(root))
    with ADMIN_USERS_LOCK:
        users_data = _load_admin_users(users_file)
        user, idx = _find_user(users_data, name)
        if idx < 0:
            return
        user['min_session_at'] = int(time.time())
        users_data['users'][idx] = user
        _save_admin_users(users_file, users_data)


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


# 用户不存在时也执行一次等价的 scrypt 运算，抹平登录接口响应时间差异，
# 防止通过时序侧信道枚举有效用户名。
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(24))


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
    try:
        # 状态文件含邮箱地址与验证码哈希，仅允许属主读取。
        os.chmod(file_path, 0o600)
    except OSError:
        pass


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


def _send_smtp_mail(settings, *, to_email: str, subject: str, html_body: str, text_body: str = '', attachments=None):
    recipient = _normalize_email(to_email)
    if not recipient:
        raise ValueError('missing recipient')
    if not _smtp_ready_for_email_auth(settings):
        raise RuntimeError('SMTP 配置不可用')

    from_name = str(settings.get('smtp_from_name') or '').strip()
    from_email = _normalize_email(settings.get('smtp_from_email', ''))
    from_header = f'{from_name} <{from_email}>' if from_name else from_email

    if attachments:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        message = MIMEMultipart('mixed')
        message['From'] = from_header
        message['To'] = recipient
        message['Subject'] = subject

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(text_body or '请使用支持 HTML 的邮箱客户端查看邮件。', 'plain', 'utf-8'))
        alt.attach(MIMEText(html_body, 'html', 'utf-8'))
        message.attach(alt)

        for fname, data_bytes, mime_type in attachments:
            maintype, subtype = (mime_type.split('/', 1) + ['octet-stream'])[:2]
            part = MIMEApplication(data_bytes, _subtype=subtype)
            part.add_header('Content-Disposition', 'attachment', filename=fname)
            message.attach(part)
    else:
        message = EmailMessage()
        message['From'] = from_header
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
    # 首页导航模块读取为公开接口（前台 nav-loader 使用）；保存归属「首页设置」权限。
    if p == '/api/nav-labels':
        return None
    if p.startswith('/api/admin/nav-labels'):
        return 'home'
    if p.startswith('/api/admin/subaccounts') or p.startswith('/admin/change-password'):
        return 'settings'
    if p.startswith('/api/admin/account/email-binding'):
        return None
    if p.startswith('/api/admin/account/passkeys'):
        return None
    if p.startswith('/api/admin/email-auth'):
        return 'site-settings'
    if p.startswith('/api/admin/security/login-geo'):
        return 'site-settings'
    if p.startswith('/api/admin/security/passkeys'):
        return 'site-settings'
    if p.startswith('/api/cdn/assets'):
        return 'cdn-assets'
    if p.startswith('/api/admin/security/turnstile') or p.startswith('/api/cdn/'):
        return 'site-settings'
    if p.startswith('/api/admin/site-reports'):
        return 'site-reports'
    if p.startswith('/api/admin/promotion-links'):
        return 'promotion-links'
    if p.startswith('/api/admin/changelog'):
        return 'log-records'
    if p.startswith('/api/admin/docker-logs'):
        return 'log-records'
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
    notify_message_email = bool((user or {}).get('notify_message_email', False))
    notify_job_email = bool((user or {}).get('notify_job_email', False))
    try:
        min_session_at = int((user or {}).get('min_session_at', 0) or 0)
    except Exception:
        min_session_at = 0
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
        'notify_message_email': notify_message_email,
        'notify_job_email': notify_job_email,
        'min_session_at': min_session_at,
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
        'notify_message_email': bool(record.get('notify_message_email', False)),
        'notify_job_email': bool(record.get('notify_job_email', False)),
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
        'admin_last_active_at',
        'admin_session_ttl',
        'admin_session_absolute_ttl',
        'admin_session_schema',
        'admin_binding_required',
        'admin_previous_login_at',
        'admin_previous_login_ip',
        'admin_current_login_at',
        'admin_current_login_ip',
        'admin_passkey_step_up_username',
        'admin_passkey_step_up_until',
        'admin_passkey_email_code_hash',
        'admin_passkey_email_code_salt',
        'admin_passkey_email_code_expires_at',
        'admin_passkey_email_code_failures',
        'admin_passkey_email_resend_at',
        CSRF_SESSION_KEY,
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
    now_ts = int(time.time())
    sess['admin_login_at'] = now_ts
    sess['admin_last_active_at'] = now_ts
    sess['admin_session_ttl'] = ADMIN_SESSION_IDLE_TIMEOUT_SECONDS
    sess['admin_session_absolute_ttl'] = ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS
    sess['admin_session_schema'] = ADMIN_SESSION_SCHEMA_VERSION
    sess['admin_binding_required'] = bool(binding_required)
    sess[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)


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
    safe_username = html.escape(_normalize_username(username) or '管理员')
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
    safe_username = html.escape(_normalize_username(username) or '管理员')
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


def _build_login_email_subject_v2():
    return '\u5143\u82af\u9a8c\u8bc1\u7801'


def _render_brand_email_v2(*, eyebrow: str, title: str, intro: str, highlight_html: str, note_lines):
    notes = ''.join(
        f'<li style="margin:0 0 8px;">{line}</li>'
        for line in (note_lines or [])
        if str(line or '').strip()
    )
    return f"""
    <div style="margin:0;padding:0;background:linear-gradient(180deg,#edf4fb 0%,#e6eef9 100%);">
      <div style="width:100%;margin:0;font-family:'Microsoft YaHei',Arial,sans-serif;color:#10233d;background:
        radial-gradient(circle at top right, rgba(39,199,217,0.22) 0, rgba(39,199,217,0) 28%),
        radial-gradient(circle at left center, rgba(18,61,113,0.08) 0, rgba(18,61,113,0) 32%),
        linear-gradient(180deg,#edf4fb 0%,#e6eef9 100%);
      ">
        <div style="position:relative;overflow:hidden;background:
          radial-gradient(circle at 78% 26%, rgba(39,199,217,0.34) 0, rgba(39,199,217,0) 18%),
          radial-gradient(circle at 12% 18%, rgba(255,255,255,0.12) 0, rgba(255,255,255,0) 20%),
          linear-gradient(135deg,#08192d 0%,#123d71 55%,#1d6f99 76%,#27c7d9 100%);
          border-radius:0;padding:44px 44px 102px;color:#ffffff;box-shadow:inset 0 -1px 0 rgba(255,255,255,0.08);">
          <div style="position:absolute;right:-78px;top:-66px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,0.08);"></div>
          <div style="position:absolute;right:74px;bottom:28px;width:132px;height:132px;border-radius:50%;background:rgba(39,199,217,0.16);filter:blur(2px);"></div>
          <div style="position:relative;z-index:1;display:inline-block;padding:8px 16px;border-radius:999px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.24);font-size:12px;letter-spacing:1.4px;box-shadow:0 10px 24px rgba(8,25,45,0.18);">
            元芯传感后台
          </div>
          <div style="position:relative;z-index:1;margin-top:24px;font-size:14px;line-height:1.8;color:rgba(255,255,255,0.78);">{eyebrow}</div>
          <h1 style="position:relative;z-index:1;margin:12px 0 0;font-size:34px;line-height:1.18;font-weight:800;color:#ffffff;text-shadow:0 10px 28px rgba(8,25,45,0.25);">{title}</h1>
          <div style="position:relative;z-index:1;margin-top:16px;width:88px;height:4px;border-radius:999px;background:linear-gradient(90deg,rgba(255,255,255,0.92) 0%,rgba(39,199,217,0.92) 100%);"></div>
        </div>
        <div style="position:relative;z-index:2;margin-top:-54px;background:
          linear-gradient(180deg,rgba(255,255,255,0.96) 0%,#ffffff 100%);
          border-top-left-radius:34px;border-top-right-radius:34px;padding:40px 44px 34px;
          box-shadow:0 28px 90px rgba(8,25,45,0.14), inset 0 1px 0 rgba(255,255,255,0.85);">
          <p style="margin:0 0 20px;font-size:17px;line-height:1.9;color:#10233d;">{intro}</p>
          <div style="margin:24px 0;padding:30px 28px;border-radius:28px;background:
            radial-gradient(circle at top center, rgba(255,255,255,0.72) 0, rgba(255,255,255,0) 34%),
            linear-gradient(180deg,rgba(39,199,217,0.18) 0%,rgba(18,61,113,0.06) 100%);
            border:1px solid rgba(39,199,217,0.30);box-shadow:inset 0 1px 0 rgba(255,255,255,0.8), 0 16px 36px rgba(18,61,113,0.08);">
            {highlight_html}
          </div>
          <div style="padding:22px 24px;border-radius:24px;background:linear-gradient(180deg,#f9fcff 0%,#f1f7fd 100%);border:1px solid rgba(18,61,113,0.08);box-shadow:inset 0 1px 0 rgba(255,255,255,0.9);">
            <div style="margin:0 0 12px;font-size:14px;font-weight:700;letter-spacing:0.4px;color:#123d71;">安全提示</div>
            <ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.9;color:#5d708b;">
              {notes}
            </ul>
          </div>
        </div>
        <div style="padding:22px 24px 32px;text-align:center;font-size:12px;line-height:1.9;color:#5d708b;background:#ffffff;">
          <div style="font-weight:700;color:#123d71;">\u5143\u82af\u4f20\u611f YX Website</div>
          <div>\u672c\u90ae\u4ef6\u7531\u540e\u53f0\u5b89\u5168\u7cfb\u7edf\u81ea\u52a8\u53d1\u9001\uff0c\u8bf7\u52ff\u76f4\u63a5\u56de\u590d\u3002</div>
        </div>
      </div>
    </div>
    """


def _build_login_email_content_v2(username: str, code: str):
    # 用户名会拼进 HTML 邮件正文，统一转义防注入（text_body 保持纯文本）。
    safe_username = html.escape(_normalize_username(username) or '\u7ba1\u7406\u5458')
    html_body = _render_brand_email_v2(
        eyebrow='\u7ba1\u7406\u5458\u767b\u5f55\u90ae\u7bb1\u9a8c\u8bc1',
        title='\u540e\u53f0\u767b\u5f55\u9a8c\u8bc1\u7801',
        intro=f'\u8d26\u53f7 <strong style="color:#123d71;">{safe_username}</strong> \u6b63\u5728\u767b\u5f55\u7ba1\u7406\u540e\u53f0\uff0c\u8bf7\u4f7f\u7528\u4e0b\u65b9\u9a8c\u8bc1\u7801\u5b8c\u6210\u5b89\u5168\u6821\u9a8c\u3002',
        highlight_html=f'''
          <div style="font-size:12px;letter-spacing:1.2px;color:#5d708b;text-align:center;">登录验证码</div>
          <div style="margin-top:16px;font-size:40px;line-height:1;font-weight:800;letter-spacing:12px;color:#0d2d56;text-align:center;text-shadow:0 8px 20px rgba(18,61,113,0.10);">{code}</div>
          <div style="margin:16px auto 0;width:72px;height:3px;border-radius:999px;background:linear-gradient(90deg,rgba(18,61,113,0.18) 0%,rgba(39,199,217,0.9) 100%);"></div>
          <div style="margin-top:14px;font-size:14px;line-height:1.8;color:#5d708b;text-align:center;">\u9a8c\u8bc1\u7801 5 \u5206\u949f\u5185\u6709\u6548</div>
        ''',
        note_lines=[
            '\u8bf7\u5728 5 \u5206\u949f\u5185\u5b8c\u6210\u9a8c\u8bc1\uff0c\u4e14\u4e0d\u8981\u5c06\u9a8c\u8bc1\u7801\u900f\u9732\u7ed9\u4ed6\u4eba\u3002',
            '\u82e5\u975e\u672c\u4eba\u64cd\u4f5c\uff0c\u8bf7\u7acb\u5373\u4fee\u6539\u540e\u53f0\u5bc6\u7801\uff0c\u5e76\u68c0\u67e5\u8d26\u53f7\u5b89\u5168\u3002',
        ],
    )
    text_body = f'\u8d26\u53f7 {safe_username} \u6b63\u5728\u767b\u5f55\u7ba1\u7406\u540e\u53f0\uff0c\u672c\u6b21\u9a8c\u8bc1\u7801\uff1a{code}\uff0c5 \u5206\u949f\u5185\u6709\u6548\u3002'
    return html_body, text_body


def _build_binding_email_content_v2(username: str, code: str):
    safe_username = html.escape(_normalize_username(username) or '\u7ba1\u7406\u5458')
    html_body = _render_brand_email_v2(
        eyebrow='\u5b89\u5168\u90ae\u7bb1\u7ed1\u5b9a',
        title='\u90ae\u7bb1\u7ed1\u5b9a\u9a8c\u8bc1\u7801',
        intro=f'\u8d26\u53f7 <strong style="color:#123d71;">{safe_username}</strong> \u6b63\u5728\u7ed1\u5b9a\u540e\u53f0\u5b89\u5168\u90ae\u7bb1\uff0c\u5b8c\u6210\u9a8c\u8bc1\u540e\u53ef\u7528\u4e8e\u540e\u7eed\u767b\u5f55\u4e8c\u6b21\u6821\u9a8c\u3002',
        highlight_html=f'''
          <div style="font-size:12px;letter-spacing:1.2px;color:#5d708b;text-align:center;">绑定验证码</div>
          <div style="margin-top:16px;font-size:40px;line-height:1;font-weight:800;letter-spacing:12px;color:#0d2d56;text-align:center;text-shadow:0 8px 20px rgba(18,61,113,0.10);">{code}</div>
          <div style="margin:16px auto 0;width:72px;height:3px;border-radius:999px;background:linear-gradient(90deg,rgba(18,61,113,0.18) 0%,rgba(39,199,217,0.9) 100%);"></div>
          <div style="margin-top:14px;font-size:14px;line-height:1.8;color:#5d708b;text-align:center;">\u9a8c\u8bc1\u7801 5 \u5206\u949f\u5185\u6709\u6548</div>
        ''',
        note_lines=[
            '\u5b8c\u6210\u7ed1\u5b9a\u540e\uff0c\u540e\u7eed\u540e\u53f0\u767b\u5f55\u5c06\u901a\u8fc7\u90ae\u7bb1\u9a8c\u8bc1\u7801\u8fdb\u884c\u4e8c\u6b21\u6821\u9a8c\u3002',
            '\u82e5\u8fd9\u4e0d\u662f\u4f60\u7684\u64cd\u4f5c\uff0c\u8bf7\u7acb\u5373\u4fee\u6539\u540e\u53f0\u5bc6\u7801\u5e76\u8054\u7cfb\u7ba1\u7406\u5458\u3002',
        ],
    )
    text_body = f'\u8d26\u53f7 {safe_username} \u6b63\u5728\u7ed1\u5b9a\u540e\u53f0\u5b89\u5168\u90ae\u7bb1\uff0c\u672c\u6b21\u9a8c\u8bc1\u7801\uff1a{code}\uff0c5 \u5206\u949f\u5185\u6709\u6548\u3002'
    return html_body, text_body


def _build_smtp_notice_content_v2(remaining_days: int, expires_at: str):
    safe_expires_at = expires_at or '\u672a\u77e5'
    day_label = f'{remaining_days} \u5929' if remaining_days >= 0 else '\u5df2\u8fc7\u671f'
    html_body = _render_brand_email_v2(
        eyebrow='SMTP / 163 \u90ae\u7bb1\u6388\u6743\u7801\u63d0\u9192',
        title='SMTP \u6388\u6743\u7801\u5373\u5c06\u5230\u671f',
        intro=f'\u540e\u53f0\u5f53\u524d\u4f7f\u7528\u7684 SMTP \u6388\u6743\u7801\u5269\u4f59\u6709\u6548\u65f6\u95f4\u4e3a <strong style="color:#123d71;">{day_label}</strong>\uff0c\u4e3a\u4e86\u907f\u514d\u7ba1\u7406\u5458\u65e0\u6cd5\u6536\u5230\u767b\u5f55\u9a8c\u8bc1\u90ae\u4ef6\uff0c\u8bf7\u5c3d\u5feb\u66f4\u65b0\u5bc6\u94a5\u3002',
        highlight_html=f'''
          <div style="font-size:12px;letter-spacing:1.2px;color:#5d708b;text-align:center;">SMTP 密钥状态</div>
          <div style="margin-top:16px;font-size:34px;line-height:1.2;font-weight:800;color:#0d2d56;text-align:center;text-shadow:0 8px 20px rgba(18,61,113,0.10);">{day_label}</div>
          <div style="margin:16px auto 0;width:72px;height:3px;border-radius:999px;background:linear-gradient(90deg,rgba(18,61,113,0.18) 0%,rgba(39,199,217,0.9) 100%);"></div>
          <div style="margin-top:14px;font-size:14px;line-height:1.8;color:#5d708b;text-align:center;">\u9884\u8ba1\u5230\u671f\u65f6\u95f4\uff1a{safe_expires_at}</div>
        ''',
        note_lines=[
            '\u8bf7\u524d\u5f80\u540e\u53f0\u300c\u7ad9\u70b9\u8bbe\u7f6e\u300d\u66f4\u65b0 163 \u90ae\u7bb1\u6388\u6743\u7801\uff0c\u5e76\u786e\u8ba4\u6d4b\u8bd5\u90ae\u4ef6\u53d1\u9001\u6b63\u5e38\u3002',
            '\u66f4\u65b0\u5bc6\u94a5\u540e\uff0c\u7cfb\u7edf\u4f1a\u81ea\u52a8\u91cd\u65b0\u8ba1\u7b97 180 \u5929\u7684\u6709\u6548\u671f\u3002',
        ],
    )
    text_body = f'SMTP \u6388\u6743\u7801\u9884\u8ba1\u8fd8\u5269 {day_label}\uff0c\u9884\u8ba1\u5230\u671f\u65f6\u95f4\uff1a{safe_expires_at}\u3002\u8bf7\u5c3d\u5feb\u66f4\u65b0\u540e\u53f0 SMTP \u6388\u6743\u7801\u3002'
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
    return default_state


def _save_login_attempts(file_path: Path, state):
    safe_state = state if isinstance(state, dict) else {'ips': {}}
    if not isinstance(safe_state.get('ips'), dict):
        safe_state['ips'] = {}
    tmp = file_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file_path)
    try:
        # 登录封禁记录含 IP 与账号信息，仅允许属主读取。
        os.chmod(file_path, 0o600)
    except OSError:
        pass


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
        delay_until = int(item.get('delay_until', 0) or 0)
        if delay_until <= now_ts:
            delay_until = 0
        if not failures and blocked_until <= 0 and delay_until <= 0:
            to_delete.append(ip)
        else:
            item['failures'] = failures
            item['blocked_until'] = blocked_until
            item['delay_until'] = delay_until
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
    delay_until = int(item.get('delay_until', 0) or 0)
    if delay_until > now_ts:
        return delay_until - now_ts
    if delay_until:
        item['delay_until'] = 0
        ips[ip_addr] = item
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
    return datetime.fromtimestamp(ts, tz=BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')


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


def _is_ip_country_allowed(ip: str, geo_settings: dict, resolve_country_code_func) -> tuple:
    """检查登录 IP 是否符合后台地域访问规则。"""
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
        if not normalize_admin_login_geo_settings(geo_settings).get('enabled', True):
            return True, ''
        return False, '无法获取 IP 归属地，已拒绝登录'
    if not is_country_code_allowed(country_code, geo_settings):
        location = ''
        try:
            from app.admin_audit import resolve_ip_location
            location = resolve_ip_location(ip)
        except Exception:
            location = ''
        continent_key = get_country_continent_key(country_code)
        continent_label = ''
        for continent in ADMIN_GEO_CONTINENTS:
            if continent['key'] == continent_key:
                continent_label = continent['label']
                break
        location_suffix = f'({location})' if location else ''
        continent_suffix = f'，所属大洲：{continent_label}' if continent_label else ''
        return False, f'您的登录 IP 归属地{location_suffix}{continent_suffix}被禁止登录'
    return True, ''


def _get_turnstile_settings(config):
    safe = config if isinstance(config, dict) else {}
    enabled = _parse_bool(safe.get('turnstile_enabled', False), False)
    site_key = str(safe.get('turnstile_site_key', '') or '').strip()
    secret_key = str(safe.get('turnstile_secret_key', '') or '').strip()
    proxy_url = str(safe.get('turnstile_proxy_url', '') or '').strip()
    proxy_fallback_enabled = _parse_bool(safe.get('turnstile_proxy_fallback_enabled', False), False)
    if enabled and (not site_key or not secret_key):
        enabled = False
    return {
        'enabled': enabled,
        'site_key': site_key,
        'secret_key': secret_key,
        'proxy_url': proxy_url,
        'proxy_fallback_enabled': proxy_fallback_enabled,
    }


def _get_admin_captcha_settings(config):
    """读取后台登录使用的验证码提供商配置。

    未设置 provider 时兼容历史配置，默认继续使用 Cloudflare Turnstile。
    ESA 由边缘规则完成验签，应用只负责把前端返回的验签参数带入业务请求。
    """
    safe = config if isinstance(config, dict) else {}
    provider = str(safe.get('admin_captcha_provider') or 'cloudflare').strip().lower()
    if provider not in {'cloudflare', 'aliyun_esa'}:
        provider = 'cloudflare'
    enabled = _parse_bool(safe.get('turnstile_enabled', False), False)
    site_key = str(safe.get('turnstile_site_key', '') or '').strip()
    secret_key = str(safe.get('turnstile_secret_key', '') or '').strip()
    proxy_url = str(safe.get('turnstile_proxy_url', '') or '').strip()
    proxy_fallback_enabled = _parse_bool(safe.get('turnstile_proxy_fallback_enabled', False), False)
    esa_identity = str(safe.get('admin_esa_identity', '') or '').strip()
    esa_scene_id = str(safe.get('admin_esa_scene_id', '') or '').strip()
    esa_region = str(safe.get('admin_esa_region', '') or 'cn').strip().lower() or 'cn'
    if esa_region not in {'cn', 'sgp'}:
        esa_region = 'cn'
    if enabled:
        if provider == 'cloudflare' and (not site_key or not secret_key):
            enabled = False
        elif provider == 'aliyun_esa' and (not esa_identity or not esa_scene_id):
            enabled = False
    return {
        'enabled': enabled,
        'provider': provider,
        'site_key': site_key,
        'secret_key': secret_key,
        'proxy_url': proxy_url,
        'proxy_fallback_enabled': proxy_fallback_enabled,
        'esa_identity': esa_identity,
        'esa_scene_id': esa_scene_id,
        'esa_region': esa_region,
    }


def _normalize_turnstile_proxy_url(raw_value: str) -> str:
    proxy_url = str(raw_value or '').strip()
    if not proxy_url:
        return ''
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return ''
    return proxy_url


def _build_turnstile_verify_request(secret_key: str, token: str, remote_ip: str = ''):
    payload = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    return Request(
        TURNSTILE_VERIFY_URL,
        data=urlencode(payload).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )


def _get_turnstile_ssl_context():
    ssl_context = None
    if CERTIFI_AVAILABLE and certifi is not None:
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_context = None
    return ssl_context


def _open_turnstile_request(req, *, timeout: int, ssl_context=None, proxy_url: str = ''):
    normalized_proxy = _normalize_turnstile_proxy_url(proxy_url)
    if not normalized_proxy:
        return urlopen(req, timeout=timeout, context=ssl_context)

    handlers = [ProxyHandler({'http': normalized_proxy, 'https': normalized_proxy})]
    if ssl_context is not None:
        handlers.append(HTTPSHandler(context=ssl_context))
    opener = build_opener(*handlers)
    return opener.open(req, timeout=timeout)


def _load_turnstile_response_json(resp):
    body = resp.read().decode('utf-8', errors='ignore')
    return json.loads(body) if body else {}


def _request_turnstile_siteverify(
    secret_key: str,
    token: str,
    *,
    remote_ip: str = '',
    timeout: int = TURNSTILE_DIRECT_TIMEOUT_SECONDS,
    proxy_url: str = '',
):
    req = _build_turnstile_verify_request(secret_key=secret_key, token=token, remote_ip=remote_ip)
    try:
        with _open_turnstile_request(
            req,
            timeout=timeout,
            ssl_context=_get_turnstile_ssl_context(),
            proxy_url=proxy_url,
        ) as resp:
            result = _load_turnstile_response_json(resp)
            return result if isinstance(result, dict) else {}
    except HTTPError as exc:
        result = _load_turnstile_response_json(exc)
        if isinstance(result, dict):
            result['_http_status'] = exc.code
            return result
        raise


def _is_turnstile_network_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return False
    return isinstance(exc, (
        TimeoutError,
        socket.timeout,
        ConnectionError,
        ConnectionResetError,
        OSError,
        URLError,
        ssl.SSLError,
    ))


def _format_turnstile_error_codes(codes) -> str:
    if isinstance(codes, list):
        return ','.join(str(x) for x in codes if x)
    return str(codes or '').strip()


def _parse_turnstile_verify_result(result):
    if bool((result or {}).get('success')):
        return True, ''

    code_text = _format_turnstile_error_codes((result or {}).get('error-codes') or [])
    if code_text:
        return False, f'验证码校验未通过({code_text})'
    return False, '验证码校验未通过'


def _verify_turnstile_token(
    secret_key: str,
    token: str,
    remote_ip: str = '',
    *,
    proxy_url: str = '',
    proxy_fallback_enabled: bool = False,
):
    normalized_proxy = _normalize_turnstile_proxy_url(proxy_url)

    try:
        result = _request_turnstile_siteverify(
            secret_key=secret_key,
            token=token,
            remote_ip=remote_ip,
            timeout=TURNSTILE_DIRECT_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        if proxy_fallback_enabled and normalized_proxy and _is_turnstile_network_error(exc):
            try:
                result = _request_turnstile_siteverify(
                    secret_key=secret_key,
                    token=token,
                    remote_ip=remote_ip,
                    timeout=TURNSTILE_PROXY_TIMEOUT_SECONDS,
                    proxy_url=normalized_proxy,
                )
            except Exception as proxy_exc:
                return False, f'验证码服务直连失败，代理重试也失败: {proxy_exc}'
        else:
            return False, f'验证码服务请求失败: {exc}'

    return _parse_turnstile_verify_result(result)


def get_turnstile_settings(config):
    """读取公共流程与后台流程共用的 Turnstile 配置。"""
    return _get_turnstile_settings(config)


def verify_turnstile_token(
    secret_key: str,
    token: str,
    remote_ip: str = '',
    *,
    proxy_url: str = '',
    proxy_fallback_enabled: bool = False,
):
    """校验公共流程与后台流程共用的 Turnstile 令牌。"""
    return _verify_turnstile_token(
        secret_key=secret_key,
        token=token,
        remote_ip=remote_ip,
        proxy_url=proxy_url,
        proxy_fallback_enabled=proxy_fallback_enabled,
    )


def _extract_admin_captcha_param(request, data):
    payload = data if isinstance(data, dict) else {}
    return str(
        payload.get('captchaVerifyParam')
        or payload.get('captcha_verify_param')
        or request.headers.get('captcha-verify-param', '')
        or request.args.get('captcha_verify_param', '')
        or ''
    ).strip()


def _verify_admin_captcha(settings, token, remote_ip=''):
    """验证后台登录挑战。

    Cloudflare 由源站调用 siteverify；ESA 的验签由边缘规则完成，应用只
    检查前端确实提交了 ESA 返回的 captchaVerifyParam，避免未配置边缘规则
    时完全绕过挑战。
    """
    if not settings.get('enabled'):
        return True, ''
    if not token:
        return False, '请先完成人机验证。'
    if settings.get('provider') == 'aliyun_esa':
        return True, ''
    return _verify_turnstile_token(
        secret_key=settings.get('secret_key', ''),
        token=token,
        remote_ip=remote_ip,
        proxy_url=settings.get('proxy_url', ''),
        proxy_fallback_enabled=settings.get('proxy_fallback_enabled', False),
    )


def _build_turnstile_connectivity_result(*, secret_key: str, proxy_url: str = ''):
    normalized_proxy = _normalize_turnstile_proxy_url(proxy_url)
    timeout = TURNSTILE_PROXY_TIMEOUT_SECONDS if normalized_proxy else TURNSTILE_DIRECT_TIMEOUT_SECONDS
    result = _request_turnstile_siteverify(
        secret_key=secret_key,
        token=TURNSTILE_CONNECTIVITY_TEST_TOKEN,
        timeout=timeout,
        proxy_url=normalized_proxy,
    )
    codes = result.get('error-codes') or []
    return {
        'success': True,
        'cloudflare_success': bool(result.get('success')),
        'error_codes': _format_turnstile_error_codes(codes),
        'http_status': result.get('_http_status') or 200,
    }


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

    html_body, text_body = _build_login_email_content_v2(username, code_to_send)
    _send_smtp_mail(
        smtp_settings,
        to_email=email,
        subject=_build_login_email_subject_v2(),
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
        if not hmac.compare_digest(_email_code_hash(code, code_salt), expected_hash):
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

    html_body, text_body = _build_binding_email_content_v2(normalized_username, code)
    _send_smtp_mail(
        smtp_settings,
        to_email=normalized_email,
        subject='元芯验证码',
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
        code_hash = _email_code_hash(code, str(item.get('code_salt', '') or '').strip())
        stored_hash = str(item.get('code_hash', '') or '').strip()
        # 统一使用常量时间比较，避免时序侧信道（与 _verify_pending_login_code 一致）。
        try:
            code_ok = hmac.compare_digest(code_hash.encode('utf-8'), stored_hash.encode('utf-8'))
        except Exception:
            code_ok = False
        if not code_ok:
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
    html_body, text_body = _build_smtp_notice_content_v2(remaining_days, settings.get('smtp_password_expires_at', ''))
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
    return is_admin_session_expired(sess)


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
    get_public_base_url=None,
):
    """向 Flask 应用注册后台管理相关路由。"""
    _resolve_ip_location = resolve_ip_location if resolve_ip_location else lambda ip: '未知'
    _resolve_ip_country_code = resolve_ip_country_code if resolve_ip_country_code else lambda ip: ''
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    # 注入会话吊销查询所需的用户数据文件路径。
    _set_users_file_for_revocation(_get_admin_users_file(root))
    # 跨进程文件锁的数据目录（登录计数/邮箱验证码/管理员账号）。
    for state_lock in (LOGIN_ATTEMPTS_LOCK, ADMIN_USERS_LOCK, EMAIL_AUTH_STATE_LOCK):
        state_lock.set_base_dir(root / 'data')
    passkey_runtime_lock = threading.RLock()
    passkey_runtime = {'key': None, 'config': None, 'store': None}

    def _load_passkey_runtime():
        public_url = str(get_public_base_url() if callable(get_public_base_url) else os.environ.get('PUBLIC_BASE_URL', '') or '')
        config = load_passkey_config(root, public_url, get_config() or {})
        runtime_key = (
            config.enabled, config.rp_id, config.rp_name, config.origin, str(config.db_path),
            config.challenge_ttl_seconds, config.max_credentials_per_user, config.error,
        )
        with passkey_runtime_lock:
            if passkey_runtime['key'] == runtime_key:
                return passkey_runtime['config'], passkey_runtime['store']
            store = PasskeyStore(config)
            if config.enabled:
                try:
                    require_webauthn()
                    store.initialize()
                except Exception as exc:
                    app.logger.error('Passkey 初始化失败，功能已关闭：%s', exc)
                    config = replace(config, enabled=False, error=str(exc))
                    store = PasskeyStore(config)
            elif config.error:
                app.logger.error('Passkey 配置无效，功能已关闭：%s', config.error)
            passkey_runtime.update({'key': runtime_key, 'config': config, 'store': store})
            return config, store

    class _PasskeyConfigProxy:
        def __getattr__(self, name):
            return getattr(_load_passkey_runtime()[0], name)

    class _PasskeyStoreProxy:
        def __getattr__(self, name):
            return getattr(_load_passkey_runtime()[1], name)

    passkey_config = _PasskeyConfigProxy()
    passkey_store = _PasskeyStoreProxy()
    try:
        _ensure_admin_users_store(root, get_config, update_config)
    except Exception:
        # 即使初始化迁移暂时异常，也尽量保持路由可用，但必须留下定位线索。
        app.logger.exception('管理员账号存储初始化失败，请检查管理员配置')
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
        if not str(session.get(CSRF_SESSION_KEY) or '').strip():
            session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
        return _build_admin_html_response('admin')

    def _passkey_session_binding():
        binding = str(session.get('admin_passkey_browser_binding', '') or '').strip()
        if not binding:
            binding = secrets.token_urlsafe(32)
            session['admin_passkey_browser_binding'] = binding
        return binding

    def _passkey_unavailable_response():
        message = passkey_config.error or 'Passkey 登录当前未启用。'
        return jsonify({'success': False, 'message': message}), 503

    def _passkey_options_payload(options, request_id: str):
        from webauthn import options_to_json
        return jsonify({
            'success': True,
            'request_id': request_id,
            'options': json.loads(options_to_json(options)),
        })

    def _passkey_device_name(raw_value):
        value = str(raw_value or '').strip()
        if not value:
            value = f"Passkey 设备 {now_beijing().strftime('%Y-%m-%d')}"
        if len(value) > 50:
            raise ValueError('设备名称不能超过 50 个字符。')
        return value

    def _passkey_step_up_valid(username: str) -> bool:
        return (
            _normalize_username(session.get('admin_passkey_step_up_username', '')) == _normalize_username(username)
            and int(session.get('admin_passkey_step_up_until', 0) or 0) >= int(time.time())
        )

    def _set_passkey_step_up(username: str):
        session['admin_passkey_step_up_username'] = _normalize_username(username)
        session['admin_passkey_step_up_until'] = int(time.time()) + 10 * 60

    @app.route('/api/admin/passkey/public-config', methods=['GET'])
    def admin_passkey_public_config():
        return jsonify({
            'success': True,
            'enabled': bool(passkey_config.enabled),
            'rp_id': passkey_config.rp_id if passkey_config.enabled else '',
            'platform_supported_hint': True,
            'message': passkey_config.error if not passkey_config.enabled else '',
        })

    @app.route('/api/admin/security/passkeys', methods=['GET'])
    @login_required
    def admin_passkey_settings_get():
        config, _store = _load_passkey_runtime()
        return jsonify({
            'success': True,
            'is_super_admin': bool(_is_super_admin_session(session)),
            'enabled': bool(config.enabled),
            'configured_enabled': bool((get_config() or {}).get('passkey_enabled', False)),
            'origin': config.origin,
            'rp_id': config.rp_id,
            'rp_name': config.rp_name,
            'max_credentials_per_user': config.max_credentials_per_user,
            'error': config.error,
            'public_base_url': str(get_public_base_url() if callable(get_public_base_url) else os.environ.get('PUBLIC_BASE_URL', '') or ''),
            'enabled_managed_by_environment': os.environ.get('PASSKEY_ENABLED') is not None,
            'max_managed_by_environment': os.environ.get('PASSKEY_MAX_CREDENTIALS_PER_USER') is not None,
        })

    @app.route('/api/admin/security/passkeys', methods=['POST'])
    @login_required
    def admin_passkey_settings_update():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        if os.environ.get('PASSKEY_ENABLED') is not None:
            return jsonify({'success': False, 'message': 'Passkey 开关当前由 Docker 环境变量管理，后台不能覆盖。'}), 409
        data = request.get_json(silent=True) or {}
        enabled = _parse_bool(data.get('enabled', False), False)
        try:
            maximum = max(1, min(50, int(data.get('max_credentials_per_user', 10) or 10)))
        except Exception:
            return jsonify({'success': False, 'message': '每账号设备上限必须是 1 到 50 的整数。'}), 400
        if os.environ.get('PASSKEY_MAX_CREDENTIALS_PER_USER') is not None:
            maximum = load_passkey_config(root, str(get_public_base_url() if callable(get_public_base_url) else ''), get_config() or {}).max_credentials_per_user
        current = get_config() or {}
        candidate = dict(current)
        candidate.update({
            'passkey_enabled': enabled,
            'passkey_max_credentials_per_user': maximum,
        })
        public_url = str(get_public_base_url() if callable(get_public_base_url) else os.environ.get('PUBLIC_BASE_URL', '') or '')
        candidate_config = load_passkey_config(root, public_url, candidate)
        if enabled and (not candidate_config.enabled or candidate_config.error):
            return jsonify({'success': False, 'message': candidate_config.error or 'Passkey 配置校验失败。'}), 400
        if enabled:
            try:
                require_webauthn()
                PasskeyStore(candidate_config).initialize()
            except Exception as exc:
                return jsonify({'success': False, 'message': f'Passkey 初始化失败：{exc}'}), 500
        update_config({
            'passkey_enabled': enabled,
            'passkey_max_credentials_per_user': maximum,
        })
        with passkey_runtime_lock:
            passkey_runtime['key'] = None
        refreshed, _store = _load_passkey_runtime()
        append_admin_login_log(
            operation='passkey_settings', success=True,
            username=session.get('admin_username', ''),
            detail=f"Passkey 登录已{'启用' if refreshed.enabled else '关闭'}；每账号上限 {refreshed.max_credentials_per_user}",
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({
            'success': True,
            'message': f"Passkey 登录已{'启用' if refreshed.enabled else '关闭'}。",
            'enabled': refreshed.enabled,
            'origin': refreshed.origin,
            'rp_id': refreshed.rp_id,
            'max_credentials_per_user': refreshed.max_credentials_per_user,
        })

    @app.route('/api/admin/ip-preflight', methods=['GET'])
    def admin_ip_preflight():
        """登录前 IP 预检：返回客户端 IP、归属地和是否允许登录。"""
        # 公开端点必须限流：每次未命中缓存都会触发最多三个出站 GeoIP 查询，
        # 不加限制会被用于放大攻击或拖垮 worker。
        preflight_ip = _get_request_ip(request)
        allowed, retry_after, _count = check_and_record(
            f'ippreflight:{preflight_ip}',
            limit=10,
            window=60,
        )
        if not allowed:
            response = jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'})
            response.headers['Retry-After'] = str(max(1, retry_after))
            return response, 429

        ip_addr = _get_request_ip(request)
        config = get_config() or {}
        geo_settings = normalize_admin_login_geo_settings(config)
        location = _resolve_ip_location(ip_addr)
        country_code = _resolve_ip_country_code(ip_addr)
        allowed, reason = _is_ip_country_allowed(
            ip_addr, geo_settings, _resolve_ip_country_code
        )
        return jsonify({
            'ip': ip_addr,
            'location': location,
            'country_code': country_code,
            'continent_key': get_country_continent_key(country_code),
            'allowed': allowed,
            'reason': reason,
        })

    @app.route('/api/admin/security/login-geo', methods=['GET'])
    @login_required
    def admin_login_geo_config():
        config = get_config() or {}
        return jsonify({
            'success': True,
            'config': build_admin_login_geo_settings_payload(config),
            'catalog': build_admin_login_geo_catalog_payload(),
        })

    @app.route('/api/admin/security/login-geo', methods=['POST'])
    @login_required
    def admin_login_geo_config_update():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        data = request.get_json(silent=True) or {}
        # 传入当前生效配置：缺失的大洲/国家键继承现状，避免部分更新自锁。
        updates = extract_admin_login_geo_updates(data, get_config() or {})
        update_config(updates)
        return jsonify({
            'success': True,
            'message': '后台登录地域访问规则已保存。',
            'config': build_admin_login_geo_settings_payload(get_config() or {}),
            'catalog': build_admin_login_geo_catalog_payload(),
        })

    @app.route('/api/admin/security/turnstile/public', methods=['GET'])
    def admin_turnstile_public_config():
        """获取登录页验证码组件使用的公开配置。"""
        config = get_config()
        settings = _get_admin_captcha_settings(config)
        return jsonify({
            'enabled': settings['enabled'],
            'provider': settings['provider'],
            'site_key': settings['site_key'] if settings['enabled'] and settings['provider'] == 'cloudflare' else '',
            'esa_identity': settings['esa_identity'] if settings['enabled'] and settings['provider'] == 'aliyun_esa' else '',
            'esa_scene_id': settings['esa_scene_id'] if settings['enabled'] and settings['provider'] == 'aliyun_esa' else '',
            'esa_region': settings['esa_region'],
        })

    @app.route('/api/admin/security/turnstile', methods=['GET'])
    @login_required
    def admin_turnstile_config():
        """获取后台面板使用的验证码配置。"""
        settings = _get_admin_captcha_settings(get_config())
        secret_masked = ''
        if settings['secret_key']:
            secret = settings['secret_key']
            secret_masked = f"{secret[:6]}...{secret[-4:]}" if len(secret) > 12 else '***'
        return jsonify({
            'enabled': settings['enabled'],
            'provider': settings['provider'],
            'site_key': settings['site_key'],
            'secret_key': secret_masked,
            'proxy_url': settings.get('proxy_url', ''),
            'proxy_fallback_enabled': bool(settings.get('proxy_fallback_enabled', False)),
            'esa_identity': settings.get('esa_identity', ''),
            'esa_scene_id': settings.get('esa_scene_id', ''),
            'esa_region': settings.get('esa_region', 'cn'),
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
        provider = str(data.get('provider') or 'cloudflare').strip().lower()
        site_key = str(data.get('site_key', '') or '').strip()
        secret_key_input = str(data.get('secret_key', '') or '').strip()
        proxy_url = str(data.get('proxy_url', '') or '').strip()
        proxy_fallback_enabled = _parse_bool(data.get('proxy_fallback_enabled', False), False)
        esa_identity = str(data.get('esa_identity', '') or '').strip()
        esa_scene_id = str(data.get('esa_scene_id', '') or '').strip()
        esa_region = str(data.get('esa_region') or 'cn').strip().lower() or 'cn'

        if provider not in {'cloudflare', 'aliyun_esa'}:
            return jsonify({'success': False, 'message': '不支持的验证码提供商。'}), 400
        if esa_region not in {'cn', 'sgp'}:
            return jsonify({'success': False, 'message': 'ESA 地区只能选择 cn 或 sgp。'}), 400

        config = get_config()
        existing_secret = str(config.get('turnstile_secret_key', '') or '').strip()
        # 提交的是掩码值或空值时，保留现有密钥。
        if secret_key_input and not secret_key_input.startswith('***'):
            secret_key = secret_key_input
        else:
            secret_key = existing_secret

        if enabled and provider == 'cloudflare' and (not site_key or not secret_key):
            return jsonify({'success': False, 'message': '启用 Cloudflare Turnstile 时必须填写站点密钥和服务端密钥。'}), 400
        if enabled and provider == 'aliyun_esa' and (not esa_identity or not esa_scene_id):
            return jsonify({'success': False, 'message': '启用阿里云 ESA 时必须填写身份标和场景 ID。'}), 400
        if provider == 'cloudflare' and proxy_url and not _normalize_turnstile_proxy_url(proxy_url):
            return jsonify({'success': False, 'message': '代理地址必须以 http:// 或 https:// 开头，并包含有效主机。'}), 400
        if provider == 'cloudflare' and proxy_fallback_enabled and not proxy_url:
            return jsonify({'success': False, 'message': '启用代理重试兜底前，请先填写代理地址。'}), 400

        update_config({
            'turnstile_enabled': bool(enabled),
            'admin_captcha_provider': provider,
            'turnstile_site_key': site_key,
            'turnstile_secret_key': secret_key,
            'turnstile_proxy_url': proxy_url,
            'turnstile_proxy_fallback_enabled': bool(proxy_fallback_enabled),
            'admin_esa_identity': esa_identity,
            'admin_esa_scene_id': esa_scene_id,
            'admin_esa_region': esa_region,
        })
        return jsonify({'success': True, 'message': '登录验证设置已保存'})

    @app.route('/api/admin/security/turnstile/test-direct', methods=['POST'])
    @login_required
    def admin_turnstile_test_direct():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403
        settings = _get_admin_captcha_settings(get_config() or {})
        if settings.get('provider') != 'cloudflare':
            return jsonify({'success': False, 'message': '当前验证码提供商不是 Cloudflare，无需测试 Turnstile 直连。'}), 400
        secret_key = settings.get('secret_key', '')
        if not secret_key:
            return jsonify({'success': False, 'message': '请先填写并保存服务端密钥。'}), 400
        try:
            result = _build_turnstile_connectivity_result(secret_key=secret_key)
        except Exception as exc:
            return jsonify({'success': False, 'message': f'直连 Cloudflare Turnstile 失败：{exc}'}), 400
        return jsonify({
            **result,
            'message': '直连 Cloudflare Turnstile 可达。',
        })

    @app.route('/api/admin/security/turnstile/test-proxy', methods=['POST'])
    @login_required
    def admin_turnstile_test_proxy():
        if not _is_super_admin_session(session):
            return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403
        data = request.get_json(silent=True) or {}
        settings = _get_admin_captcha_settings(get_config() or {})
        if settings.get('provider') != 'cloudflare':
            return jsonify({'success': False, 'message': '当前验证码提供商不是 Cloudflare，无需测试 Turnstile 代理。'}), 400
        secret_key = settings.get('secret_key', '')
        proxy_url = str(data.get('proxy_url') or settings.get('proxy_url', '') or '').strip()
        normalized_proxy = _normalize_turnstile_proxy_url(proxy_url)
        if not secret_key:
            return jsonify({'success': False, 'message': '请先填写并保存服务端密钥。'}), 400
        if not normalized_proxy:
            return jsonify({'success': False, 'message': '请先填写有效的代理地址，例如 http://glash:7890。'}), 400
        try:
            result = _build_turnstile_connectivity_result(secret_key=secret_key, proxy_url=normalized_proxy)
        except Exception as exc:
            return jsonify({'success': False, 'message': f'代理访问 Cloudflare Turnstile 失败：{exc}'}), 400
        return jsonify({
            **result,
            'message': '代理访问 Cloudflare Turnstile 可达。',
        })

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

        try:
            smtp_port = int(data.get('smtp_port') or 465)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'SMTP 端口必须是数字。'}), 400

        updates = {
            'email_auth_enabled': _parse_bool(data.get('email_auth_enabled', False), False),
            'smtp_host': str(data.get('smtp_host', '') or '').strip(),
            'smtp_port': smtp_port,
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
        session['admin_previous_login_at'] = prev_last_login_at
        session['admin_previous_login_ip'] = prev_last_login_ip
        session['admin_current_login_at'] = current_login_at
        session['admin_current_login_ip'] = ip_addr
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
            'csrf_token': session.get(CSRF_SESSION_KEY, ''),
            'last_login_at': prev_last_login_at,
            'last_login_ip': prev_last_login_ip,
            'current_login_at': current_login_at,
            'current_login_ip': ip_addr,
        })

    @app.route('/admin/passkey/login/options', methods=['POST'])
    def admin_passkey_login_options():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        ip_addr = _get_request_ip(request)
        geo_settings = normalize_admin_login_geo_settings(get_config() or {})
        allowed, reason = _is_ip_country_allowed(ip_addr, geo_settings, _resolve_ip_country_code)
        if not allowed:
            return jsonify({'success': False, 'message': reason}), 403
        if not passkey_store.check_rate_limit(ip_addr):
            return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试。'}), 429
        attempts_file = _get_login_attempts_file(root)
        now_ts = int(time.time())
        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            blocked_until = int((ip_item or {}).get('blocked_until', 0) or 0)
            delay_seconds = _get_login_delay_seconds(attempts_state, ip_addr, now_ts)
        if blocked_until > now_ts or delay_seconds > 0:
            return jsonify({'success': False, 'message': '登录尝试过于频繁，请稍后再试。'}), 429
        try:
            from webauthn import generate_authentication_options
            from webauthn.helpers.structs import UserVerificationRequirement
            options = generate_authentication_options(
                rp_id=passkey_config.rp_id,
                user_verification=UserVerificationRequirement.REQUIRED,
                timeout=60000,
            )
            request_id = passkey_store.create_challenge(
                'login', options.challenge, _passkey_session_binding()
            )
            return _passkey_options_payload(options, request_id)
        except Exception as exc:
            app.logger.exception('生成 Passkey 登录请求失败')
            return jsonify({'success': False, 'message': f'无法发起 Passkey 登录：{exc}'}), 500

    @app.route('/admin/passkey/login/verify', methods=['POST'])
    def admin_passkey_login_verify():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        request_id = str(data.get('request_id', '') or '').strip()
        credential = data.get('credential') if isinstance(data.get('credential'), dict) else {}
        credential_id = str(credential.get('id', '') or '').strip()
        ip_addr = _get_request_ip(request)
        geo_settings = normalize_admin_login_geo_settings(get_config() or {})
        allowed, reason = _is_ip_country_allowed(ip_addr, geo_settings, _resolve_ip_country_code)
        if not allowed:
            return jsonify({'success': False, 'message': reason}), 403
        try:
            challenge = passkey_store.load_challenge(
                request_id, 'login', _passkey_session_binding()
            )
            stored = passkey_store.get_credential(credential_id)
            if not stored:
                raise ValueError('未知 Passkey')
            with ADMIN_USERS_LOCK:
                users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
                login_user, _ = _find_user(users_data, stored.get('username', ''))
                if login_user is not None:
                    login_user = dict(login_user)
            if login_user is None or not bool(login_user.get('enabled', True)):
                raise ValueError('账号不可用')
            from webauthn import verify_authentication_response
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=passkey_config.rp_id,
                expected_origin=passkey_config.origin,
                credential_public_key=bytes(stored['public_key']),
                credential_current_sign_count=int(stored.get('sign_count', 0) or 0),
                require_user_verification=True,
            )
            passkey_store.update_usage(
                credential_id,
                verification.new_sign_count,
                ip_addr,
                bool(getattr(verification, 'credential_backed_up', stored.get('backup_state', False))),
            )
            passkey_store.consume_challenge(request_id)
            with LOGIN_ATTEMPTS_LOCK:
                attempts_file = _get_login_attempts_file(root)
                attempts_state = _load_login_attempts(attempts_file)
                _prune_login_attempts(attempts_state, int(time.time()))
                _reset_login_attempts_for_ip(attempts_state, ip_addr)
                _save_login_attempts(attempts_file, attempts_state)
            return _finalize_login_success(login_user, ip_addr, detail_suffix='Passkey 验证通过')
        except Exception as exc:
            with LOGIN_ATTEMPTS_LOCK:
                attempts_file = _get_login_attempts_file(root)
                attempts_state = _load_login_attempts(attempts_file)
                now_ts = int(time.time())
                _prune_login_attempts(attempts_state, now_ts)
                blocked_now, _blocked_until, _remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                if not blocked_now:
                    _set_login_delay(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
            app.logger.warning('Passkey 登录验证失败 [%s]：%s', credential_id[:12], exc)
            append_admin_login_log(
                operation='admin_login', success=False, username='',
                detail=f'Passkey 验证失败；credential: {credential_id[:8]}', hidden_account=False,
            )
            return jsonify({'success': False, 'message': 'Passkey 验证失败，请改用邮箱验证码或账号密码。'}), 401

    @app.route('/api/admin/account/passkeys/confirm/email/send', methods=['POST'])
    @login_required
    def admin_passkey_confirm_email_send():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        username = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            user, _ = _find_user(users_data, username)
        if user is None or not _has_verified_email(user):
            return jsonify({'success': False, 'message': '当前账号尚未绑定已验证安全邮箱。'}), 400
        smtp_settings = _get_email_auth_settings(get_config() or {})
        if not smtp_settings['enabled'] or not _smtp_ready_for_email_auth(smtp_settings):
            return jsonify({'success': False, 'message': '邮箱验证当前不可用，请联系管理员。'}), 503
        now_ts = int(time.time())
        resend_at = int(session.get('admin_passkey_email_resend_at', 0) or 0)
        if resend_at > now_ts:
            return jsonify({'success': False, 'message': f'请等待 {resend_at - now_ts} 秒后重试。'}), 429
        code = _generate_email_code()
        salt = secrets.token_hex(16)
        safe_username = html.escape(username)
        try:
            _send_smtp_mail(
                smtp_settings,
                to_email=user.get('email', ''),
                subject='元芯传感后台 Passkey 安全验证',
                text_body=f'您正在为后台账号 {username} 管理 Passkey。验证码：{code}，5 分钟内有效。若非本人操作，请忽略。',
                html_body=f'<p>您正在为后台账号 <strong>{safe_username}</strong> 管理 Passkey。</p><p>验证码：<strong style="font-size:24px">{code}</strong></p><p>5 分钟内有效。若非本人操作，请忽略。</p>',
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'验证码发送失败：{exc}'}), 400
        session['admin_passkey_email_code_hash'] = _email_code_hash(code, salt)
        session['admin_passkey_email_code_salt'] = salt
        session['admin_passkey_email_code_expires_at'] = now_ts + EMAIL_CODE_EXPIRES_SECONDS
        session['admin_passkey_email_code_failures'] = 0
        session['admin_passkey_email_resend_at'] = now_ts + EMAIL_CODE_RESEND_COOLDOWN_SECONDS
        return jsonify({
            'success': True, 'message': '验证码已发送。',
            'email_masked': _mask_email_address(user.get('email', '')),
            'resend_after': EMAIL_CODE_RESEND_COOLDOWN_SECONDS,
        })

    @app.route('/api/admin/account/passkeys/confirm/email/verify', methods=['POST'])
    @login_required
    def admin_passkey_confirm_email_verify():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        code = str((request.get_json(silent=True) or {}).get('code', '') or '').strip()
        username = _normalize_username(session.get('admin_username', ''))
        now_ts = int(time.time())
        failures = int(session.get('admin_passkey_email_code_failures', 0) or 0)
        expected = str(session.get('admin_passkey_email_code_hash', '') or '')
        salt = str(session.get('admin_passkey_email_code_salt', '') or '')
        expires_at = int(session.get('admin_passkey_email_code_expires_at', 0) or 0)
        if not code or not expected or expires_at < now_ts or failures >= EMAIL_CODE_MAX_VERIFY_FAILURES:
            return jsonify({'success': False, 'message': '验证码已失效，请重新发送。'}), 400
        if not secrets.compare_digest(expected, _email_code_hash(code, salt)):
            session['admin_passkey_email_code_failures'] = failures + 1
            return jsonify({'success': False, 'message': '验证码错误。'}), 400
        for key in ('admin_passkey_email_code_hash', 'admin_passkey_email_code_salt',
                    'admin_passkey_email_code_expires_at', 'admin_passkey_email_code_failures'):
            session.pop(key, None)
        _set_passkey_step_up(username)
        return jsonify({'success': True, 'message': '安全验证通过。', 'valid_for': 600})

    @app.route('/api/admin/account/passkeys/verify/options', methods=['POST'])
    @login_required
    def admin_passkey_step_up_options():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        username = _normalize_username(session.get('admin_username', ''))
        if not passkey_store.check_rate_limit(_get_request_ip(request)):
            return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试。'}), 429
        ids = passkey_store.credential_ids(username)
        if not ids:
            return jsonify({'success': False, 'message': '当前账号尚未绑定 Passkey，请使用邮箱验证码。'}), 400
        try:
            from webauthn import generate_authentication_options
            from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
            options = generate_authentication_options(
                rp_id=passkey_config.rp_id,
                allow_credentials=[PublicKeyCredentialDescriptor(id=item) for item in ids],
                user_verification=UserVerificationRequirement.REQUIRED,
                timeout=60000,
            )
            request_id = passkey_store.create_challenge(
                'step_up', options.challenge, _passkey_session_binding(), username
            )
            return _passkey_options_payload(options, request_id)
        except Exception as exc:
            return jsonify({'success': False, 'message': f'无法发起安全验证：{exc}'}), 500

    @app.route('/api/admin/account/passkeys/verify', methods=['POST'])
    @login_required
    def admin_passkey_step_up_verify():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        credential = data.get('credential') if isinstance(data.get('credential'), dict) else {}
        credential_id = str(credential.get('id', '') or '').strip()
        request_id = str(data.get('request_id', '') or '').strip()
        username = _normalize_username(session.get('admin_username', ''))
        try:
            challenge = passkey_store.load_challenge(
                request_id, 'step_up', _passkey_session_binding(), username
            )
            stored = passkey_store.get_credential(credential_id)
            if not stored or _normalize_username(stored.get('username', '')) != username:
                raise ValueError('Passkey 不属于当前账号')
            from webauthn import verify_authentication_response
            verification = verify_authentication_response(
                credential=credential, expected_challenge=challenge,
                expected_rp_id=passkey_config.rp_id, expected_origin=passkey_config.origin,
                credential_public_key=bytes(stored['public_key']),
                credential_current_sign_count=int(stored.get('sign_count', 0) or 0),
                require_user_verification=True,
            )
            passkey_store.update_usage(credential_id, verification.new_sign_count, _get_request_ip(request),
                                       bool(getattr(verification, 'credential_backed_up', stored.get('backup_state', False))))
            passkey_store.consume_challenge(request_id)
            _set_passkey_step_up(username)
            return jsonify({'success': True, 'message': '安全验证通过。', 'valid_for': 600})
        except Exception as exc:
            app.logger.warning('Passkey 二次验证失败 [%s]：%s', credential_id[:12], exc)
            return jsonify({'success': False, 'message': 'Passkey 安全验证失败。'}), 401

    @app.route('/api/admin/account/passkeys', methods=['GET'])
    @login_required
    def admin_passkeys_list():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        username = _normalize_username(session.get('admin_username', ''))
        items = passkey_store.list_credentials(username)
        return jsonify({'success': True, 'items': items, 'count': len(items),
                        'max_credentials': passkey_config.max_credentials_per_user,
                        'step_up_valid': _passkey_step_up_valid(username)})

    @app.route('/api/admin/account/passkeys/register/options', methods=['POST'])
    @login_required
    def admin_passkey_register_options():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        username = _normalize_username(session.get('admin_username', ''))
        if not passkey_store.check_rate_limit(_get_request_ip(request)):
            return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试。'}), 429
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            user, _ = _find_user(users_data, username)
        if user is None or not bool(user.get('enabled', True)) or not _has_verified_email(user):
            return jsonify({'success': False, 'message': '账号必须先绑定并验证安全邮箱。'}), 400
        if not _passkey_step_up_valid(username):
            method = 'passkey' if passkey_store.count_credentials(username) else 'email'
            return jsonify({'success': False, 'requires_step_up': True, 'step_up_method': method,
                            'message': '添加 Passkey 前需要完成安全验证。'}), 403
        try:
            from webauthn import generate_registration_options
            from webauthn.helpers.structs import (
                AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                ResidentKeyRequirement, UserVerificationRequirement,
            )
            user_handle = passkey_store.get_or_create_user_handle(username)
            ids = passkey_store.credential_ids(username)
            options = generate_registration_options(
                rp_id=passkey_config.rp_id, rp_name=passkey_config.rp_name,
                user_id=user_handle, user_name=username, user_display_name=username,
                exclude_credentials=[PublicKeyCredentialDescriptor(id=item) for item in ids],
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.REQUIRED,
                    user_verification=UserVerificationRequirement.REQUIRED,
                ),
                timeout=60000,
            )
            request_id = passkey_store.create_challenge(
                'register', options.challenge, _passkey_session_binding(), username
            )
            return _passkey_options_payload(options, request_id)
        except Exception as exc:
            return jsonify({'success': False, 'message': f'无法发起 Passkey 注册：{exc}'}), 500

    @app.route('/api/admin/account/passkeys/register/verify', methods=['POST'])
    @login_required
    def admin_passkey_register_verify():
        if not passkey_config.enabled:
            return _passkey_unavailable_response()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.get_json(silent=True) or {}
        credential = data.get('credential') if isinstance(data.get('credential'), dict) else {}
        request_id = str(data.get('request_id', '') or '').strip()
        username = _normalize_username(session.get('admin_username', ''))
        try:
            device_name = _passkey_device_name(data.get('device_name'))
            if not _passkey_step_up_valid(username):
                raise ValueError('安全验证已过期')
            challenge = passkey_store.load_challenge(
                request_id, 'register', _passkey_session_binding(), username
            )
            from webauthn import verify_registration_response
            verification = verify_registration_response(
                credential=credential, expected_challenge=challenge,
                expected_rp_id=passkey_config.rp_id, expected_origin=passkey_config.origin,
                require_user_verification=True,
            )
            response_data = credential.get('response') if isinstance(credential.get('response'), dict) else {}
            transports = response_data.get('transports') if isinstance(response_data.get('transports'), list) else []
            user_handle = passkey_store.get_or_create_user_handle(username)
            passkey_store.add_credential(
                credential_id=verification.credential_id, username=username, user_handle=user_handle,
                public_key=verification.credential_public_key, sign_count=verification.sign_count,
                transports=transports,
                backup_eligible=(getattr(getattr(verification, 'credential_device_type', None), 'value', '') == 'multi_device'),
                backup_state=bool(getattr(verification, 'credential_backed_up', False)),
                device_name=device_name,
            )
            passkey_store.consume_challenge(request_id)
            append_admin_login_log(operation='passkey_manage', success=True, username=username,
                                   detail=f'添加 Passkey：{device_name}', hidden_account=_is_hidden_admin_session(session))
            return jsonify({'success': True, 'message': 'Passkey 添加成功。'})
        except Exception as exc:
            app.logger.warning('Passkey 注册验证失败：%s', exc)
            return jsonify({'success': False, 'message': f'Passkey 添加失败：{exc}'}), 400

    @app.route('/api/admin/account/passkeys/<credential_id>', methods=['PATCH'])
    @login_required
    def admin_passkey_rename(credential_id):
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        username = _normalize_username(session.get('admin_username', ''))
        try:
            name = _passkey_device_name((request.get_json(silent=True) or {}).get('device_name'))
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        if not passkey_store.rename_credential(username, credential_id, name):
            return jsonify({'success': False, 'message': '未找到该 Passkey。'}), 404
        return jsonify({'success': True, 'message': '设备名称已更新。'})

    @app.route('/api/admin/account/passkeys/<credential_id>', methods=['DELETE'])
    @login_required
    def admin_passkey_revoke(credential_id):
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        username = _normalize_username(session.get('admin_username', ''))
        if not _passkey_step_up_valid(username):
            return jsonify({'success': False, 'requires_step_up': True, 'message': '移除 Passkey 前需要安全验证。'}), 403
        if not passkey_store.revoke_credential(username, credential_id, username):
            return jsonify({'success': False, 'message': '未找到该 Passkey。'}), 404
        append_admin_login_log(operation='passkey_manage', success=True, username=username,
                               detail=f'移除 Passkey：{credential_id[:8]}', hidden_account=_is_hidden_admin_session(session))
        return jsonify({'success': True, 'message': 'Passkey 已移除。'})

    @app.route('/api/admin/subaccounts/<username>/passkeys', methods=['GET'])
    @login_required
    def admin_subaccount_passkeys(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        target = _normalize_username(username)
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            target_user, _ = _find_user(users_data, target)
        if target_user is None or _is_hidden_admin_record(target_user) or str(target_user.get('role')) == 'super_admin':
            return _hidden_admin_not_found_response()
        items = passkey_store.list_credentials(target) if passkey_config.enabled else []
        return jsonify({'success': True, 'username': target, 'items': items, 'count': len(items)})

    @app.route('/api/admin/subaccounts/<username>/passkeys/<credential_id>', methods=['DELETE'])
    @login_required
    def admin_subaccount_passkey_revoke(username, credential_id):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        actor = _normalize_username(session.get('admin_username', ''))
        if not _passkey_step_up_valid(actor):
            return jsonify({'success': False, 'requires_step_up': True, 'message': '强制吊销前需要安全验证。'}), 403
        target = _normalize_username(username)
        # 与“吊销全部”端点一致：拒绝以超管/隐藏账号为目标，防止跨账号吊销。
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            target_user, _ = _find_user(users_data, target)
        if target_user is None or _is_hidden_admin_record(target_user) or str(target_user.get('role')) == 'super_admin':
            return _hidden_admin_not_found_response()
        if not passkey_store.revoke_credential(target, credential_id, actor):
            return jsonify({'success': False, 'message': '未找到该 Passkey。'}), 404
        append_admin_login_log(operation='passkey_manage', success=True, username=actor,
                               detail=f'强制移除子账号 {target} 的 Passkey：{credential_id[:8]}',
                               hidden_account=_is_hidden_admin_session(session))
        return jsonify({'success': True, 'message': '子账号 Passkey 已吊销。'})

    @app.route('/api/admin/subaccounts/<username>/passkeys', methods=['DELETE'])
    @login_required
    def admin_subaccount_passkeys_revoke_all(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        actor = _normalize_username(session.get('admin_username', ''))
        if not _passkey_step_up_valid(actor):
            return jsonify({'success': False, 'requires_step_up': True, 'message': '强制吊销前需要安全验证。'}), 403
        target = _normalize_username(username)
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            target_user, _ = _find_user(users_data, target)
        if target_user is None or _is_hidden_admin_record(target_user) or str(target_user.get('role')) == 'super_admin':
            return _hidden_admin_not_found_response()
        count = passkey_store.revoke_all(target, actor)
        append_admin_login_log(operation='passkey_manage', success=True, username=actor,
                               detail=f'强制移除子账号 {target} 的全部 Passkey（{count} 个）',
                               hidden_account=_is_hidden_admin_session(session))
        return jsonify({'success': True, 'message': f'已吊销 {count} 个 Passkey。', 'revoked_count': count})

    def _perform_login_start():
        # 登录接口同样执行同源校验，防止跨站表单把受害者浏览器
        # 静默登录到攻击者控制的账号（login CSRF）。
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        data = request.form if request.form else request.get_json(silent=True) or {}
        login_method = str(data.get('login_method', '') or data.get('loginMethod', '') or 'username_password').strip()
        if login_method not in {'username_password', 'email_password', 'account_password'}:
            login_method = 'username_password'
        account = str(data.get('account', '') or '').strip()
        username = str(data.get('username', '') or '').strip()
        email = _normalize_email(data.get('email', ''))
        if login_method == 'account_password':
            username = account
            if '@' in account:
                email = _normalize_email(account)
        password = str(data.get('password', '') or '')
        turnstile_token = str(data.get('turnstileToken', '') or data.get('cf_turnstile_response', '') or '').strip()
        captcha_verify_param = _extract_admin_captcha_param(request, data)
        ip_addr = _get_request_ip(request)
        now_ts = int(time.time())
        attempts_file = _get_login_attempts_file(root)
        config = get_config() or {}
        geo_settings = normalize_admin_login_geo_settings(config)
        turnstile_settings = _get_admin_captcha_settings(config)
        smtp_settings = _get_email_auth_settings(config)

        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            if login_method == 'email_password' or (login_method == 'account_password' and '@' in username):
                login_user = _find_user_by_email(users_data, email)
            else:
                login_user, _ = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)

        is_hidden_admin = _is_hidden_admin_record(login_user)
        login_identifier = email if login_method == 'email_password' else username

        # 封禁/延迟前置检查：密码哈希（scrypt）与验证码校验代价高，必须在
        # 验证凭据之前拒绝已封禁或处于延迟窗口的来源，避免被封禁 IP 仍能
        # 通过高频请求消耗 CPU 打满 worker。
        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            pre_ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            pre_blocked_until = int(pre_ip_item.get('blocked_until', 0) or 0) if isinstance(pre_ip_item, dict) else 0
            pre_delay_seconds = _get_login_delay_seconds(attempts_state, ip_addr, now_ts)
            _save_login_attempts(attempts_file, attempts_state)
        if pre_blocked_until > now_ts:
            blocked_at = _format_blocked_until(pre_blocked_until)
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=login_identifier,
                detail=f'IP 已封禁至 {blocked_at or pre_blocked_until}',
                hidden_account=is_hidden_admin,
            )
            return jsonify({'success': False, 'message': f'当前登录 IP 已被封禁至 {blocked_at}，请稍后再试。'}), 429
        if pre_delay_seconds > 0:
            wait_hint = f'{pre_delay_seconds // 60}m {pre_delay_seconds % 60}s' if pre_delay_seconds >= 60 else f'{pre_delay_seconds}s'
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=login_identifier,
                detail=f'登录已触发延迟保护，等待 {wait_hint}',
                hidden_account=is_hidden_admin,
            )
            return jsonify({'success': False, 'message': f'失败次数过多，请等待 {wait_hint} 后再试。'}), 429

        country_allowed, country_reason = _is_ip_country_allowed(ip_addr, geo_settings, _resolve_ip_country_code)
        if not country_allowed:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=login_identifier,
                detail=country_reason,
                hidden_account=is_hidden_admin,
            )
            return jsonify({'success': False, 'message': country_reason}), 403

        captcha_token = captcha_verify_param if turnstile_settings.get('provider') == 'aliyun_esa' else turnstile_token
        turnstile_ok, turnstile_fail_reason = _verify_admin_captcha(
            turnstile_settings,
            captcha_token,
            remote_ip=ip_addr,
        )

        user_enabled = bool(login_user and login_user.get('enabled', True))
        user_password_hash = str((login_user or {}).get('password_hash', '') or '').strip()
        if login_user is None:
            # 用户不存在：执行哑哈希运算保持耗时一致，再按失败处理。
            _verify_password(_DUMMY_PASSWORD_HASH, password)
            password_ok = False
        else:
            # 停用账号同样执行完整哈希校验，避免与“账号不存在”之间出现
            # 可测量时序差异（可用于枚举用户名）。
            password_verified = _verify_password(user_password_hash, password)
            password_ok = bool(user_enabled and password_verified)
        email_login_verified = not (login_method == 'email_password' or (login_method == 'account_password' and '@' in username)) or _has_verified_email(login_user)
        credentials_ok = bool(turnstile_ok and password_ok and email_login_verified)
        login_username = _normalize_username((login_user or {}).get('username', '') or username)

        if login_method == 'account_password':
            if not username and not password:
                fail_reason = '用户名/邮箱和密码不能为空。'
            elif not username:
                fail_reason = '请输入用户名或邮箱。'
            elif '@' in username and not email:
                fail_reason = '请输入有效的邮箱地址。'
            elif not password:
                fail_reason = '请输入密码。'
            elif turnstile_settings['enabled'] and not turnstile_ok:
                fail_reason = turnstile_fail_reason or '人机验证失败，请重试。'
            elif login_user and not user_enabled:
                fail_reason = '该账号已被停用，请联系管理员。'
            elif password_ok and not email_login_verified:
                fail_reason = '该邮箱尚未完成安全验证，请使用用户名登录后绑定安全邮箱。'
            else:
                fail_reason = '账号或密码错误。'
        elif login_method == 'email_password':
            if not email and not password:
                fail_reason = '邮箱和密码不能为空。'
            elif not email:
                fail_reason = '请输入邮箱。'
            elif '@' not in email:
                fail_reason = '请输入有效的邮箱地址。'
            elif not password:
                fail_reason = '请输入密码。'
            elif turnstile_settings['enabled'] and not turnstile_ok:
                fail_reason = turnstile_fail_reason or '人机验证失败，请重试。'
            elif login_user and not user_enabled:
                fail_reason = '该账号已被停用，请联系管理员。'
            elif password_ok and not email_login_verified:
                fail_reason = '该邮箱尚未完成安全验证，请使用用户名登录后绑定安全邮箱。'
            else:
                fail_reason = '邮箱或密码错误。'
        elif not username and not password:
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
                is_blocked_now, blocked_until, _remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                if not is_blocked_now:
                    _set_login_delay(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
                if is_blocked_now:
                    blocked_at = _format_blocked_until(blocked_until)
                    failed_payload = {'success': False, 'message': f'{fail_reason} 同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'}
                    failed_status = 429
                    failed_detail = f'{fail_reason}；已封禁至 {blocked_at or blocked_until}'
                else:
                    failed_payload = {'success': False, 'message': f'{fail_reason} 已触发延迟保护，请稍后再试。'}
                    failed_status = 401 if fail_reason in {'用户名或密码错误。', '邮箱或密码错误。', '账号或密码错误。'} else 400
                    failed_detail = f'{fail_reason}；已触发延迟保护'

        if failed_payload is not None:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=login_identifier,
                detail=failed_detail,
                hidden_account=is_hidden_admin,
            )
            return jsonify(failed_payload), failed_status

        email_verification_available = bool(smtp_settings['enabled'] and _smtp_ready_for_email_auth(smtp_settings))

        if email_verification_available and _has_verified_email(login_user):
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
            binding_required=bool(email_verification_available and not _has_verified_email(login_user)),
            detail_suffix='凭据校验通过；已进入后台' + ('；需绑定安全邮箱' if email_verification_available and not _has_verified_email(login_user) else ''),
        )

    @app.route('/admin/login/start', methods=['POST'])
    def admin_login_start():
        return _perform_login_start()

    @app.route('/admin/login/email-code/send', methods=['POST'])
    def admin_login_email_code_send():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        # 该端点不校验密码即可发码，必须按 IP 硬限流，防止攻击者循环
        # “新建 pending → 猜 5 次 → 再新建”对 6 位邮箱验证码无限爆破。
        send_ip_addr = _get_request_ip(request)
        allowed, retry_after, _count = check_and_record(
            f'admin-email-code-send:{send_ip_addr}', limit=10, window=3600
        )
        if not allowed:
            return jsonify({
                'success': False,
                'message': f'验证码发送过于频繁，请 {max(1, int(retry_after))} 秒后再试。',
            }), 429
        data = request.get_json(silent=True) or {}
        email = _normalize_email(data.get('email', ''))
        turnstile_token = str(data.get('turnstileToken', '') or data.get('cf_turnstile_response', '') or '').strip()
        captcha_verify_param = _extract_admin_captcha_param(request, data)
        ip_addr = _get_request_ip(request)
        now_ts = int(time.time())
        attempts_file = _get_login_attempts_file(root)
        config = get_config() or {}
        geo_settings = normalize_admin_login_geo_settings(config)
        turnstile_settings = _get_admin_captcha_settings(config)
        smtp_settings = _get_email_auth_settings(config)

        if not email:
            return jsonify({'success': False, 'message': '请输入已验证安全邮箱。'}), 400
        if '@' not in email:
            return jsonify({'success': False, 'message': '请输入有效的邮箱地址。'}), 400
        if not smtp_settings['enabled'] or not _smtp_ready_for_email_auth(smtp_settings):
            return jsonify({'success': False, 'message': '邮箱验证快捷登录暂不可用，请联系管理员。'}), 503

        country_allowed, country_reason = _is_ip_country_allowed(ip_addr, geo_settings, _resolve_ip_country_code)
        if not country_allowed:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=email,
                detail=country_reason,
                hidden_account=False,
            )
            return jsonify({'success': False, 'message': country_reason}), 403

        captcha_token = captcha_verify_param if turnstile_settings.get('provider') == 'aliyun_esa' else turnstile_token
        turnstile_ok, turnstile_fail_reason = _verify_admin_captcha(
            turnstile_settings,
            captcha_token,
            remote_ip=ip_addr,
        )

        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user = _find_user_by_email(users_data, email)
            if login_user is not None:
                login_user = dict(login_user)

        is_hidden_admin = _is_hidden_admin_record(login_user)
        user_enabled = bool(login_user and login_user.get('enabled', True))
        email_ok = bool(login_user and user_enabled and _has_verified_email(login_user))
        credentials_ok = bool(turnstile_ok and email_ok)

        if turnstile_settings['enabled'] and not turnstile_ok:
            fail_reason = turnstile_fail_reason or '人机验证失败，请重试。'
        elif login_user and not user_enabled:
            fail_reason = '该账号已被停用，请联系管理员。'
        else:
            fail_reason = '该邮箱未绑定后台账号或尚未完成验证。'

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
                is_blocked_now, blocked_until, _remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                if not is_blocked_now:
                    _set_login_delay(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
                if is_blocked_now:
                    blocked_at = _format_blocked_until(blocked_until)
                    failed_payload = {'success': False, 'message': f'{fail_reason} 同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'}
                    failed_status = 429
                    failed_detail = f'{fail_reason}；已封禁至 {blocked_at or blocked_until}'
                else:
                    failed_payload = {'success': False, 'message': f'{fail_reason} 已触发延迟保护，请稍后再试。'}
                    failed_status = 400 if fail_reason != '该邮箱未绑定后台账号或尚未完成验证。' else 401
                    failed_detail = f'{fail_reason}；已触发延迟保护'

        if failed_payload is not None:
            append_admin_login_log(
                operation='admin_login',
                success=False,
                username=email,
                detail=failed_detail,
                hidden_account=is_hidden_admin,
            )
            return jsonify(failed_payload), failed_status

        login_username = _normalize_username((login_user or {}).get('username', ''))
        pending_login_id = _create_pending_login(root, login_username, ip_addr)
        _set_pending_login_session(session, pending_login_id=pending_login_id, username=login_username, ip_addr=ip_addr)
        try:
            ok, message, payload = _send_pending_login_code(
                root,
                pending_login_id=pending_login_id,
                email=(login_user or {}).get('email', ''),
                smtp_settings=smtp_settings,
            )
        except Exception as exc:
            _delete_pending_login(root, pending_login_id)
            _clear_pending_login_session(session)
            return jsonify({'success': False, 'message': f'验证码邮件发送失败：{exc}'}), 400
        if not ok:
            _delete_pending_login(root, pending_login_id)
            _clear_pending_login_session(session)
            return jsonify({'success': False, 'message': message, **payload}), 400

        return jsonify({
            'success': True,
            'message': message,
            'pending_login_id': pending_login_id,
            **payload,
        })

    @app.route('/admin/login/send-email-code', methods=['POST'])
    def admin_login_send_email_code():
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
        resend_ip_addr = _get_request_ip(request)
        allowed, retry_after, _count = check_and_record(
            f'admin-email-code-resend:{resend_ip_addr}', limit=15, window=3600
        )
        if not allowed:
            return jsonify({
                'success': False,
                'message': f'验证码发送过于频繁，请 {max(1, int(retry_after))} 秒后再试。',
            }), 429
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

        # 验证码尝试按 IP 硬限流 + 失败计入登录封禁，防止跨 pending 循环爆破。
        ip_addr = _get_request_ip(request)
        attempts_file = _get_login_attempts_file(root)
        allowed, retry_after, _count = check_and_record(
            f'admin-email-code-verify:{ip_addr}', limit=30, window=3600
        )
        if not allowed:
            return jsonify({
                'success': False,
                'message': f'验证码尝试过于频繁，请 {max(1, int(retry_after))} 秒后再试。',
            }), 429

        now_ts = int(time.time())
        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            blocked_until = int(ip_item.get('blocked_until', 0) or 0) if isinstance(ip_item, dict) else 0
            delay_until = int(ip_item.get('delay_until', 0) or 0) if isinstance(ip_item, dict) else 0
        if blocked_until > now_ts:
            blocked_at = _format_blocked_until(blocked_until)
            return jsonify({'success': False, 'message': f'当前登录 IP 已被封禁至 {blocked_at}，请稍后再试。'}), 429
        if delay_until > now_ts:
            return jsonify({'success': False, 'message': '失败次数过多，请稍后再试。'}), 429

        ok, message, pending_login = _verify_pending_login_code(root, pending_login_id=pending_login_id, code=code)
        if not ok:
            with LOGIN_ATTEMPTS_LOCK:
                attempts_state = _load_login_attempts(attempts_file)
                _prune_login_attempts(attempts_state, now_ts)
                blocked_now, blocked_until, _remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                if not blocked_now:
                    _set_login_delay(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
            return jsonify({'success': False, 'message': message}), 400

        username = _normalize_username((pending_login or {}).get('username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            login_user, _ = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)
        if login_user is None or not _has_verified_email(login_user) or not bool(login_user.get('enabled', True)):
            _delete_pending_login(root, pending_login_id)
            return jsonify({'success': False, 'message': '账号状态已变化，请重新登录。'}), 400

        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            _reset_login_attempts_for_ip(attempts_state, ip_addr)
            _save_login_attempts(attempts_file, attempts_state)

        _delete_pending_login(root, pending_login_id)
        # 审计记录使用本次请求的真实来源 IP，而非 pending 创建时的旧值。
        return _finalize_login_success(login_user, ip_addr, detail_suffix='凭据校验通过；邮箱验证码通过')

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
            # 改密后吊销该账号所有现有会话（含当前会话之外的旧 cookie）。
            updated_user['min_session_at'] = int(time.time())
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

        if passkey_config.enabled and current_admin != new_username:
            passkey_store.rename_user(current_admin, new_username)

        # 当前浏览器会话继续有效：以改密时刻作为新的会话起点，
        # 其余旧 cookie（含被窃取副本）因早于 min_session_at 而失效。
        session['admin_username'] = new_username
        session['admin_is_hidden'] = bool(current_is_hidden)
        session['admin_login_at'] = int(time.time())
        session['admin_last_active_at'] = int(time.time())
        session.pop('admin_passkey_step_up_username', None)
        session.pop('admin_passkey_step_up_until', None)
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
            **_admin_feature_response_fields(),
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
        if passkey_config.enabled:
            for item in items:
                item['passkey_count'] = passkey_store.count_credentials(item.get('username', ''))
        else:
            for item in items:
                item['passkey_count'] = 0
        return jsonify({
            'success': True,
            'items': items,
            **_admin_feature_response_fields(),
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
        # 用 _parse_bool 严格解析，防止 JSON 字符串 "false" 被 bool() 当成 True。
        enabled = _parse_bool(data.get('enabled', True), True)
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)
        notify_message_email = bool(data.get('notify_message_email', False))
        notify_job_email = bool(data.get('notify_job_email', False))

        if not USERNAME_RULE.match(username):
            return jsonify({'success': False, 'message': '用户名需为 3 到 32 位，仅支持字母、数字、下划线、点和短横线。'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': '密码至少需要 8 位。'}), 400
        if not permissions:
            return jsonify({'success': False, 'message': '请至少选择 1 项权限。'}), 400
        if _locked_permissions(permissions):
            return jsonify({'success': False, 'message': '包含尚未解锁的功能权限，无法分配。'}), 400

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
                'notify_message_email': notify_message_email,
                'notify_job_email': notify_job_email,
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
        enabled = _parse_bool(data.get('enabled', True), True)
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)
        reset_password = str(data.get('password', '') or '')
        notify_message_email = bool(data.get('notify_message_email', False))
        notify_job_email = bool(data.get('notify_job_email', False))

        if not permissions:
            return jsonify({'success': False, 'message': '请至少选择 1 项权限。'}), 400
        if _locked_permissions(permissions):
            return jsonify({'success': False, 'message': '包含尚未解锁的功能权限，无法分配。'}), 400
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
            updated['notify_message_email'] = notify_message_email
            updated['notify_job_email'] = notify_job_email
            if reset_password:
                updated['password_hash'] = _hash_password(reset_password)
            permissions_changed = sorted(
                _normalize_permissions(target_user.get('permissions', []), is_super_admin=False)
            ) != sorted(permissions)
            if reset_password or not enabled or permissions_changed:
                # 重置密码、停用或收窄权限后立即吊销该子账号的全部既有会话：
                # login_required 读取的是会话内的权限快照，不吊销的话被收权
                # 的子账号在空闲超时窗口内仍可用旧权限继续操作。
                updated['min_session_at'] = int(time.time())
            updated['updated_at'] = now_iso
            users_data['users'][idx] = _sanitize_user_record(updated, fallback_username=target_name, is_super_admin=False)
            _save_admin_users(users_file, users_data)

        if passkey_config.enabled and not enabled:
            passkey_store.revoke_all(target_name, _normalize_username(session.get('admin_username', '')))

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

        if passkey_config.enabled:
            passkey_store.revoke_all(target_name, _normalize_username(session.get('admin_username', '')))

        append_admin_login_log(
            operation='subaccount_manage',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'删除子账号：{target_name}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': '子账号已删除。'})
    @app.route('/api/admin/subaccounts/<username>/email', methods=['PUT'])
    @login_required
    def admin_subaccounts_force_email(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403

        target_name = _normalize_username(username)
        data = request.get_json(silent=True) or {}
        new_email = _normalize_email(data.get('email', ''))

        if not new_email or '@' not in new_email:
            return jsonify({'success': False, 'message': '请输入有效的邮箱地址。'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            target_user, idx = _find_user(users_data, target_name)
            if target_user is None or idx < 0:
                return jsonify({'success': False, 'message': '未找到该子账号。'}), 404
            if _is_hidden_admin_record(target_user):
                return _hidden_admin_not_found_response()
            if str(target_user.get('role') or '') == 'super_admin':
                return jsonify({'success': False, 'message': '不能在此处修改超级管理员账号。'}), 400

            # 检查邮箱是否已被其他账号占用
            duplicated = _find_user_by_email(users_data, new_email, exclude_username=target_name)
            if duplicated is not None:
                dup_name = _normalize_username(duplicated.get('username', ''))
                return jsonify({'success': False, 'message': f'该邮箱已被账号 {dup_name} 绑定。'}), 400

            now_iso = now_beijing().isoformat(timespec='seconds')
            updated = dict(target_user)
            updated['email'] = new_email
            updated['email_verified'] = True
            updated['email_bound_at'] = now_iso
            updated['updated_at'] = now_iso
            users_data['users'][idx] = _sanitize_user_record(updated, fallback_username=target_name, is_super_admin=False)
            _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='subaccount_manage',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'强制更改子账号 {target_name} 的绑定邮箱为 {new_email}',
            hidden_account=_is_hidden_admin_session(session),
        )
        return jsonify({'success': True, 'message': f'已将 {target_name} 的邮箱强制更改为 {new_email}。'})
    @app.route('/admin/logout', methods=['POST'])
    def admin_logout():
        """Handle admin logout."""
        # 拦截带跨站来源头的登出请求（login CSRF 的对偶：logout CSRF）。
        # 部分隐私浏览器会剥离 Origin/Referer，此时不能把登出变成不可用，
        # 仍允许通过（该请求只会清除当前浏览器自己的会话，无服务端副作用）。
        if not _is_same_origin_request(request):
            has_origin_header = bool(
                normalize_origin(request.headers.get('Origin', ''))
                or normalize_origin(request.headers.get('Referer', ''))
            )
            if has_origin_header:
                return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试。'}), 403
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
            # 服务端会话吊销：登出后旧 cookie（含被窃取的副本）立即失效。
            try:
                bump_user_min_session_at(root, username)
            except Exception:
                pass
        _clear_admin_session(session)
        return jsonify({'success': True})
    @app.route('/admin/check')
    def admin_check():
        """Check whether an admin session is still valid."""
        logged_in = bool(session.get('admin_logged_in', False))
        if logged_in and _is_admin_session_expired(session):
            session.clear()
            logged_in = False
        # 与 login_required 保持一致的吊销校验：登出/改密后早于
        # min_session_at 的旧 cookie、旧 schema 会话都必须立即失效，
        # 否则被盗 cookie 仍可从这里读取账号信息与 CSRF token。
        if logged_in and session.get('admin_session_schema') != ADMIN_SESSION_SCHEMA_VERSION:
            session.clear()
            logged_in = False
        if logged_in:
            login_at = int(session.get('admin_login_at', 0) or 0)
            check_username = _normalize_username(session.get('admin_username', ''))
            min_session_at = query_user_min_session_at(check_username)
            if min_session_at and (not login_at or login_at < min_session_at):
                session.clear()
                logged_in = False
        if not logged_in:
            if not str(session.get(CSRF_SESSION_KEY) or '').strip():
                session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
            return jsonify({
                'logged_in': False,
                'username': '',
                'is_super_admin': False,
                'is_hidden_admin': False,
                'binding_required': False,
                'permissions': [],
                'csrf_token': session.get(CSRF_SESSION_KEY, ''),
                **_admin_feature_response_fields(),
            })

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        current_name = _normalize_username(session.get('admin_username', ''))
        with ADMIN_USERS_LOCK:
            users_data, _ = _ensure_admin_users_store(root, get_config, update_config)
            user, _ = _find_user(users_data, current_name)

        if user is None or not bool(user.get('enabled', True)):
            session.clear()
            session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
            return jsonify({
                'logged_in': False,
                'username': '',
                'is_super_admin': False,
                'is_hidden_admin': False,
                'binding_required': False,
                'permissions': [],
                'csrf_token': session.get(CSRF_SESSION_KEY, ''),
                **_admin_feature_response_fields(),
            })

        is_super_admin = bool(str(user.get('role') or '') == 'super_admin')
        is_hidden_admin = _is_hidden_admin_record(user)
        permissions = _normalize_permissions(user.get('permissions', []), is_super_admin=is_super_admin)
        permissions = _filter_unlocked_permissions(permissions)
        feature_fields = _admin_feature_response_fields()
        current_login_at = str(session.get('admin_current_login_at') or user.get('last_login_at') or '')
        current_login_ip = str(session.get('admin_current_login_ip') or user.get('last_login_ip') or '')
        previous_login_at = str(session.get('admin_previous_login_at') or '')
        previous_login_ip = str(session.get('admin_previous_login_ip') or '')
        has_previous_login_state = 'admin_previous_login_at' in session or 'admin_previous_login_ip' in session
        display_last_login_at = previous_login_at if has_previous_login_state else str(user.get('last_login_at') or '')
        display_last_login_ip = previous_login_ip if has_previous_login_state else str(user.get('last_login_ip') or '')
        display_last_login_location = _resolve_ip_location(display_last_login_ip) if display_last_login_ip else ''
        current_login_location = _resolve_ip_location(current_login_ip) if current_login_ip else ''
        session['admin_is_super_admin'] = is_super_admin
        session['admin_is_hidden'] = is_hidden_admin
        session['admin_permissions'] = permissions
        session['admin_username'] = _normalize_username(user.get('username', current_name))
        session['admin_binding_required'] = bool((get_config() or {}).get('email_auth_enabled', False) and not _has_verified_email(user))
        if not str(session.get(CSRF_SESSION_KEY) or '').strip():
            session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
        maybe_refresh_admin_session(session, request)

        return jsonify({
            'logged_in': True,
            'username': session.get('admin_username', ''),
            'is_super_admin': is_super_admin,
            'is_hidden_admin': is_hidden_admin,
            'binding_required': bool(session.get('admin_binding_required', False)),
            'permissions': permissions,
            **feature_fields,
            'last_login_at': display_last_login_at,
            'last_login_ip': display_last_login_ip,
            'last_login_location': display_last_login_location,
            'current_login_at': current_login_at,
            'current_login_ip': current_login_ip,
            'current_login_location': current_login_location,
            # 不再返回明文邮箱；前端展示使用 email_masked。
            'email_masked': _mask_email_address(user.get('email', '')),
            'email_verified': bool(user.get('email_verified', False)),
            'csrf_token': session.get(CSRF_SESSION_KEY, ''),
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

    def _split_admin_log_path_list(raw_value):
        if not raw_value:
            return []
        return [item.strip() for item in re.split(r'[\r\n,]+', raw_value) if item.strip()]

    def _resolve_admin_log_candidates(env_key, default_relative_paths):
        raw_value = os.environ.get(env_key, '').strip()
        raw_paths = _split_admin_log_path_list(raw_value) if raw_value else list(default_relative_paths)
        resolved = []
        seen = set()
        for raw_path in raw_paths:
            path_obj = Path(raw_path)
            if not path_obj.is_absolute():
                path_obj = Path(project_root) / raw_path
            normalized = str(path_obj)
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(path_obj)
        return resolved

    def _tail_admin_log_files(paths, lines):
        chunks = []
        for path_obj in paths:
            try:
                if not path_obj.exists() or not path_obj.is_file():
                    continue
                with path_obj.open('r', encoding='utf-8', errors='replace') as f:
                    all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if all_lines else []
                content = ''.join(tail_lines).strip()
                if not content:
                    continue
                try:
                    label = os.path.relpath(str(path_obj), project_root)
                except Exception:
                    label = str(path_obj)
                chunks.append(f'[{label}]\n{content}')
            except Exception:
                continue
        if not chunks:
            return None
        return '\n\n'.join(chunks)

    def _clear_admin_log_files(paths):
        cleared = 0
        for path_obj in paths:
            try:
                if not path_obj.exists() or not path_obj.is_file():
                    continue
                path_obj.write_text('', encoding='utf-8')
                cleared += 1
            except Exception:
                continue
        return cleared

    @app.route('/api/admin/docker-logs')
    @login_required
    def admin_docker_logs():
        """获取网站应用容器日志；Docker 不可用时回退到本地日志文件。"""
        container1_name = os.environ.get('DOCKER_CONTAINER_1_NAME', 'yx-website')
        lines = request.args.get('lines', default=200, type=int)
        lines = max(10, min(lines, 1000))
        app_log_candidates = _resolve_admin_log_candidates(
            'DOCKER_LOG_FALLBACK_APP_FILES',
            (
                'data/logs/gunicorn-error.log',
                'data/logs/gunicorn-access.log',
                'data/logs/app.log',
                'data/app.log',
                'app.log',
            ),
        )
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

        logs1 = get_container_logs(container1_name)

        if logs1 is None:
            local_logs = _tail_admin_log_files(app_log_candidates, lines)
            if local_logs:
                logs1 = f'[文件日志回退] 应用服务日志:\n{local_logs}'
            else:
                logs1 = '暂无应用服务日志记录（当前环境无法直接执行 docker logs，且未找到可读取的应用日志文件）'

        return jsonify({
            'single_container': True,
            'container1': {
                'name': container1_name,
                'logs': logs1
            }
        })

    @app.route('/api/admin/docker-logs/clear', methods=['POST'])
    @login_required
    def admin_docker_logs_clear():
        """清理后台日志页可见的共享日志文件。"""
        try:
            data = request.get_json(silent=True) or {}
            container = data.get('container', 'all')

            app_log_candidates = _resolve_admin_log_candidates(
                'DOCKER_LOG_FALLBACK_APP_FILES',
                (
                    'data/logs/gunicorn-error.log',
                    'data/logs/gunicorn-access.log',
                    'data/logs/app.log',
                    'data/app.log',
                    'app.log',
                ),
            )
            cleared = 0
            if container == 'all' or container == 'container1':
                cleared += _clear_admin_log_files(app_log_candidates)

            if cleared <= 0:
                return jsonify({'success': False, 'message': '未找到可清除的日志文件'}), 404

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
