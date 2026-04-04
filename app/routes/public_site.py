"""公开站点路由模块。

负责公开页面渲染、SEO 元信息、搜索、favicon 与静态资源访问控制。
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
from urllib.parse import urljoin

from flask import Response, jsonify, redirect, request, send_file, send_from_directory

BEIJING_TZ = timezone(timedelta(hours=8))

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
):
    """注册公开站点的 SEO、搜索与静态资源路由。"""
    root = Path(app_root)
    favicon_file = Path(cdn_assets_dir) / Path(site_favicon_relative_path)

    search_index = {
        'pages': [],
        'last_updated': 0.0,
    }
    search_lock = threading.Lock()

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
        text = html.unescape(str(raw_html or '').replace('\u00a0', ' '))
        text = re.sub(r'(?is)<(script|style|svg|noscript).*?>.*?</\1>', ' ', text)
        text = re.sub(r'(?is)<br\s*/?>', ' ', text)
        text = re.sub(r'(?is)<[^>]+>', ' ', text)
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text).strip()
        return text

    def extract_html_title(html_body: str) -> str:
        match = re.search(r'(?is)<title\b[^>]*>(.*?)</title>', html_body or '')
        return strip_html_markup(match.group(1) if match else '')

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

    def extract_primary_heading(html_body: str) -> str:
        match = re.search(r'(?is)<h1\b[^>]*>(.*?)</h1>', html_body or '')
        return strip_html_markup(match.group(1) if match else '')

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

        forwarded_host = first_forwarded_value(request.headers.get('X-Forwarded-Host', ''))
        host = (forwarded_host or request.host or '').strip()
        forwarded_proto = first_forwarded_value(request.headers.get('X-Forwarded-Proto', '')).lower()
        scheme = forwarded_proto if forwarded_proto in {'http', 'https'} else (request.scheme or 'https')
        if not host:
            host = fallback or 'localhost:8000'
        return f'{scheme}://{host}', host.split(':', 1)[0]

    def extract_primary_image_url(html_body: str, *, base_url: str, page_url: str) -> str:
        for match in re.finditer(r'(?is)<img\b[^>]*>', html_body or ''):
            attrs = extract_html_tag_attributes(match.group(0))
            src = str(attrs.get('src') or '').strip()
            if not src or src.startswith('data:'):
                continue
            return absolute_public_url(src, base_url=base_url, page_url=page_url)
        return absolute_public_url(site_logo_path, base_url=base_url, page_url=page_url)

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
            if image_url:
                article_data['image'] = [image_url]
            payloads.append(article_data)

        return payloads

    def inject_seo_head_markup(html_body: str) -> str:
        base_url, _ = absolute_public_base_url()
        canonical_path = canonical_public_path_for_request(request.path or '') or (request.path or '/')
        canonical_url = absolute_public_url(canonical_path, base_url=base_url)
        title_text = extract_html_title(html_body)
        heading_text = extract_primary_heading(html_body)
        description = build_page_description(canonical_path, html_body, title_text, heading_text)
        image_url = extract_primary_image_url(html_body, base_url=base_url, page_url=canonical_url)
        structured_data = build_structured_data(canonical_path, canonical_url, html_body, title_text, description, image_url)

        head_tags: list[str] = []
        if not extract_meta_content(html_body, attr_name='name', attr_value='description'):
            head_tags.append(f'<meta name="description" content="{html.escape(description, quote=True)}">')
        if not extract_link_href(html_body, rel_value='canonical'):
            head_tags.append(f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">')
        if not extract_meta_content(html_body, attr_name='name', attr_value='robots'):
            head_tags.append(f'<meta name="robots" content="{seo_default_robots}">')
        if not extract_link_href(html_body, rel_value='icon'):
            head_tags.append('<link rel="icon" href="/favicon.png" sizes="32x32" type="image/png">')
        if not extract_link_href(html_body, rel_value='apple-touch-icon'):
            head_tags.append('<link rel="apple-touch-icon" href="/apple-touch-icon.png">')
        if structured_data and 'application/ld+json' not in html_body.lower():
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
                if url.endswith('/index.html'):
                    url = url[:-10] + '/'
                add_url(url, html_file, changefreq='weekly', priority='0.8' if '/news/' in url else '0.7')

        return output

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
            f'Sitemap: {base_url}/sitemap.xml',
        ]
        if host_no_port:
            lines.append(f'Host: {host_no_port}')
        response = Response('\n'.join(lines) + '\n', mimetype='text/plain')
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    @app.route('/sitemap.xml')
    def sitemap_xml():
        base_url, _ = absolute_public_base_url()
        entries = collect_public_html_urls()
        rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for item in entries:
            path = str(item.get('path') or '/').strip() or '/'
            rows.append('  <url>')
            rows.append(f'    <loc>{html.escape(f"{base_url}{path}", quote=True)}</loc>')
            rows.append(f'    <lastmod>{html.escape(str(item.get("lastmod") or ""), quote=True)}</lastmod>')
            rows.append(f'    <changefreq>{html.escape(str(item.get("changefreq") or "weekly"), quote=True)}</changefreq>')
            rows.append(f'    <priority>{html.escape(str(item.get("priority") or "0.7"), quote=True)}</priority>')
            rows.append('  </url>')
        rows.append('</urlset>')
        response = Response('\n'.join(rows) + '\n', mimetype='application/xml')
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

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
            if 'text/html' not in content_type:
                return response

            response.headers.setdefault('Content-Security-Policy', public_html_content_security_policy)
            response.direct_passthrough = False
            html_body = response.get_data(as_text=True)
            if not html_body:
                return response

            html_body = inject_seo_head_markup(html_body)

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

    class TextExtractor(HTMLParser):
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

    def extract_text_from_html(html_content):
        try:
            parser = TextExtractor()
            parser.feed(html_content)
            return parser.get_text()
        except Exception:
            return ''

    def extract_title_from_html(html_content):
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()
        h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content, re.IGNORECASE)
        if h1_match:
            return h1_match.group(1).strip()
        return ''

    def build_search_index():
        with search_lock:
            pages_dir = root / 'pages'
            index_file = root / 'index.html'
            pages = []

            if index_file.exists():
                try:
                    content = index_file.read_text(encoding='utf-8')
                    title = extract_title_from_html(content)
                    text = extract_text_from_html(content)
                    pages.append({
                        'url': '/',
                        'title': title or '首页',
                        'content': text[:2000],
                        'path': 'index.html',
                    })
                except Exception:
                    pass

            for html_file in pages_dir.rglob('*.html'):
                if 'admin' in str(html_file).lower():
                    continue
                try:
                    content = html_file.read_text(encoding='utf-8')
                    title = extract_title_from_html(content)
                    text = extract_text_from_html(content)
                    rel_path = html_file.relative_to(root)
                    url = '/' + str(rel_path).replace('\\', '/')
                    pages.append({
                        'url': url,
                        'title': title or html_file.stem,
                        'content': text[:2000],
                        'path': str(rel_path),
                    })
                except Exception as exc:
                    print(f'Error indexing {html_file}: {exc}')
                    continue

            search_index['pages'] = pages
            search_index['last_updated'] = time.time()
            return pages

    def search_pages(query, limit=20):
        if not search_index['pages'] or time.time() - search_index['last_updated'] > 300:
            build_search_index()

        if not query:
            return []

        query_lower = query.lower()
        results = []
        for page in search_index['pages']:
            score = 0
            snippet = ''
            title = page.get('title', '')
            content = page.get('content', '')
            title_lower = title.lower()
            content_lower = content.lower()

            if query_lower in title_lower:
                score += 100
                snippet = title

            if query_lower in content_lower:
                score += 50
                idx = content_lower.find(query_lower)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(query) + 100)
                snippet = content[start:end]
                if start > 0:
                    snippet = '...' + snippet
                if end < len(content):
                    snippet = snippet + '...'

            for word in query_lower.split():
                if len(word) >= 2:
                    if word in title_lower:
                        score += 30
                    if word in content_lower:
                        score += 10

            if score > 0:
                results.append({
                    'url': page['url'],
                    'title': title,
                    'snippet': snippet or (content[:150] + '...' if content else ''),
                    'score': score,
                })

        results.sort(key=lambda item: item['score'], reverse=True)
        return results[:limit]

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

    @app.route('/')
    def index():
        return send_from_directory(str(root), 'index.html')

    @app.route('/<path:path>')
    def serve_static(path):
        canonical_path = canonical_public_path_for_request(path)
        request_path = request.path or ''
        if canonical_path and canonical_path != request_path:
            return redirect(f'{canonical_path}{build_request_query_suffix()}', code=301)

        normalized = normalize_public_static_path(path)
        if not normalized:
            return Response(status=404)
        is_admin_html = normalized in {'admin', 'admin/index', 'admin/index.html'} or normalized.startswith('admin/')

        exact_path = root / normalized
        if exact_path.is_file():
            response = send_from_directory(str(root), normalized)
            if is_admin_html:
                response.headers['Cache-Control'] = 'no-store, max-age=0'
            return response

        html_path = root / f'{normalized}.html'
        if html_path.is_file():
            response = send_from_directory(str(root), f'{normalized}.html')
            if is_admin_html:
                response.headers['Cache-Control'] = 'no-store, max-age=0'
            return response

        if exact_path.is_dir():
            index_path = exact_path / 'index.html'
            if index_path.is_file():
                response = send_from_directory(str(exact_path), 'index.html')
                if is_admin_html:
                    response.headers['Cache-Control'] = 'no-store, max-age=0'
                return response

        return Response(status=404)
