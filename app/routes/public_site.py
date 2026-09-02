"""
公开站点路由模块。

本模块提供公开页面的渲染和访问控制功能，包括：
1. 页面渲染
2. SEO优化
3. 静态资源访问
4. 搜索功能

主要功能：
1. 页面渲染
   - HTML页面动态渲染
   - 静态文件服务
   - 目录索引生成
   - MIME类型适配

2. SEO优化
   - Meta标签注入
   - 结构化数据生成
   - robots.txt配置
   - 面包屑导航
   - 描述信息优化

3. 安全控制
   - 私有路径保护
   - 反爬虫机制
   - CSP策略设置
   - Referrer策略

4. 静态资源访问
   - 精确文件映射
   - 目录访问控制
   - 缓存策略

5. 搜索功能
   - 搜索索引重建
   - 搜索结果返回

6. 站点统计
   - 访问日志
   - 用户行为追踪

作者：元芯传感技术团队
"""

from __future__ import annotations

import html
import json
import posixpath
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from flask import Response, jsonify, redirect, request, send_file, send_from_directory

from app.asset_versioning import inject_html_asset_versions, inject_js_asset_versions
from app.public_urls import (
    LEGACY_PUBLIC_REDIRECTS,
    canonicalize_public_path,
    canonicalize_public_url,
    is_legacy_public_path,
)
from app.request_security import get_trusted_forwarded_host_proto
from app.text_encoding import repair_known_mojibake

BEIJING_TZ = timezone(timedelta(hours=8))


class PublicSiteTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'nav', 'header', 'footer', 'noscript'}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text and len(text) > 1:
                self.text_parts.append(text)

    def get_text(self):
        return ' '.join(self.text_parts)


def extract_public_text_from_html(html_content):
    try:
        parser = PublicSiteTextExtractor()
        parser.feed(html_content)
        return parser.get_text()
    except Exception:
        return ''


def extract_public_title_from_html(html_content):
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()
    h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content, re.IGNORECASE)
    if h1_match:
        return h1_match.group(1).strip()
    return ''


def strip_public_html_markup(raw_html: str) -> str:
    text = html.unescape(str(raw_html or '').replace('\u00a0', ' '))
    text = re.sub(r'(?is)<(script|style|svg|noscript).*?>.*?</\1>', ' ', text)
    text = re.sub(r'(?is)<br\s*/?>', ' ', text)
    text = re.sub(r'(?is)<[^>]+>', ' ', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def extract_public_heading_from_html(html_content):
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content or '', re.IGNORECASE | re.DOTALL)
    if h1_match:
        return strip_public_html_markup(h1_match.group(1))
    return ''


def canonical_public_search_url(rel_path: str) -> str:
    normalized = str(rel_path or '').replace('\\', '/').lstrip('/')
    if not normalized or normalized == 'index.html':
        return '/'
    return canonicalize_public_path('/' + normalized)


def classify_public_search_page(url: str) -> str:
    path = str(url or '').lower()
    if path in {'/', '/index.html'}:
        return 'home'
    if '/pages/contact/' in path:
        return 'contact'
    if '/pages/customization/' in path or path in {
        '/pages/solutions/custom-solutions.html',
        '/pages/biosensing/custom_bio_sensor_chip.html',
        '/pages/research/micro-nano.html',
        '/pages/about/micro-nano.html',
    }:
        return 'custom'
    if path in {
        '/pages/gassensing/all-products.html',
        '/pages/biosensing/',
        '/pages/biosensing/index.html',
        '/pages/solutions/solutions-index.html',
    }:
        return 'overview'
    if '/pages/solutions/' in path or '/pages/gassensing/cases/' in path:
        return 'solution'
    if '/pages/gassensing/' in path or '/pages/biosensing/' in path or '/pages/measurement/' in path:
        return 'product'
    if '/pages/news/' in path:
        return 'news'
    if '/pages/careers/' in path:
        return 'career'
    if '/pages/about/' in path or '/pages/honors/' in path:
        return 'about'
    if '/pages/research/' in path or '/pages/services/' in path:
        return 'service'
    return 'other'


def infer_public_search_business_line(url: str, title: str = '', content: str = '') -> str:
    combined = f'{url} {title} {content[:500]}'.lower()
    if '/pages/biosensing/' in combined or '生物' in combined or 'bio' in combined:
        return 'biosensing'
    if '/pages/gassensing/' in combined or '/pages/measurement/' in combined or '氢' in combined or '气体' in combined or 'gas' in combined:
        return 'gassensing'
    if '/pages/solutions/' in combined or '方案' in combined:
        return 'solutions'
    if '/pages/customization/' in combined or '定制' in combined:
        return 'customization'
    return ''


def build_public_search_keywords(title: str, heading: str, content: str, url: str) -> list[str]:
    combined = f'{title} {heading} {content[:1200]} {url}'.lower()
    keywords = []
    seen = set()
    for term in PUBLIC_SEARCH_KEY_TERMS:
        term_lower = term.lower()
        if term_lower in combined and term_lower not in seen:
            seen.add(term_lower)
            keywords.append(term_lower)
    for token in re.findall(r'[A-Za-z0-9][A-Za-z0-9_.-]{1,}', combined):
        key = token.lower()
        if key not in seen:
            seen.add(key)
            keywords.append(key)
    return keywords[:30]


def build_public_search_page(root: Path, file_path: Path, html_content: str, rel_path: str) -> dict:
    title = extract_public_title_from_html(html_content)
    heading = extract_public_heading_from_html(html_content)
    text = extract_public_text_from_html(html_content)
    url = canonical_public_search_url(rel_path)
    page_type = classify_public_search_page(url)
    return {
        'url': url,
        'title': title or heading or Path(rel_path).stem or '首页',
        'h1': heading,
        'content': text[:5000],
        'summary': text[:260],
        'path': str(rel_path).replace('\\', '/'),
        'page_type': page_type,
        'business_line': infer_public_search_business_line(url, title, text),
        'keywords': build_public_search_keywords(title, heading, text, url),
        'file_exists': bool(file_path and Path(file_path).is_file()),
    }


def build_public_search_index(root: Path):
    root = Path(root)
    pages_dir = root / 'pages'
    index_file = root / 'index.html'
    pages = []

    if index_file.exists():
        try:
            content = index_file.read_text(encoding='utf-8')
            pages.append(build_public_search_page(root, index_file, content, 'index.html'))
        except Exception:
            pass

    if pages_dir.exists():
        for html_file in pages_dir.rglob('*.html'):
            if 'admin' in str(html_file).lower():
                continue
            try:
                content = html_file.read_text(encoding='utf-8')
                rel_path = html_file.relative_to(root)
                pages.append(build_public_search_page(root, html_file, content, str(rel_path)))
            except Exception as exc:
                print(f'Error indexing {html_file}: {exc}')
                continue

    return pages


PUBLIC_SEARCH_KEY_TERMS = (
    '定制化', '定制服务', '定制方案', '特殊开发', '开发需求', '特殊需求', '非标',
    '客制化', '微纳加工', '工艺定制', '芯片定制', '器件定制', '封装测试',
    '定制', '开发', '需求', '产品', '型号', '参数', '选型', '方案', '解决方案',
    '应用', '行业', '场景', '部署', '工况', '联系', '电话', '邮箱', '售后',
    '报价', '价格', '采购', '打样', '样机', '传感器', '传感', '检测', '检测仪',
    '模块', '报警器', '芯片', '器件', '气体', '氢气', '氧气', '氮气', '甲烷',
    '生物', '碳基', '半导体', 'MEMS', 'OEM',
)

PUBLIC_SEARCH_QUERY_EXPANSIONS = {
    'solution': {
        'triggers': ('方案', '解决方案', '行业', '应用场景'),
        'terms': ('解决方案', '行业', '氢能', '电力', '环境', '储能', '检漏', '定制化'),
    },
    'product': {
        'triggers': ('产品', '型号', '传感器', '模块', '检测仪', '报警器', '选型'),
        'terms': ('产品', '传感器', '模块', '检测仪', '报警器', '参数', '量程'),
    },
    'custom': {
        'triggers': ('定制', '定制化', '特殊开发', '开发需求', '非标', '微纳加工'),
        'terms': ('定制服务', '定制化', '特殊开发', '微纳加工', '芯片定制', '封装测试'),
    },
    'contact': {
        'triggers': ('联系', '电话', '邮箱', '地址', '售后', '客服', '报价', '价格', '采购'),
        'terms': ('联系', '电话', '邮箱', '留言', '报价', '售后'),
    },
}

