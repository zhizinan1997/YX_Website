"""媒体分发与远程代理路由模块。

负责 CDN 设置、远程视频代理、白名单校验以及 CDN 资源访问辅助能力。
"""

from pathlib import Path
from urllib.parse import quote, urlparse

from flask import Response, jsonify, redirect, request, send_from_directory, stream_with_context

APP_ROOT = Path(__file__).resolve().parents[2]
_CDN_ASSETS_DIR = APP_ROOT / 'cdn_assets'
_HERO_CONFIG_FILE = APP_ROOT / 'data' / 'hero' / 'hero.json'
_MEDIA_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'
_GET_CONFIG = lambda: {}
_UPDATE_CONFIG = lambda _updates: {}
_IS_SAME_ORIGIN_REQUEST = lambda _req: False
_VALIDATE_SAFE_REMOTE_FETCH_URL = lambda _url: (False, '', '')
_FIRST_FORWARDED_VALUE = lambda raw_value: str(raw_value or '').strip().split(',')[0].strip()
_GET_H2_HOME_CONFIG = lambda: {}
_GET_HERO_CONFIG = lambda *_args, **_kwargs: {}
_SANITIZE_PUBLIC_MEDIA_URL = lambda raw_url, **_kwargs: raw_url or ''
_REQUESTS_SUPPORT = False
_REQUESTS_MODULE = None
_HTTPX_SUPPORT = False
_HTTPX_MODULE = None

CDN_CONNECTIVITY_CHECK_HEADERS = {
    # 使用更接近浏览器的请求特征，避免 CDN/WAF 与自有反爬规则误判请求。
    # 这样连通性探测不会被当成机器人流量。
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/123.0.0.0 Safari/537.36'
    ),
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}


def normalize_cdn_domain(raw_value: str) -> str:
    """将加速域名整理为“协议://主机[:端口]”格式。"""
    value = (raw_value or '').strip()
    if not value:
        return ''

    if value.startswith('//'):
        value = f'https:{value}'
    elif '://' not in value:
        value = f'https://{value}'

    try:
        parsed = urlparse(value)
    except Exception:
        return ''

    if parsed.scheme not in {'http', 'https'}:
        return ''
    if not parsed.netloc:
        return ''

    return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')


def normalize_remote_video_url(raw_url: str) -> str:
    """为白名单校验规范化远程视频 URL。"""
    if not raw_url:
        return ''
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return ''
    if parsed.scheme not in {'http', 'https'}:
        return ''
    if not parsed.netloc:
        return ''
    # 只移除 fragment，保留 query 参数，因为部分 CDN 依赖它们。
    return parsed._replace(fragment='').geturl()


def get_cdn_settings() -> dict:
    """从配置中读取 CDN 加速设置。"""
    config = _GET_CONFIG() or {}
    domain = normalize_cdn_domain(str(config.get('cdn_domain') or ''))
    enabled = bool(config.get('cdn_enabled', False)) and bool(domain)
    return {
        'cdn_enabled': enabled,
        'cdn_domain': domain,
    }


def _collect_remote_urls_from_items(items) -> set:
    allowed = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = normalize_remote_video_url(item.get('url', ''))
        ok = False
        if url:
            ok, _, url = _VALIDATE_SAFE_REMOTE_FETCH_URL(url)
        if url and ok:
            allowed.add(url)
    return allowed


def get_allowed_remote_media_urls() -> set:
    """仅允许代理 H2 首页和首页 Hero 已配置的媒体 URL。"""
    allowed = set()
    h2_config = _GET_H2_HOME_CONFIG() or {}
    hero_config = _GET_HERO_CONFIG(_HERO_CONFIG_FILE, _SANITIZE_PUBLIC_MEDIA_URL) or {}
    allowed.update(_collect_remote_urls_from_items(h2_config.get('items', [])))
    allowed.update(_collect_remote_urls_from_items(hero_config.get('items', [])))
    return allowed



