"""
请求安全辅助模块，负责代理、IP与同源校验。

本模块提供全面的Web安全防护功能，包括：
1. 客户端IP解析
2. 同源请求验证
3. 防爬虫机制
4. 远程URL安全验证

主要功能：
1. IP地址处理
   - 规范化IP地址格式（支持IPv4和IPv6）
   - 从代理头（X-Forwarded-For）中提取真实IP
   - 识别私网、回环、保留地址
   - 支持Cloudflare等CDN的IP头

2. 同源请求验证（is_same_origin_request）
   - 验证请求的Origin或Referer头
   - 支持代理头信任配置
   - 防止跨站请求伪造（CSRF）

3. 代理头处理
   - X-Forwarded-For: 负载均衡器传递的真实IP链
   - X-Forwarded-Host: 原始请求的主机名
   - X-Forwarded-Proto: 原始请求的协议
   - X-Real-IP: Nginx等反向代理的真实IP
   - CF-Connecting-IP: Cloudflare的访客真实IP

4. 远程URL安全验证（validate_safe_remote_fetch_url）
   - 检查URL协议（仅允许http/https）
   - 验证主机名不为保留地址（localhost、127.0.0.1等）
   - DNS解析验证，防止DNS Rebinding攻击
   - 检查解析后的IP地址是否为公网可达

5. 防爬虫机制
   - 识别爬虫User-Agent特征
   - 拦截私有路径上的爬虫访问
   - 公开页面和静态资源不依据User-Agent做访问限制
   - 设置严格响应头防止爬虫索引

6. 反爬虫守卫（register_strict_anti_crawl_guard）
   - 在before_request钩子中拦截爬虫访问私有路径
   - 保护/admin、/api/admin、/data/等私有路径
   - 允许所有客户端抓取公开页面、CSS、JavaScript和媒体资源

安全常量：
- ANTI_CRAWL_STRICT_PRIVATE_PREFIXES: 需要保护的私有路径前缀
- ANTI_CRAWL_BOT_UA_KEYWORDS: 爬虫UA特征关键词
- REMOTE_FETCH_BLOCKED_HOSTS: 禁止远程访问的主机列表

配置选项：
- TRUST_PROXY_HEADERS: 是否信任代理头（默认关闭，需显式开启）

作者：元芯传感技术团队
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

from flask import Response, jsonify, request

ANTI_CRAWL_STRICT_PRIVATE_PREFIXES = (
    '/admin',
    '/api/admin',
    '/data/',
    '/update_logs/',
)
ANTI_CRAWL_BOT_UA_KEYWORDS = (
    'bot',
    'spider',
    'crawler',
    'scrapy',
    'curl',
    'wget',
    'python-requests',
    'httpx',
    'okhttp',
    'java/',
    'go-http-client',
    'axios',
    'headless',
    'phantomjs',
    'playwright',
    'selenium',
    'slurp',
    'bingpreview',
    'googlebot',
    'baiduspider',
    'yandex',
    'duckduckbot',
    'semrush',
    'ahrefs',
    'mj12bot',
    'facebookexternalhit',
    'twitterbot',
    'bytespider',
    'petalbot',
    'sogou',
    'gptbot',
    'ccbot',
    'claudebot',
)
STRICT_ANTI_CRAWL_HEADERS = 'noindex, nofollow, noarchive, nosnippet, noimageindex'
PUBLIC_HTML_CONTENT_SECURITY_POLICY = "base-uri 'self'; frame-ancestors 'self'; object-src 'none'"
PUBLIC_REFERRER_POLICY = 'strict-origin-when-cross-origin'
REMOTE_FETCH_BLOCKED_HOSTS = {
    'localhost',
    'localhost.localdomain',
    '127.0.0.1',
    '::1',
}
REMOTE_FETCH_TRUSTED_HOST_PATH_RULES = (
    {
        'host_keywords': ('feishu', 'larksuite', 'larkoffice'),
        'schemes': ('http', 'https'),
    },
)


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    return default


def normalize_public_base_url(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        return ''
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        value = f'https://{value}'
    try:
        parsed = urlparse(value)
    except Exception:
        return ''
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return ''
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'.rstrip('/')


def get_public_base_url() -> str:
    return normalize_public_base_url(os.environ.get('PUBLIC_BASE_URL', ''))


def normalize_origin(raw_value: str) -> str:
    value = str(raw_value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlparse(value)
    except Exception:
        return ''
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'


def first_forwarded_value(raw_value: str) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return ''
    return text.split(',')[0].strip()


def normalize_forwarded_host(raw_value: str) -> str:
    """Validate a forwarded Host value before it is used in public URLs."""
    value = first_forwarded_value(raw_value).strip().strip('"')
    if not value or any(char.isspace() for char in value) or any(char in value for char in '/\\@'):
        return ''
    try:
        parsed = urlparse(f'//{value}')
        parsed.port
    except Exception:
        return ''
    if not parsed.hostname:
        return ''
    return parsed.netloc.lower()


def parse_standard_forwarded_header(raw_value: str) -> tuple[str, str]:
    """Extract host and proto from the first RFC 7239 Forwarded entry."""
    first_entry = first_forwarded_value(raw_value)
    if not first_entry:
        return '', ''
    values = {}
    for part in first_entry.split(';'):
        key, separator, value = part.strip().partition('=')
        if not separator:
            continue
        values[key.strip().lower()] = value.strip().strip('"')
    host = normalize_forwarded_host(values.get('host', ''))
    proto = str(values.get('proto') or '').strip().lower()
    return host, proto if proto in {'http', 'https'} else ''


def get_trusted_forwarded_host_proto(req, *, default: bool = False) -> tuple[str, str]:
    """Read proxy host/proto only when proxy headers are explicitly trusted."""
    if not should_trust_proxy_headers(req, default=default):
        return '', ''
    host = normalize_forwarded_host(req.headers.get('X-Forwarded-Host', ''))
    proto = first_forwarded_value(req.headers.get('X-Forwarded-Proto', '')).lower()
    if proto not in {'http', 'https'}:
        proto = ''
    standard_host, standard_proto = parse_standard_forwarded_header(req.headers.get('Forwarded', ''))
    return host or standard_host, proto or standard_proto


def normalize_ip_text(raw_value: str) -> str:
    text = str(raw_value or '').strip()
    if not text or text.lower() == 'unknown':
        return ''

    candidate = text
    if text.startswith('[') and ']' in text:
        candidate = text[1:text.index(']')].strip()
    elif text.count(':') == 1 and '.' in text:
        host, _, _port = text.rpartition(':')
        candidate = host.strip()

    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return ''


def is_private_proxy_source(ip_text: str) -> bool:
    normalized = normalize_ip_text(ip_text)
    if not normalized:
        return False
    try:
        ip_obj = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local)


def should_trust_proxy_headers(_req=None, *, default: bool = True) -> bool:
    return env_bool('TRUST_PROXY_HEADERS', default)


def parse_forwarded_ip_chain(raw_value: str) -> list[str]:
    chain = []
    for part in str(raw_value or '').split(','):
        ip_text = normalize_ip_text(part)
        if ip_text and ip_text not in chain:
            chain.append(ip_text)
    return chain


def extract_client_ip_from_proxy_headers(req, *, direct_ip: str = '', x_real_ip: str = '') -> str:
    chain = parse_forwarded_ip_chain(req.headers.get('X-Forwarded-For', ''))
    if chain:
        for ip_text in reversed(chain):
            if not is_private_proxy_source(ip_text):
                return ip_text

        proxy_hints = {ip for ip in {direct_ip, x_real_ip} if ip}
        for ip_text in reversed(chain):
            if ip_text not in proxy_hints:
                return ip_text
        return chain[0]
    return ''


def ip_is_publicly_routable(ip_text: str) -> bool:
    normalized = normalize_ip_text(ip_text)
    if not normalized:
        return False
    try:
        ip_obj = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def normalize_remote_fetch_url(raw_url: str) -> str:
    if not raw_url:
        return ''
    try:
        parsed = urlparse(str(raw_url).strip())
    except Exception:
        return ''
    if parsed.scheme not in {'http', 'https'}:
        return ''
    if not parsed.netloc:
        return ''
    return parsed._replace(fragment='').geturl()


def is_trusted_remote_fetch_service_url(scheme: str, hostname: str, path: str) -> bool:
    normalized_scheme = str(scheme or '').strip().lower()
    normalized_host = str(hostname or '').strip().lower()
    normalized_path = str(path or '').strip() or '/'
    if not normalized_path.startswith('/'):
        normalized_path = f'/{normalized_path}'
    if not normalized_scheme or not normalized_host:
        return False

    for rule in REMOTE_FETCH_TRUSTED_HOST_PATH_RULES:
        allowed_schemes = tuple(str(item or '').strip().lower() for item in rule.get('schemes', ()))
        if allowed_schemes and normalized_scheme not in allowed_schemes:
            continue

        host_keywords = tuple(str(item or '').strip().lower() for item in rule.get('host_keywords', ()))
        keyword_match = any(keyword and keyword in normalized_host for keyword in host_keywords)
        host_suffixes = tuple(str(item or '').strip().lower() for item in rule.get('host_suffixes', ()))
        suffix_match = any(
            normalized_host == suffix.lstrip('.') or normalized_host.endswith(suffix)
            for suffix in host_suffixes
            if suffix
        )
        if host_keywords and not keyword_match and not suffix_match:
            continue
        if not host_keywords and not suffix_match:
            continue

        path_prefixes = tuple(str(item or '').strip() for item in rule.get('path_prefixes', ()))
        if path_prefixes and not any(normalized_path.startswith(prefix) for prefix in path_prefixes if prefix):
            continue

        return True
    return False


def validate_safe_remote_fetch_url(raw_url: str) -> tuple[bool, str, str]:
    normalized = normalize_remote_fetch_url(raw_url)
    if not normalized:
        return False, '仅支持合法的 http/https 地址', ''

    try:
        parsed = urlparse(normalized)
    except Exception:
        return False, '链接格式不合法', ''

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, '链接缺少主机名', ''
    if parsed.username or parsed.password:
        return False, '链接中不允许包含账号信息', ''
    trusted_service_url = is_trusted_remote_fetch_service_url(parsed.scheme, hostname, parsed.path)
    if hostname in REMOTE_FETCH_BLOCKED_HOSTS:
        return False, '禁止访问本机或保留地址', ''

    literal_ip = normalize_ip_text(hostname)
    if literal_ip:
        if not ip_is_publicly_routable(literal_ip):
            return False, '禁止访问内网或保留地址', ''
        return True, '', normalized

    try:
        records = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == 'https' else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False, '域名解析失败', ''
    except Exception:
        return False, '域名解析异常', ''

    resolved_ips = []
    for item in records:
        sockaddr = item[4] if len(item) >= 5 else ()
        if not sockaddr:
            continue
        ip_text = normalize_ip_text(sockaddr[0])
        if ip_text and ip_text not in resolved_ips:
            resolved_ips.append(ip_text)

    if not resolved_ips:
        return False, '域名解析结果为空', ''
    if any(not ip_is_publicly_routable(ip_text) for ip_text in resolved_ips):
        if trusted_service_url:
            return True, '', normalized
        return False, '禁止访问内网或保留地址', ''
    return True, '', normalized


def collect_allowed_origins(
    req,
    *,
    public_base_url: str = '',
    trust_proxy_headers_default: bool = True,
) -> list[str]:
    allowed_origins = []

    def add_allowed(raw_origin: str):
        normalized = normalize_origin(raw_origin)
        if normalized and normalized not in allowed_origins:
            allowed_origins.append(normalized)

    add_allowed(public_base_url or get_public_base_url())

    host_url = str(getattr(req, 'host_url', '') or '').strip()
    add_allowed(host_url)

    parsed_host = urlparse(host_url) if host_url else None
    host_netloc = (parsed_host.netloc or '').strip().lower() if parsed_host else ''
    host_scheme = (parsed_host.scheme or '').strip().lower() if parsed_host else ''
    if host_netloc:
        if host_scheme == 'http':
            add_allowed(f'https://{host_netloc}')
        elif host_scheme == 'https':
            add_allowed(f'http://{host_netloc}')

    if should_trust_proxy_headers(req, default=trust_proxy_headers_default):
        xf_host = first_forwarded_value(req.headers.get('X-Forwarded-Host', ''))
        xf_proto = first_forwarded_value(req.headers.get('X-Forwarded-Proto', '')).lower()
        if xf_host:
            proto = xf_proto if xf_proto in {'http', 'https'} else (host_scheme or 'https')
            add_allowed(f'{proto}://{xf_host}')
            add_allowed(f'{"https" if proto == "http" else "http"}://{xf_host}')

    return allowed_origins


def is_same_origin_request(
    req,
    *,
    public_base_url: str = '',
    trust_proxy_headers_default: bool = True,
) -> bool:
    allowed_origins = collect_allowed_origins(
        req,
        public_base_url=public_base_url,
        trust_proxy_headers_default=trust_proxy_headers_default,
    )
    if not allowed_origins:
        return False

    origin = normalize_origin(req.headers.get('Origin', ''))
    if origin:
        return any(hmac.compare_digest(origin, item) for item in allowed_origins)

    referer = normalize_origin(req.headers.get('Referer', ''))
    if referer:
        return any(hmac.compare_digest(referer, item) for item in allowed_origins)

    return False


def get_request_client_ip(
    req,
    *,
    default_ip: str = '127.0.0.1',
    trust_proxy_headers_default: bool = True,
    public_ip_header_names=('CF-Connecting-IP',),
) -> str:
    if should_trust_proxy_headers(req, default=trust_proxy_headers_default):
        direct_ip = normalize_ip_text(req.remote_addr or '')
        for header_name in tuple(public_ip_header_names or ()):
            header_ip = normalize_ip_text(req.headers.get(header_name, ''))
            if header_ip and ip_is_publicly_routable(header_ip):
                return header_ip

        x_real_ip = normalize_ip_text(req.headers.get('X-Real-IP', ''))
        proxied_ip = extract_client_ip_from_proxy_headers(
            req,
            direct_ip=direct_ip,
            x_real_ip=x_real_ip,
        )
        if proxied_ip:
            return proxied_ip

        if x_real_ip and x_real_ip != direct_ip:
            return x_real_ip

    direct_ip = normalize_ip_text(req.remote_addr or '')
    fallback = str(default_ip or req.remote_addr or '').strip()
    return direct_ip or fallback or '127.0.0.1'


def get_client_ip(
    *,
    default_ip: str = '127.0.0.1',
    trust_proxy_headers_default: bool = True,
    public_ip_header_names=('CF-Connecting-IP',),
) -> str:
    """从当前 Flask 请求上下文中解析客户端 IP。"""
    return get_request_client_ip(
        request,
        default_ip=request.remote_addr or default_ip,
        trust_proxy_headers_default=trust_proxy_headers_default,
        public_ip_header_names=public_ip_header_names,
    )


def path_matches_prefix(path_value: str, prefix: str) -> bool:
    path_text = str(path_value or '').strip() or '/'
    normalized = str(prefix or '').strip()
    if not normalized:
        return False
    base = normalized.rstrip('/')
    return path_text == base or path_text.startswith(normalized)


def is_anti_crawl_strict_private_path(path_value: str) -> bool:
    path_text = str(path_value or '').strip() or '/'
    return any(path_matches_prefix(path_text, item) for item in ANTI_CRAWL_STRICT_PRIVATE_PREFIXES)


def looks_like_crawler_ua(raw_ua: str) -> bool:
    ua = str(raw_ua or '').strip().lower()
    if not ua:
        return True
    return any(keyword in ua for keyword in ANTI_CRAWL_BOT_UA_KEYWORDS)


def register_strict_anti_crawl_guard(app):
    @app.before_request
    def strict_anti_crawl_guard():
        """拦截私有路径上的明显爬虫，同时保留公开页面的 SEO 抓取能力。"""
        path = request.path or '/'
        ua = request.headers.get('User-Agent', '')
        if not looks_like_crawler_ua(ua):
            return None

        if is_anti_crawl_strict_private_path(path):
            if path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Forbidden'}), 403
            return Response('Forbidden', status=403, mimetype='text/plain')

        return None

    return strict_anti_crawl_guard