PUBLIC_SEARCH_DEFAULT_EXCLUDED_TYPES = {'news', 'career', 'about'}
PUBLIC_SEARCH_EXPLICIT_TYPE_TERMS = {
    'news': ('新闻', '资讯', '动态', '文章'),
    'career': ('招聘', '职位', '工作', '加入'),
    'about': ('公司介绍', '关于我们', '荣誉', '发展历程', '企业文化'),
}
PUBLIC_SEARCH_PAGE_TYPE_WEIGHT = {
    'product': 90,
    'custom': 90,
    'solution': 82,
    'overview': 70,
    'contact': 65,
    'service': 45,
    'home': 25,
    'news': 5,
    'career': 0,
    'about': 0,
    'other': 0,
}


def tokenize_public_search_query(query):
    query_lower = str(query or '').strip().lower()
    if not query_lower:
        return []
    tokens = []
    seen = set()

    def add_token(token):
        token = str(token or '').strip().lower()
        if len(token) < 2 or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    for word in re.split(r'[\s,，。；;、/\\|]+', query_lower):
        add_token(word)
    for term in PUBLIC_SEARCH_KEY_TERMS:
        term_lower = term.lower()
        if term_lower in query_lower:
            add_token(term_lower)
    for expansion in PUBLIC_SEARCH_QUERY_EXPANSIONS.values():
        if any(trigger.lower() in query_lower for trigger in expansion['triggers']):
            for term in expansion['terms']:
                add_token(term)
    return tokens


def public_search_allows_page_type(query_lower: str, page_type: str) -> bool:
    if page_type not in PUBLIC_SEARCH_DEFAULT_EXCLUDED_TYPES:
        return True
    explicit_terms = PUBLIC_SEARCH_EXPLICIT_TYPE_TERMS.get(page_type, ())
    return any(term.lower() in query_lower for term in explicit_terms)


def build_public_search_snippet(content: str, terms: list[str]) -> str:
    content = str(content or '')
    content_lower = content.lower()
    for term in terms:
        term = str(term or '').lower()
        if len(term) < 2:
            continue
        idx = content_lower.find(term)
        if idx == -1:
            continue
        start = max(0, idx - 50)
        end = min(len(content), idx + len(term) + 120)
        snippet = content[start:end]
        if start > 0:
            snippet = '...' + snippet
        if end < len(content):
            snippet += '...'
        return snippet
    return (content[:180] + '...') if len(content) > 180 else content


def search_public_pages(query, pages, limit=20):
    if not query:
        return []

    query_lower = str(query or '').strip().lower()
    if not query_lower:
        return []

    query_terms = tokenize_public_search_query(query_lower)
    results = []
    for page in pages or []:
        if not page.get('file_exists', True):
            continue
        score = 0
        snippet = ''
        title = page.get('title', '')
        heading = page.get('h1', '')
        content = page.get('content', '')
        keywords = page.get('keywords') or []
        page_type = page.get('page_type') or classify_public_search_page(page.get('url', ''))
        title_lower = title.lower()
        heading_lower = heading.lower()
        content_lower = content.lower()
        keyword_text = ' '.join([str(item) for item in keywords]).lower()

        if not public_search_allows_page_type(query_lower, page_type):
            continue

        if query_lower in title_lower:
            score += 100
            snippet = title
        if query_lower in heading_lower:
            score += 80
            snippet = heading or snippet

        if query_lower in content_lower:
            score += 50
            snippet = build_public_search_snippet(content, [query_lower])

        for word in query_terms:
            if word in title_lower:
                score += 36
                if not snippet:
                    snippet = title
            if word in heading_lower:
                score += 30
                if not snippet:
                    snippet = heading
            if word in keyword_text:
                score += 18
            if word in content_lower:
                score += 10
                if not snippet:
                    snippet = build_public_search_snippet(content, [word])

        score += PUBLIC_SEARCH_PAGE_TYPE_WEIGHT.get(page_type, 0)

        if score > 0:
            results.append({
                'url': page.get('url', ''),
                'title': title,
                'h1': heading,
                'snippet': snippet or page.get('summary') or build_public_search_snippet(content, query_terms),
                'score': score,
                'page_type': page_type,
                'business_line': page.get('business_line', ''),
                'keywords': keywords,
            })

    results.sort(key=lambda item: item['score'], reverse=True)
    return results[:limit]

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)



