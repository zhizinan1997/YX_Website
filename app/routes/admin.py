"""后台认证与管理路由模块。

负责管理员登录、会话校验、账号管理、站点设置以及后台运维相关接口。
"""

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
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
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
try:
    ADMIN_SESSION_MAX_AGE_SECONDS = max(300, int((os.environ.get('ADMIN_SESSION_MAX_AGE_SECONDS') or '7200').strip()))
except Exception:
    ADMIN_SESSION_MAX_AGE_SECONDS = 7200
ADMIN_SESSION_SCHEMA_VERSION = 2
LOGIN_DELAY_SECONDS = [60, 180]
ALLOWED_LOGIN_COUNTRIES = {'CN', 'HK', 'MO', 'TW'}

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
    {'key': 'chatbot', 'label': 'AI 接口'},
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


def resolve_permission_for_path(path: str, method: str = 'GET'):
    p = str(path or '').strip()
    m = str(method or 'GET').upper()
    if not p:
        return None

    # 公开页、登录页和会话检查接口在别处处理。
    if p in {'/admin', '/admin/login', '/admin/logout', '/admin/check'}:
        return None

    # 历史登录日志为全管理员只读审计信息，不绑定单一侧栏权限，避免子账号误拦截。
    if p.startswith('/api/admin/login-logs'):
        return None
    if p.startswith('/api/admin/subaccounts') or p.startswith('/admin/change-password'):
        return 'settings'
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


def _sanitize_user_record(user, fallback_username: str = '', is_super_admin: bool = False):
    now_iso = now_beijing().isoformat(timespec='seconds')
    username = _normalize_username(user.get('username') if isinstance(user, dict) else fallback_username)
    if not username:
        username = fallback_username
    enabled = bool(user.get('enabled', True)) if isinstance(user, dict) else True
    role = 'super_admin' if is_super_admin else 'sub_admin'
    permissions = _normalize_permissions((user or {}).get('permissions', []), is_super_admin=is_super_admin)
    if is_super_admin:
        enabled = True
    password_hash = str((user or {}).get('password_hash', '') or '').strip()
    created_at = str((user or {}).get('created_at', '') or '').strip() or now_iso
    updated_at = str((user or {}).get('updated_at', '') or '').strip() or now_iso
    last_login_at = str((user or {}).get('last_login_at', '') or '').strip()
    last_login_ip = str((user or {}).get('last_login_ip', '') or '').strip()
    return {
        'username': username,
        'password_hash': password_hash,
        'role': role,
        'enabled': enabled,
        'permissions': permissions,
        'created_at': created_at,
        'updated_at': updated_at,
        'last_login_at': last_login_at,
        'last_login_ip': last_login_ip,
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
    }