# 路由注册入口。
def register_media_delivery_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
    is_same_origin_request,
    validate_safe_remote_fetch_url,
    first_forwarded_value,
    get_h2_home_config,
    get_hero_config,
    hero_config_file,
    sanitize_public_media_url,
    cdn_assets_dir,
    media_immutable_cache_control,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
):
    """注册 CDN 设置、媒体代理和公开资源分发相关路由。"""
    global _CDN_ASSETS_DIR, _HERO_CONFIG_FILE, _MEDIA_IMMUTABLE_CACHE_CONTROL
    global _GET_CONFIG, _UPDATE_CONFIG, _IS_SAME_ORIGIN_REQUEST, _VALIDATE_SAFE_REMOTE_FETCH_URL
    global _FIRST_FORWARDED_VALUE, _GET_H2_HOME_CONFIG, _GET_HERO_CONFIG, _SANITIZE_PUBLIC_MEDIA_URL
    global _REQUESTS_SUPPORT, _REQUESTS_MODULE, _HTTPX_SUPPORT, _HTTPX_MODULE

    _CDN_ASSETS_DIR = Path(cdn_assets_dir)
    _HERO_CONFIG_FILE = Path(hero_config_file)
    _MEDIA_IMMUTABLE_CACHE_CONTROL = media_immutable_cache_control
    _GET_CONFIG = get_config
    _UPDATE_CONFIG = update_config
    _IS_SAME_ORIGIN_REQUEST = is_same_origin_request
    _VALIDATE_SAFE_REMOTE_FETCH_URL = validate_safe_remote_fetch_url
    _FIRST_FORWARDED_VALUE = first_forwarded_value
    _GET_H2_HOME_CONFIG = get_h2_home_config
    _GET_HERO_CONFIG = get_hero_config
    _SANITIZE_PUBLIC_MEDIA_URL = sanitize_public_media_url
    _REQUESTS_SUPPORT = bool(requests_support and requests_module is not None)
    _REQUESTS_MODULE = requests_module if _REQUESTS_SUPPORT else None
    _HTTPX_SUPPORT = bool(httpx_support and httpx_module is not None)
    _HTTPX_MODULE = httpx_module if _HTTPX_SUPPORT else None

    @app.route('/api/video-proxy')
    def proxy_video():
        """为跨域 CDN 资源提供同源媒体代理。"""
        raw_url = (request.args.get('url') or '').strip()
        target_url = normalize_remote_video_url(raw_url)
        if not target_url:
            return jsonify({'success': False, 'message': '媒体地址不合法'}), 400

        allowed_urls = get_allowed_remote_media_urls()
        if target_url not in allowed_urls:
            return jsonify({'success': False, 'message': '该视频地址未授权代理'}), 403
        ok, reason, safe_target_url = _VALIDATE_SAFE_REMOTE_FETCH_URL(target_url)
        if not ok:
            return jsonify({'success': False, 'message': reason or '媒体地址不安全'}), 400

        if not _REQUESTS_SUPPORT:
            return jsonify({'success': False, 'message': '服务器缺少 requests 依赖，无法代理媒体'}), 500

        upstream_headers = {}
        range_header = request.headers.get('Range')
        if range_header:
            upstream_headers['Range'] = range_header

        try:
            upstream = _REQUESTS_MODULE.get(
                safe_target_url,
                headers=upstream_headers,
                stream=True,
                timeout=(8, 120),
                allow_redirects=False,
            )
        except Exception:
            return jsonify({'success': False, 'message': '代理媒体失败：无法连接上游服务'}), 502

        passthrough_headers = [
            'Content-Type',
            'Content-Length',
            'Content-Range',
            'Accept-Ranges',
            'ETag',
            'Last-Modified',
            'Cache-Control',
        ]
        response_headers = {}
        for key in passthrough_headers:
            value = upstream.headers.get(key)
            if value:
                response_headers[key] = value
        if not response_headers.get('Cache-Control'):
            response_headers['Cache-Control'] = 'public, max-age=86400'
        response_headers['Access-Control-Allow-Origin'] = '*'

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            status=upstream.status_code,
            headers=response_headers,
        )

    @app.route('/api/cdn/settings', methods=['GET'])
    @login_required
    def get_cdn_settings_api():
        """获取 CDN 加速设置。"""
        return jsonify(get_cdn_settings())

    @app.route('/api/cdn/settings', methods=['POST'])
    @login_required
    def update_cdn_settings_api():
        """更新 CDN 加速设置。"""
        if not _IS_SAME_ORIGIN_REQUEST(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

        data = request.json or {}
        enabled = bool(data.get('cdn_enabled', False))
        domain = normalize_cdn_domain(str(data.get('cdn_domain') or ''))

        if enabled and not domain:
            return jsonify({'success': False, 'message': '启用加速时必须填写有效 CDN 域名'}), 400
        if domain:
            ok, reason, _ = _VALIDATE_SAFE_REMOTE_FETCH_URL(f'{domain}/')
            if not ok:
                return jsonify({'success': False, 'message': reason or 'CDN 域名不安全'}), 400

        _UPDATE_CONFIG({
            'cdn_enabled': enabled,
            'cdn_domain': domain,
        })
        return jsonify({'success': True, 'message': 'CDN 设置已保存', 'settings': get_cdn_settings()})

    @app.route('/api/cdn/test', methods=['POST'])
    @login_required
    def test_cdn_settings_api():
        """测试 CDN 域名连通性。"""
        if not _IS_SAME_ORIGIN_REQUEST(request):
            return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

        data = request.json or {}
        settings = get_cdn_settings()
        domain = normalize_cdn_domain(str(data.get('cdn_domain') or settings.get('cdn_domain') or ''))
        asset_path = str(data.get('asset_path') or '/cdn_assets/images/common/f1dcc87cdcca.png').strip()
        if not asset_path.startswith('/'):
            asset_path = f'/{asset_path}'
        if not asset_path.startswith('/cdn_assets/'):
            asset_path = '/cdn_assets/images/common/f1dcc87cdcca.png'

        if not domain:
            return jsonify({'success': False, 'message': '请先填写有效 CDN 域名'}), 400

        url = f'{domain}{asset_path}'
        ok, reason, safe_url = _VALIDATE_SAFE_REMOTE_FETCH_URL(url)
        if not ok:
            return jsonify({'success': False, 'message': reason or 'CDN 检测地址不安全'}), 400

        result = {
            'url': safe_url,
            'head_status': None,
            'get_status': None,
            'reachable': False,
            'error': '',
        }

        try:
            if _REQUESTS_SUPPORT:
                try:
                    head_res = _REQUESTS_MODULE.head(
                        safe_url,
                        headers=CDN_CONNECTIVITY_CHECK_HEADERS,
                        allow_redirects=False,
                        timeout=(4, 8),
                    )
                    result['head_status'] = int(head_res.status_code)
                    if 200 <= head_res.status_code < 400:
                        result['reachable'] = True
                except Exception:
                    pass

                try:
                    get_res = _REQUESTS_MODULE.get(
                        safe_url,
                        headers={
                            **CDN_CONNECTIVITY_CHECK_HEADERS,
                            'Range': 'bytes=0-2047',
                        },
                        stream=True,
                        timeout=(4, 10),
                        allow_redirects=False,
                    )
                    result['get_status'] = int(get_res.status_code)
                    if get_res.status_code in (200, 206):
                        result['reachable'] = True
                except Exception as e:
                    if not result.get('error'):
                        result['error'] = str(e)
            elif _HTTPX_SUPPORT:
                try:
                    head_res = _HTTPX_MODULE.head(
                        safe_url,
                        headers=CDN_CONNECTIVITY_CHECK_HEADERS,
                        follow_redirects=False,
                        timeout=8.0,
                    )
                    result['head_status'] = int(head_res.status_code)
                    if 200 <= head_res.status_code < 400:
                        result['reachable'] = True
                except Exception:
                    pass

                try:
                    get_res = _HTTPX_MODULE.get(
                        safe_url,
                        headers={
                            **CDN_CONNECTIVITY_CHECK_HEADERS,
                            'Range': 'bytes=0-2047',
                        },
                        follow_redirects=False,
                        timeout=10.0,
                    )
                    result['get_status'] = int(get_res.status_code)
                    if get_res.status_code in (200, 206):
                        result['reachable'] = True
                except Exception as e:
                    if not result.get('error'):
                        result['error'] = str(e)
            else:
                result['error'] = '缺少 HTTP 客户端依赖（requests/httpx）'
        except Exception as e:
            result['error'] = str(e)

        message = 'CDN 可访问' if result['reachable'] else 'CDN 连通性失败'
        return jsonify({'success': result['reachable'], 'message': message, 'result': result})

    @app.route('/api/cdn/switch-header', methods=['GET', 'HEAD'])
    def get_cdn_switch_header():
        """网关 `auth_request` 使用的内部接口，返回 CDN 开关状态的轻量响应头。"""
        settings = get_cdn_settings()
        response = Response(status=204)
        response.headers['X-CDN-Enabled'] = '1' if settings.get('cdn_enabled') else '0'
        response.headers['X-CDN-Domain'] = settings.get('cdn_domain', '')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/cdn_assets/<path:asset_path>', methods=['GET', 'HEAD'])
    def serve_cdn_asset_with_redirect(asset_path):
        """主站 CDN 资源入口；开启 CDN 时重定向到 CDN 域名，未开启时回源本地文件。"""
        relative_path = str(asset_path or '').lstrip('/')
        if not relative_path:
            return jsonify({'error': '文件路径不能为空'}), 400

        settings = get_cdn_settings()
        cdn_domain = str(settings.get('cdn_domain') or '').strip()
        cdn_enabled = bool(settings.get('cdn_enabled', False)) and bool(cdn_domain)
        cdn_entry_request = str(request.headers.get('X-YX-CDN-Entry') or '').strip() == '1'

        if cdn_enabled and not cdn_entry_request:
            forwarded_host = _FIRST_FORWARDED_VALUE(request.headers.get('X-Forwarded-Host', ''))
            current_host = (forwarded_host or request.host or '').strip().lower()
            cdn_host = (urlparse(cdn_domain).netloc or '').strip().lower()

            # 避免同主机重定向造成循环。
            if cdn_host and current_host != cdn_host:
                target = f"{cdn_domain}/cdn_assets/{quote(relative_path, safe='/')}"
                raw_qs = (request.query_string or b'').decode('utf-8', errors='ignore').strip()
                if raw_qs:
                    target = f'{target}?{raw_qs}'
                response = redirect(target, code=302)
                # 后台切换 CDN 开关时，避免命中陈旧缓存。
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                response.headers['Vary'] = 'Host'
                return response

        response = send_from_directory(str(_CDN_ASSETS_DIR), relative_path)
        response.headers['Cache-Control'] = _MEDIA_IMMUTABLE_CACHE_CONTROL
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