# 路由注册入口。
def register_public_site_routes(
    app,
    *,
    login_required,
    app_root,
    cdn_assets_dir,
    site_favicon_relative_path,
    public_static_exact_files,
    public_static_root_dirs,
    private_static_prefixes,
    get_public_base_url,
    first_forwarded_value,
    is_anti_crawl_strict_private_path,
    strict_anti_crawl_headers,
    public_html_content_security_policy,
    public_referrer_policy,
    chem_subscript_script_src,
    site_analytics_script_src,
    site_brand_name,
    site_company_name,
    site_display_name,
    site_default_description,
    site_logo_path,
    seo_default_robots,
    seo_section_descriptions,
    seo_breadcrumb_labels,
    seo_breadcrumb_targets,
    get_gassensing_products_with_settings=lambda: [],
    get_biosensing_products_with_settings_data=lambda: [],
    build_hero_bootstrap_payload=None,
    get_image_asset=lambda _url, _owner_page='': None,
    get_indexable_images_for_page=lambda _owner_page: [],
):
    """注册公开站点的 SEO、搜索与静态资源路由。"""
    root = Path(app_root)
    favicon_file = Path(cdn_assets_dir) / Path(site_favicon_relative_path)

    search_index = {
        'pages': [],
        'last_updated': 0.0,
    }
    search_lock = threading.Lock()

    legacy_public_redirects = dict(LEGACY_PUBLIC_REDIRECTS)

    def product_path_from_item(item: dict) -> str:
        product_id = str((item or {}).get('id') or '').strip()
        if not product_id:
            return ''
        if product_id.startswith('../biosensing/'):
            return f'/pages/biosensing/{product_id.rsplit("/", 1)[-1]}.html'
        if product_id.startswith('../customization/'):
            return f'/pages/customization/{product_id.rsplit("/", 1)[-1]}.html'
        return f'/pages/gassensing/{product_id}.html'

    def get_product_for_path(path_value: str) -> dict:
        target = str(path_value or '').strip()
        try:
            products = list(get_gassensing_products_with_settings() or [])
            products.extend(get_biosensing_products_with_settings_data() or [])
        except Exception:
            return {}
        for item in products:
            if isinstance(item, dict) and product_path_from_item(item) == target:
                return item
        return {}

    def blocked_disabled_promotion_link_response():
        mark = str(request.args.get('utm_id') or '').strip()
        if not mark:
            return None
        try:
            from app.routes.promotion_links import load_promotion_links, normalize_promotion_mark

            safe_mark = normalize_promotion_mark(mark)
            if not safe_mark:
                return None
            for item in load_promotion_links():
                if normalize_promotion_mark(item.get('promotion_mark')) != safe_mark:
                    continue
                if item.get('archived_at') or not bool(item.get('enabled', True)):
                    return Response(
                        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<title>推广链接已停用</title></head>'
                        '<body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;'
                        'display:flex;min-height:100vh;align-items:center;justify-content:center;'
                        'margin:0;background:#f8fafc;color:#0f172a;">'
                        '<main style="max-width:520px;padding:28px;background:#fff;border:1px solid #e2e8f0;'
                        'border-radius:14px;box-shadow:0 20px 48px rgba(15,23,42,.12);">'
                        '<h1 style="font-size:22px;margin:0 0 12px;">推广链接已停用</h1>'
                        '<p style="font-size:15px;line-height:1.8;margin:0;color:#475569;">'
                        '该推广链接已被管理员停用或隐藏，请返回官网或联系工作人员获取新的访问入口。'
                        '</p></main></body></html>',
                        status=410,
                        mimetype='text/html',
                    )
                return None
        except Exception:
            return None
        return None

    def normalize_public_static_path(raw_path: str) -> str:
        candidate = posixpath.normpath('/' + str(raw_path or '').replace('\\', '/')).lstrip('/')
        if not candidate or candidate in {'.', '/'}:
            return ''
        parts = [part for part in candidate.split('/') if part]
        if not parts:
            return ''
        if any(part in {'.', '..'} or part.startswith('.') for part in parts):
            return ''
        top = parts[0]
        if candidate in public_static_exact_files:
            return candidate
        if top in public_static_root_dirs:
            return candidate
        if any(candidate == prefix or candidate.startswith(prefix + '/') for prefix in private_static_prefixes):
            return ''
        return ''

    def build_request_query_suffix() -> str:
        raw_query = request.query_string or b''
        if not raw_query:
            return ''
        return '?' + raw_query.decode('utf-8', errors='ignore')

    def legacy_redirect_target(path_value: str) -> str:
        target = legacy_public_redirects.get(str(path_value or '').strip(), '')
        if not target:
            return ''
        target_path, fragment_mark, fragment = target.partition('#')
        query_suffix = build_request_query_suffix()
        if fragment_mark:
            return f'{target_path}{query_suffix}#{fragment}'
        return f'{target_path}{query_suffix}'

    def is_legacy_redirect_source(path_value: str) -> bool:
        return is_legacy_public_path(path_value)

    @app.before_request
    def redirect_alternate_public_host():
        """将生产裸域名永久收敛到 PUBLIC_BASE_URL 指定的 www 主域名。"""
        public_base_url = str(get_public_base_url() or '').strip()
        if not public_base_url:
            return None
        try:
            parsed_base = urlparse(public_base_url)
        except Exception:
            return None

        canonical_host = str(parsed_base.hostname or '').strip().lower()
        if not canonical_host.startswith('www.') or not parsed_base.scheme or not parsed_base.netloc:
            return None
        alternate_host = canonical_host[4:]

        forwarded_host, _forwarded_proto = get_trusted_forwarded_host_proto(request, default=False)
        request_host = str(forwarded_host or request.host or '').strip().lower().split(':', 1)[0]
        if request_host != alternate_host:
            return None

        path_and_query = request.full_path or request.path or '/'
        if path_and_query.endswith('?'):
            path_and_query = path_and_query[:-1]
        target = f'{parsed_base.scheme}://{parsed_base.netloc}{path_and_query}'
        status_code = 301 if request.method in {'GET', 'HEAD'} else 308
        response = redirect(target, code=status_code)
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    def absolute_public_url(path_or_url: str, *, base_url: str = '', page_url: str = '') -> str:
        value = str(path_or_url or '').strip()
        if not value:
            return ''
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
            return value
        if value.startswith('//'):
            anchor = base_url or page_url or 'https://localhost'
            parsed = absolute_public_base_url(anchor)
            scheme = parsed[0].split('://', 1)[0] if '://' in parsed[0] else 'https'
            return f'{scheme}:{value}'
        if value.startswith('/'):
            if not base_url and page_url:
                if '://' in page_url:
                    base_url = page_url.split('/', 3)[:3]
                    base_url = '/'.join(base_url)
            return f'{base_url.rstrip("/")}{value}' if base_url else value
        anchor = page_url or base_url or ''
        return urljoin(anchor + ('/' if anchor and not anchor.endswith('/') else ''), value)

    def normalize_public_html_links(html_body: str) -> str:
        """Rewrite internal links that resolve through public redirects."""
        request_path = canonical_public_path_for_request(request.path or '') or (request.path or '/')

        def normalize_href(raw_url: str) -> str:
            direct = canonicalize_public_url(raw_url)
            if direct != raw_url:
                return direct
            parsed = urlparse(str(raw_url or '').strip())
            if (
                not parsed.path
                or parsed.scheme
                or parsed.netloc
                or str(raw_url or '').startswith(('#', '//'))
            ):
                return raw_url
            resolved = urljoin(request_path, raw_url)
            normalized = canonicalize_public_url(resolved)
            return normalized if normalized != resolved else raw_url

        def replace_anchor(match):
            tag = match.group(0)
            return re.sub(
                r'(?is)(\bhref\s*=\s*)(["\'])(.*?)\2',
                lambda href_match: (
                    f'{href_match.group(1)}{href_match.group(2)}'
                    f'{normalize_href(href_match.group(3))}{href_match.group(2)}'
                ),
                tag,
            )

        return re.sub(r'(?is)<a\b[^>]*>', replace_anchor, html_body or '')

    def canonical_public_path_for_request(raw_path: str) -> str:
        normalized = normalize_public_static_path((raw_path or '').lstrip('/'))
        if not normalized:
            return ''

        exact_path = root / normalized
        html_path = root / f'{normalized}.html'

        if normalized in {'index', 'index.html'}:
            return '/'
        if normalized.endswith('/index.html'):
            return '/' + normalized[:-10].rstrip('/') + '/'
        if normalized.endswith('/index') and html_path.is_file():
            return '/' + normalized[:-6].rstrip('/') + '/'
        if exact_path.is_dir() and (exact_path / 'index.html').is_file():
            return '/' + normalized.rstrip('/') + '/'
        if exact_path.is_file():
            return '/' + normalized
        if html_path.is_file():
            return '/' + normalized + '.html'
        return ''

    def extract_html_tag_attributes(fragment: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for match in re.finditer(r'([a-zA-Z_:][\w:.-]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s"\'>/]+))', fragment or ''):
            name = str(match.group(1) or '').strip().lower()
            value = match.group(3) or match.group(4) or match.group(5) or ''
            if name:
                attrs[name] = html.unescape(value.strip())
        return attrs

    def strip_html_markup(raw_html: str) -> str:
        return strip_public_html_markup(raw_html)

    def extract_html_title(html_body: str) -> str:
        match = re.search(r'(?is)<title\b[^>]*>(.*?)</title>', html_body or '')
        return strip_html_markup(match.group(1) if match else '')

    def title_override_for_public_path(path_value: str) -> str:
        path_text = str(path_value or '').strip() or '/'
        overrides = {
            '/pages/careers/job.aspx.html': '在线招聘列表 - 元芯传感',
        }
        product = get_product_for_path(path_text)
        if product:
            custom_title = str(product.get('seoTitle') or '').strip()
            if custom_title:
                return custom_title
        return overrides.get(path_text, '')

    def robots_override_for_public_path(path_value: str) -> str:
        path_text = str(path_value or '').strip()
        product = get_product_for_path(path_text)
        if product and product.get('indexable') is False:
            return 'noindex,follow,max-image-preview:large'
        return ''

    def should_exclude_from_public_sitemap(path_value: str) -> bool:
        path_text = str(path_value or '').strip()
        product = get_product_for_path(path_text)
        return bool(product and product.get('indexable') is False)

    def replace_html_title(html_body: str, title_text: str) -> str:
        clean_title = str(title_text or '').strip()
        if not clean_title:
            return html_body
        escaped_title = html.escape(clean_title, quote=False)
        body = str(html_body or '')
        if re.search(r'(?is)<title\b[^>]*>.*?</title>', body):
            return re.sub(
                r'(?is)(<title\b[^>]*>).*?(</title>)',
                lambda match: f'{match.group(1)}{escaped_title}{match.group(2)}',
                body,
                count=1,
            )
        head_match = re.search(r'(?is)<head\b[^>]*>', body)
        if head_match:
            insert_pos = head_match.end()
            return body[:insert_pos] + f'\n<title>{escaped_title}</title>' + body[insert_pos:]
        return f'<title>{escaped_title}</title>\n{body}'

    def normalize_public_title_markup(html_body: str, path_value: str) -> str:
        override = title_override_for_public_path(path_value)
        if override:
            return replace_html_title(html_body, override)

        title_text = extract_html_title(html_body)
        # 婀栧/鍏冭/绉戞/鏈夐檺 为公司名的乱码形态样本（检测并修复损坏的标题），请勿改成正常汉字
        if re.search(r'[锟\ufffd]|婀栧|鍏冭|绉戞|鏈夐檺', title_text or ''):
            fixed = re.sub(r'\s*-\s*.*$', f' - {site_company_name}', title_text).strip()
            if fixed:
                return replace_html_title(html_body, fixed)
        return html_body

    def truncate_seo_text(text: str, max_length: int = 155) -> str:
        clean = re.sub(r'\s{2,}', ' ', str(text or '').strip())
        if len(clean) <= max_length:
            return clean
        cut = clean[:max_length + 1]
        if ' ' in cut:
            cut = cut.rsplit(' ', 1)[0]
        return cut.rstrip(' ,;:.-')

    def extract_meta_content(html_body: str, *, attr_name: str, attr_value: str) -> str:
        for match in re.finditer(r'(?is)<meta\b[^>]*>', html_body or ''):
            attrs = extract_html_tag_attributes(match.group(0))
            if str(attrs.get(attr_name.lower()) or '').strip().lower() == attr_value.lower():
                return str(attrs.get('content') or '').strip()
        return ''

    def extract_link_href(html_body: str, *, rel_value: str) -> str:
        target = rel_value.lower()
        for match in re.finditer(r'(?is)<link\b[^>]*>', html_body or ''):
            attrs = extract_html_tag_attributes(match.group(0))
            rel_tokens = {token.strip().lower() for token in str(attrs.get('rel') or '').split() if token.strip()}
            if target in rel_tokens:
                return str(attrs.get('href') or '').strip()
        return ''

    def is_invalid_public_canonical_url(value: str) -> bool:
        lowered = str(value or '').strip().lower()
        return (
            '/api/products/code/download' in lowered
            or '/api/bio-products/code/download' in lowered
        )

    def strip_invalid_existing_seo_markup(html_body: str) -> str:
        body = str(html_body or '')
        lowered = body.lower()
        if '/api/products/code/download' not in lowered and '/api/bio-products/code/download' not in lowered:
            return body

        def replace_link_tag(match):
            tag = match.group(0)
            attrs = extract_html_tag_attributes(tag)
            rel_tokens = {token.strip().lower() for token in str(attrs.get('rel') or '').split() if token.strip()}
            if 'canonical' in rel_tokens and is_invalid_public_canonical_url(attrs.get('href', '')):
                return ''
            return tag

        def replace_jsonld_tag(match):
            tag = match.group(0)
            return '' if is_invalid_public_canonical_url(tag) else tag

        body = re.sub(r'(?is)<link\b[^>]*>', replace_link_tag, body)
        body = re.sub(
            r'(?is)<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
            replace_jsonld_tag,
            body,
        )
        return body

    def extract_primary_heading(html_body: str) -> str:
        return extract_public_heading_from_html(html_body)

    def normalize_public_h1_markup(html_body: str, fallback_heading: str) -> str:
        body = str(html_body or '')
        kept_primary = False

        def replace_h1(match):
            nonlocal kept_primary
            attrs = match.group(1) or ''
            inner = match.group(2) or ''
            heading_text = strip_html_markup(inner)
            if not heading_text:
                return ''
            if not kept_primary:
                kept_primary = True
                return match.group(0)
            return f'<h2{attrs}>{inner}</h2>'

        normalized = re.sub(r'(?is)<h1\b([^>]*)>(.*?)</h1>', replace_h1, body)
        if kept_primary:
            return normalized

        heading = strip_brand_suffix(fallback_heading) or site_display_name or site_brand_name
        heading = strip_html_markup(heading)
        if not heading:
            return normalized

        fallback_h1 = f'<h1 class="seo-fallback-heading">{html.escape(heading, quote=False)}</h1>'
        body_match = re.search(r'(?is)<body\b[^>]*>', normalized)
        if body_match:
            insert_pos = body_match.end()
            return normalized[:insert_pos] + '\n' + fallback_h1 + normalized[insert_pos:]
        return fallback_h1 + '\n' + normalized

    def enhance_product_image_markup(html_body: str, path_value: str) -> str:
        product = get_product_for_path(path_value)
        if not product:
            return html_body
        product_name = str(product.get('displayName') or product.get('name') or '').strip()
        configured_alt = str(product.get('imageAlt') or '').strip()
        image_number = 0

        def replace_image(match):
            nonlocal image_number
            tag = match.group(0)
            attrs = extract_html_tag_attributes(tag)
            src = str(attrs.get('src') or '').strip()
            lowered = src.lower()
            if not src or '${' in src or any(token in lowered for token in ('logo', 'favicon', 'qrcode', 'qr-code', 'wechat')):
                return tag
            image_number += 1
            alt = str(attrs.get('alt') or '').strip()
            if not alt or re.fullmatch(r'(?i)(product|产品图|图片|image|产品图\s*\d+)', alt):
                replacement_alt = configured_alt if image_number == 1 and configured_alt else f'{product_name}产品图{image_number}'
                if 'alt=' in tag.lower():
                    tag = re.sub(r'(?i)\balt\s*=\s*(["\']).*?\1', f'alt="{html.escape(replacement_alt, quote=True)}"', tag, count=1)
                else:
                    tag = re.sub(r'\s*/?>$', f' alt="{html.escape(replacement_alt, quote=True)}">', tag)
            if 'decoding=' not in tag.lower():
                tag = re.sub(r'\s*/?>$', ' decoding="async">', tag)
            if image_number == 1:
                if 'fetchpriority=' not in tag.lower():
                    tag = re.sub(r'\s*/?>$', ' fetchpriority="high">', tag)
            elif 'loading=' not in tag.lower():
                tag = re.sub(r'\s*/?>$', ' loading="lazy">', tag)
            return tag

        return re.sub(r'(?is)<img\b[^>]*>', replace_image, html_body or '')

    def enhance_all_image_markup(html_body: str, path_value: str) -> str:
        image_number = 0

        def set_attribute(tag: str, name: str, value: str) -> str:
            escaped = html.escape(str(value), quote=True)
            if re.search(rf'(?i)\b{re.escape(name)}\s*=', tag):
                return re.sub(
                    rf'(?i)\b{re.escape(name)}\s*=\s*(["\']).*?\1',
                    f'{name}="{escaped}"',
                    tag,
                    count=1,
                )
            return re.sub(r'\s*/?>$', f' {name}="{escaped}">', tag)

        def replace_image(match):
            nonlocal image_number
            tag = match.group(0)
            attrs = extract_html_tag_attributes(tag)
            src = str(attrs.get('src') or '').strip()
            if not src or src.startswith(('data:', 'blob:')) or '${' in src:
                return tag
            image_number += 1
            try:
                asset = get_image_asset(src, path_value) or {}
            except Exception:
                asset = {}
            if asset.get('ignored'):
                return tag
            role = str(asset.get('role') or '').strip().lower()
            current_alt = str(attrs.get('alt') or '').strip()
            generic_alt = (
                not current_alt
                or re.fullmatch(r'(?i)(image|img|图片|产品图|新闻图片|news|product|hero)(\s*\d+)?', current_alt)
                or re.search(r'产品图\s*\d+$', current_alt)
            )
            if role in {'decorative', 'logo', 'qrcode'}:
                tag = set_attribute(tag, 'alt', '')
            elif asset.get('alt') and generic_alt:
                tag = set_attribute(tag, 'alt', asset['alt'])
            elif 'alt' not in attrs:
                # Every static image must expose an alt attribute; unreviewed
                # content stays empty until the asset centre approves wording.
                tag = set_attribute(tag, 'alt', '')
            if asset.get('title'):
                tag = set_attribute(tag, 'title', asset['title'])
            if asset.get('width') and 'width' not in attrs:
                tag = set_attribute(tag, 'width', str(asset['width']))
            if asset.get('height') and 'height' not in attrs:
                tag = set_attribute(tag, 'height', str(asset['height']))
            if 'decoding' not in attrs:
                tag = set_attribute(tag, 'decoding', 'async')
            if image_number == 1 and role not in {'decorative', 'logo', 'qrcode'}:
                if 'fetchpriority' not in attrs:
                    tag = set_attribute(tag, 'fetchpriority', 'high')
            elif 'loading' not in attrs:
                tag = set_attribute(tag, 'loading', 'lazy')
            return tag

        return re.sub(r'(?is)<img\b[^>]*>', replace_image, html_body or '')

    def looks_like_noise_description(text: str) -> bool:
        candidate = str(text or '').strip()
        if len(candidate) < 24:
            return True
        lowered = candidate.lower()
        if '版权所有' in candidate or 'ICP备' in candidate or 'copyright' in lowered:
            return True
        if candidate.count('|') >= 2:
            return True
        if '首页' in candidate and '联系我们' in candidate:
            return True
        return False

    def extract_summary_candidates(html_body: str) -> list[str]:
        body = str(html_body or '')
        body = re.sub(r'(?is)<(script|style|svg|noscript|header|nav|footer).*?>.*?</\1>', ' ', body)
        candidates: list[str] = []
        for pattern in (
            r'(?is)<p\b[^>]*>(.*?)</p>',
            r'(?is)<li\b[^>]*>(.*?)</li>',
            r'(?is)<div\b[^>]*class=["\'][^"\']*(?:hero__desc|lead|subtitle|summary|desc)[^"\']*["\'][^>]*>(.*?)</div>',
        ):
            for match in re.finditer(pattern, body):
                text = strip_html_markup(match.group(1))
                if not text or looks_like_noise_description(text):
                    continue
                candidates.append(text)
        return candidates

    def strip_brand_suffix(text: str) -> str:
        value = str(text or '').strip()
        if not value:
            return ''
        for suffix in (
            f' - {site_company_name}',
            f' - {site_brand_name}',
            ' - 科研服务',
            f'_{site_company_name}',
        ):
            if value.endswith(suffix):
                value = value[:-len(suffix)].strip()
        return value

    def default_section_description(path_value: str) -> str:
        path_text = str(path_value or '').strip() or '/'
        if path_text == '/':
            return site_default_description
        for prefix, description in seo_section_descriptions:
            if path_text.startswith(prefix):
                return description
        return site_default_description

    def build_page_description(path_value: str, html_body: str, title_text: str, heading_text: str) -> str:
        product = get_product_for_path(path_value)
        if product:
            product_description = str(product.get('seoDescription') or '').strip()
            if product_description:
                return truncate_seo_text(product_description)
        existing = extract_meta_content(html_body, attr_name='name', attr_value='description')
        if existing:
            return truncate_seo_text(existing)

        if path_value == '/':
            return truncate_seo_text(site_default_description)

        for candidate in extract_summary_candidates(html_body):
            if len(candidate) >= 36:
                return truncate_seo_text(candidate)

        heading = heading_text or strip_brand_suffix(title_text)
        section_default = default_section_description(path_value)
        if heading:
            return truncate_seo_text(f'{heading}。{section_default}')
        return truncate_seo_text(section_default)

    def absolute_public_base_url(fallback: str = '') -> tuple[str, str]:
        explicit = get_public_base_url()
        if explicit:
            host = explicit.split('://', 1)[1].split('/', 1)[0].split(':', 1)[0].strip().lower()
            return explicit, host

        forwarded_host, forwarded_proto = get_trusted_forwarded_host_proto(request, default=False)
        host = (forwarded_host or request.host or '').strip()
        scheme = forwarded_proto if forwarded_proto in {'http', 'https'} else (request.scheme or 'https')
        if not host:
            host = fallback or 'localhost:8000'
        return f'{scheme}://{host}', host.split(':', 1)[0]

    def extract_primary_image_url(html_body: str, *, base_url: str, page_url: str) -> str:
        for match in re.finditer(r'(?is)<img\b[^>]*>', html_body or ''):
            attrs = extract_html_tag_attributes(match.group(0))
            src = str(attrs.get('src') or '').strip()
            if (
                not src or src.startswith(('data:', 'blob:')) or '${' in src
                or src.lower() in {'undefined', 'null'}
            ):
                continue
            return absolute_public_url(src, base_url=base_url, page_url=page_url)
        return absolute_public_url(site_logo_path, base_url=base_url, page_url=page_url)

    def extract_public_image_urls(html_body: str, *, base_url: str, page_url: str, limit: int = 12) -> list[str]:
        images = []
        seen = set()
        for match in re.finditer(r'(?is)<img\b[^>]*>', html_body or ''):
            attrs = extract_html_tag_attributes(match.group(0))
            src = str(attrs.get('src') or '').strip()
            lowered = src.lower()
            if not src or src.startswith(('data:', 'blob:')) or '${' in src:
                continue
            if any(token in lowered for token in ('logo', 'favicon', 'qrcode', 'qr-code', 'wechat')):
                continue
            absolute = absolute_public_url(src, base_url=base_url, page_url=page_url)
            if absolute and absolute not in seen:
                seen.add(absolute)
                images.append(absolute)
            if len(images) >= limit:
                break
        return images

    def extract_article_date(html_body: str) -> str:
        hero_meta = re.search(r'(?is)<div\b[^>]*class=["\'][^"\']*article-hero__meta[^"\']*["\'][^>]*>(.*?)</div>', html_body or '')
        if hero_meta:
            match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', strip_html_markup(hero_meta.group(1)))
            if match:
                return match.group(1)
        match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', html_body or '')
        return match.group(1) if match else ''

    def build_breadcrumb_data(path_value: str, canonical_url: str, page_title: str) -> list[dict]:
        path_text = str(path_value or '').strip() or '/'
        if path_text == '/':
            return []

        entries = [{
            '@type': 'ListItem',
            'position': 1,
            'name': '首页',
            'item': absolute_public_url('/', page_url=canonical_url),
        }]

        segments = [part for part in path_text.strip('/').split('/') if part]
        for index, segment in enumerate(segments, start=2):
            label = seo_breadcrumb_labels.get(segment, '')
            is_last = index == len(segments) + 1
            if is_last:
                label = page_title or label or segment
            if not label:
                continue
            if is_last:
                item_url = canonical_url
            else:
                target_path = str(seo_breadcrumb_targets.get(segment) or '').strip()
                if not target_path:
                    continue
                item_url = absolute_public_url(target_path, page_url=canonical_url)
                if item_url == canonical_url:
                    continue
            entries.append({
                '@type': 'ListItem',
                'position': len(entries) + 1,
                'name': label,
                'item': item_url,
            })

        if len(entries) <= 1:
            return []
        return [{
            '@context': 'https://schema.org',
            '@type': 'BreadcrumbList',
            'itemListElement': entries,
        }]

    def build_structured_data(path_value: str, canonical_url: str, html_body: str, title_text: str, description: str, image_url: str) -> list[dict]:
        page_title = extract_primary_heading(html_body) or strip_brand_suffix(title_text) or site_brand_name
        payloads: list[dict] = []

        if path_value == '/':
            payloads.append({
                '@context': 'https://schema.org',
                '@type': 'Organization',
                'name': site_company_name,
                'alternateName': site_brand_name,
                'url': canonical_url,
                'logo': absolute_public_url(site_logo_path, page_url=canonical_url),
            })
            payloads.append({
                '@context': 'https://schema.org',
                '@type': 'WebSite',
                'name': site_display_name,
                'alternateName': site_brand_name,
                'url': canonical_url,
                'inLanguage': 'zh-CN',
            })
            return payloads

        payloads.extend(build_breadcrumb_data(path_value, canonical_url, page_title))
        try:
            reviewed_images = [
                absolute_public_url(item.get('url', ''), page_url=canonical_url)
                for item in get_indexable_images_for_page(path_value) or []
                if item.get('url')
            ]
        except Exception:
            reviewed_images = []

        product = get_product_for_path(path_value)
        if product:
            base_url, _ = absolute_public_base_url()
            product_images = extract_public_image_urls(
                html_body,
                base_url=base_url,
                page_url=canonical_url,
            )
            configured_image = str(product.get('cardImage') or product.get('image') or '').strip()
            if configured_image:
                configured_image = absolute_public_url(configured_image, base_url=base_url, page_url=canonical_url)
                if configured_image and configured_image not in product_images:
                    product_images.insert(0, configured_image)
            product_data = {
                '@context': 'https://schema.org',
                '@type': 'Product',
                'name': str(product.get('displayName') or product.get('name') or page_title).strip(),
                'description': description,
                'url': canonical_url,
                'image': reviewed_images or product_images or ([image_url] if image_url else []),
                'sku': str(product.get('sku') or product.get('shortName') or product.get('id') or '').strip(),
                'brand': {'@type': 'Brand', 'name': str(product.get('brand') or site_brand_name).strip()},
                'manufacturer': {'@type': 'Organization', 'name': str(product.get('manufacturer') or site_company_name).strip()},
                'category': str(product.get('seoCategory') or product.get('category') or '').strip(),
            }
            properties = []
            for item in product.get('technicalProperties') or []:
                if not isinstance(item, dict) or not item.get('name') or not item.get('value'):
                    continue
                properties.append({
                    '@type': 'PropertyValue',
                    'name': str(item['name']),
                    'value': str(item['value']),
                })
            if properties:
                product_data['additionalProperty'] = properties
            payloads.append(product_data)

        if path_value.startswith('/pages/news/news_show'):
            article_data = {
                '@context': 'https://schema.org',
                '@type': 'Article',
                'headline': page_title,
                'description': description,
                'mainEntityOfPage': canonical_url,
                'url': canonical_url,
                'author': {
                    '@type': 'Organization',
                    'name': site_company_name,
                },
                'publisher': {
                    '@type': 'Organization',
                    'name': site_company_name,
                    'logo': {
                        '@type': 'ImageObject',
                        'url': absolute_public_url(site_logo_path, page_url=canonical_url),
                    },
                },
            }
            publish_date = extract_article_date(html_body)
            if publish_date:
                article_data['datePublished'] = publish_date
                article_data['dateModified'] = publish_date
            article_images = reviewed_images or ([image_url] if image_url else [])
            if article_images:
                article_data['image'] = article_images
            payloads.append(article_data)

        if not product and not path_value.startswith('/pages/news/news_show'):
            page_data = {
                '@context': 'https://schema.org',
                '@type': 'WebPage',
                'name': page_title,
                'description': description,
                'url': canonical_url,
                'inLanguage': 'zh-CN',
            }
            page_images = reviewed_images or ([image_url] if image_url else [])
            if page_images:
                page_data['primaryImageOfPage'] = {'@type': 'ImageObject', 'url': page_images[0]}
                page_data['image'] = page_images
            payloads.append(page_data)

        return payloads

    def append_meta_tag_if_missing(head_tags: list[str], html_body: str, *, attr_name: str, attr_value: str, content: str):
        if extract_meta_content(html_body, attr_name=attr_name, attr_value=attr_value):
            return
        escaped_attr_value = html.escape(attr_value, quote=True)
        escaped_content = html.escape(content or '', quote=True)
        head_tags.append(f'<meta {attr_name}="{escaped_attr_value}" content="{escaped_content}">')

    def append_social_meta_tags(
        head_tags: list[str],
        html_body: str,
        *,
        canonical_path: str,
        canonical_url: str,
        title_text: str,
        description: str,
        image_url: str,
    ):
        page_title = strip_brand_suffix(extract_primary_heading(html_body)) or title_text or site_display_name
        page_type = 'article' if str(canonical_path or '').startswith('/pages/news/news_show') else 'website'
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:type', content=page_type)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:site_name', content=site_display_name)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:locale', content='zh_CN')
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:title', content=page_title)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:description', content=description)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:url', content=canonical_url)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='property', attr_value='og:image', content=image_url)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='name', attr_value='twitter:card', content='summary_large_image')
        append_meta_tag_if_missing(head_tags, html_body, attr_name='name', attr_value='twitter:title', content=page_title)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='name', attr_value='twitter:description', content=description)
        append_meta_tag_if_missing(head_tags, html_body, attr_name='name', attr_value='twitter:image', content=image_url)

    def inject_seo_head_markup(html_body: str) -> str:
        html_body = strip_invalid_existing_seo_markup(html_body)
        base_url, _ = absolute_public_base_url()
        request_canonical_path = canonical_public_path_for_request(request.path or '') or (request.path or '/')
        canonical_path = request_canonical_path
        canonical_url = absolute_public_url(canonical_path, base_url=base_url)
        html_body = normalize_public_title_markup(html_body, request_canonical_path)
        title_text = extract_html_title(html_body)
        html_body = normalize_public_h1_markup(html_body, title_text)
        html_body = enhance_product_image_markup(html_body, request_canonical_path)
        html_body = enhance_all_image_markup(html_body, request_canonical_path)
        heading_text = extract_primary_heading(html_body)
        description = build_page_description(request_canonical_path, html_body, title_text, heading_text)
        product = get_product_for_path(request_canonical_path)
        configured_image = str(product.get('cardImage') or product.get('image') or '').strip() if product else ''
        image_url = (
            absolute_public_url(configured_image, base_url=base_url, page_url=canonical_url)
            if configured_image and '${' not in configured_image
            else extract_primary_image_url(html_body, base_url=base_url, page_url=canonical_url)
        )
        structured_data = build_structured_data(canonical_path, canonical_url, html_body, title_text, description, image_url)

        head_tags: list[str] = []
        if not extract_meta_content(html_body, attr_name='name', attr_value='description'):
            head_tags.append(f'<meta name="description" content="{html.escape(description, quote=True)}">')
        if not extract_link_href(html_body, rel_value='canonical'):
            head_tags.append(f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">')
        if not extract_meta_content(html_body, attr_name='name', attr_value='robots'):
            robots_content = robots_override_for_public_path(request_canonical_path) or seo_default_robots
            head_tags.append(f'<meta name="robots" content="{robots_content}">')
        if not extract_link_href(html_body, rel_value='icon'):
            head_tags.append('<link rel="icon" href="/favicon.png" sizes="32x32" type="image/png">')
        if not extract_link_href(html_body, rel_value='apple-touch-icon'):
            head_tags.append('<link rel="apple-touch-icon" href="/apple-touch-icon.png">')
        if 'seo-fallback-heading' in html_body and 'seo-fallback-heading-style' not in html_body:
            head_tags.append(
                '<style id="seo-fallback-heading-style">.seo-fallback-heading{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0 0 0 0)!important;white-space:nowrap!important;border:0!important;}</style>'
            )
        append_social_meta_tags(
            head_tags,
            html_body,
            canonical_path=canonical_path,
            canonical_url=canonical_url,
            title_text=title_text,
            description=description,
            image_url=image_url,
        )
        if structured_data:
            html_body = re.sub(
                r'(?is)<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
                '',
                html_body,
            )
            payload = json.dumps(structured_data[0] if len(structured_data) == 1 else structured_data, ensure_ascii=False)
            payload = payload.replace('</', '<\\/')
            head_tags.append(f'<script type="application/ld+json">{payload}</script>')

        if not head_tags:
            return html_body

        insertion = '\n'.join(head_tags) + '\n'
        lower_body = html_body.lower()
        head_pos = lower_body.rfind('</head>')
        if head_pos != -1:
            return html_body[:head_pos] + insertion + html_body[head_pos:]
        return insertion + html_body

    def collect_public_html_urls():
        output = []
        seen = set()

        def add_url(path_text: str, file_path: Path, changefreq: str = 'weekly', priority: str = '0.7'):
            url_path = str(path_text or '').strip() or '/'
            if not url_path.startswith('/'):
                url_path = f'/{url_path}'
            if url_path in seen:
                return
            seen.add(url_path)
            try:
                lastmod = datetime.fromtimestamp(file_path.stat().st_mtime, tz=BEIJING_TZ).strftime('%Y-%m-%d')
            except Exception:
                lastmod = now_beijing().strftime('%Y-%m-%d')
            output.append({
                'path': url_path,
                'lastmod': lastmod,
                'changefreq': changefreq,
                'priority': priority,
            })

        index_file = root / 'index.html'
        if index_file.exists():
            add_url('/', index_file, changefreq='daily', priority='1.0')

        pages_root = root / 'pages'
        if pages_root.exists():
            for html_file in sorted(pages_root.rglob('*.html')):
                rel = html_file.relative_to(root).as_posix()
                if rel.startswith('admin/'):
                    continue
                url = f'/{rel}'
                if is_legacy_redirect_source(url):
                    continue
                if should_exclude_from_public_sitemap(url):
                    continue
                if url.endswith('/index.html'):
                    url = url.removesuffix('index.html')
                    if should_exclude_from_public_sitemap(url):
                        continue
                add_url(url, html_file, changefreq='weekly', priority='0.8' if '/news/' in url else '0.7')

        return output

    def public_html_file_for_path(path_value: str) -> Path | None:
        """Resolve a canonical public page URL to its backing HTML file."""
        canonical_path = canonicalize_public_path(str(path_value or '').strip() or '/')
        if canonical_path == '/':
            candidate = root / 'index.html'
        elif canonical_path.endswith('/'):
            candidate = root / canonical_path.lstrip('/') / 'index.html'
        else:
            candidate = root / canonical_path.lstrip('/')
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            return None
        return resolved if resolved.is_file() and resolved.suffix.lower() == '.html' else None

    @app.route('/robots.txt')
    def robots_txt():
        base_url, host_no_port = absolute_public_base_url()
        lines = [
            'User-agent: *',
            'Allow: /',
            'Disallow: /admin',
            'Disallow: /api/admin',
            'Disallow: /data/',
            'Disallow: /update_logs/',
            '',
            '# Allow rendering resources for SEO',
            'Allow: /assets/',
            'Allow: /cdn_assets/',
            'Allow: /media/',
            '',
            'User-agent: bingbot',
            'Allow: /',
            'Disallow: /admin',
            'Disallow: /api/admin',
            'Disallow: /data/',
            'Disallow: /update_logs/',
            '',
            'User-agent: Baiduspider',
            'Allow: /',
            'Disallow: /admin',
            'Disallow: /api/admin',
            'Disallow: /data/',
            'Disallow: /update_logs/',
            '',
            f'Sitemap: {base_url}/sitemap-index.xml',
        ]
        if host_no_port:
            lines.append(f'Host: {host_no_port}')
        response = Response('\n'.join(lines) + '\n', mimetype='text/plain')
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    def render_urlset(entries, *, include_images: bool = False):
        base_url, _ = absolute_public_base_url()
        namespace = ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' if include_images else ''
        rows = ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"{namespace}>']
        for item in entries:
            path = str(item.get('path') or '/').strip() or '/'
            rows.append('  <url>')
            rows.append(f'    <loc>{html.escape(f"{base_url}{path}", quote=True)}</loc>')
            rows.append(f'    <lastmod>{html.escape(str(item.get("lastmod") or ""), quote=True)}</lastmod>')
            rows.append(f'    <changefreq>{html.escape(str(item.get("changefreq") or "weekly"), quote=True)}</changefreq>')
            rows.append(f'    <priority>{html.escape(str(item.get("priority") or "0.7"), quote=True)}</priority>')
            for image_item in item.get('images', []) if include_images else []:
                rows.append('    <image:image>')
                rows.append(f'      <image:loc>{html.escape(str(image_item.get("loc") or ""), quote=True)}</image:loc>')
                if image_item.get('title'):
                    rows.append(f'      <image:title>{html.escape(str(image_item["title"]))}</image:title>')
                if image_item.get('caption'):
                    rows.append(f'      <image:caption>{html.escape(str(image_item["caption"]))}</image:caption>')
                rows.append('    </image:image>')
            rows.append('  </url>')
        rows.append('</urlset>')
        response = Response('\n'.join(rows) + '\n', mimetype='application/xml')
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    def sitemap_entries_for_kind(kind: str):
        entries = collect_public_html_urls()
        if kind == 'products':
            return [item for item in entries if get_product_for_path(item['path'])]
        if kind == 'news':
            return [item for item in entries if item['path'].startswith('/pages/news/')]
        if kind == 'pages':
            return [item for item in entries if not get_product_for_path(item['path']) and not item['path'].startswith('/pages/news/')]
        return entries

    @app.route('/sitemap-pages.xml')
    @app.route('/sitemap-products.xml')
    @app.route('/sitemap-news.xml')
    def typed_sitemap_xml():
        kind = request.path.removeprefix('/sitemap-').removesuffix('.xml')
        return render_urlset(sitemap_entries_for_kind(kind))

    @app.route('/sitemap-images.xml')
    def image_sitemap_xml():
        base_url, _ = absolute_public_base_url()
        entries = []
        seen_images = set()
        for item in collect_public_html_urls():
            file_path = public_html_file_for_path(item['path'])
            if file_path is None:
                continue
            try:
                html_body = file_path.read_text(encoding='utf-8')
            except Exception:
                continue
            product = get_product_for_path(item['path'])
            title = str(product.get('displayName') or product.get('name') or extract_primary_heading(html_body) or extract_html_title(html_body)).strip()
            caption = str(product.get('imageCaption') or product.get('seoDescription') or product.get('description') or '').strip()
            try:
                reviewed = list(get_indexable_images_for_page(item['path']) or [])
            except Exception:
                reviewed = []
            urls = []
            metadata = {}
            for asset in reviewed:
                url = absolute_public_url(asset.get('url', ''), base_url=base_url, page_url=f'{base_url}{item["path"]}')
                if not url or url in seen_images:
                    continue
                seen_images.add(url)
                urls.append(url)
                metadata[url] = asset
            if not reviewed:
                for url in extract_public_image_urls(html_body, base_url=base_url, page_url=f'{base_url}{item["path"]}'):
                    if url in seen_images:
                        continue
                    try:
                        asset = get_image_asset(url, item['path']) or {}
                    except Exception:
                        asset = {}
                    if asset and not asset.get('indexable', True):
                        continue
                    if str(asset.get('role') or '') in {'decorative', 'logo', 'qrcode'}:
                        continue
                    seen_images.add(url)
                    urls.append(url)
                    metadata[url] = asset
            configured = str(product.get('cardImage') or product.get('image') or '').strip()
            if configured:
                configured = absolute_public_url(configured, base_url=base_url, page_url=f'{base_url}{item["path"]}')
                if configured and configured not in urls and configured not in seen_images:
                    urls.insert(0, configured)
                    seen_images.add(configured)
            if urls:
                enriched = dict(item)
                enriched['images'] = [{
                    'loc': url,
                    'title': str(metadata.get(url, {}).get('title') or metadata.get(url, {}).get('alt') or title).strip(),
                    'caption': str(metadata.get(url, {}).get('caption') or caption).strip(),
                } for url in urls]
                entries.append(enriched)
        return render_urlset(entries, include_images=True)

    @app.route('/sitemap-index.xml')
    def sitemap_index_xml():
        base_url, _ = absolute_public_base_url()
        today = now_beijing().strftime('%Y-%m-%d')
        rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for name in ('pages', 'products', 'news', 'images'):
            rows.extend(['  <sitemap>', f'    <loc>{base_url}/sitemap-{name}.xml</loc>', f'    <lastmod>{today}</lastmod>', '  </sitemap>'])
        rows.append('</sitemapindex>')
        return Response('\n'.join(rows) + '\n', mimetype='application/xml', headers={'Cache-Control': 'public, max-age=3600'})

    @app.route('/sitemap.xml')
    def sitemap_xml():
        return render_urlset(collect_public_html_urls())

    @app.after_request
    def inject_public_site_metadata(response):
        try:
            path = request.path or ''
            response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            response.headers.setdefault('Referrer-Policy', public_referrer_policy)
            response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
            if is_anti_crawl_strict_private_path(path):
                response.headers['X-Robots-Tag'] = strict_anti_crawl_headers

            if path.startswith('/admin'):
                response.headers.setdefault('Content-Security-Policy', public_html_content_security_policy)
                return response

            content_type = (response.headers.get('Content-Type') or '').lower()
            content_disposition = (response.headers.get('Content-Disposition') or '').lower()

            if path.startswith('/api/') or 'attachment' in content_disposition:
                return response

            # ── JavaScript 响应：为 JS 中引用的本地资源路径注入版本号 ──
            if 'javascript' in content_type and 'text/html' not in content_type:
                response.direct_passthrough = False
                js_body = response.get_data(as_text=True)
                if js_body:
                    js_body = inject_js_asset_versions(js_body, root)
                    response.set_data(js_body)
                return response

            if 'text/html' not in content_type:
                return response

            response.headers.setdefault('Content-Security-Policy', public_html_content_security_policy)
            response.headers['Cache-Control'] = 'no-store, no-cache, max-age=0, must-revalidate'
            response.headers['CDN-Cache-Control'] = 'no-store'
            response.headers['Cloudflare-CDN-Cache-Control'] = 'no-store'
            response.headers['Surrogate-Control'] = 'no-store'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.direct_passthrough = False
            html_body = response.get_data(as_text=True)
            if not html_body:
                return response

            # Pages can be persisted on a mounted host directory and outlive
            # the application image. Repair the verified sequence at the
            # response boundary as a last-line safeguard.
            html_body = repair_known_mojibake(html_body)
            html_body = normalize_public_html_links(html_body)
            html_body = inject_seo_head_markup(html_body)

            # ── 为 HTML 中所有 href/src 引用的本地静态资源注入 mtime 版本号 ──
            html_body = inject_html_asset_versions(html_body, root, path)

            script_tags = []
            if chem_subscript_script_src not in html_body:
                script_tags.append(f'<script src="{chem_subscript_script_src}" defer></script>')
            if site_analytics_script_src not in html_body:
                script_tags.append(f'<script src="{site_analytics_script_src}" defer></script>')
            if script_tags:
                script_block = '\n'.join(script_tags)
                lower_body = html_body.lower()
                body_pos = lower_body.rfind('</body>')
                html_pos = lower_body.rfind('</html>')
                if body_pos != -1:
                    html_body = html_body[:body_pos] + script_block + '\n' + html_body[body_pos:]
                elif html_pos != -1:
                    html_body = html_body[:html_pos] + script_block + '\n' + html_body[html_pos:]
                else:
                    html_body += script_block

            response.set_data(html_body)
        except Exception:
            pass
        return response

    def build_search_index():
        with search_lock:
            pages_dir = root / 'pages'
            index_file = root / 'index.html'
            pages = []

            if index_file.exists():
                try:
                    content = index_file.read_text(encoding='utf-8')
                    pages.append(build_public_search_page(root, index_file, content, 'index.html'))
                except Exception:
                    pass

            for html_file in pages_dir.rglob('*.html'):
                if 'admin' in str(html_file).lower():
                    continue
                try:
                    content = html_file.read_text(encoding='utf-8')
                    rel_path = html_file.relative_to(root)
                    if is_legacy_redirect_source('/' + rel_path.as_posix()):
                        continue
                    pages.append(build_public_search_page(root, html_file, content, str(rel_path)))
                except Exception as exc:
                    print(f'Error indexing {html_file}: {exc}')
                    continue

            search_index['pages'] = pages
            search_index['last_updated'] = time.time()
            return pages

    def search_pages(query, limit=20):
        if not search_index['pages'] or time.time() - search_index['last_updated'] > 300:
            build_search_index()

        return search_public_pages(query, search_index['pages'], limit)

    app.extensions.setdefault('yx_public_site_search', {})
    app.extensions['yx_public_site_search']['search_pages'] = search_pages
    app.extensions['yx_public_site_search']['build_search_index'] = build_search_index
    app.extensions['yx_public_site_search']['resolve_page'] = canonical_public_path_for_request

    @app.route('/api/search')
    def api_search():
        query = request.args.get('q', '').strip()
        limit = request.args.get('limit', 20, type=int)
        if not query:
            return jsonify({'results': [], 'query': ''})
        results = search_pages(query, limit)
        return jsonify({'results': results, 'query': query, 'total': len(results)})

    @app.route('/api/search/rebuild')
    @login_required
    def api_search_rebuild():
        pages = build_search_index()
        return jsonify({
            'success': True,
            'message': f'索引重建完成，共索引 {len(pages)} 个页面',
        })

    @app.route('/favicon.ico')
    @app.route('/apple-touch-icon.png')
    @app.route('/favicon.png')
    def site_favicon():
        if favicon_file.exists() and favicon_file.is_file():
            response = send_file(str(favicon_file), mimetype='image/png')
            response.headers['Cache-Control'] = 'public, max-age=86400'
            return response
        return Response(status=204)

    hero_bootstrap_marker = '<section class="vs-hero">'

    def render_home_index_response():
        index_file = root / 'index.html'
        try:
            html_body = index_file.read_text(encoding='utf-8')
        except Exception:
            return send_from_directory(str(root), 'index.html')

        if build_hero_bootstrap_payload is not None and hero_bootstrap_marker in html_body:
            try:
                payload = build_hero_bootstrap_payload()
                if isinstance(payload, dict) and payload.get('items'):
                    bootstrap_json = json.dumps(
                        payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True
                    ).replace('</', '<\\/')
                    bootstrap_script = (
                        '<script>window.__HERO_BOOTSTRAP__=' + bootstrap_json + ';</script>\n    '
                    )
                    html_body = html_body.replace(
                        hero_bootstrap_marker, bootstrap_script + hero_bootstrap_marker, 1
                    )
            except Exception:
                pass

        return Response(html_body, mimetype='text/html')

    @app.route('/')
    def index():
        blocked = blocked_disabled_promotion_link_response()
        if blocked:
            return blocked
        return render_home_index_response()

    @app.route('/<path:path>')
    def serve_static(path):
        blocked = blocked_disabled_promotion_link_response()
        if blocked:
            return blocked
        redirect_target = legacy_redirect_target(request.path or '')
        if redirect_target:
            return redirect(redirect_target, code=301)
        canonical_path = canonical_public_path_for_request(path)
        request_path = request.path or ''
        if canonical_path and canonical_path != request_path:
            return redirect(f'{canonical_path}{build_request_query_suffix()}', code=301)

        normalized = normalize_public_static_path(path)
        if not normalized:
            return Response(status=404)
        admin_roots = ('admin',)
        is_admin_html = any(
            normalized == base
            or normalized == f'{base}/index'
            or normalized == f'{base}/index.html'
            or normalized.startswith(f'{base}/')
            for base in admin_roots
        )

        exact_path = root / normalized
        if exact_path.is_file():
            if normalized == 'index.html':
                return render_home_index_response()
            response = send_from_directory(str(root), normalized)
            if is_admin_html:
                response.headers['Cache-Control'] = 'no-store, max-age=0'
            elif 'v=' in (request.query_string.decode('utf-8', 'ignore') if request.query_string else ''):
                response.headers['Cache-Control'] = 'public, max-age=31536000'
            else:
                response.headers['Cache-Control'] = 'public, max-age=300'
            return response

        html_path = root / f'{normalized}.html'
        if html_path.is_file():
            response = send_from_directory(str(root), f'{normalized}.html')
            if is_admin_html:
                response.headers['Cache-Control'] = 'no-store, max-age=0'
            elif 'v=' in (request.query_string.decode('utf-8', 'ignore') if request.query_string else ''):
                response.headers['Cache-Control'] = 'public, max-age=31536000'
            else:
                response.headers['Cache-Control'] = 'public, max-age=300'
            return response

        if exact_path.is_dir():
            index_path = exact_path / 'index.html'
            if index_path.is_file():
                response = send_from_directory(str(exact_path), 'index.html')
                if is_admin_html:
                    response.headers['Cache-Control'] = 'no-store, max-age=0'
                elif 'v=' in (request.query_string.decode('utf-8', 'ignore') if request.query_string else ''):
                    response.headers['Cache-Control'] = 'public, max-age=31536000'
                else:
                    response.headers['Cache-Control'] = 'public, max-age=300'
                return response

        return Response(status=404)
