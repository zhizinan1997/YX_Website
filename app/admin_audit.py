"""Admin login audit and IP geo helpers."""

import ipaddress
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / 'data'
ADMIN_LOGIN_LOG_FILE = DATA_DIR / 'admin_login_logs.json'
ADMIN_LOGIN_LOG_LOCK = threading.Lock()
ADMIN_IP_LOCATION_CACHE = {}
ADMIN_IP_LOCATION_LOCK = threading.Lock()
ADMIN_IP_LOCATION_CACHE_MAX = 2048
ADMIN_IP_LOCATION_CACHE_TTL_SUCCESS = 7 * 24 * 3600
ADMIN_IP_LOCATION_CACHE_TTL_UNKNOWN = 15 * 60
BEIJING_TZ = timezone(timedelta(hours=8))
REQUESTS_SUPPORT = False
REQUESTS_MODULE = None
HTTPX_SUPPORT = False
HTTPX_MODULE = None


def _default_get_client_ip() -> str:
    return '127.0.0.1'


GET_CLIENT_IP = _default_get_client_ip


def configure_admin_audit(
    *,
    data_dir=None,
    beijing_tz=None,
    requests_support: bool = False,
    requests_module=None,
    httpx_support: bool = False,
    httpx_module=None,
    get_client_ip=None,
):
    """Configure runtime dependencies for admin audit helpers."""
    global ADMIN_LOGIN_LOG_FILE, BEIJING_TZ
    global REQUESTS_SUPPORT, REQUESTS_MODULE, HTTPX_SUPPORT, HTTPX_MODULE, GET_CLIENT_IP

    if data_dir is not None:
        ADMIN_LOGIN_LOG_FILE = Path(data_dir) / 'admin_login_logs.json'
    if beijing_tz is not None:
        BEIJING_TZ = beijing_tz

    REQUESTS_SUPPORT = bool(requests_support and requests_module is not None)
    REQUESTS_MODULE = requests_module if REQUESTS_SUPPORT else None
    HTTPX_SUPPORT = bool(httpx_support and httpx_module is not None)
    HTTPX_MODULE = httpx_module if HTTPX_SUPPORT else None

    if get_client_ip is not None:
        GET_CLIENT_IP = get_client_ip


