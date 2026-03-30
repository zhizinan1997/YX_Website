"""Product editor/admin routes and product HTML helpers."""

from __future__ import annotations

import base64
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from flask import Response, jsonify, request, stream_with_context

try:
    import httpx
    HTTPX_SUPPORT = True
except ImportError:
    HTTPX_SUPPORT = False

try:
    import requests
    REQUESTS_SUPPORT = True
except ImportError:
    REQUESTS_SUPPORT = False


_DEPS = {}
PRODUCT_ADMIN_DATA_PREFIX = 'MC_PRODUCT_ADMIN_DATA:'
ALLOWED_PRODUCT_CATEGORIES = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}


def configure_product_editor(
    *,
    app_root,
    require_super_admin_api,
    render_markdown,
    get_product_page_ai_config,
    get_product_page_ai_system_prompt,
    get_product_settings,
    save_product_settings,
    default_product_categories,
    normalize_ai_product_image_extension,
    infer_ai_product_image_extension_from_mime,
    allowed_ai_product_image_mime_types,
):
    """Configure shared dependencies for product editor helpers/routes."""
    _DEPS.clear()
    _DEPS.update({
        'app_root': Path(app_root),
        'require_super_admin_api': require_super_admin_api,
        'render_markdown': render_markdown,
        'get_product_page_ai_config': get_product_page_ai_config,
        'get_product_page_ai_system_prompt': get_product_page_ai_system_prompt,
        'get_product_settings': get_product_settings,
        'save_product_settings': save_product_settings,
        'default_product_categories': dict(default_product_categories or {}),
        'normalize_ai_product_image_extension': normalize_ai_product_image_extension,
        'infer_ai_product_image_extension_from_mime': infer_ai_product_image_extension_from_mime,
        'allowed_ai_product_image_mime_types': set(allowed_ai_product_image_mime_types or set()),
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'Product editor dependency not configured: {name}')
    return value


def _product_template_files() -> tuple[Path, Path]:
    app_root = _dep('app_root')
    return (
        app_root / 'pages' / 'gassensing' / '模板.html',
        app_root / 'templates' / 'gassensing-product-template.html',
    )


def _product_ai_reference_file() -> Path:
    return _dep('app_root') / 'pages' / 'gassensing' / 'mc_ld_h2.html'


def _gassensing_products_dir() -> Path:
    return _dep('app_root') / 'pages' / 'gassensing'


def get_product_template_html() -> str:
    """Load product page template HTML from legacy/new template paths."""
    for template_file in _product_template_files():
        if template_file.exists():
            return template_file.read_text(encoding='utf-8', errors='ignore')
    checked = ' | '.join(str(p) for p in _product_template_files())
    raise FileNotFoundError(f'产品模板不存在，已检查: {checked}')


def get_product_ai_reference_html() -> str:
    """Load AI generation reference HTML, fallback to generic template."""
    reference_file = _product_ai_reference_file()
    if reference_file.exists():
        return reference_file.read_text(encoding='utf-8', errors='ignore')
    return get_product_template_html()


def extract_product_template_placeholders(template_html: str):
    """Extract ordered unique placeholders like 【产品名字】 from template."""
    seen = set()
    ordered = []
    for token in re.findall(r'【[^】]+】', template_html or ''):
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def split_product_detail_from_editor(content_html: str):
    """Split visual editor content into two detail paragraphs."""
    source = (content_html or '').strip()
    if not source:
        return '', ''

    paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', source, re.S | re.I)
    if paragraphs:
        cleaned = []
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', '', p)
            text = html.unescape(text).strip()
            if text:
                cleaned.append(text)
        if cleaned:
            return cleaned[0], (cleaned[1] if len(cleaned) > 1 else '')

    plain = re.sub(r'(?i)<br\s*/?>', '\n', source)
    plain = re.sub(r'<[^>]+>', '', plain)
    plain = html.unescape(plain)
    parts = [x.strip() for x in re.split(r'\n{2,}|\n', plain) if x.strip()]
    if not parts:
        return '', ''
    return parts[0], (parts[1] if len(parts) > 1 else '')


def _strip_html_text(fragment: str) -> str:
    if not fragment:
        return ''
    text = re.sub(r'<[^>]+>', '', fragment, flags=re.S)
    return html.unescape(text).strip()


def extract_legacy_template_fields(page_html: str, defaults: dict):
    """Extract template-like fields from legacy product HTML structure."""
    extracted = {}
    content = page_html or ''

    def set_field(key, value):
        if key in defaults:
            val = str(value or '').strip()
            if val:
                extracted[key] = val

    def find_anchors_with_class(section_html: str, required_class: str):
        items = []
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', section_html or '', re.S | re.I):
            attrs = m.group(1) or ''
            body = m.group(2) or ''
            class_m = re.search(r'class="([^"]*)"', attrs, re.I)
            href_m = re.search(r'href="([^"]*)"', attrs, re.I)
            classes = class_m.group(1) if class_m else ''
            href = href_m.group(1) if href_m else ''
            if required_class in classes:
                items.append((href, body))
        return items

    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.S | re.I)
    if h1:
        title = _strip_html_text(h1.group(1))
        for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
            set_field(key, title)
    desc = re.search(r'<p[^>]*class="[^"]*vs-product-hero__desc[^"]*"[^>]*>(.*?)</p>', content, re.S | re.I)
    if desc:
        set_field('【产品描述】', _strip_html_text(desc.group(1)))

    main_img = re.search(r'<img[^>]*id="mainImage"[^>]*src="([^"]+)"', content, re.I)
    if not main_img:
        main_img = re.search(r'<div[^>]*class="[^"]*vs-gallery-main[^"]*"[^>]*>.*?<img[^>]*src="([^"]+)"', content, re.S | re.I)
    if main_img:
        set_field('【主图链接】', main_img.group(1))

    thumbs_block = re.search(r'<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>(.*?)</div>\s*</div>', content, re.S | re.I)
    if thumbs_block:
        thumbs = re.findall(r'<img[^>]*src="([^"]+)"', thumbs_block.group(1), re.I)
        for i, src in enumerate(thumbs, 1):
            set_field(f'【缩略图{i}链接】', src)

    feature_ul = re.search(r'<ul[^>]*class="[^"]*vs-feature-list[^"]*"[^>]*>(.*?)</ul>', content, re.S | re.I)
    if feature_ul:
        features = re.findall(r'<li[^>]*>(.*?)</li>', feature_ul.group(1), re.S | re.I)
        for i, item in enumerate(features, 1):
            set_field(f'【特性{i}】', _strip_html_text(item))

    detail_block = re.search(
        r'产品详情\s*</h2>\s*<div[^>]*class="[^"]*vs-product-section__content[^"]*"[^>]*>(.*?)</div>',
        content, re.S | re.I
    )
    if detail_block:
        ps = re.findall(r'<p[^>]*>(.*?)</p>', detail_block.group(1), re.S | re.I)
        cleaned = [_strip_html_text(p) for p in ps if _strip_html_text(p)]
        if cleaned:
            set_field('【产品详情1】', cleaned[0])
        if len(cleaned) > 1:
            set_field('【产品详情2】', cleaned[1])

    adv_grid = re.search(r'<div[^>]*class="[^"]*vs-advantages-grid[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</section>', content, re.S | re.I)
    if adv_grid:
        cards = re.findall(r'<div[^>]*class="[^"]*vs-advantage-card[^"]*"[^>]*>(.*?)</div>', adv_grid.group(1), re.S | re.I)
        for i, card in enumerate(cards, 1):
            h = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            if h:
                set_field(f'【优势{i}】', _strip_html_text(h.group(1)))
            if p:
                set_field(f'【优势{i}的描述】', _strip_html_text(p.group(1)))

    app_grid = re.search(r'<div[^>]*class="[^"]*vs-applications-grid[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</section>', content, re.S | re.I)
    if app_grid:
        cards = re.findall(r'<div[^>]*class="[^"]*vs-application-card[^"]*"[^>]*>(.*?)</div>\s*</div>', app_grid.group(1), re.S | re.I)
        for i, card in enumerate(cards, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', card, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            if img:
                set_field(f'【应用图{i}链接】', img.group(1))
            if h4:
                title = _strip_html_text(h4.group(1)).replace('•', ' ').strip()
                set_field(f'【应用{i}】', re.sub(r'\s+', ' ', title))
            if p:
                set_field(f'【应用{i}的描述】', _strip_html_text(p.group(1)))

    specs_table = re.search(r'<table[^>]*class="[^"]*vs-specs-table[^"]*"[^>]*>(.*?)</table>', content, re.S | re.I)
    if specs_table:
        rows = re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>', specs_table.group(1), re.S | re.I)
        key_map = [
            (['检测原理', '传感器技术'], '【传感器技术】'),
            (['检测对象', '检测气体'], '【检测气体】'),
            (['检测范围'], '【检测范围】'),
            (['检测精度', '精度'], '【检测精度】'),
            (['响应速度', '响应时间'], '【响应时间】'),
            (['最低检测限'], '【最低检测限】'),
            (['模块功耗', '检测功耗', '功耗'], '【检测功耗】'),
            (['续航时间', '设计寿命'], '【续航时间】'),
            (['工作环境', '工作温度'], '【工作温度】'),
            (['产品尺寸', '尺寸'], '【产品尺寸】'),
            (['重量'], '【重量】'),
        ]
        for raw_k, raw_v in rows:
            k = _strip_html_text(raw_k)
            v = _strip_html_text(raw_v)
            for aliases, target in key_map:
                if any(alias in k for alias in aliases):
                    set_field(target, v)
                    break

    news_section = re.search(r'<section[^>]*class="[^"]*vs-related-news[^"]*"[^>]*>(.*?)</section>', content, re.S | re.I)
    if news_section:
        items = find_anchors_with_class(news_section.group(1), 'vs-news-item')
        for i, (href, block) in enumerate(items, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', block, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', block, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S | re.I)
            set_field(f'【新闻链接{i}】', href)
            if img:
                set_field(f'【新闻图片{i}链接】', img.group(1))
            if h4:
                set_field(f'【新闻标题{i}】', _strip_html_text(h4.group(1)))
            if p:
                set_field(f'【新闻描述{i}】', _strip_html_text(p.group(1)))

    related_section = re.search(r'<section[^>]*class="[^"]*vs-related-products[^"]*"[^>]*>(.*?)</section>', content, re.S | re.I)
    if related_section:
        items = find_anchors_with_class(related_section.group(1), 'vs-related-item')
        for i, (href, block) in enumerate(items, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', block, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', block, re.S | re.I)
            set_field(f'【相关产品链接{i}】', href)
            if img:
                set_field(f'【相关产品图片{i}链接】', img.group(1))
            if h4:
                set_field(f'【相关产品标题{i}】', _strip_html_text(h4.group(1)))

    return extracted


def normalize_product_template_fields(raw_fields):
    """Keep only valid template placeholder key/value pairs."""
    normalized = {}
    if not isinstance(raw_fields, dict):
        return normalized
    for key, value in raw_fields.items():
        k = str(key or '').strip()
        if not k.startswith('【') or not k.endswith('】'):
            continue
        normalized[k] = str(value or '').strip()
    return normalized


def build_product_template_defaults(title: str, summary: str, image_url: str, detail1: str, detail2: str):
    """Build default values for all placeholders in product template HTML."""
    placeholders = extract_product_template_placeholders(get_product_template_html())
    image = (image_url or '/assets/images/logo.png').strip()
    defaults = {}
    for key in placeholders:
        if '链接' in key:
            if any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
                defaults[key] = image
            elif '新闻链接' in key or '相关产品链接' in key:
                defaults[key] = '#'
            else:
                defaults[key] = ''
        else:
            defaults[key] = ''

    for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
        defaults[key] = title
    defaults['【产品描述】'] = summary
    defaults['【产品详情1】'] = detail1
    defaults['【产品详情2】'] = detail2
    defaults['【主图链接】'] = image
    defaults['【缩略图1链接】'] = image
    return defaults


def sanitize_product_template_value(key: str, value: str) -> str:
    """Escape placeholder values safely for HTML/template substitution."""
    v = (value or '').strip()
    if not v:
        if '链接' in key:
            if any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
                return '/assets/images/logo.png'
            if '新闻链接' in key or '相关产品链接' in key:
                return '#'
        return ''
    if '链接' in key and any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
        if v.lower().startswith('assets/'):
            v = '/' + v
    if '链接' in key:
        return html.escape(v, quote=True)
    return html.escape(v, quote=True).replace('\n', '<br>')


def inject_product_meta_tags(page_html: str, title: str, short_name: str, image_url: str, summary: str, category: str) -> str:
    """Inject product-* meta tags for admin scanner compatibility."""
    safe_title = html.escape(title or '', quote=True)
    safe_short_name = html.escape(short_name or '', quote=True)
    safe_image = html.escape(image_url or '', quote=True)
    safe_summary = html.escape(summary or '', quote=True)
    safe_category = html.escape(category or 'module', quote=True)

    meta_block = f"""
    <meta name="product-name" content="{safe_title}" />
    <meta name="product-short-name" content="{safe_short_name}" />
    <meta name="product-image" content="{safe_image}" />
    <meta name="product-description" content="{safe_summary}" />
    <meta name="product-category" content="{safe_category}" />
"""
    if '</head>' in page_html:
        return page_html.replace('</head>', meta_block + '\n</head>', 1)
    return page_html + meta_block


def encode_product_admin_data(payload: dict) -> str:
    """Encode admin editor state into HTML comment for future edits."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
    return f'<!-- {PRODUCT_ADMIN_DATA_PREFIX}{encoded} -->'


def decode_product_admin_data(page_html: str):
    """Decode embedded admin editor payload from HTML comment."""
    m = re.search(r'<!--\s*' + re.escape(PRODUCT_ADMIN_DATA_PREFIX) + r'([A-Za-z0-9+/=_-]+)\s*-->', page_html or '')
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group(1)).decode('utf-8')
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def render_gassensing_product_html(
    title: str,
    short_name: str,
    category: str,
    image_url: str,
    summary: str,
    content_html: str,
    template_fields=None
):
    """Render product page based on resolved product template HTML."""
    safe_title = (title or '').strip()
    safe_short_name = (short_name or safe_title).strip()
    safe_category = (category or 'module').strip()
    safe_image = (image_url or '/assets/images/logo.png').strip()
    safe_summary = (summary or '').strip()
    safe_content = (content_html or '').strip()

    detail1, detail2 = split_product_detail_from_editor(safe_content)
    defaults = build_product_template_defaults(
        title=safe_title,
        summary=safe_summary,
        image_url=safe_image,
        detail1=detail1,
        detail2=detail2,
    )
    incoming = normalize_product_template_fields(template_fields)
    placeholders = extract_product_template_placeholders(get_product_template_html())

    resolved = dict(defaults)
    for key in placeholders:
        if key in incoming and incoming[key]:
            resolved[key] = incoming[key]

    for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
        resolved[key] = safe_title
    resolved['【产品描述】'] = safe_summary
    resolved['【主图链接】'] = safe_image
    if not resolved.get('【缩略图1链接】'):
        resolved['【缩略图1链接】'] = safe_image
    if not resolved.get('【产品详情1】'):
        resolved['【产品详情1】'] = detail1
    if not resolved.get('【产品详情2】'):
        resolved['【产品详情2】'] = detail2

    page_html = get_product_template_html()
    for key in placeholders:
        page_html = page_html.replace(key, sanitize_product_template_value(key, resolved.get(key, '')))

    page_html = inject_product_meta_tags(
        page_html=page_html,
        title=safe_title,
        short_name=safe_short_name,
        image_url=safe_image,
        summary=safe_summary,
        category=safe_category,
    )

    admin_payload = {
        'version': 2,
        'title': safe_title,
        'short_name': safe_short_name,
        'category': safe_category,
        'image_url': safe_image,
        'summary': safe_summary,
        'content_html': safe_content,
        'template_fields': resolved,
    }
    marker = encode_product_admin_data(admin_payload)
    if '</body>' in page_html:
        page_html = page_html.replace('</body>', marker + '\n</body>', 1)
    else:
        page_html += '\n' + marker

    return page_html, resolved


def parse_gassensing_product_detail(filepath: Path):
    """Parse product detail page fields for admin editing."""
    if not filepath.exists():
        return None

    content = filepath.read_text(encoding='utf-8', errors='ignore')
    admin_data = decode_product_admin_data(content)
    if isinstance(admin_data, dict):
        return {
            'id': filepath.stem,
            'title': (admin_data.get('title') or '').strip(),
            'short_name': (admin_data.get('short_name') or '').strip(),
            'category': (admin_data.get('category') or 'module').strip(),
            'image_url': (admin_data.get('image_url') or '').strip(),
            'summary': (admin_data.get('summary') or '').strip(),
            'content_html': (admin_data.get('content_html') or '').strip(),
            'template_fields': normalize_product_template_fields(admin_data.get('template_fields', {})),
        }

    base = extract_product_meta_from_html(filepath) or {}
    title = (base.get('name') or '').strip()
    short_name = (base.get('shortName') or '').strip()
    category = (base.get('category') or 'module').strip()
    image_url = (base.get('image') or '').strip()
    summary = (base.get('description') or '').strip()

    detail_match = re.search(
        r'<h3\s+class="section-header">\s*产品详情\s*</h3>\s*<div[^>]*>(.*?)</div>',
        content,
        re.S | re.I,
    )
    if detail_match:
        content_html = detail_match.group(1).strip()
    else:
        article_match = re.search(r'<main\b[^>]*>(.*?)</main>', content, re.S | re.I)
        content_html = (article_match.group(1).strip() if article_match else '')

    detail1, detail2 = split_product_detail_from_editor(content_html)
    template_fields = build_product_template_defaults(
        title=title,
        summary=summary,
        image_url=image_url,
        detail1=detail1,
        detail2=detail2,
    )
    legacy_extracted = extract_legacy_template_fields(content, template_fields)
    if legacy_extracted:
        template_fields.update(legacy_extracted)
    return {
        'id': filepath.stem,
        'title': title,
        'short_name': short_name,
        'category': category,
        'image_url': image_url,
        'summary': summary,
        'content_html': content_html,
        'template_fields': template_fields,
    }


def call_openai_api_sync_with_custom_config(messages, config):
    """Call OpenAI-compatible API with explicit config."""
    api_key = (config or {}).get('api_key', '')
    api_base = (config or {}).get('api_base', 'https://api.openai.com/v1')
    model = (config or {}).get('model', 'gpt-4o-mini')

    if not api_key:
        return None, "产品页编程AI未配置 API Key"

    api_url = api_base.rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': messages,
        'stream': False,
    }
    connect_timeout = 20
    read_timeout = 300
    attempts = 2
    try:
        if REQUESTS_SUPPORT:
            last_error = None
            for i in range(attempts):
                try:
                    response = requests.post(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=(connect_timeout, read_timeout),
                    )
                except requests.exceptions.ReadTimeout:
                    last_error = f"上游响应超时（>{read_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"
                except requests.exceptions.ConnectTimeout:
                    last_error = f"连接超时（>{connect_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"

                if response.status_code != 200:
                    detail = ''
                    try:
                        detail = (response.text or '').strip()
                    except Exception:
                        detail = ''
                    if detail:
                        detail = detail[:500]
                    return None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                result = response.json()
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content'], None
                return None, "API返回格式错误"
            return None, f"API调用失败: {last_error or '未知错误'}"
        if HTTPX_SUPPORT:
            last_error = None
            timeout_obj = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=60, pool=60)
            for i in range(attempts):
                try:
                    response = httpx.post(api_url, json=payload, headers=headers, timeout=timeout_obj)
                except httpx.ReadTimeout:
                    last_error = f"上游响应超时（>{read_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"
                except httpx.ConnectTimeout:
                    last_error = f"连接超时（>{connect_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"

                if response.status_code != 200:
                    detail = ''
                    try:
                        detail = (response.text or '').strip()
                    except Exception:
                        detail = ''
                    if detail:
                        detail = detail[:500]
                    return None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                result = response.json()
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content'], None
                return None, "API返回格式错误"
            return None, f"API调用失败: {last_error or '未知错误'}"
        return None, "缺少HTTP客户端库(requests或httpx)"
    except Exception as e:
        print(f"Product AI API error: {e}")
        return None, f"API调用失败: {str(e)}"


def _extract_stream_chunk_text(chunk_obj):
    """Extract text delta from OpenAI-compatible stream chunk."""
    if not isinstance(chunk_obj, dict):
        return ''
    choices = chunk_obj.get('choices') or []
    if not choices:
        return ''
    delta = choices[0].get('delta') or {}
    content = delta.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str):
                    parts.append(text)
        return ''.join(parts)
    return ''


def call_openai_api_stream_with_custom_config(messages, config):
    """Call OpenAI-compatible stream API with explicit config."""
    api_key = (config or {}).get('api_key', '')
    api_base = (config or {}).get('api_base', 'https://api.openai.com/v1')
    model = (config or {}).get('model', 'gpt-4o-mini')

    if not api_key:
        return None, "产品页编程AI未配置 API Key"

    api_url = api_base.rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': messages,
        'stream': True,
    }
    connect_timeout = 20
    read_timeout = 300

    if HTTPX_SUPPORT:
        def gen_httpx():
            try:
                timeout_obj = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=60, pool=60)
                with httpx.Client(timeout=timeout_obj) as client:
                    with client.stream('POST', api_url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            detail = (response.text or '').strip()
                            if detail:
                                detail = detail[:500]
                            yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                            return
                        for line in response.iter_lines():
                            if not line:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode('utf-8', errors='ignore')
                            if not line.startswith('data: '):
                                continue
                            data = line[6:].strip()
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            text = _extract_stream_chunk_text(chunk)
                            if text:
                                yield text, None
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_httpx()

    if REQUESTS_SUPPORT:
        def gen_requests():
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=(connect_timeout, read_timeout),
                )
                if response.status_code != 200:
                    detail = (response.text or '').strip()
                    if detail:
                        detail = detail[:500]
                    yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                    return
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode('utf-8', errors='ignore')
                    if not line.startswith('data: '):
                        continue
                    data = line[6:].strip()
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_stream_chunk_text(chunk)
                    if text:
                        yield text, None
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_requests()

    return None, "缺少HTTP客户端库(requests或httpx)"


def parse_json_object_from_ai_text(text: str):
    """Extract first valid JSON object from AI text."""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('AI返回为空')
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError('未找到 JSON 对象')
    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError('JSON 顶层必须是对象')
    return obj


def extract_html_from_ai_text(text: str, title: str = '产品页面'):
    """Extract HTML document from model output, with robust fallbacks."""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('AI返回为空')
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

    try:
        obj = parse_json_object_from_ai_text(raw)
        if isinstance(obj, dict):
            for key in ('page_html', 'html', 'content'):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    raw = value.strip()
                    break
    except Exception:
        pass

    lower = raw.lower()
    idx = lower.find('<!doctype html')
    if idx < 0:
        idx = lower.find('<html')
    html_text = raw[idx:].strip() if idx >= 0 else raw
    if '<html' in html_text.lower():
        return html_text

    fragment = html_text.strip()
    if any(tag in fragment.lower() for tag in ('<body', '<main', '<section', '<div', '<h1', '<h2', '<p')):
        return (
            "<!DOCTYPE html>\n"
            "<html lang=\"zh-CN\">\n"
            "<head>\n"
            "  <meta charset=\"UTF-8\">\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"  <title>{html.escape(title or '产品页面')}</title>\n"
            "</head>\n"
            "<body>\n"
            f"{fragment}\n"
            "</body>\n"
            "</html>"
        )

    preview = re.sub(r'\s+', ' ', raw)[:220]
    raise ValueError(f'AI未返回可识别的HTML（片段预览: {preview}）')


def build_product_content_html_from_template_fields(template_fields: dict):
    """Build editor content_html from template fields for admin edit backfill."""
    d1 = str((template_fields or {}).get('【产品详情1】', '') or '').strip()
    d2 = str((template_fields or {}).get('【产品详情2】', '') or '').strip()
    parts = []
    if d1:
        parts.append(f"<p>{html.escape(d1)}</p>")
    if d2:
        parts.append(f"<p>{html.escape(d2)}</p>")
    if not parts:
        parts.append("<p>请填写产品详情内容</p>")
    return ''.join(parts)


def _normalize_text_lines(value):
    """Normalize multiline / comma-separated text into clean non-empty lines."""
    if value is None:
        return []
    if isinstance(value, list):
        raw = '\n'.join([str(x or '') for x in value])
    else:
        raw = str(value)
    raw = raw.replace('\r', '\n')
    raw = raw.replace('，', ',').replace('；', ';')
    parts = re.split(r'[\n,;]+', raw)
    return [p.strip() for p in parts if p and p.strip()]


def _build_product_ai_html_messages(
    title,
    short_name,
    category,
    image_url,
    summary,
    context_text,
    detail_image_urls='',
    news_urls='',
    related_product_urls='',
):
    """Build system/user messages for product full-html generation."""
    ai_cfg = _dep('get_product_page_ai_config')()
    reference_html = get_product_ai_reference_html()
    system_prompt = _dep('get_product_page_ai_system_prompt')()
    detail_images = _normalize_text_lines(detail_image_urls)
    news_links = _normalize_text_lines(news_urls)
    related_links = _normalize_text_lines(related_product_urls)
    detail_images_block = '\n'.join([f"  - {u}" for u in detail_images]) if detail_images else '  - （无）'
    news_links_block = '\n'.join([f"  - {u}" for u in news_links]) if news_links else '  - （无）'
    related_links_block = '\n'.join([f"  - {u}" for u in related_links]) if related_links else '  - （无）'
    user_prompt = (
        "请基于“参考样例HTML”和“产品资料”直接生成完整产品页HTML文件。\n"
        "硬性要求：\n"
        "1) 输出必须是完整HTML文档（包含 <!DOCTYPE html> ... </html>）。\n"
        "2) 请直接开始写代码，代码写完后不要添加任何其他内容。\n"
        "3) 只输出HTML，不要解释、不要Markdown代码块。\n"
        "4) 必须参考模板结构与样式，保留可复用的布局和资源引用，不要删掉关键脚本/样式。\n"
        "5) 内容按资料进行替换与完善，不能编造资质证书、认证、客户案例。\n"
        "6) 必须确保页面中有可见图片：主图、详情图、新闻图、相关产品图至少要有可显示来源。\n"
        "7) 若某类图片URL未提供，可优先复用主图或详情图首图，最后兜底 /assets/images/logo.png。\n"
        "8) 相关新闻与相关产品区块必须保留，并尽量使用提供的 URL 生成链接。\n\n"
        "9) 相关新闻区块必须包含 `.vs-related-news .vs-news-grid` 结构。\n"
        "10) 相关产品区块必须包含 `.vs-related-products .vs-related-grid` 结构。\n"
        "11) 必须保留 `<script src=\"/assets/js/nav-loader.js\"></script>` 以支持动态数据填充。\n\n"
        f"产品资料：\n"
        f"- 产品标题: {title}\n"
        f"- 产品简称: {short_name}\n"
        f"- 产品分类: {category}\n"
        f"- 产品主图URL: {image_url or '/assets/images/logo.png'}\n"
        f"- 产品摘要: {summary or '（请你生成）'}\n"
        f"- 产品详情图片URL列表:\n{detail_images_block}\n"
        f"- 相关新闻URL列表:\n{news_links_block}\n"
        f"- 相关产品URL列表:\n{related_links_block}\n"
        f"- 详细补充资料:\n{context_text or '（无）'}\n\n"
        "参考样例HTML如下（请以此为参考生成最终完整HTML）:\n"
        f"{reference_html}"
    )
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]
    return messages, ai_cfg


def _ensure_html_tail(page_html: str) -> str:
    """Best-effort close missing body/html tail when output is truncated."""
    txt = (page_html or '').strip()
    if '<html' not in txt.lower():
        return txt
    low = txt.lower()
    if '</body>' not in low:
        txt += '\n</body>'
        low = txt.lower()
    if '</html>' not in low:
        txt += '\n</html>'
    return txt


def _is_html_complete(page_html: str) -> bool:
    return '</html>' in (page_html or '').lower()


def _continuation_prompt():
    return (
        "你上一次输出被截断。请仅从中断处继续输出剩余 HTML 代码，"
        "不要重复之前已输出内容，不要解释，直到输出到 </html> 结束。"
    )


def _insert_before_last_tag(text: str, tag: str, snippet: str) -> str:
    pattern = re.compile(rf'</{re.escape(tag)}\s*>', re.I)
    matches = list(pattern.finditer(text or ''))
    if matches:
        match = matches[-1]
        return (text or '')[:match.start()] + snippet + '\n' + (text or '')[match.start():]
    return (text or '') + '\n' + snippet


def _build_related_section_html(section_class: str, title: str, grid_class: str, loading_text: str) -> str:
    return (
        f'<section class="{section_class}">\n'
        '    <div class="vs-container">\n'
        f'        <h2>{title}</h2>\n'
        f'        <div class="{grid_class}">\n'
        f'            <p style="grid-column: 1/-1; text-align:center; color:#64748b;">{loading_text}</p>\n'
        '        </div>\n'
        '    </div>\n'
        '</section>'
    )


def ensure_product_dynamic_sections(page_html: str) -> str:
    """Post-process AI HTML to ensure related-news/products dynamic blocks are renderable."""
    text = str(page_html or '')
    if not text.strip():
        return text

    if not re.search(r'<script[^>]*src=["\']/assets/js/nav-loader\.js["\']', text, re.I):
        nav_script = '<script src="/assets/js/nav-loader.js"></script>'
        if re.search(r'</head\s*>', text, re.I):
            text = _insert_before_last_tag(text, 'head', nav_script)
        else:
            text = _insert_before_last_tag(text, 'body', nav_script)

    checks = [
        ('vs-related-news', '相关新闻', 'vs-news-grid', '正在加载相关新闻...'),
        ('vs-related-products', '相关产品', 'vs-related-grid', '正在加载相关产品...'),
    ]

    for section_class, title, grid_class, loading_text in checks:
        section_pattern = re.compile(
            rf'<section[^>]*class=["\'][^"\']*\b{re.escape(section_class)}\b[^"\']*["\'][^>]*>.*?</section>',
            re.S | re.I,
        )
        grid_pattern = re.compile(
            rf'class=["\'][^"\']*\b{re.escape(grid_class)}\b[^"\']*["\']',
            re.I,
        )
        section_html = _build_related_section_html(section_class, title, grid_class, loading_text)
        match = section_pattern.search(text)
        if not match:
            if re.search(r'</main\s*>', text, re.I):
                text = _insert_before_last_tag(text, 'main', section_html)
            else:
                text = _insert_before_last_tag(text, 'body', section_html)
            continue
        if not grid_pattern.search(match.group(0)):
            text = text[:match.start()] + section_html + text[match.end():]

    return text


def _build_product_ai_revise_messages(
    title,
    category,
    image_url,
    detail_image_urls,
    news_urls,
    related_product_urls,
    summary,
    context_text,
    instruction,
    current_html,
):
    """Build system/user messages for product HTML revise workflow."""
    system_prompt = _dep('get_product_page_ai_system_prompt')()
    detail_images = _normalize_text_lines(detail_image_urls)
    news_links = _normalize_text_lines(news_urls)
    related_links = _normalize_text_lines(related_product_urls)
    detail_images_block = '\n'.join([f"  - {u}" for u in detail_images]) if detail_images else '  - （无）'
    news_links_block = '\n'.join([f"  - {u}" for u in news_links]) if news_links else '  - （无）'
    related_links_block = '\n'.join([f"  - {u}" for u in related_links]) if related_links else '  - （无）'
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': (
            "请基于下方“当前HTML代码”和“修改意见”输出一份修改后的完整HTML。\n"
            "要求：\n"
            "1) 只输出完整HTML代码，不要解释，不要Markdown代码块。\n"
            "2) 尽量保留原有结构和样式，仅按修改意见调整。\n"
            "3) 输出必须从 <!DOCTYPE html> 或 <html> 开始，并在 </html> 结束。\n\n"
            "4) 相关新闻区块必须保留 `.vs-related-news .vs-news-grid` 结构。\n"
            "5) 相关产品区块必须保留 `.vs-related-products .vs-related-grid` 结构。\n"
            "6) 必须保留 `<script src=\"/assets/js/nav-loader.js\"></script>`。\n\n"
            "产品资料补充（用于保证图片和链接完整，可结合修改意见一起处理）：\n"
            f"- 产品标题: {title}\n"
            f"- 产品分类: {category}\n"
            f"- 产品主图URL: {image_url or '/assets/images/logo.png'}\n"
            f"- 产品摘要: {summary or '（未填写）'}\n"
            f"- 产品详情图片URL列表:\n{detail_images_block}\n"
            f"- 相关新闻URL列表:\n{news_links_block}\n"
            f"- 相关产品URL列表:\n{related_links_block}\n"
            f"- 详细补充资料:\n{context_text or '（无）'}\n\n"
            f"修改意见：\n{instruction}\n\n"
            f"当前HTML代码：\n{current_html}"
        )},
    ]


def extract_product_meta_from_html(filepath):
    """从产品HTML文件中提取meta标签信息"""

    class ProductMetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.meta = {}
            self.title = ''
            self.in_title = False
            self.first_h1 = ''
            self.in_h1 = False
            self.first_p = ''
            self.in_p = False
            self.found_h1 = False
            self.found_p = False
            self.first_img = ''

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)

            if tag == 'meta':
                name = attrs_dict.get('name', '')
                content = attrs_dict.get('content', '')
                if name.startswith('product-'):
                    key = name.replace('product-', '')
                    self.meta[key] = content
            elif tag == 'title':
                self.in_title = True
            elif tag == 'h1' and not self.found_h1:
                self.in_h1 = True
            elif tag == 'p' and self.found_h1 and not self.found_p:
                self.in_p = True
            elif tag == 'img' and not self.first_img and 'src' in attrs_dict:
                src = attrs_dict['src']
                if not any(x in src.lower() for x in ['icon', 'logo', 'arrow', 'btn', 'button']):
                    self.first_img = src

        def handle_data(self, data):
            data = data.strip()
            if self.in_title:
                self.title = data
            elif self.in_h1:
                self.first_h1 += data
            elif self.in_p:
                self.first_p += data

        def handle_endtag(self, tag):
            if tag == 'title':
                self.in_title = False
            elif tag == 'h1':
                self.in_h1 = False
                self.found_h1 = True
            elif tag == 'p':
                self.in_p = False
                if self.first_p:
                    self.found_p = True

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        parser = ProductMetaParser()
        parser.feed(content)

        product_id = filepath.stem
        name = parser.meta.get('name', '') or parser.first_h1 or parser.title.replace(' - 元芯传感', '').replace(' - 气体传感产品', '').strip()
        if not name:
            return None

        short_name = parser.meta.get('short-name', '')
        if not short_name:
            short_name = name[:20] + ('...' if len(name) > 20 else '')

        main_img = re.search(r'<img[^>]*id="mainImage"[^>]*src="([^"]+)"', content, re.I)
        gallery_thumb = re.search(
            r'<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>.*?<img[^>]*src="([^"]+)"',
            content, re.S | re.I,
        )
        image = (
            parser.meta.get('image', '')
            or (main_img.group(1) if main_img else '')
            or (gallery_thumb.group(1) if gallery_thumb else '')
            or parser.first_img
        )

        description = parser.meta.get('description', '') or parser.first_p[:200] if parser.first_p else ''
        category = parser.meta.get('category', '') or _dep('default_product_categories').get(product_id, 'module')

        return {
            'id': product_id,
            'name': name,
            'shortName': short_name,
            'image': image,
            'description': description,
            'category': category,
        }
    except Exception as e:
        print(f"Error parsing product file {filepath}: {e}")
        return None


def register_product_editor_routes(
    app,
    *,
    login_required,
    app_root,
    require_super_admin_api,
    render_markdown,
    get_product_page_ai_config,
    get_product_page_ai_system_prompt,
    get_product_settings,
    save_product_settings,
    default_product_categories,
    normalize_ai_product_image_extension,
    infer_ai_product_image_extension_from_mime,
    allowed_ai_product_image_mime_types,
):
    """Register product editor/admin routes."""
    configure_product_editor(
        app_root=app_root,
        require_super_admin_api=require_super_admin_api,
        render_markdown=render_markdown,
        get_product_page_ai_config=get_product_page_ai_config,
        get_product_page_ai_system_prompt=get_product_page_ai_system_prompt,
        get_product_settings=get_product_settings,
        save_product_settings=save_product_settings,
        default_product_categories=default_product_categories,
        normalize_ai_product_image_extension=normalize_ai_product_image_extension,
        infer_ai_product_image_extension_from_mime=infer_ai_product_image_extension_from_mime,
        allowed_ai_product_image_mime_types=allowed_ai_product_image_mime_types,
    )

    @app.route('/api/products/template/placeholders')
    @login_required
    def get_product_template_placeholders_api():
        """Get placeholder list from product template for admin visual form."""
        placeholders = extract_product_template_placeholders(get_product_template_html())
        return jsonify({'items': placeholders, 'count': len(placeholders)})

    @app.route('/api/products/ai-generate-html', methods=['POST'])
    @login_required
    def ai_generate_product_html():
        """Generate full product HTML by AI with template.html as reference."""
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or 'sensor').strip()
        image_url = (data.get('image_url') or '').strip()
        detail_image_urls = (data.get('detail_image_urls') or '').strip()
        news_urls = (data.get('news_urls') or '').strip()
        related_product_urls = (data.get('related_product_urls') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or '').strip()

        if not title or not short_name:
            return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

        messages, ai_cfg = _build_product_ai_html_messages(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url,
            summary=summary,
            context_text=context_text,
            detail_image_urls=detail_image_urls,
            news_urls=news_urls,
            related_product_urls=related_product_urls,
        )
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        response_text = ''
        attempts_used = 0
        for _ in range(3):
            attempts_used += 1
            piece, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
            if error:
                return jsonify({'success': False, 'message': error}), 502
            piece = piece or ''
            response_text += piece
            if _is_html_complete(response_text):
                break
            messages.append({'role': 'assistant', 'content': piece})
            messages.append({'role': 'user', 'content': _continuation_prompt()})

        try:
            page_html = extract_html_from_ai_text(_ensure_html_tail(response_text), title=title)
            page_html = ensure_product_dynamic_sections(page_html)
        except Exception as e:
            return jsonify({'success': False, 'message': f'AI输出HTML解析失败: {str(e)}'}), 500

        return jsonify({'success': True, 'page_html': page_html, 'attempts_used': attempts_used})

    @app.route('/api/products/ai-upload-images', methods=['POST'])
    @login_required
    def ai_upload_product_images():
        """Upload AI product images into pages/gassensing/<MODEL>/ folder."""
        slug = (request.form.get('slug') or '').strip().lower()
        short_name = (request.form.get('short_name') or '').strip()
        files = request.files.getlist('files')

        if not slug or not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '请提供合法链接标识（小写字母/数字/下划线）'}), 400
        if not files:
            return jsonify({'success': False, 'message': '请至少上传一张图片'}), 400

        slug_dash = slug.replace('_', '-')
        model_folder = re.sub(r'[^A-Za-z0-9._-]+', '', short_name.upper()) if short_name else ''
        if not model_folder:
            model_folder = slug_dash.upper()

        target_dir = _gassensing_products_dir() / model_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(target_dir.glob(f'{slug_dash}-product-*.*'))
        counter = len(existing) + 1
        urls = []

        for uploaded in files:
            original_name = uploaded.filename or ''
            mime = (uploaded.mimetype or uploaded.content_type or '').lower()
            sample = b''
            try:
                stream = uploaded.stream
                current_pos = stream.tell()
                sample = stream.read(1024)
                stream.seek(current_pos)
            except Exception:
                sample = b''

            ext = _dep('normalize_ai_product_image_extension')(original_name, mime, sample)
            if not ext:
                display_ext = Path((original_name or '')).suffix.lower() or '未知'
                return jsonify({
                    'success': False,
                    'message': (
                        f'不支持的图片格式: {display_ext}。'
                        '支持 PNG/JPG/JPEG/WEBP/BMP/GIF/TIF/TIFF/HEIC/HEIF/AVIF'
                    ),
                }), 400

            mime_clean = (mime or '').split(';')[0].strip().lower()
            if mime_clean and mime_clean.startswith('image/') and mime_clean not in _dep('allowed_ai_product_image_mime_types'):
                inferred_from_mime = _dep('infer_ai_product_image_extension_from_mime')(mime_clean)
                if not inferred_from_mime:
                    return jsonify({'success': False, 'message': f'文件类型不受支持: {mime_clean}'}), 400

            while True:
                filename = f'{slug_dash}-product-{counter:02d}{ext}'
                filepath = target_dir / filename
                if not filepath.exists():
                    break
                counter += 1

            uploaded.save(str(filepath))
            urls.append(f'/pages/gassensing/{model_folder}/{filename}')
            counter += 1

        return jsonify({'success': True, 'folder': model_folder, 'urls': urls})

    @app.route('/api/products/ai-generate-html-stream', methods=['POST'])
    @login_required
    def ai_generate_product_html_stream():
        """Generate full product HTML by AI with streaming + auto continuation."""
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or 'sensor').strip()
        image_url = (data.get('image_url') or '').strip()
        detail_image_urls = (data.get('detail_image_urls') or '').strip()
        news_urls = (data.get('news_urls') or '').strip()
        related_product_urls = (data.get('related_product_urls') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or '').strip()

        if not title or not short_name:
            return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

        messages, ai_cfg = _build_product_ai_html_messages(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url,
            summary=summary,
            context_text=context_text,
            detail_image_urls=detail_image_urls,
            news_urls=news_urls,
            related_product_urls=related_product_urls,
        )
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        def generate():
            accumulated = ''
            for round_idx in range(3):
                if round_idx > 0:
                    yield f"data: {json.dumps({'type': 'retry', 'attempt': round_idx + 1, 'message': '检测到输出被截断，正在自动续写...'}, ensure_ascii=False)}\n\n"

                stream = call_openai_api_stream_with_custom_config(messages, ai_cfg)
                if isinstance(stream, tuple):
                    _, err = stream
                    yield f"data: {json.dumps({'type': 'error', 'error': err or 'API调用失败'}, ensure_ascii=False)}\n\n"
                    return

                round_text = ''
                for chunk, err in stream:
                    if err:
                        yield f"data: {json.dumps({'type': 'error', 'error': err}, ensure_ascii=False)}\n\n"
                        return
                    if not chunk:
                        continue
                    round_text += chunk
                    accumulated += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

                if _is_html_complete(accumulated):
                    break

                messages.append({'role': 'assistant', 'content': round_text or accumulated[-4000:]})
                messages.append({'role': 'user', 'content': _continuation_prompt()})

            accumulated = _ensure_html_tail(accumulated)
            try:
                page_html = extract_html_from_ai_text(accumulated, title=title)
                page_html = ensure_product_dynamic_sections(page_html)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'AI输出HTML解析失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'done', 'page_html': page_html}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    @app.route('/api/products/ai-revise-html-stream', methods=['POST'])
    @login_required
    def ai_revise_product_html_stream():
        """Revise already-generated HTML by user instruction (streaming)."""
        data = request.json or {}
        title = (data.get('title') or '').strip() or '产品页面'
        category = (data.get('category') or 'sensor').strip()
        image_url = (data.get('image_url') or '').strip()
        detail_image_urls = (data.get('detail_image_urls') or '').strip()
        news_urls = (data.get('news_urls') or '').strip()
        related_product_urls = (data.get('related_product_urls') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or '').strip()
        instruction = (data.get('instruction') or '').strip()
        current_html = (data.get('current_html') or '').strip()

        if not instruction:
            return jsonify({'success': False, 'message': '请先填写修改意见'}), 400
        if '<html' not in current_html.lower():
            return jsonify({'success': False, 'message': '当前HTML为空或格式无效，请先生成HTML'}), 400

        ai_cfg = _dep('get_product_page_ai_config')()
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        messages = _build_product_ai_revise_messages(
            title=title,
            category=category,
            image_url=image_url,
            detail_image_urls=detail_image_urls,
            news_urls=news_urls,
            related_product_urls=related_product_urls,
            summary=summary,
            context_text=context_text,
            instruction=instruction,
            current_html=current_html,
        )

        def generate():
            accumulated = ''
            for round_idx in range(3):
                if round_idx > 0:
                    yield f"data: {json.dumps({'type': 'retry', 'attempt': round_idx + 1, 'message': '检测到输出被截断，正在自动续写...'}, ensure_ascii=False)}\n\n"

                stream = call_openai_api_stream_with_custom_config(messages, ai_cfg)
                if isinstance(stream, tuple):
                    _, err = stream
                    yield f"data: {json.dumps({'type': 'error', 'error': err or 'API调用失败'}, ensure_ascii=False)}\n\n"
                    return

                round_text = ''
                for chunk, err in stream:
                    if err:
                        yield f"data: {json.dumps({'type': 'error', 'error': err}, ensure_ascii=False)}\n\n"
                        return
                    if not chunk:
                        continue
                    round_text += chunk
                    accumulated += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

                if _is_html_complete(accumulated):
                    break

                messages.append({'role': 'assistant', 'content': round_text or accumulated[-4000:]})
                messages.append({'role': 'user', 'content': _continuation_prompt()})

            accumulated = _ensure_html_tail(accumulated)
            try:
                page_html = extract_html_from_ai_text(accumulated, title=title)
                page_html = ensure_product_dynamic_sections(page_html)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'AI输出HTML解析失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'done', 'page_html': page_html}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    @app.route('/api/products/ai-revise-html', methods=['POST'])
    @login_required
    def ai_revise_product_html():
        """Revise already-generated HTML by user instruction (non-stream fallback)."""
        data = request.json or {}
        title = (data.get('title') or '').strip() or '产品页面'
        category = (data.get('category') or 'sensor').strip()
        image_url = (data.get('image_url') or '').strip()
        detail_image_urls = (data.get('detail_image_urls') or '').strip()
        news_urls = (data.get('news_urls') or '').strip()
        related_product_urls = (data.get('related_product_urls') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or '').strip()
        instruction = (data.get('instruction') or '').strip()
        current_html = (data.get('current_html') or '').strip()

        if not instruction:
            return jsonify({'success': False, 'message': '请先填写修改意见'}), 400
        if '<html' not in current_html.lower():
            return jsonify({'success': False, 'message': '当前HTML为空或格式无效，请先生成HTML'}), 400

        ai_cfg = _dep('get_product_page_ai_config')()
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        messages = _build_product_ai_revise_messages(
            title=title,
            category=category,
            image_url=image_url,
            detail_image_urls=detail_image_urls,
            news_urls=news_urls,
            related_product_urls=related_product_urls,
            summary=summary,
            context_text=context_text,
            instruction=instruction,
            current_html=current_html,
        )

        response_text = ''
        attempts_used = 0
        for _ in range(3):
            attempts_used += 1
            piece, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
            if error:
                return jsonify({'success': False, 'message': error}), 502
            piece = piece or ''
            response_text += piece
            if _is_html_complete(response_text):
                break
            messages.append({'role': 'assistant', 'content': piece or response_text[-4000:]})
            messages.append({'role': 'user', 'content': _continuation_prompt()})

        try:
            page_html = extract_html_from_ai_text(_ensure_html_tail(response_text), title=title)
            page_html = ensure_product_dynamic_sections(page_html)
        except Exception as e:
            return jsonify({'success': False, 'message': f'AI输出HTML解析失败: {str(e)}'}), 500

        return jsonify({'success': True, 'page_html': page_html, 'attempts_used': attempts_used})

    @app.route('/api/products/ai-create-html', methods=['POST'])
    @login_required
    def ai_create_product_from_html():
        """Save AI-generated full HTML as a product page file."""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        slug = (data.get('slug') or '').strip()
        page_html = (data.get('page_html') or '').strip()

        if not title or not category or not slug:
            return jsonify({'success': False, 'message': '请填写标题、分类和链接标识'}), 400
        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400
        if '<html' not in page_html.lower():
            return jsonify({'success': False, 'message': 'HTML源码无效，请先生成完整HTML'}), 400
        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        if not short_name:
            short_name = slug.replace('_', '-').upper()
        if not summary:
            summary = title

        page_html = ensure_product_dynamic_sections(page_html)
        enriched_html = inject_product_meta_tags(
            page_html=page_html,
            title=title,
            short_name=short_name,
            image_url=image_url or '/assets/images/logo.png',
            summary=summary,
            category=category,
        )

        admin_payload = {
            'version': 3,
            'title': title,
            'short_name': short_name,
            'category': category,
            'image_url': image_url or '/assets/images/logo.png',
            'summary': summary,
            'content_html': '',
            'template_fields': {},
            'source': 'ai-full-html',
        }
        marker = encode_product_admin_data(admin_payload)
        if '</body>' in enriched_html:
            enriched_html = enriched_html.replace('</body>', marker + '\n</body>', 1)
        else:
            enriched_html += '\n' + marker

        products_dir = _gassensing_products_dir()
        products_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{slug}.html'
        filepath = products_dir / filename
        if filepath.exists():
            return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409
        filepath.write_text(enriched_html, encoding='utf-8')
        return jsonify({'success': True, 'filename': filename, 'link': f'/pages/gassensing/{filename}'})

    @app.route('/api/products/ai-generate-fields', methods=['POST'])
    @login_required
    def ai_generate_product_template_fields():
        """Generate template fields by product-page coding AI."""
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or 'sensor').strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or '').strip()

        if not title or not short_name:
            return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

        ai_cfg = _dep('get_product_page_ai_config')()
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        placeholders = extract_product_template_placeholders(get_product_template_html())
        defaults = build_product_template_defaults(
            title=title,
            summary=summary,
            image_url=image_url or '/assets/images/logo.png',
            detail1='',
            detail2='',
        )
        system_prompt = _dep('get_product_page_ai_system_prompt')()
        user_prompt = (
            "请根据以下资料，生成模板字段 JSON。\n"
            f"产品标题: {title}\n"
            f"产品简称: {short_name}\n"
            f"产品分类: {category}\n"
            f"封面图: {image_url}\n"
            f"产品摘要: {summary}\n\n"
            f"补充资料:\n{context_text or '（无）'}\n\n"
            f"可用占位符列表（只能使用这些 key）:\n{json.dumps(placeholders, ensure_ascii=False)}\n\n"
            f"默认字段（可参考）:\n{json.dumps(defaults, ensure_ascii=False)}\n"
        )
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        response_text, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
        if error:
            return jsonify({'success': False, 'message': error}), 502

        try:
            parsed = parse_json_object_from_ai_text(response_text or '')
        except Exception as e:
            return jsonify({'success': False, 'message': f'AI输出解析失败: {str(e)}'}), 500

        ai_title = str(parsed.get('title') or title).strip() or title
        ai_short = str(parsed.get('short_name') or short_name).strip() or short_name
        ai_summary = str(parsed.get('summary') or summary).strip() or summary
        ai_fields_raw = parsed.get('template_fields', parsed if isinstance(parsed, dict) else {})
        ai_fields = normalize_product_template_fields(ai_fields_raw if isinstance(ai_fields_raw, dict) else {})

        merged = dict(defaults)
        for key in placeholders:
            if key in ai_fields and str(ai_fields[key]).strip():
                merged[key] = str(ai_fields[key]).strip()

        for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
            merged[key] = ai_title
        if ai_summary:
            merged['【产品描述】'] = ai_summary
        if image_url:
            merged['【主图链接】'] = image_url
            if not merged.get('【缩略图1链接】'):
                merged['【缩略图1链接】'] = image_url

        return jsonify({
            'success': True,
            'title': ai_title,
            'short_name': ai_short,
            'summary': ai_summary,
            'template_fields': merged,
        })

    @app.route('/api/products/ai-create', methods=['POST'])
    @login_required
    def ai_create_gassensing_product():
        """Create product HTML from AI-generated template fields."""
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        slug = (data.get('slug') or '').strip()
        template_fields = normalize_product_template_fields(data.get('template_fields', {}))

        if not title or not short_name or not category or not summary or not slug:
            return jsonify({'success': False, 'message': '请填写标题、简称、分类、链接标识和摘要'}), 400
        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400
        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        content_html = build_product_content_html_from_template_fields(template_fields)
        html_text, _ = render_gassensing_product_html(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url or '/assets/images/logo.png',
            summary=summary,
            content_html=content_html,
            template_fields=template_fields,
        )

        products_dir = _gassensing_products_dir()
        products_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{slug}.html'
        filepath = products_dir / filename
        if filepath.exists():
            return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409

        filepath.write_text(html_text, encoding='utf-8')
        return jsonify({'success': True, 'filename': filename, 'link': f'/pages/gassensing/{filename}'})

    @app.route('/api/products/create', methods=['POST'])
    @login_required
    def create_gassensing_product():
        """Create a gassensing product detail page from admin visual form."""
        data = request.json or {}
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        slug = (data.get('slug') or '').strip()
        content = (data.get('content') or '').strip()
        content_is_html = bool(data.get('content_is_html', False))
        template_fields = normalize_product_template_fields(data.get('template_fields', {}))

        if not title or not short_name or not category or not summary or not slug or not content:
            return jsonify({'success': False, 'message': '请填写标题、简称、分类、链接标识、摘要和正文'}), 400

        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400

        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        content_html = content if content_is_html else _dep('render_markdown')(content)
        html_text, _ = render_gassensing_product_html(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url or '/assets/images/logo.png',
            summary=summary,
            content_html=content_html,
            template_fields=template_fields,
        )

        products_dir = _gassensing_products_dir()
        products_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{slug}.html'
        filepath = products_dir / filename
        if filepath.exists():
            return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409

        filepath.write_text(html_text, encoding='utf-8')
        return jsonify({
            'success': True,
            'filename': filename,
            'link': f'/pages/gassensing/{filename}',
        })

    @app.route('/api/products/detail')
    @login_required
    def get_product_detail():
        """Get one gassensing product detail for admin visual editing."""
        product_id = (request.args.get('id') or '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        if product_id.startswith('../'):
            return jsonify({'success': False, 'message': '该产品不在气体传感目录，暂不支持可视化编辑'}), 400
        if not re.fullmatch(r'[a-z0-9_]+', product_id):
            return jsonify({'success': False, 'message': '产品ID不合法'}), 400

        filepath = _gassensing_products_dir() / f'{product_id}.html'
        detail = parse_gassensing_product_detail(filepath)
        if not detail:
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        return jsonify({'success': True, 'detail': detail})

    @app.route('/api/products/update', methods=['POST'])
    @login_required
    def update_gassensing_product():
        """Update an existing gassensing product detail page."""
        data = request.json or {}
        original_slug = (data.get('original_slug') or '').strip()
        slug = (data.get('slug') or '').strip()
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        content = (data.get('content') or '').strip()
        content_is_html = bool(data.get('content_is_html', False))
        template_fields = normalize_product_template_fields(data.get('template_fields', {}))

        if not original_slug or not slug:
            return jsonify({'success': False, 'message': '缺少原始链接标识或新链接标识'}), 400
        if not title or not short_name or not category or not summary or not content:
            return jsonify({'success': False, 'message': '请填写标题、简称、分类、摘要和正文'}), 400
        if not re.fullmatch(r'[a-z0-9_]+', original_slug) or not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400

        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        products_dir = _gassensing_products_dir()
        old_path = products_dir / f'{original_slug}.html'
        if not old_path.exists():
            return jsonify({'success': False, 'message': '原产品文件不存在'}), 404
        new_path = products_dir / f'{slug}.html'
        if slug != original_slug and new_path.exists():
            return jsonify({'success': False, 'message': f'目标文件已存在：{slug}.html'}), 409

        content_html = content if content_is_html else _dep('render_markdown')(content)
        html_text, _ = render_gassensing_product_html(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url or '/assets/images/logo.png',
            summary=summary,
            content_html=content_html,
            template_fields=template_fields,
        )

        if slug != original_slug:
            try:
                old_path.unlink()
            except Exception:
                pass
        new_path.write_text(html_text, encoding='utf-8')

        if slug != original_slug:
            settings = _dep('get_product_settings')()
            if original_slug in settings:
                settings[slug] = settings.get(original_slug, {})
                settings.pop(original_slug, None)
                _dep('save_product_settings')(settings)

        return jsonify({
            'success': True,
            'filename': f'{slug}.html',
            'link': f'/pages/gassensing/{slug}.html',
        })

    @app.route('/api/products/preview-page', methods=['POST'])
    @login_required
    def preview_product_page():
        """Render full gassensing product page HTML for admin live preview."""
        data = request.json or {}
        title = (data.get('title') or '').strip() or '产品标题'
        short_name = (data.get('short_name') or '').strip() or title
        category = (data.get('category') or '').strip() or 'sensor'
        image_url = (data.get('image_url') or '').strip() or '/assets/images/logo.png'
        summary = (data.get('summary') or '').strip() or '产品摘要'
        content = (data.get('content') or '').strip() or '<p>请填写产品详情内容</p>'
        content_is_html = bool(data.get('content_is_html', False))
        template_fields = normalize_product_template_fields(data.get('template_fields', {}))
        content_html = content if content_is_html else _dep('render_markdown')(content)

        page_html, _ = render_gassensing_product_html(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url,
            summary=summary,
            content_html=content_html,
            template_fields=template_fields,
        )

        resize_bridge = """
<script>
(function () {
  function sendHeight() {
    var h = Math.max(
      document.body ? document.body.scrollHeight : 0,
      document.documentElement ? document.documentElement.scrollHeight : 0
    );
    try { parent.postMessage({ type: 'product-preview-height', height: h }, '*'); } catch (e) {}
  }
  window.addEventListener('load', sendHeight);
  window.addEventListener('resize', sendHeight);
  setTimeout(sendHeight, 100);
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1200);
})();
</script>
"""
        if '</body>' in page_html:
            page_html = page_html.replace('</body>', resize_bridge + '\n</body>')
        else:
            page_html += resize_bridge

        return jsonify({'success': True, 'page_html': page_html})


__all__ = [
    'extract_product_meta_from_html',
    'register_product_editor_routes',
]
