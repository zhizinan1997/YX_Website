"""
静态资源版本号（cache busting）工具模块。

根据文件 mtime 自动生成版本号，供 after_request 拦截器注入到
HTML/JS 响应中的静态资源 URL 上（如 ?v=1719012345）。

设计要点：
- 内存缓存 60 秒，避免每次请求都 stat 文件系统
- 线程安全（读写不加锁，容忍偶发重复 stat，不引入性能瓶颈）
- 文件不存在时返回空字符串，调用方自行跳过
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# ── 配置 ──────────────────────────────────────────────

_CACHE_TTL_SECONDS = 60

# mtime 缓存: {abs_path_str: (version_str, cached_at_monotonic)}
_mtime_cache: dict[str, tuple[str, float]] = {}

# ── 路径解析 ──────────────────────────────────────────

# 这些目录的文件可以被版本化（安全地 stat）。
# 以这些前缀开头的 URL 路径才会被解析为文件系统路径。
_VERSIONABLE_PREFIXES = ('/assets/', '/cdn_assets/')


def _is_local_asset_url(url: str) -> bool:
    """判断 URL 是否为本地静态资源（需要注入版本号）。"""
    if not url:
        return False
    stripped = url.lstrip()
    # 跳过外部 URL
    if stripped.startswith(('http://', 'https://', '//')):
        return False
    # 跳过 data URI
    if stripped.startswith('data:'):
        return False
    # 跳过 mailto / javascript / #
    if stripped.startswith(('mailto:', 'javascript:', '#')):
        return False
    return True


def resolve_asset_path(url: str, app_root: Path, request_path: str = '') -> Path | None:
    """
    将 URL 中的资源路径解析为 APP_ROOT 下的实际文件系统路径。

    处理三种路径形式：
    - 绝对路径: /assets/css/x.css → APP_ROOT/assets/css/x.css
    - 相对路径: ../../assets/js/x.js → 基于 request_path 所在目录解析
    - 无前导斜杠: assets/css/x.css → 基于首页目录（APP_ROOT）解析

    返回 None 表示无法解析或文件不存在。
    """
    if not url:
        return None

    # 去掉查询参数和锚点
    path_part = url.split('?')[0].split('#')[0]
    if not path_part:
        return None

    if path_part.startswith('/'):
        # 绝对路径
        fs_path = app_root / path_part.lstrip('/')
    else:
        # 相对路径：基于 request_path 所在的 HTML 目录解析
        if request_path:
            base_dir = (app_root / request_path.lstrip('/')).parent
        else:
            base_dir = app_root
        fs_path = (base_dir / path_part).resolve()

    # 安全检查：确保解析后的路径在 APP_ROOT 内
    try:
        fs_path.relative_to(app_root.resolve())
    except (ValueError, RuntimeError):
        return None

    if fs_path.is_file():
        return fs_path
    return None


def get_asset_version(url: str, app_root: Path, request_path: str = '') -> str:
    """
    返回资源文件的 mtime 版本字符串。

    如果文件存在，返回 mtime 的整数时间戳字符串（如 "1719012345"）。
    如果文件不存在或无法解析，返回空字符串。
    """
    if not _is_local_asset_url(url):
        return ''

    fs_path = resolve_asset_path(url, app_root, request_path)
    if fs_path is None:
        return ''

    cache_key = str(fs_path)
    now = time.monotonic()

    cached = _mtime_cache.get(cache_key)
    if cached is not None:
        version, cached_at = cached
        if now - cached_at < _CACHE_TTL_SECONDS:
            return version

    # 缓存未命中或已过期，重新 stat
    try:
        mtime = int(fs_path.stat().st_mtime)
        version = str(mtime)
    except (OSError, ValueError):
        return ''

    _mtime_cache[cache_key] = (version, now)
    return version


def inject_version_into_url(url: str, version: str) -> str:
    """
    在 URL 中注入或替换 ?v= 版本参数。

    保留其他查询参数。如果 version 为空，返回原始 URL。
    """
    if not version:
        return url

    # 分离锚点
    if '#' in url:
        url_part, fragment = url.split('#', 1)
        fragment = '#' + fragment
    else:
        url_part = url
        fragment = ''

    # 分离查询参数
    if '?' in url_part:
        base, query = url_part.split('?', 1)
        params = parse_qsl(query, keep_blank_values=True)
        # 移除已有的 v 参数
        params = [(k, v) for k, v in params if k != 'v']
        params.append(('v', version))
    else:
        base = url_part
        params = [('v', version)]

    return base + '?' + urlencode(params) + fragment


# ── HTML / JS 版本注入 ────────────────────────────────

import re

# 匹配 HTML 中的 href="..." 和 src="..." 属性
# 捕获组 1: 属性名 (href 或 src)，组 2: 引号，组 3: URL
_HTML_ASSET_PATTERN = re.compile(
    r'\b(href|src)\s*=\s*(["\'])([^"\']+)\2',
    re.IGNORECASE
)

# 匹配 JS 中单引号或双引号包裹的本地资源路径
# 如 '/assets/css/nav-component.css' 或 "/assets/js/chatbot.js?v=xxx"
_JS_ASSET_PATTERN = re.compile(
    r'''(["'])((?:/assets/|/cdn_assets/)[^"'?\s]+\.(?:css|js|html|png|jpg|jpeg|webp|gif|svg|woff2?|ttf|eot))(?:\?[^"'?]*)?\1''',
    re.IGNORECASE
)


def inject_html_asset_versions(html_body: str, app_root: Path, request_path: str = '') -> str:
    """
    遍历 HTML 中所有 href/src 属性，为本地资源 URL 注入 mtime 版本号。

    如果 URL 已有 ?v=xxx，会被替换为新的 mtime 版本。
    """
    def replacer(match: re.Match) -> str:
        attr_name = match.group(1)
        quote = match.group(2)
        url = match.group(3)

        if not _is_local_asset_url(url):
            return match.group(0)

        # 只处理指向 /assets/ 或 /cdn_assets/ 的路径，以及相对路径中的 assets/cdn_assets
        path_check = url.split('?')[0].split('#')[0]
        if not (path_check.startswith('/assets/') or path_check.startswith('/cdn_assets/')
                or '/assets/' in path_check or '/cdn_assets/' in path_check
                or path_check.startswith('assets/') or path_check.startswith('cdn_assets/')):
            return match.group(0)

        version = get_asset_version(url, app_root, request_path)
        if not version:
            return match.group(0)

        new_url = inject_version_into_url(url, version)
        return f'{attr_name}={quote}{new_url}{quote}'

    return _HTML_ASSET_PATTERN.sub(replacer, html_body)


def inject_js_asset_versions(js_body: str, app_root: Path) -> str:
    """
    遍历 JS 代码中引号包裹的本地资源路径，为它们注入 mtime 版本号。

    处理模式：
    - '/assets/css/x.css' → '/assets/css/x.css?v=1719012345'
    - '/assets/css/x.css?v=old' → '/assets/css/x.css?v=1719012345'
    - '/assets/css/x.css?v=' + VAR → '/assets/css/x.css?v=1719012345'
    """
    def replacer(match: re.Match) -> str:
        quote = match.group(1)
        base_path = match.group(2)

        version = get_asset_version(base_path, app_root)
        if not version:
            return match.group(0)

        new_url = inject_version_into_url(base_path, version)
        return f'{quote}{new_url}{quote}'

    result = _JS_ASSET_PATTERN.sub(replacer, js_body)
    return result