def load_admin_login_logs():
    """Load admin login logs from file."""
    default_data = {'items': []}
    if ADMIN_LOGIN_LOG_FILE.exists():
        try:
            data = json.loads(ADMIN_LOGIN_LOG_FILE.read_text(encoding='utf-8'))
            items = data.get('items', [])
            if not isinstance(items, list):
                items = []
            return [item for item in items if isinstance(item, dict)]
        except Exception:
            pass

    ADMIN_LOGIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_LOGIN_LOG_FILE.write_text(
        json.dumps(default_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return []


def save_admin_login_logs(items):
    """Persist admin login logs to file."""
    safe_items = [item for item in (items or []) if isinstance(item, dict)]
    ADMIN_LOGIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_LOGIN_LOG_FILE.write_text(
        json.dumps({'items': safe_items}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _build_location_text(*parts):
    cleaned = []
    seen = set()
    for value in parts:
        text = str(value or '').strip()
        if not text or text in {'-', '--'}:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    if not cleaned:
        return '未知'
    return ' / '.join(cleaned)


def _http_get_json(url: str, timeout: float = 2.5):
    headers = {
        'User-Agent': 'YX-Website-Admin/1.0',
        'Accept': 'application/json,text/plain,*/*',
    }

    if REQUESTS_SUPPORT:
        try:
            res = REQUESTS_MODULE.get(url, timeout=timeout, headers=headers)
            if res.ok:
                return res.json()
        except Exception:
            pass

    if HTTPX_SUPPORT:
        try:
            res = HTTPX_MODULE.get(url, timeout=timeout, headers=headers, follow_redirects=True)
            if 200 <= res.status_code < 300:
                return res.json()
        except Exception:
            pass

    return None


def _fetch_ip_location_from_ipwhois(ip: str):
    data = _http_get_json(f'https://ipwho.is/{ip}?lang=zh', timeout=2.6)
    if not isinstance(data, dict):
        return ''
    if data.get('success') is False:
        return ''
    connection = data.get('connection') if isinstance(data.get('connection'), dict) else {}
    return _build_location_text(
        data.get('country') or data.get('country_code'),
        data.get('region'),
        data.get('city'),
        connection.get('isp') or connection.get('org'),
    )


def _fetch_ip_location_from_ipapi_co(ip: str):
    data = _http_get_json(f'https://ipapi.co/{ip}/json/', timeout=2.6)
    if not isinstance(data, dict):
        return ''
    if data.get('error') is True:
        return ''
    return _build_location_text(
        data.get('country_name') or data.get('country'),
        data.get('region'),
        data.get('city'),
        data.get('org') or data.get('asn'),
    )


def _fetch_ip_location_from_ip_api(ip: str):
    data = _http_get_json(
        f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp',
        timeout=2.6,
    )
    if not isinstance(data, dict):
        return ''
    if data.get('status') != 'success':
        return ''
    return _build_location_text(
        data.get('country'),
        data.get('regionName'),
        data.get('city'),
        data.get('isp'),
    )


def fetch_ip_location(ip):
    """Resolve geo location for a public IP by external service."""
    ip_text = str(ip or '').strip()
    if not ip_text:
        return '未知'

    for resolver in (
        _fetch_ip_location_from_ipwhois,
        _fetch_ip_location_from_ipapi_co,
        _fetch_ip_location_from_ip_api,
    ):
        try:
            location = str(resolver(ip_text) or '').strip()
        except Exception:
            location = ''
        if location and location != '未知':
            return location
    return '未知'


def _is_unknown_location(value: str) -> bool:
    text = str(value or '').strip().lower()
    return not text or text in {'未知', 'unknown', 'n/a', '-'}


def resolve_ip_location(ip):
    """Get a readable location text for IP."""
    ip_text = str(ip or '').strip()
    if not ip_text:
        return '未知'

    now_ts = int(time.time())
    with ADMIN_IP_LOCATION_LOCK:
        cached = ADMIN_IP_LOCATION_CACHE.get(ip_text)
        if isinstance(cached, dict):
            cached_location = str(cached.get('location') or '').strip()
            expires_at = int(cached.get('expires_at', 0) or 0)
            if cached_location and expires_at > now_ts:
                return cached_location
        elif isinstance(cached, str) and cached.strip() and not _is_unknown_location(cached):
            # Backward compatibility for legacy in-memory cache format.
            return cached.strip()

    location = '未知'
    try:
        ip_obj = ipaddress.ip_address(ip_text)
        if ip_obj.is_loopback:
            location = '本机回环地址'
        elif ip_obj.is_private:
            location = '内网地址'
        elif ip_obj.is_unspecified:
            location = '未指定地址'
        elif ip_obj.is_reserved:
            location = '保留地址'
        elif ip_obj.is_multicast:
            location = '组播地址'
        else:
            location = fetch_ip_location(ip_text)
    except ValueError:
        location = '未知'

    ttl = ADMIN_IP_LOCATION_CACHE_TTL_UNKNOWN if _is_unknown_location(location) else ADMIN_IP_LOCATION_CACHE_TTL_SUCCESS
    cache_item = {
        'location': str(location or '未知').strip() or '未知',
        'expires_at': now_ts + ttl,
    }

    with ADMIN_IP_LOCATION_LOCK:
        if len(ADMIN_IP_LOCATION_CACHE) >= ADMIN_IP_LOCATION_CACHE_MAX:
            # Prefer clearing expired entries first; if still large then reset.
            expired_keys = []
            for key, value in ADMIN_IP_LOCATION_CACHE.items():
                if isinstance(value, dict) and int(value.get('expires_at', 0) or 0) <= now_ts:
                    expired_keys.append(key)
            for key in expired_keys:
                ADMIN_IP_LOCATION_CACHE.pop(key, None)
            if len(ADMIN_IP_LOCATION_CACHE) >= ADMIN_IP_LOCATION_CACHE_MAX:
                ADMIN_IP_LOCATION_CACHE.clear()
        ADMIN_IP_LOCATION_CACHE[ip_text] = cache_item
    return cache_item['location']


def now_beijing_iso():
    """Current datetime string in Asia/Shanghai timezone."""
    return datetime.now(BEIJING_TZ).isoformat(timespec='seconds')


MAX_ADMIN_LOGIN_LOG_ITEMS = 500


def append_admin_login_log(operation, success, username='', detail=''):
    """Append one immutable admin login-operation log record."""
    ip = GET_CLIENT_IP()
    log_item = {
        'id': uuid.uuid4().hex,
        'ip': ip,
        'location': resolve_ip_location(ip),
        'success': bool(success),
        'timestamp': now_beijing_iso(),
        'operation': str(operation or '后台操作').strip(),
        'username': str(username or '').strip(),
        'detail': str(detail or '').strip(),
    }

    with ADMIN_LOGIN_LOG_LOCK:
        items = load_admin_login_logs()
        items.append(log_item)
        if len(items) > MAX_ADMIN_LOGIN_LOG_ITEMS:
            items = items[-MAX_ADMIN_LOGIN_LOG_ITEMS:]
        save_admin_login_logs(items)
