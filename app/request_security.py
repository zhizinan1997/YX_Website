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
- TRUST_PROXY_HEADERS: 是否信任代理头（默认开启，站点部署在 CDN/反向代理之后
  时必须保持开启，否则客户端真实 IP 会变成代理 IP；直接暴露时建议显式设为
  false，防止伪造 XFF 绕过限流）

作者：元芯传感技术团队
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
import socket
import threading
from contextlib import contextmanager
from urllib.parse import urlparse

from flask import Response, jsonify, request, session

CSRF_SESSION_KEY = 'admin_csrf_token'
CSRF_HEADER_NAME = 'X-CSRF-Token'

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
# 可信远程服务白名单：仅按“域名后缀”（点分锚定，防止 evil-feishu.com 这类
# 子串伪装命中）匹配；命中后仍需通过 HTTPS 且允许其解析到私有地址（飞书
# 内网回源场景）。不要用子串关键词匹配——那会被攻击者注册的域名绕过。
REMOTE_FETCH_TRUSTED_HOST_PATH_RULES = (
    {
        'host_suffixes': ('feishu.cn', 'feishu.net', 'larksuite.com', 'larkoffice.com'),
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


# 可信代理判定：
# 1. TRUST_PROXY_HEADERS 显式开启 → 无条件信任代理头（部署在 CDN/反代后且无法
#    枚举代理网段时的兼容开关，此时代理必须负责改写这些头）。
# 2. TRUST_PROXY_HEADERS 显式关闭 → 永不信任。
# 3. 未配置（默认）→ 仅当直连地址 remote_addr 是回环/私网（本地反向代理），
#    或命中 TRUSTED_PROXY_CIDRS 显式声明的代理网段时才信任，避免公网客户端
#    伪造 X-Forwarded-For / CF-Connecting-IP 绕过限流、污染审计日志。
def should_trust_proxy_headers(req=None, *, default: bool = True) -> bool:
    raw = (os.environ.get('TRUST_PROXY_HEADERS') or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False

    if req is None:
        # 无请求上下文时保持保守：不基于代理头做任何判断。
        return False
    remote_ip = normalize_ip_text(getattr(req, 'remote_addr', '') or '')
    if not remote_ip:
        return False
    if is_private_proxy_source(remote_ip):
        return True
    return _remote_addr_in_trusted_proxy_networks(remote_ip)


def _trusted_proxy_networks() -> tuple:
    """解析 TRUSTED_PROXY_CIDRS（逗号分隔的 IP/CIDR），供可信代理判定使用。"""
    raw = (os.environ.get('TRUSTED_PROXY_CIDRS') or '').strip()
    if not raw:
        return ()
    networks = []
    for part in raw.split(','):
        text = part.strip()
        if not text:
            continue
        if '/' not in text:
            text = f'{text}/128' if ':' in text else f'{text}/32'
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _remote_addr_in_trusted_proxy_networks(remote_ip: str) -> bool:
    networks = _trusted_proxy_networks()
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False
    return any(addr in network for network in networks)


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

        # 整条链都是私有地址时，说明没有任何可信代理追加过真实客户端 IP；
        # 此时链内的私有地址全部来自客户端伪造，用于限流/审计会造成每请求
        # 换桶绕过限流，因此回落到直连地址（代理本身）而非链内任意值。
        if direct_ip:
            return direct_ip
        if x_real_ip:
            return x_real_ip
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
        # 后缀必须点分锚定：host == suffix 或 host 以 ".suffix" 结尾，
        # 避免 "evilfeishu.cn" 命中 "feishu.cn"。
        suffix_match = any(
            normalized_host == suffix or normalized_host.endswith(f'.{suffix}')
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


def validate_safe_remote_fetch_url_detail(raw_url: str) -> tuple[bool, str, str, str]:
    """校验远程抓取地址，并返回可用于固定建连的已验证 IP。

    返回 (ok, reason, normalized_url, pinned_ip)。pinned_ip 为域名解析出的
    公网 IP（纯 IP 字面量或无需固定时为空字符串）；调用方把它交给
    pinned_dns_resolution()，让实际请求跳过第二次 DNS 解析，闭合
    “校验时公网、连接时内网”的 rebinding 窗口。
    """
    normalized = normalize_remote_fetch_url(raw_url)
    if not normalized:
        return False, '仅支持合法的 http/https 地址', '', ''

    try:
        parsed = urlparse(normalized)
    except Exception:
        return False, '链接格式不合法', '', ''

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, '链接缺少主机名', '', ''
    if parsed.username or parsed.password:
        return False, '链接中不允许包含账号信息', '', ''
    trusted_service_url = is_trusted_remote_fetch_service_url(parsed.scheme, hostname, parsed.path)
    if hostname in REMOTE_FETCH_BLOCKED_HOSTS:
        return False, '禁止访问本机或保留地址', '', ''

    literal_ip = normalize_ip_text(hostname)
    if literal_ip:
        if not ip_is_publicly_routable(literal_ip):
            return False, '禁止访问内网或保留地址', '', ''
        # IP 字面量没有二次解析，无需固定。
        return True, '', normalized, ''

    try:
        records = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == 'https' else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False, '域名解析失败', '', ''
    except Exception:
        return False, '域名解析异常', '', ''

    resolved_ips = []
    for item in records:
        sockaddr = item[4] if len(item) >= 5 else ()
        if not sockaddr:
            continue
        ip_text = normalize_ip_text(sockaddr[0])
        if ip_text and ip_text not in resolved_ips:
            resolved_ips.append(ip_text)

    if not resolved_ips:
        return False, '域名解析结果为空', '', ''
    if any(not ip_is_publicly_routable(ip_text) for ip_text in resolved_ips):
        if trusted_service_url:
            # 可信服务（如飞书）允许解析到私有地址，同样按首个结果固定。
            return True, '', normalized, resolved_ips[0]
        return False, '禁止访问内网或保留地址', '', ''
    return True, '', normalized, resolved_ips[0]


def validate_safe_remote_fetch_url(raw_url: str) -> tuple[bool, str, str]:
    ok, reason, normalized, _pinned_ip = validate_safe_remote_fetch_url_detail(raw_url)
    return ok, reason, normalized


# ── DNS 固定（防 rebinding）────────────────────────────────────────
# validate_safe_remote_fetch_url_detail 在校验时解析一次 DNS；若实际请求
# 再解析一次，攻击者控制权威 DNS 可在两次解析之间换答（首次公网通过
# 校验、二次解析成内网 IP），形成 SSRF。固定方案：把校验得到的已验证 IP
# 放入当前线程的 pin 栈，请求期间 getaddrinfo 对该域名直接返回该 IP；
# 建连、SNI、证书校验、Cookie 仍按原域名进行，URL 行为完全不变。
_PINNED_DNS_STATE = threading.local()
_BASE_GETADDRINFO = socket.getaddrinfo


def _dns_pinned_getaddrinfo(host, *args, **kwargs):
    """线程级固定解析：命中当前线程 pin 栈的域名直接解析为已验证 IP。"""
    stack = getattr(_PINNED_DNS_STATE, 'stack', None)
    if stack:
        for mapping in reversed(stack):
            pinned_ip = mapping.get(str(host))
            if pinned_ip:
                host = pinned_ip
                break
    return _BASE_GETADDRINFO(host, *args, **kwargs)


socket.getaddrinfo = _dns_pinned_getaddrinfo


@contextmanager
def pinned_dns_resolution(normalized_url: str, pinned_ip: str):
    """在当前线程内把 URL 域名的解析固定为校验时的已验证 IP。

    pinned_ip 来自 validate_safe_remote_fetch_url_detail；为空（IP 字面量
    等）时不做任何固定。可重入：嵌套进入按栈逐层匹配。
    """
    if not normalized_url or not pinned_ip:
        yield
        return
    try:
        hostname = (urlparse(normalized_url).hostname or '').strip().lower()
    except Exception:
        yield
        return
    if not hostname or normalize_ip_text(hostname):
        yield
        return
    stack = getattr(_PINNED_DNS_STATE, 'stack', None)
    if stack is None:
        stack = []
        _PINNED_DNS_STATE.stack = stack
    stack.append({hostname: pinned_ip})
    try:
        yield
    finally:
        stack.pop()


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


def _origin_matches_allowed(origin: str, allowed_origins: list[str]) -> bool:
    # hmac.compare_digest 对含非 ASCII 字符的 str 会抛 TypeError，
    # 统一转成字节后再做常量时间比较，避免畸形 Origin 头引发 500。
    origin_bytes = origin.encode('utf-8')
    for item in allowed_origins:
        try:
            if hmac.compare_digest(origin_bytes, item.encode('utf-8')):
                return True
        except Exception:
            continue
    return False


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
        return _origin_matches_allowed(origin, allowed_origins)

    referer = normalize_origin(req.headers.get('Referer', ''))
    if referer:
        return _origin_matches_allowed(referer, allowed_origins)

    # 部分隐私浏览器会剥离 Origin/Referer；此时仍要求不可被跨站读取的
    # session-bound token，避免把“缺少来源头”直接变成放行条件。
    expected_token = str(session.get(CSRF_SESSION_KEY, '') or '').strip()
    provided_token = str(
        req.headers.get(CSRF_HEADER_NAME)
        or req.form.get('csrf_token', '')
        or ''
    ).strip()
    if not expected_token or not provided_token:
        return False
    try:
        return hmac.compare_digest(
            expected_token.encode('utf-8'), provided_token.encode('utf-8')
        )
    except Exception:
        return False


def get_request_client_ip(
    req,
    *,
    default_ip: str = '127.0.0.1',
    trust_proxy_headers_default: bool = True,
    public_ip_header_names=None,
) -> str:
    if should_trust_proxy_headers(req, default=trust_proxy_headers_default):
        direct_ip = normalize_ip_text(req.remote_addr or '')
        configured_headers = None
        if public_ip_header_names is not None:
            header_names = tuple(public_ip_header_names)
        else:
            configured_headers = get_configured_real_client_ip_headers()
            header_names = configured_headers or ('CF-Connecting-IP',)
        for header_name in header_names:
            header_ip = normalize_ip_text(req.headers.get(header_name, ''))
            if header_ip and ip_is_publicly_routable(header_ip):
                return header_ip

        if configured_headers:
            # 显式配置了 CDN 专用真实 IP 头（如 ESA 的 Ali-Real-Client-IP）：
            # 请求里却没有该头，说明流量没有经过 CDN 边缘（直连源站的攻击
            # 流量）。此时 CF-Connecting-IP / X-Real-IP 等头全部可由客户端
            # 伪造，不得作为回退；按 XFF 最右公网收敛，直连场景收敛到反代
            # 自身，形成共享限流桶压制攻击。
            proxied_ip = extract_client_ip_from_proxy_headers(req, direct_ip=direct_ip, x_real_ip='')
            if proxied_ip:
                return proxied_ip
            if direct_ip:
                return direct_ip

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


def get_configured_real_client_ip_headers() -> tuple[str, ...]:
    """读取环境变量 REAL_CLIENT_IP_HEADERS（逗号分隔的头部名）。

    CDN/边缘（阿里云 ESA 托管转换注入 Ali-Real-Client-IP，CDN/DCDN 透传
    Ali-CDN-Real-IP）会把客户端真实 IP 放在专用头里回源，这类头由边缘
    覆写、客户端无法伪造；而 CF-Connecting-IP 是 Cloudflare 专有头，在
    非 Cloudflare 链路中只能来自客户端伪造。未配置时保持旧行为
    （CF-Connecting-IP 优先），配置后进入严格模式：只信列表内的头。
    """
    raw = (os.environ.get('REAL_CLIENT_IP_HEADERS') or '').strip()
    if not raw:
        return ()
    headers = []
    for part in raw.split(','):
        name = part.strip()
        if name and name not in headers:
            headers.append(name)
    return tuple(headers)


def get_client_ip(
    *,
    default_ip: str = '127.0.0.1',
    trust_proxy_headers_default: bool = True,
    public_ip_header_names=None,
) -> str:
    """从当前 Flask 请求上下文中解析客户端 IP。

    默认（不显式传 public_ip_header_names）遵循 REAL_CLIENT_IP_HEADERS
    环境变量：未配置时保持 CF-Connecting-IP 优先的旧行为；配置后（如
    ESA 链路设为 Ali-Real-Client-IP,Ali-CDN-Real-IP）进入严格模式。
    """
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