def _is_super_admin_session(sess) -> bool:
    return bool(sess.get('admin_is_super_admin', False))


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

        now_iso = now_beijing().isoformat(timespec='seconds')

        super_idx = -1
        for idx, item in enumerate(users):
            if str(item.get('role') or '') == 'super_admin':
                super_idx = idx
                break

        changed_users = False
        if super_idx < 0:
            initial_hash = config_admin_hash or (_hash_password(config_admin_plain) if config_admin_plain else '')
            if not initial_hash:
                raise RuntimeError('缺少管理员初始化凭据，无法创建超级管理员账号。')
            super_user = _sanitize_user_record({
                'username': config_admin_username,
                'password_hash': initial_hash,
                'permissions': list(ADMIN_PERMISSION_KEYS),
                'created_at': now_iso,
                'updated_at': now_iso,
            }, fallback_username=config_admin_username, is_super_admin=True)
            users.insert(0, super_user)
            super_idx = 0
            changed_users = True
        else:
            super_user = _sanitize_user_record(users[super_idx], fallback_username=config_admin_username, is_super_admin=True)
            if not super_user['username']:
                super_user['username'] = config_admin_username
            if not super_user['password_hash']:
                if config_admin_hash:
                    super_user['password_hash'] = config_admin_hash
                elif config_admin_plain:
                    super_user['password_hash'] = _hash_password(config_admin_plain)
                else:
                    raise RuntimeError('缺少管理员初始化凭据，无法修复超级管理员账号。')
            super_user['updated_at'] = now_iso
            users[super_idx] = super_user
            changed_users = True

        # 规范化子账号记录，并去掉重复用户名。
        normalized_users = []
        seen_names = set()
        for idx, raw_user in enumerate(users):
            is_super = idx == super_idx
            fallback = config_admin_username if is_super else ''
            item = _sanitize_user_record(raw_user, fallback_username=fallback, is_super_admin=is_super)
            uname = item['username']
            if not uname or uname in seen_names:
                continue
            if not item['password_hash']:
                if is_super:
                    if config_admin_hash:
                        item['password_hash'] = config_admin_hash
                    elif config_admin_plain:
                        item['password_hash'] = _hash_password(config_admin_plain)
                    else:
                        continue
                else:
                    # 没有密码哈希的无效子账号直接跳过。
                    continue
            seen_names.add(uname)
            normalized_users.append(item)

        users_data = {'version': 1, 'users': normalized_users}
        _save_admin_users(users_file, users_data)

        # 把配置同步到哈希口令模式，并补齐超级管理员标识。
        super_user = next((u for u in normalized_users if str(u.get('role')) == 'super_admin'), None)
        if super_user is not None:
            config_updates = {}
            if _normalize_username(config.get('admin_username', '')) != super_user.get('username', ''):
                config_updates['admin_username'] = super_user.get('username', '')
            if str(config.get('admin_password_hash', '') or '').strip() != str(super_user.get('password_hash', '') or '').strip():
                config_updates['admin_password_hash'] = str(super_user.get('password_hash', '') or '').strip()
            if str(config.get('admin_password', '') or '').strip():
                config_updates['admin_password'] = ''
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


