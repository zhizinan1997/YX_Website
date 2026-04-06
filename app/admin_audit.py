"""
后台登录审计与IP归属地辅助模块。

本模块提供管理员登录操作的审计功能和IP地址归属地解析能力，
用于安全监控和访问控制。

主要功能：
1. 登录审计日志（append_admin_login_log）
   - 记录所有登录尝试（成功和失败）
   - 记录操作类型（登录、登出、密码修改等）
   - 关联用户名、IP地址、归属地信息
   - 自动持久化到JSON文件

2. 登录日志查询（load_admin_login_logs）
   - 从文件加载历史登录日志
   - 自动初始化日志文件
   - 限制日志条目数量（最多500条）

3. IP归属地解析
   - 支持多个IP查询服务（ipwho.is、ipapi.co、ip-api.com）
   - 按优先级自动重试
   - 返回归属地文本和国家代码

4. IP归属地缓存
   - 内存缓存加速重复查询
   - 成功解析缓存7天
   - 失败解析缓存15分钟
   - 自动清理过期缓存

5. IP地址分类识别
   - 本机回环地址识别
   - 内网地址识别
   - 公网地址识别
   - 保留地址识别

6. 时区处理
   - 使用北京时区（Asia/Shanghai）
   - ISO格式时间戳输出

安全特性：
- 日志不可变更（append-only）
- 线程安全的文件操作
- 异常情况优雅降级

作者：元芯传感技术团队
"""

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
    """配置后台审计辅助函数运行时所需的共享依赖。"""
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
    """从文件加载后台登录日志。"""
    default_data = {'items': []}
    if ADMIN_LOGIN_LOG_FILE.exists():
        try:
            data = json.loads(ADMIN_LOGIN_LOG_FILE.read_text(encoding='utf-8'))
            items = data.get('items', [])
            if not isinstance(items, list):
                items = []
            normalized = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = dict(item)
                record['hidden_account'] = bool(record.get('hidden_account', False))
                normalized.append(record)
            return normalized
        except Exception:
            pass

    ADMIN_LOGIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_LOGIN_LOG_FILE.write_text(
        json.dumps(default_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return []


def save_admin_login_logs(items):
    """将后台登录日志持久化保存到文件。"""
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
        return '', ''
    if data.get('success') is False:
        return '', ''
    country_code = str(data.get('country_code') or '').strip().upper()
    connection = data.get('connection') if isinstance(data.get('connection'), dict) else {}
    location = _build_location_text(
        data.get('country') or country_code,
        data.get('region'),
        data.get('city'),
        connection.get('isp') or connection.get('org'),
    )
    return location, country_code


def _fetch_ip_location_from_ipapi_co(ip: str):
    data = _http_get_json(f'https://ipapi.co/{ip}/json/', timeout=2.6)
    if not isinstance(data, dict):
        return '', ''
    if data.get('error') is True:
        return '', ''
    country_code = str(data.get('country_code') or data.get('country') or '').strip().upper()
    # ipapi.co 的 country 字段本身就是 ISO 代码
    if country_code and len(country_code) != 2:
        country_code = ''
    location = _build_location_text(
        data.get('country_name') or country_code,
        data.get('region'),
        data.get('city'),
        data.get('org') or data.get('asn'),
    )
    return location, country_code


def _fetch_ip_location_from_ip_api(ip: str):
    data = _http_get_json(
        f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp,countryCode',
        timeout=2.6,
    )
    if not isinstance(data, dict):
        return '', ''
    if data.get('status') != 'success':
        return '', ''
    country_code = str(data.get('countryCode') or '').strip().upper()
    location = _build_location_text(
        data.get('country'),
        data.get('regionName'),
        data.get('city'),
        data.get('isp'),
    )
    return location, country_code


def fetch_ip_location(ip):
    """通过外部服务解析公网 IP 的归属地信息。

    返回 (归属地展示文本, ISO 国家代码) 的元组。
    如果所有 API 均不可用，返回 ('未知', '')。
    """
    ip_text = str(ip or '').strip()
    if not ip_text:
        return '未知', ''

    for resolver in (
        _fetch_ip_location_from_ipwhois,
        _fetch_ip_location_from_ipapi_co,
        _fetch_ip_location_from_ip_api,
    ):
        try:
            result = resolver(ip_text)
            if isinstance(result, tuple) and len(result) == 2:
                location, cc = result
            else:
                location, cc = str(result or '').strip(), ''
        except Exception:
            location, cc = '', ''
        location = str(location or '').strip()
        cc = str(cc or '').strip().upper()
        if location and location != '未知':
            return location, cc
    return '未知', ''


def fetch_ip_country_code(ip):
    """仅获取公网 IP 对应的 ISO 国家代码，供登录地域校验使用。"""
    _, cc = fetch_ip_location(ip)
    return cc


def _is_unknown_location(value: str) -> bool:
    text = str(value or '').strip().lower()
    return not text or text in {'未知', 'unknown', 'n/a', '-'}


def resolve_ip_location(ip):
    """获取适合展示的 IP 归属地文本。"""
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
            # 兼容旧版内存缓存格式。
            return cached.strip()

    location = '未知'
    country_code = ''
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
            location, country_code = fetch_ip_location(ip_text)
    except ValueError:
        location = '未知'

    ttl = ADMIN_IP_LOCATION_CACHE_TTL_UNKNOWN if _is_unknown_location(location) else ADMIN_IP_LOCATION_CACHE_TTL_SUCCESS
    cache_item = {
        'location': str(location or '未知').strip() or '未知',
        'country_code': str(country_code or '').strip().upper(),
        'expires_at': now_ts + ttl,
    }

    with ADMIN_IP_LOCATION_LOCK:
        if len(ADMIN_IP_LOCATION_CACHE) >= ADMIN_IP_LOCATION_CACHE_MAX:
            # 优先清理过期项；如果仍然过大，再整体重置缓存。
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


def resolve_ip_country_code(ip):
    """获取 IP 对应的 ISO 国家代码（带缓存），供登录地域校验使用。

    会先调用 resolve_ip_location 确保缓存已填充，然后从缓存中读取 country_code。
    """
    ip_text = str(ip or '').strip()
    if not ip_text:
        return ''
    # 确保缓存已填充
    resolve_ip_location(ip_text)
    with ADMIN_IP_LOCATION_LOCK:
        cached = ADMIN_IP_LOCATION_CACHE.get(ip_text)
        if isinstance(cached, dict):
            return str(cached.get('country_code') or '').strip().upper()
    return ''


def now_beijing_iso():
    """返回上海时区当前时间的 ISO 字符串。"""
    return datetime.now(BEIJING_TZ).isoformat(timespec='seconds')


MAX_ADMIN_LOGIN_LOG_ITEMS = 500


def append_admin_login_log(operation, success, username='', detail='', hidden_account=False):
    """追加一条不可变更的后台登录操作日志。"""
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
        'hidden_account': bool(hidden_account),
    }

    with ADMIN_LOGIN_LOG_LOCK:
        items = load_admin_login_logs()
        items.append(log_item)
        if len(items) > MAX_ADMIN_LOGIN_LOG_ITEMS:
            items = items[-MAX_ADMIN_LOGIN_LOG_ITEMS:]
        save_admin_login_logs(items)