def _is_ip_country_allowed(ip: str, allowed_countries: set, resolve_location_func) -> tuple:
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
    location = resolve_location_func(ip)
    if not location or location == '未知':
        return False, '无法获取IP归属地，已拒绝登录'
    country_code = ''
    for part in location.split('/'):
        part = part.strip().upper()
        if len(part) == 2 and part.isalpha():
            country_code = part
            break
    if not country_code:
        return False, '无法识别IP归属地，已拒绝登录'
    if country_code not in allowed_countries:
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
        with urlopen(req, timeout=8, context=ssl_context) as resp:
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
):
    """向 Flask 应用注册后台管理相关路由。"""
    _resolve_ip = resolve_ip_location if resolve_ip_location else lambda ip: '未知'
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    try:
        _ensure_admin_users_store(root, get_config, update_config)
    except Exception:
        # 即使初始化迁移暂时异常，也尽量保持路由可用。
        pass

    @app.route('/admin', strict_slashes=False)
    def admin_page():
        """后台登录页与控制台入口页面。"""
        resp = make_response(send_from_directory('admin', 'index.html'))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'same-origin'
        return resp

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
            return jsonify({'success': False, 'message': '启用 Turnstile 时必须填写 Site Key 和 Secret Key'}), 400

        update_config({
            'turnstile_enabled': bool(enabled),
            'turnstile_site_key': site_key,
            'turnstile_secret_key': secret_key
        })
        return jsonify({'success': True, 'message': 'Turnstile 设置已保存'})

    @app.route('/admin/login', methods=['POST'])
    def admin_login():
        """处理管理员登录。"""
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

        country_allowed, country_reason = _is_ip_country_allowed(
            ip_addr, ALLOWED_LOGIN_COUNTRIES, _resolve_ip
        )
        if not country_allowed:
            append_admin_login_log(
                operation='后台登录',
                success=False,
                username=username,
                detail=country_reason
            )
            return jsonify({
                'success': False,
                'message': country_reason
            }), 403

        turnstile_ok = True
        turnstile_fail_reason = ''
        if turnstile_settings['enabled']:
            if not turnstile_token:
                turnstile_ok = False
                turnstile_fail_reason = '请先完成人机验证'
            else:
                turnstile_ok, detail = _verify_turnstile_token(
                    secret_key=turnstile_settings['secret_key'],
                    token=turnstile_token,
                    remote_ip=ip_addr,
                )
                if not turnstile_ok:
                    turnstile_fail_reason = detail or '验证码校验失败，请重试'

        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            login_user, login_user_index = _find_user(users_data, username)
            if login_user is not None:
                login_user = dict(login_user)

        user_enabled = bool(login_user and login_user.get('enabled', True))
        user_password_hash = str((login_user or {}).get('password_hash', '') or '').strip()
        password_ok = bool(login_user) and user_enabled and _verify_password(user_password_hash, password)
        credentials_ok = bool(turnstile_ok and password_ok)

        is_super_admin = bool((login_user or {}).get('role') == 'super_admin')
        user_permissions = _normalize_permissions((login_user or {}).get('permissions', []), is_super_admin=is_super_admin)
        login_username = _normalize_username((login_user or {}).get('username', '') or username)

        if not username and not password:
            fail_reason = '用户名和密码不能为空'
        elif not username:
            fail_reason = '用户名不能为空'
        elif not password:
            fail_reason = '密码不能为空'
        elif turnstile_settings['enabled'] and not turnstile_ok:
            fail_reason = turnstile_fail_reason or '验证码校验失败，请重试'
        elif login_user and not user_enabled:
            fail_reason = '账号已被禁用，请联系管理员'
        else:
            fail_reason = '用户名或密码错误'

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
                    'message': f'当前 IP 已被封禁，解封时间：{blocked_at}，请稍后再试。'
                }
                failed_status = 429
                failed_detail = f'IP 被封禁，解封时间：{blocked_at or blocked_until}'
            elif delay_seconds > 0:
                delay_minutes = delay_seconds // 60
                delay_secs = delay_seconds % 60
                if delay_minutes > 0:
                    wait_hint = f'{delay_minutes}分{delay_secs}秒'
                else:
                    wait_hint = f'{delay_secs}秒'
                failed_payload = {
                    'success': False,
                    'message': f'登录失败次数过多，请等待 {wait_hint} 后再试。'
                }
                failed_status = 429
                failed_detail = f'登录延迟中，需等待 {wait_hint}'
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
                        'message': f'{fail_reason}。同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'
                    }
                    failed_status = 429
                    failed_detail = f'{fail_reason}；同一 IP 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，封禁至 {blocked_at or blocked_until}'
                else:
                    fail_count = remaining - 1
                    if fail_count > 0:
                        fail_payload_msg = f'{fail_reason}。您的IP已触发保护机制，请稍后再试。'
                    else:
                        fail_payload_msg = f'{fail_reason}。当前IP已触发保护，将延迟3分钟后才能继续登录。'
                    failed_payload = {
                        'success': False,
                        'message': fail_payload_msg
                    }
                    failed_status = 400 if fail_reason != '用户名或密码错误' else 401
                    failed_detail = f'{fail_reason}；失败{fail_count + 1}次，触发延迟保护'

        if failed_payload is not None:
            append_admin_login_log(
                operation='后台登录',
                success=False,
                username=username,
                detail=failed_detail
            )
            return jsonify(failed_payload), failed_status

        session.clear()
        session['admin_logged_in'] = True
        session['admin_username'] = login_username
        session['admin_is_super_admin'] = bool(is_super_admin)
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
            operation='后台登录',
            success=True,
            username=login_username,
            detail=('用户名和密码验证通过；人机验证通过' if turnstile_settings['enabled'] else '用户名和密码验证通过')
            + ('；角色：超级管理员' if is_super_admin else '；角色：子账号')
        )
        return jsonify({
            'success': True,
            'last_login_at': prev_last_login_at,
            'last_login_ip': prev_last_login_ip,
            'current_login_at': current_login_at,
        })

    @app.route('/admin/change-password', methods=['POST'])
    @login_required
    def change_password():
        """修改管理员用户名和密码。"""
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

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
            return jsonify({'success': False, 'message': '当前会话已失效，请重新登录'}), 401

        if not _verify_password(str(current_user.get('password_hash', '') or ''), old_password):
            append_admin_login_log(
                operation='修改账号密码',
                success=False,
                username=current_admin,
                detail='原密码校验失败'
            )
            return jsonify({'success': False, 'message': '原密码错误'}), 400

        if not new_username or not new_password:
            append_admin_login_log(
                operation='修改账号密码',
                success=False,
                username=current_admin,
                detail='新用户名或新密码为空'
            )
            return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

        if not USERNAME_RULE.match(new_username):
            return jsonify({'success': False, 'message': '用户名仅支持 3-32 位字母、数字、下划线、点、短横线'}), 400
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': '新密码长度至少 8 位'}), 400

        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            current_user, current_index = _find_user(users_data, current_admin)
            if current_user is None or current_index < 0:
                session.clear()
                return jsonify({'success': False, 'message': '当前会话已失效，请重新登录'}), 401

            existing, existing_idx = _find_user(users_data, new_username)
            if existing is not None and existing_idx != current_index:
                return jsonify({'success': False, 'message': '用户名已存在，请更换'}), 400

            now_iso = now_beijing().isoformat(timespec='seconds')
            updated_user = dict(current_user)
            updated_user['username'] = new_username
            updated_user['password_hash'] = _hash_password(new_password)
            updated_user['updated_at'] = now_iso
            users_data['users'][current_index] = _sanitize_user_record(
                updated_user,
                fallback_username=new_username,
                is_super_admin=bool(str(current_user.get('role') or '') == 'super_admin')
            )
            _save_admin_users(users_file, users_data)

            if str(current_user.get('role') or '') == 'super_admin':
                update_config({
                    'admin_username': new_username,
                    'admin_password_hash': users_data['users'][current_index]['password_hash'],
                    'admin_password': ''
                })

        session['admin_username'] = new_username
        append_admin_login_log(
            operation='修改账号密码',
            success=True,
            username=new_username,
            detail='账号信息更新成功'
        )

        return jsonify({'success': True, 'message': '修改成功'})

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
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

        data = request.get_json(silent=True) or {}
        username = _normalize_username(data.get('username', ''))
        password = str(data.get('password', '') or '')
        enabled = bool(data.get('enabled', True))
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)

        if not USERNAME_RULE.match(username):
            return jsonify({'success': False, 'message': '用户名仅支持 3-32 位字母、数字、下划线、点、短横线'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': '密码长度至少 8 位'}), 400
        if not permissions:
            return jsonify({'success': False, 'message': '请至少分配 1 项权限'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            existing, _ = _find_user(users_data, username)
            if existing is not None:
                return jsonify({'success': False, 'message': '用户名已存在'}), 400
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
            operation='子账号管理',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'新增子账号：{username}'
        )
        return jsonify({'success': True, 'message': '子账号创建成功'})

    @app.route('/api/admin/subaccounts/<username>', methods=['PUT'])
    @login_required
    def admin_subaccounts_update(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

        target_name = _normalize_username(username)
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get('enabled', True))
        permissions = _normalize_permissions(data.get('permissions', []), is_super_admin=False)
        reset_password = str(data.get('password', '') or '')

        if not permissions:
            return jsonify({'success': False, 'message': '请至少分配 1 项权限'}), 400
        if reset_password and len(reset_password) < 8:
            return jsonify({'success': False, 'message': '新密码长度至少 8 位'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            target_user, idx = _find_user(users_data, target_name)
            if target_user is None or idx < 0:
                return jsonify({'success': False, 'message': '子账号不存在'}), 404
            if str(target_user.get('role') or '') == 'super_admin':
                return jsonify({'success': False, 'message': '超级管理员账号不可在此修改'}), 400

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
            operation='子账号管理',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'更新子账号：{target_name}'
        )
        return jsonify({'success': True, 'message': '子账号更新成功'})

    @app.route('/api/admin/subaccounts/<username>', methods=['DELETE'])
    @login_required
    def admin_subaccounts_delete(username):
        if not _is_super_admin_session(session):
            return _forbidden_subaccount_manage()
        if not _is_same_origin_request(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

        target_name = _normalize_username(username)
        current_name = _normalize_username(session.get('admin_username', ''))
        if target_name == current_name:
            return jsonify({'success': False, 'message': '不能删除当前登录账号'}), 400

        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        with ADMIN_USERS_LOCK:
            users_data, users_file = _ensure_admin_users_store(root, get_config, update_config)
            target_user, idx = _find_user(users_data, target_name)
            if target_user is None or idx < 0:
                return jsonify({'success': False, 'message': '子账号不存在'}), 404
            if str(target_user.get('role') or '') == 'super_admin':
                return jsonify({'success': False, 'message': '超级管理员账号不可删除'}), 400

            users = users_data.get('users', [])
            users.pop(idx)
            users_data['users'] = users
            _save_admin_users(users_file, users_data)

        append_admin_login_log(
            operation='子账号管理',
            success=True,
            username=session.get('admin_username', ''),
            detail=f'删除子账号：{target_name}'
        )
        return jsonify({'success': True, 'message': '子账号已删除'})

    @app.route('/admin/logout', methods=['POST'])
    def admin_logout():
        """处理管理员登出。"""
        username = session.get('admin_username') or ''
        if session.get('admin_logged_in'):
            append_admin_login_log(
                operation='退出登录',
                success=True,
                username=username,
                detail='管理员主动退出'
            )
        session.pop('admin_logged_in', None)
        session.pop('admin_username', None)
        session.pop('admin_is_super_admin', None)
        session.pop('admin_permissions', None)
        session.pop('admin_login_at', None)
        session.pop('admin_session_ttl', None)
        return jsonify({'success': True})

    @app.route('/admin/check')
    def admin_check():
        """检查管理员是否已登录。"""
        logged_in = bool(session.get('admin_logged_in', False))
        if logged_in and _is_admin_session_expired(session):
            session.clear()
            logged_in = False
        if not logged_in:
            return jsonify({
                'logged_in': False,
                'username': '',
                'is_super_admin': False,
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
                'permissions': [],
                'permission_catalog': ADMIN_PERMISSION_CATALOG,
            })

        is_super_admin = bool(str(user.get('role') or '') == 'super_admin')
        permissions = _normalize_permissions(user.get('permissions', []), is_super_admin=is_super_admin)
        session['admin_is_super_admin'] = is_super_admin
        session['admin_permissions'] = permissions
        session['admin_username'] = _normalize_username(user.get('username', current_name))

        return jsonify({
            'logged_in': True,
            'username': session.get('admin_username', ''),
            'is_super_admin': is_super_admin,
            'permissions': permissions,
            'permission_catalog': ADMIN_PERMISSION_CATALOG,
            'last_login_at': str(user.get('last_login_at') or ''),
            'last_login_ip': str(user.get('last_login_ip') or ''),
        })

    @app.route('/api/admin/login-logs')
    @login_required
    def admin_login_logs():
        """获取不可变更的管理员登录操作日志。"""
        # 兼容旧调用方式：支持 `?limit=300`。
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
                items = load_admin_login_logs()

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
            items = list(reversed(load_admin_login_logs()))

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
