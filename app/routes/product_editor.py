"""
产品编辑与产品页HTML处理路由模块。

本模块提供产品页面的编辑和管理功能，支持模板编辑、
文件上传下载、AI辅助内容生成等功能。

主要功能：
1. 产品页面模板
   - HTML模板读取
   - 模板字段提取
   - 模板结构解析

2. 字段与区块编辑
   - 页面字段编辑
   - 区块内容管理
   - 配置保存

3. 文件管理
   - 产品图片上传
   - 图片AI处理
   - 文件下载
   - 文件删除

4. AI辅助内容
   - 产品页AI配置
   - AI参考内容获取
   - Markdown渲染

5. 产品管理
   - 产品列表获取
   - 产品详情获取
   - 产品新增/删除
   - 精选产品管理

6. 解决方案管理
   - 氢气解决方案配置
   - 方案产品关联
   - 方案精选管理

作者：元芯传感技术团队
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import json
import re
import threading
import uuid
from html.parser import HTMLParser
from pathlib import Path

from flask import Response, jsonify, request, send_file, session, stream_with_context

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


# 模块级依赖容器，在 configure/register 阶段一次性注入。
_DEPS = {}
PRODUCT_ADMIN_DATA_PREFIX = 'MC_PRODUCT_ADMIN_DATA:'
ALLOWED_PRODUCT_CATEGORIES = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}
PRODUCT_AI_DRAFTS_LOCK = threading.Lock()
PRODUCT_SECTION_TEXT_KEYS = {'title', 'description', 'detail', 'app_intro', 'cta_title', 'cta_desc'}
PRODUCT_SECTION_LIST_KEYS = {
    'images',
    'highlights',
    'advantages',
    'applications',
    'specs',
    'news',
    'related_products',
}
PRODUCT_SECTION_KEYS = PRODUCT_SECTION_TEXT_KEYS | PRODUCT_SECTION_LIST_KEYS
PRODUCT_AI_DRAFT_STATUSES = {'draft', 'generated', 'published'}
PRODUCT_AI_DRAFT_MODES = {'structured', 'html'}

PRODUCT_SPECS_MOBILE_GUARD = """

        /* Product Specs Mobile Guard */
        @media (max-width: 900px) {
            .vs-specs-table {
                display: block !important;
                width: 100% !important;
                max-width: 100% !important;
                border: 0 !important;
                border-collapse: separate !important;
                border-spacing: 0 !important;
                background: transparent !important;
                box-shadow: none !important;
            }

            .vs-specs-table tbody {
                display: grid !important;
                width: 100% !important;
                gap: 12px !important;
            }

            .vs-specs-table tr {
                display: grid !important;
                grid-template-columns: minmax(96px, 34%) minmax(0, 1fr) !important;
                width: 100% !important;
                margin: 0 !important;
                overflow: hidden !important;
                border-radius: 14px !important;
                background: #ffffff !important;
                box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08) !important;
            }

            .vs-specs-table td {
                display: flex !important;
                align-items: center !important;
                width: auto !important;
                min-width: 0 !important;
                min-height: 64px !important;
                padding: 16px 18px !important;
                border: 0 !important;
                line-height: 1.65 !important;
                overflow-wrap: anywhere !important;
                word-break: break-word !important;
            }

            .vs-specs-table tr td:first-child {
                border-radius: 0 !important;
                border-bottom: 0 !important;
                background: linear-gradient(180deg, #0b4a7c 0%, #083f6a 100%) !important;
                color: #ffffff !important;
                font-size: 15px !important;
                font-weight: 700 !important;
            }

            .vs-specs-table tr td:last-child {
                border-radius: 0 !important;
                background: #ffffff !important;
                color: #26364d !important;
                font-size: 15px !important;
                font-weight: 500 !important;
            }
        }
"""



# 依赖注入配置入口。
def configure_product_editor(
    *,
    app_root,
    require_super_admin_api,
    render_markdown,
    get_product_page_ai_config,
    get_product_page_ai_system_prompt,
    get_product_settings,
    save_product_settings,
    product_featured_file,
    excluded_product_files,
    hydrogen_solutions_config_file,
    get_hydrogen_solution_products_config,
    save_hydrogen_solution_products_config,
    default_product_categories,
    normalize_ai_product_image_extension,
    infer_ai_product_image_extension_from_mime,
    allowed_ai_product_image_mime_types,
):
    """配置产品编辑模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update({
        'app_root': Path(app_root),
        'require_super_admin_api': require_super_admin_api,
        'render_markdown': render_markdown,
        'get_product_page_ai_config': get_product_page_ai_config,
        'get_product_page_ai_system_prompt': get_product_page_ai_system_prompt,
        'get_product_settings': get_product_settings,
        'save_product_settings': save_product_settings,
        'product_featured_file': Path(product_featured_file),
        'excluded_product_files': set(excluded_product_files or set()),
        'hydrogen_solutions_config_file': Path(hydrogen_solutions_config_file),
        'get_hydrogen_solution_products_config': get_hydrogen_solution_products_config,
        'save_hydrogen_solution_products_config': save_hydrogen_solution_products_config,
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


def _product_ai_reference_file(product_family: str = 'gas') -> Path:
    app_root = _dep('app_root')
    if str(product_family or '').strip().lower() == 'bio':
        return app_root / 'pages' / 'biosensing' / 'blood_potassium_chip.html'
    return app_root / 'pages' / 'gassensing' / 'mc_ld_h2.html'


def _gassensing_products_dir() -> Path:
    return _dep('app_root') / 'pages' / 'gassensing'


def _biosensing_products_dir() -> Path:
    return _dep('app_root') / 'pages' / 'biosensing'


def _get_product_family_from_request() -> str:
    path = str(getattr(request, 'path', '') or '').strip().lower()
    if path.startswith('/api/bio-products/'):
        return 'bio'
    return 'gas'


def _get_products_dir_by_family(product_family: str) -> Path:
    return _biosensing_products_dir() if str(product_family or '').strip().lower() == 'bio' else _gassensing_products_dir()


def _get_products_web_prefix_by_family(product_family: str) -> str:
    return '/pages/biosensing' if str(product_family or '').strip().lower() == 'bio' else '/pages/gassensing'


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _product_ai_drafts_file() -> Path:
    return _dep('app_root') / 'data' / 'product_ai_drafts.json'


def _current_admin_username() -> str:
    return str(session.get('admin_username') or '').strip()


def _read_product_ai_drafts_payload() -> dict:
    path = _product_ai_drafts_file()
    if not path.exists():
        return {'version': 1, 'items': []}
    try:
        payload = json.loads(path.read_text(encoding='utf-8') or '{}')
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    items = payload.get('items')
    if not isinstance(items, list):
        items = []
    return {'version': int(payload.get('version', 1) or 1), 'items': [item for item in items if isinstance(item, dict)]}


def _write_product_ai_drafts_payload(payload: dict) -> None:
    path = _product_ai_drafts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = payload if isinstance(payload, dict) else {'version': 1, 'items': []}
    items = safe_payload.get('items')
    if not isinstance(items, list):
        items = []
    safe_payload = {'version': int(safe_payload.get('version', 1) or 1), 'items': [item for item in items if isinstance(item, dict)]}
    tmp = path.with_suffix(path.suffix + f'.tmp-{uuid.uuid4().hex}')
    tmp.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def _safe_draft_id(raw_value: str) -> str:
    value = str(raw_value or '').strip()
    if re.fullmatch(r'[A-Za-z0-9_-]{8,80}', value):
        return value
    return ''


def _new_product_ai_draft_id() -> str:
    return f'draft_{uuid.uuid4().hex}'


def _normalize_product_family(value: str) -> str:
    return 'bio' if str(value or '').strip().lower() == 'bio' else 'gas'


def _normalize_draft_status(value: str) -> str:
    status = str(value or '').strip().lower()
    return status if status in PRODUCT_AI_DRAFT_STATUSES else 'draft'


def _normalize_draft_mode(value: str) -> str:
    mode = str(value or '').strip().lower()
    return mode if mode in PRODUCT_AI_DRAFT_MODES else 'structured'


def _clean_draft_text(value, max_length: int = 20000) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if max_length > 0 and len(text) > max_length:
        text = text[:max_length]
    return text


def resolve_product_html_path_by_id(product_id: str) -> tuple[Path | None, str]:
    """根据产品 ID 解析 pages 目录中的本地 HTML 路径。"""
    pid = str(product_id or '').strip()
    base_dir = _dep('app_root') / 'pages'
    if pid.startswith('../customization/'):
        slug = pid.replace('../customization/', '').strip('/')
        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return None, ''
        return base_dir / 'customization' / f'{slug}.html', slug
    if pid.startswith('../biosensing/'):
        slug = pid.replace('../biosensing/', '').strip('/')
        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return None, ''
        return base_dir / 'biosensing' / f'{slug}.html', slug
    if not re.fullmatch(r'[a-z0-9_]+', pid):
        return None, ''
    return base_dir / 'gassensing' / f'{pid}.html', pid


def _cleanup_deleted_product_references(product_id: str):
    """清理后台配置中已删除产品的关联引用。"""
    settings = _dep('get_product_settings')()
    if product_id in settings:
        settings.pop(product_id, None)
        _dep('save_product_settings')(settings)

    product_featured_file = _dep('product_featured_file')
    if product_featured_file.exists():
        try:
            raw = json.loads(product_featured_file.read_text(encoding='utf-8'))
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            ids = raw.get('ids', [])
            if isinstance(ids, list):
                filtered_ids = []
                for item in ids:
                    current_id = str(item or '').strip()
                    if not current_id or current_id == product_id or current_id in filtered_ids:
                        continue
                    filtered_ids.append(current_id)
                if filtered_ids != ids:
                    raw['ids'] = filtered_ids[:3]
                    product_featured_file.write_text(
                        json.dumps(raw, ensure_ascii=False, indent=2),
                        encoding='utf-8',
                    )

    hydrogen_solutions_config_file = _dep('hydrogen_solutions_config_file')
    if hydrogen_solutions_config_file.exists():
        save_hydrogen_solution_products_config = _dep('save_hydrogen_solution_products_config')
        get_hydrogen_solution_products_config = _dep('get_hydrogen_solution_products_config')
        save_hydrogen_solution_products_config(get_hydrogen_solution_products_config())


def get_product_template_html() -> str:
    """从旧模板或新模板路径加载产品页面模板 HTML。"""
    for template_file in _product_template_files():
        if template_file.exists():
            return template_file.read_text(encoding='utf-8', errors='ignore')
    checked = ' | '.join(str(p) for p in _product_template_files())
    raise FileNotFoundError(f'产品模板不存在，已检查: {checked}')


def get_product_ai_reference_html(product_family: str = 'gas') -> str:
    """加载 AI 生成参考 HTML，缺失时回退到通用模板。"""
    reference_file = _product_ai_reference_file(product_family)
    if reference_file.exists():
        return reference_file.read_text(encoding='utf-8', errors='ignore')
    return get_product_template_html()


def extract_product_template_placeholders(template_html: str):
    """从模板中提取按顺序出现的唯一占位符，如【产品名字】。"""
    seen = set()
    ordered = []
    for token in re.findall(r'【[^】]+】', template_html or ''):
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def split_product_detail_from_editor(content_html: str):
    """将可视化编辑器内容拆分成两段产品详情。"""
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
    """从旧版产品 HTML 结构中提取模板式字段。"""
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
    """仅保留有效的模板占位符键值对。"""
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
    """为产品模板中的全部占位符构建默认值。"""
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
    """为 HTML 或模板替换安全转义占位符值。"""
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
    """注入 `product-*` meta 标签，兼容后台扫描逻辑。"""
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
    """将后台编辑状态编码进 HTML 注释，便于后续继续编辑。"""
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
    return f'<!-- {PRODUCT_ADMIN_DATA_PREFIX}{encoded} -->'


def decode_product_admin_data(page_html: str):
    """从 HTML 注释中解码嵌入的后台编辑载荷。"""
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
    """基于解析后的产品模板 HTML 渲染产品页。"""
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
    page_html = ensure_product_responsive_guards(page_html)

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
    """解析产品详情页字段，供后台编辑使用。"""
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
    """使用显式配置调用兼容 OpenAI 的同步 API。"""
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
    """从兼容 OpenAI 的流式分片中提取文本增量。"""
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
    """使用显式配置调用兼容 OpenAI 的流式 API。"""
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
    """从 AI 文本中提取第一个有效 JSON 对象。"""
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
    """从模型输出中提取 HTML 文档，并做稳健兜底。"""
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
    """基于模板字段构建编辑器使用的 `content_html` 回填内容。"""
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
    """将多行或逗号分隔文本规范化为非空文本列表。"""
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


def _unique_nonempty_strings(values, limit: int = 12) -> list[str]:
    result = []
    source = values if isinstance(values, list) else _normalize_text_lines(values)
    for item in source:
        text = str(item or '').strip()
        if not text or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _normalize_icon(value: str, fallback: str = 'fas fa-check-circle') -> str:
    text = str(value or '').strip()
    if not text:
        return fallback
    text = re.sub(r'[^A-Za-z0-9 _-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text or fallback


def _normalize_product_sections(raw_sections, *, partial: bool = False, defaults: dict | None = None) -> dict:
    """Normalize AI/page section data into the fixed `vs-*` editing model."""
    source = raw_sections if isinstance(raw_sections, dict) else {}
    normalized = {} if partial else dict(defaults or {})

    def should_take(key: str) -> bool:
        return key in source

    for key in PRODUCT_SECTION_TEXT_KEYS:
        if should_take(key):
            normalized[key] = _clean_draft_text(source.get(key), max_length=6000)
        elif not partial and key not in normalized:
            normalized[key] = ''

    if should_take('images'):
        normalized['images'] = _unique_nonempty_strings(source.get('images'), limit=12)
    elif not partial and 'images' not in normalized:
        normalized['images'] = []

    if should_take('highlights'):
        normalized['highlights'] = _unique_nonempty_strings(source.get('highlights'), limit=12)
    elif not partial and 'highlights' not in normalized:
        normalized['highlights'] = []

    if should_take('advantages'):
        items = source.get('advantages') if isinstance(source.get('advantages'), list) else []
        cards = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_draft_text(item.get('title'), max_length=120)
            desc = _clean_draft_text(item.get('desc') or item.get('description'), max_length=360)
            if not title and not desc:
                continue
            cards.append({
                'icon': _normalize_icon(item.get('icon'), fallback='fas fa-check-circle'),
                'title': title,
                'desc': desc,
            })
            if len(cards) >= 12:
                break
        normalized['advantages'] = cards
    elif not partial and 'advantages' not in normalized:
        normalized['advantages'] = []

    if should_take('applications'):
        items = source.get('applications') if isinstance(source.get('applications'), list) else []
        cards = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_draft_text(item.get('title'), max_length=120)
            desc = _clean_draft_text(item.get('desc') or item.get('description'), max_length=420)
            scenario = _clean_draft_text(item.get('scenario') or item.get('scenarios'), max_length=240)
            img = _clean_draft_text(item.get('img') or item.get('image'), max_length=600)
            if not title and not desc and not scenario:
                continue
            cards.append({
                'icon': _normalize_icon(item.get('icon'), fallback='fas fa-circle'),
                'title': title,
                'desc': desc,
                'scenario': scenario,
                'img': img,
            })
            if len(cards) >= 12:
                break
        normalized['applications'] = cards
    elif not partial and 'applications' not in normalized:
        normalized['applications'] = []

    if should_take('specs'):
        rows = source.get('specs') if isinstance(source.get('specs'), list) else []
        specs = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _clean_draft_text(row.get('key') or row.get('name'), max_length=120)
            value = _clean_draft_text(row.get('value') or row.get('val'), max_length=300)
            if not key and not value:
                continue
            specs.append({'key': key, 'value': value})
            if len(specs) >= 48:
                break
        normalized['specs'] = specs
    elif not partial and 'specs' not in normalized:
        normalized['specs'] = []

    if should_take('news'):
        items = source.get('news') if isinstance(source.get('news'), list) else []
        news = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_draft_text(item.get('title'), max_length=180)
            desc = _clean_draft_text(item.get('desc') or item.get('description'), max_length=320)
            href = _clean_draft_text(item.get('href') or item.get('url') or item.get('link'), max_length=600) or '#'
            img = _clean_draft_text(item.get('img') or item.get('image'), max_length=600)
            if not title and not desc:
                continue
            news.append({'href': href, 'img': img, 'title': title, 'desc': desc})
            if len(news) >= 12:
                break
        normalized['news'] = news
    elif not partial and 'news' not in normalized:
        normalized['news'] = []

    if should_take('related_products'):
        items = source.get('related_products') if isinstance(source.get('related_products'), list) else []
        related = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_draft_text(item.get('title') or item.get('name'), max_length=160)
            href = _clean_draft_text(item.get('href') or item.get('url') or item.get('link'), max_length=600) or '#'
            img = _clean_draft_text(item.get('img') or item.get('image'), max_length=600)
            if not title:
                continue
            related.append({'href': href, 'img': img, 'title': title})
            if len(related) >= 12:
                break
        normalized['related_products'] = related
    elif not partial and 'related_products' not in normalized:
        normalized['related_products'] = []

    return {key: normalized[key] for key in PRODUCT_SECTION_KEYS if key in normalized}


def _build_default_product_sections(
    *,
    title: str,
    summary: str,
    image_url: str,
    detail_image_urls='',
    context_text: str = '',
) -> dict:
    images = _unique_nonempty_strings([image_url, *_normalize_text_lines(detail_image_urls)], limit=12)
    fallback_image = image_url or '/assets/images/logo.png'
    if not images:
        images = [fallback_image]
    clean_title = _clean_draft_text(title, max_length=160) or '产品页面'
    clean_summary = _clean_draft_text(summary, max_length=600)
    return {
        'title': clean_title,
        'description': clean_summary or f'{clean_title}产品详情与应用方案。',
        'images': images,
        'highlights': [],
        'detail': _clean_draft_text(context_text, max_length=6000),
        'advantages': [],
        'app_intro': '',
        'applications': [],
        'specs': [],
        'news': [],
        'related_products': [],
        'cta_title': f'获取{clean_title}产品方案',
        'cta_desc': '欢迎联系元芯传感，获取产品选型、技术支持与定制化方案。',
    }


def _first_image_from_sections(sections, fallback: str = '/assets/images/logo.png') -> str:
    if isinstance(sections, dict):
        images = sections.get('images')
        if isinstance(images, list):
            for item in images:
                text = str(item or '').strip()
                if text:
                    return text
    return fallback


def _merge_product_sections(current_sections: dict, patch_sections: dict) -> dict:
    merged = dict(current_sections if isinstance(current_sections, dict) else {})
    for key in PRODUCT_SECTION_KEYS:
        if key in patch_sections:
            merged[key] = patch_sections[key]
    return _normalize_product_sections(merged)


def _extract_product_sections_from_ai_response(response_text: str, *, defaults: dict | None = None) -> dict:
    parsed = parse_json_object_from_ai_text(response_text or '')
    raw_sections = parsed.get('sections') if isinstance(parsed.get('sections'), dict) else parsed
    return _normalize_product_sections(raw_sections, defaults=defaults)


def _extract_product_patch_from_ai_response(response_text: str) -> dict:
    parsed = parse_json_object_from_ai_text(response_text or '')
    raw_patch = parsed.get('patch') if isinstance(parsed.get('patch'), dict) else parsed
    return _normalize_product_sections(raw_patch, partial=True)


def _product_sections_schema_for_prompt() -> dict:
    return {
        'sections': {
            'title': '产品标题',
            'description': '一句话产品价值描述',
            'images': ['产品图片 URL'],
            'highlights': ['核心亮点短句'],
            'detail': '产品详情正文，可用空行分段',
            'advantages': [{'icon': 'Font Awesome class', 'title': '优势标题', 'desc': '优势描述'}],
            'app_intro': '应用场景引导文字',
            'applications': [{'icon': 'Font Awesome class', 'title': '应用标题', 'desc': '应用描述', 'scenario': '重点场景'}],
            'specs': [{'key': '参数名', 'value': '参数值'}],
            'news': [{'href': '新闻链接', 'img': '新闻图 URL', 'title': '新闻标题', 'desc': '新闻摘要'}],
            'related_products': [{'href': '产品链接', 'img': '产品图 URL', 'title': '产品标题'}],
            'cta_title': '底部联系标题',
            'cta_desc': '底部联系说明',
        }
    }


def _build_product_ai_sections_messages(
    title,
    short_name,
    category,
    image_url,
    summary,
    context_text,
    detail_image_urls='',
    news_urls='',
    related_product_urls='',
    product_family='gas',
):
    """Build compact messages that ask AI for structured product sections only."""
    ai_cfg = _dep('get_product_page_ai_config')()
    system_prompt = _dep('get_product_page_ai_system_prompt')()
    reference_sections = extract_vs_product_sections(ensure_product_dynamic_sections(get_product_ai_reference_html(product_family)))
    compact_reference = {
        'section_keys': [key for key in PRODUCT_SECTION_KEYS if key in reference_sections],
        'example_highlights': (reference_sections.get('highlights') or [])[:3],
        'example_specs': (reference_sections.get('specs') or [])[:4],
        'example_advantages': (reference_sections.get('advantages') or [])[:2],
        'example_applications': (reference_sections.get('applications') or [])[:2],
    }
    user_prompt = (
        "请根据产品资料生成产品页结构化 JSON，不要输出 HTML。\n"
        "输出要求：\n"
        "1) 只输出一个 JSON 对象，不要 Markdown，不要解释。\n"
        "2) JSON 顶层必须包含 sections 字段。\n"
        "3) sections 只能使用给定 schema 中的字段；不知道的内容留空数组或空字符串，不要编造认证、客户案例或测试报告。\n"
        "4) 图片字段只能使用已提供的图片 URL；没有图片时使用 /assets/images/logo.png。\n\n"
        f"schema:\n{json.dumps(_product_sections_schema_for_prompt(), ensure_ascii=False)}\n\n"
        f"参考页区块摘要（只用于风格和字段数量参考，不要照抄产品内容）:\n{json.dumps(compact_reference, ensure_ascii=False)}\n\n"
        f"产品资料：\n"
        f"- 产品标题: {title}\n"
        f"- 产品简称: {short_name}\n"
        f"- 产品分类: {category}\n"
        f"- 产品主图URL: {image_url or '/assets/images/logo.png'}\n"
        f"- 产品摘要: {summary or '（请你生成）'}\n"
        f"- 产品详情图片URL列表: {json.dumps(_normalize_text_lines(detail_image_urls), ensure_ascii=False)}\n"
        f"- 相关新闻URL列表: {json.dumps(_normalize_text_lines(news_urls), ensure_ascii=False)}\n"
        f"- 相关产品URL列表: {json.dumps(_normalize_text_lines(related_product_urls), ensure_ascii=False)}\n"
        f"- 详细补充资料:\n{context_text or '（无）'}"
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ], ai_cfg


def _build_product_ai_revise_sections_messages(
    *,
    instruction: str,
    current_sections: dict,
    title: str,
    summary: str,
    context_text: str,
):
    """Build compact messages that ask AI for a section merge patch only."""
    system_prompt = _dep('get_product_page_ai_system_prompt')()
    compact_current = _normalize_product_sections(current_sections)
    user_prompt = (
        "请根据修改意见返回产品页 sections 的 JSON patch，不要输出完整 HTML。\n"
        "输出要求：\n"
        "1) 只输出一个 JSON 对象，不要 Markdown，不要解释。\n"
        "2) 顶层必须是 {\"patch\": {...}}。\n"
        "3) patch 只包含需要修改的字段；未修改字段不要返回。\n"
        "4) 数组字段如果需要改动，请返回该数组的新完整值。\n"
        "5) 只能使用 schema 中的字段。\n\n"
        f"schema:\n{json.dumps(_product_sections_schema_for_prompt(), ensure_ascii=False)}\n\n"
        f"修改意见:\n{instruction}\n\n"
        f"当前产品: {title or compact_current.get('title') or '产品页面'}\n"
        f"当前摘要: {summary or compact_current.get('description') or ''}\n"
        f"补充资料:\n{context_text or '（无）'}\n\n"
        f"当前 sections:\n{json.dumps(compact_current, ensure_ascii=False)}"
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def render_product_page_from_sections(
    *,
    product_family: str,
    title: str,
    short_name: str,
    category: str,
    image_url: str,
    summary: str,
    sections: dict,
    source_text: str = '',
) -> tuple[str, dict]:
    """Render a full product HTML page from structured `vs-*` sections."""
    family = _normalize_product_family(product_family)
    normalized_sections = _normalize_product_sections(
        sections,
        defaults=_build_default_product_sections(
            title=title,
            summary=summary,
            image_url=image_url or '/assets/images/logo.png',
            detail_image_urls=(sections or {}).get('images', []),
            context_text=source_text,
        ),
    )
    page_title = normalized_sections.get('title') or title or '产品页面'
    page_summary = summary or normalized_sections.get('description') or page_title
    page_image = image_url or (normalized_sections.get('images') or ['/assets/images/logo.png'])[0] or '/assets/images/logo.png'

    page_html = ensure_product_dynamic_sections(get_product_ai_reference_html(family))
    page_html = patch_vs_product_sections(page_html, normalized_sections)
    page_html = ensure_product_dynamic_sections(page_html)
    page_html = inject_product_meta_tags(
        page_html=page_html,
        title=page_title,
        short_name=short_name or page_title,
        image_url=page_image,
        summary=page_summary,
        category=category or ('sensor' if family == 'bio' else 'detector'),
    )
    admin_payload = {
        'version': 4,
        'title': page_title,
        'short_name': short_name or page_title,
        'category': category or ('sensor' if family == 'bio' else 'detector'),
        'image_url': page_image,
        'summary': page_summary,
        'content_html': build_product_content_html_from_template_fields({}),
        'template_fields': {},
        'sections': normalized_sections,
        'source': 'ai-structured-sections',
    }
    marker = encode_product_admin_data(admin_payload)
    if '</body>' in page_html:
        page_html = page_html.replace('</body>', marker + '\n</body>', 1)
    else:
        page_html += '\n' + marker
    return ensure_product_responsive_guards(page_html), normalized_sections


def _normalize_product_ai_draft(data: dict, *, family: str, existing: dict | None = None) -> tuple[dict | None, str]:
    source = data if isinstance(data, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    now = _utc_now_iso()
    draft_id = _safe_draft_id(current.get('id') or source.get('id')) or _new_product_ai_draft_id()
    normalized_family = _normalize_product_family(family or current.get('family') or source.get('family'))
    slug = _clean_draft_text(source.get('slug', current.get('slug', '')), max_length=120).lower()
    if slug and not re.fullmatch(r'[a-z0-9_]+', slug):
        return None, '链接标识仅支持小写字母、数字、下划线'

    image_urls_raw = source.get('image_urls', source.get('images', current.get('image_urls', [])))
    if not image_urls_raw and source.get('detail_image_urls'):
        image_urls_raw = _normalize_text_lines(source.get('detail_image_urls'))
    image_urls = _unique_nonempty_strings(image_urls_raw, limit=24)

    raw_sections = source.get('sections', current.get('sections', {}))
    defaults = _build_default_product_sections(
        title=source.get('title', current.get('title', '')),
        summary=source.get('summary', current.get('summary', '')),
        image_url=(image_urls[0] if image_urls else source.get('image_url', current.get('image_url', ''))),
        detail_image_urls=image_urls,
        context_text=source.get('source_text', source.get('context_text', current.get('source_text', ''))),
    )
    sections = _normalize_product_sections(raw_sections, defaults=defaults)
    page_html = _clean_draft_text(source.get('page_html', current.get('page_html', '')), max_length=400000)

    draft = {
        'id': draft_id,
        'family': normalized_family,
        'status': _normalize_draft_status(source.get('status', current.get('status', 'draft'))),
        'slug': slug,
        'title': _clean_draft_text(source.get('title', current.get('title', sections.get('title', ''))), max_length=180),
        'short_name': _clean_draft_text(source.get('short_name', current.get('short_name', '')), max_length=120),
        'category': _clean_draft_text(
            source.get('category', current.get('category', 'sensor' if normalized_family == 'bio' else 'detector')),
            max_length=40,
        ),
        'summary': _clean_draft_text(source.get('summary', current.get('summary', sections.get('description', ''))), max_length=800),
        'source_text': _clean_draft_text(
            source.get('source_text', source.get('context_text', source.get('full_text', current.get('source_text', '')))),
            max_length=50000,
        ),
        'image_urls': image_urls,
        'sections': sections,
        'page_html': page_html,
        'mode': _normalize_draft_mode(source.get('mode', current.get('mode', 'structured'))),
        'published_link': _clean_draft_text(source.get('published_link', current.get('published_link', '')), max_length=600),
        'created_at': _clean_draft_text(current.get('created_at') or source.get('created_at') or now, max_length=40),
        'updated_at': now,
        'updated_by': _clean_draft_text(_current_admin_username() or source.get('updated_by') or current.get('updated_by'), max_length=80),
    }
    if draft['category'] not in ALLOWED_PRODUCT_CATEGORIES:
        draft['category'] = 'sensor' if normalized_family == 'bio' else 'detector'
    if not draft['title']:
        draft['title'] = sections.get('title') or draft['slug'] or '未命名产品'
    if not draft['short_name']:
        draft['short_name'] = draft['slug'].replace('_', '-').upper() if draft['slug'] else draft['title']
    if not draft['summary']:
        draft['summary'] = sections.get('description') or draft['title']
    return draft, ''


def _product_ai_draft_list_item(draft: dict) -> dict:
    return {
        key: draft.get(key, '')
        for key in (
            'id',
            'family',
            'status',
            'slug',
            'title',
            'short_name',
            'category',
            'summary',
            'mode',
            'published_link',
            'created_at',
            'updated_at',
            'updated_by',
        )
    } | {'image_count': len(draft.get('image_urls') or [])}


def _find_product_ai_draft(items: list[dict], draft_id: str, family: str) -> tuple[dict | None, int]:
    safe_id = _safe_draft_id(draft_id)
    if not safe_id:
        return None, -1
    expected_family = _normalize_product_family(family)
    for idx, item in enumerate(items):
        if item.get('id') == safe_id and _normalize_product_family(item.get('family')) == expected_family:
            return item, idx
    return None, -1


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
    product_family='gas',
):
    """构建用于整页产品 HTML 生成的 system/user 消息。"""
    ai_cfg = _dep('get_product_page_ai_config')()
    reference_html = get_product_ai_reference_html(product_family)
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
    """在输出被截断时尽力补齐缺失的 body/html 尾部。"""
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


def ensure_product_responsive_guards(page_html: str) -> str:
    """Ensure generated product pages keep mobile table layout overrides."""
    text = str(page_html or '')
    if 'vs-specs-table' not in text or 'Product Specs Mobile Guard' in text:
        return text

    if re.search(r'</style\s*>', text, re.I):
        return _insert_before_last_tag(text, 'style', PRODUCT_SPECS_MOBILE_GUARD.rstrip())

    style_block = '<style>' + PRODUCT_SPECS_MOBILE_GUARD.rstrip() + '\n    </style>'
    if re.search(r'</head\s*>', text, re.I):
        return _insert_before_last_tag(text, 'head', style_block)
    return style_block + '\n' + text


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
    """后处理 AI 生成 HTML，确保相关新闻或产品动态区块可正常渲染。"""
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

    return ensure_product_responsive_guards(text)


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
    """构建用于产品 HTML 修改流程的 system/user 消息。"""
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



# 路由注册入口。
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
    product_featured_file,
    excluded_product_files,
    hydrogen_solutions_config_file,
    get_hydrogen_solution_products_config,
    save_hydrogen_solution_products_config,
    default_product_categories,
    normalize_ai_product_image_extension,
    infer_ai_product_image_extension_from_mime,
    allowed_ai_product_image_mime_types,
):
    """注册产品编辑后台相关路由。"""
    configure_product_editor(
        app_root=app_root,
        require_super_admin_api=require_super_admin_api,
        render_markdown=render_markdown,
        get_product_page_ai_config=get_product_page_ai_config,
        get_product_page_ai_system_prompt=get_product_page_ai_system_prompt,
        get_product_settings=get_product_settings,
        save_product_settings=save_product_settings,
        product_featured_file=product_featured_file,
        excluded_product_files=excluded_product_files,
        hydrogen_solutions_config_file=hydrogen_solutions_config_file,
        get_hydrogen_solution_products_config=get_hydrogen_solution_products_config,
        save_hydrogen_solution_products_config=save_hydrogen_solution_products_config,
        default_product_categories=default_product_categories,
        normalize_ai_product_image_extension=normalize_ai_product_image_extension,
        infer_ai_product_image_extension_from_mime=infer_ai_product_image_extension_from_mime,
        allowed_ai_product_image_mime_types=allowed_ai_product_image_mime_types,
    )

    @app.route('/api/products/template/placeholders')
    @login_required
    def get_product_template_placeholders_api():
        """获取后台可视化表单所需的模板占位符列表。"""
        placeholders = extract_product_template_placeholders(get_product_template_html())
        return jsonify({'items': placeholders, 'count': len(placeholders)})

    @app.route('/api/products/ai-drafts', methods=['GET', 'POST'])
    @app.route('/api/bio-products/ai-drafts', methods=['GET', 'POST'])
    @login_required
    def product_ai_drafts_collection():
        """List or create AI product drafts for the current product family."""
        product_family = _get_product_family_from_request()
        if request.method == 'GET':
            with PRODUCT_AI_DRAFTS_LOCK:
                payload = _read_product_ai_drafts_payload()
                items = [
                    _product_ai_draft_list_item(item)
                    for item in payload.get('items', [])
                    if _normalize_product_family(item.get('family')) == product_family
                ]
            items.sort(key=lambda item: item.get('updated_at', ''), reverse=True)
            return jsonify({'success': True, 'items': items, 'count': len(items)})

        body = request.get_json(force=True, silent=True) or {}
        draft, error = _normalize_product_ai_draft(body, family=product_family)
        if error:
            return jsonify({'success': False, 'message': error}), 400
        with PRODUCT_AI_DRAFTS_LOCK:
            payload = _read_product_ai_drafts_payload()
            items = payload.get('items', [])
            items.append(draft)
            payload['items'] = items
            _write_product_ai_drafts_payload(payload)
        return jsonify({'success': True, 'draft': draft})

    @app.route('/api/products/ai-drafts/<draft_id>', methods=['GET', 'PUT', 'DELETE'])
    @app.route('/api/bio-products/ai-drafts/<draft_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def product_ai_drafts_item(draft_id):
        """Read, update, or delete one AI product draft."""
        product_family = _get_product_family_from_request()
        if not _safe_draft_id(draft_id):
            return jsonify({'success': False, 'message': '草稿ID不合法'}), 400

        with PRODUCT_AI_DRAFTS_LOCK:
            payload = _read_product_ai_drafts_payload()
            items = payload.get('items', [])
            draft, idx = _find_product_ai_draft(items, draft_id, product_family)
            if draft is None:
                return jsonify({'success': False, 'message': '草稿不存在'}), 404

            if request.method == 'GET':
                return jsonify({'success': True, 'draft': draft})

            if request.method == 'DELETE':
                payload['items'] = items[:idx] + items[idx + 1:]
                _write_product_ai_drafts_payload(payload)
                return jsonify({'success': True, 'message': '草稿已删除'})

            body = request.get_json(force=True, silent=True) or {}
            updated, error = _normalize_product_ai_draft(body, family=product_family, existing=draft)
            if error:
                return jsonify({'success': False, 'message': error}), 400
            items[idx] = updated
            payload['items'] = items
            _write_product_ai_drafts_payload(payload)
        return jsonify({'success': True, 'draft': updated})

    @app.route('/api/products/ai-generate-sections', methods=['POST'])
    @app.route('/api/bio-products/ai-generate-sections', methods=['POST'])
    @login_required
    def ai_generate_product_sections():
        """Generate compact structured product page sections with AI."""
        data = request.get_json(force=True, silent=True) or {}
        product_family = _get_product_family_from_request()
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip()
        category = (data.get('category') or ('sensor' if product_family == 'bio' else 'detector')).strip()
        image_url = (data.get('image_url') or '').strip()
        detail_image_urls = data.get('detail_image_urls') or data.get('image_urls') or ''
        news_urls = (data.get('news_urls') or '').strip()
        related_product_urls = (data.get('related_product_urls') or '').strip()
        summary = (data.get('summary') or '').strip()
        context_text = (data.get('context_text') or data.get('source_text') or data.get('full_text') or '').strip()

        if not title or not short_name:
            return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400
        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        messages, ai_cfg = _build_product_ai_sections_messages(
            title=title,
            short_name=short_name,
            category=category,
            image_url=image_url,
            summary=summary,
            context_text=context_text,
            detail_image_urls=detail_image_urls,
            news_urls=news_urls,
            related_product_urls=related_product_urls,
            product_family=product_family,
        )
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        response_text, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
        if error:
            return jsonify({'success': False, 'message': error}), 502

        defaults = _build_default_product_sections(
            title=title,
            summary=summary,
            image_url=image_url or '/assets/images/logo.png',
            detail_image_urls=detail_image_urls,
            context_text=context_text,
        )
        try:
            sections = _extract_product_sections_from_ai_response(response_text or '', defaults=defaults)
            page_html, sections = render_product_page_from_sections(
                product_family=product_family,
                title=title,
                short_name=short_name,
                category=category,
                image_url=image_url or (sections.get('images') or ['/assets/images/logo.png'])[0],
                summary=summary or sections.get('description', ''),
                sections=sections,
                source_text=context_text,
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'AI输出解析失败: {exc}'}), 500

        draft_id = _safe_draft_id(data.get('draft_id') or '')
        draft = None
        if draft_id:
            with PRODUCT_AI_DRAFTS_LOCK:
                payload = _read_product_ai_drafts_payload()
                items = payload.get('items', [])
                existing, idx = _find_product_ai_draft(items, draft_id, product_family)
                if existing is not None:
                    draft, _ = _normalize_product_ai_draft({
                        **existing,
                        'title': title,
                        'short_name': short_name,
                        'category': category,
                        'summary': summary or sections.get('description', ''),
                        'source_text': context_text,
                        'image_urls': sections.get('images', []),
                        'sections': sections,
                        'page_html': page_html,
                        'status': 'generated',
                        'mode': 'structured',
                    }, family=product_family, existing=existing)
                    items[idx] = draft
                    payload['items'] = items
                    _write_product_ai_drafts_payload(payload)

        return jsonify({'success': True, 'sections': sections, 'page_html': page_html, 'draft': draft})

    @app.route('/api/products/ai-revise-sections', methods=['POST'])
    @app.route('/api/bio-products/ai-revise-sections', methods=['POST'])
    @login_required
    def ai_revise_product_sections():
        """Revise structured product page sections with a compact AI merge patch."""
        data = request.get_json(force=True, silent=True) or {}
        product_family = _get_product_family_from_request()
        instruction = (data.get('instruction') or '').strip()
        if not instruction:
            return jsonify({'success': False, 'message': '请先填写修改意见'}), 400

        current_sections = _normalize_product_sections(data.get('sections') or {})
        if not current_sections:
            return jsonify({'success': False, 'message': '当前页面内容为空，请先生成页面内容'}), 400

        ai_cfg = _dep('get_product_page_ai_config')()
        if not ai_cfg.get('enabled', False):
            return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
        if not ai_cfg.get('api_key'):
            return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

        title = (data.get('title') or current_sections.get('title') or '产品页面').strip()
        short_name = (data.get('short_name') or '').strip() or title
        category = (data.get('category') or ('sensor' if product_family == 'bio' else 'detector')).strip()
        image_url = (data.get('image_url') or (current_sections.get('images') or ['/assets/images/logo.png'])[0]).strip()
        summary = (data.get('summary') or current_sections.get('description') or title).strip()
        context_text = (data.get('context_text') or data.get('source_text') or '').strip()

        messages = _build_product_ai_revise_sections_messages(
            instruction=instruction,
            current_sections=current_sections,
            title=title,
            summary=summary,
            context_text=context_text,
        )
        response_text, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
        if error:
            return jsonify({'success': False, 'message': error}), 502

        try:
            patch = _extract_product_patch_from_ai_response(response_text or '')
            sections = _merge_product_sections(current_sections, patch)
            page_html, sections = render_product_page_from_sections(
                product_family=product_family,
                title=title,
                short_name=short_name,
                category=category,
                image_url=image_url,
                summary=summary,
                sections=sections,
                source_text=context_text,
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'AI输出解析失败: {exc}'}), 500

        draft_id = _safe_draft_id(data.get('draft_id') or '')
        draft = None
        if draft_id:
            with PRODUCT_AI_DRAFTS_LOCK:
                payload = _read_product_ai_drafts_payload()
                items = payload.get('items', [])
                existing, idx = _find_product_ai_draft(items, draft_id, product_family)
                if existing is not None:
                    draft, _ = _normalize_product_ai_draft({
                        **existing,
                        'title': title,
                        'short_name': short_name,
                        'category': category,
                        'summary': summary,
                        'source_text': context_text or existing.get('source_text', ''),
                        'image_urls': sections.get('images', []),
                        'sections': sections,
                        'page_html': page_html,
                        'status': 'generated',
                        'mode': 'structured',
                    }, family=product_family, existing=existing)
                    items[idx] = draft
                    payload['items'] = items
                    _write_product_ai_drafts_payload(payload)

        return jsonify({'success': True, 'patch': patch, 'sections': sections, 'page_html': page_html, 'draft': draft})

    @app.route('/api/products/ai-preview-sections', methods=['POST'])
    @app.route('/api/bio-products/ai-preview-sections', methods=['POST'])
    @login_required
    def ai_preview_product_sections():
        """Render a preview HTML page from structured sections."""
        data = request.get_json(force=True, silent=True) or {}
        product_family = _get_product_family_from_request()
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip() or title
        category = (data.get('category') or ('sensor' if product_family == 'bio' else 'detector')).strip()
        image_url = (data.get('image_url') or '').strip()
        summary = (data.get('summary') or '').strip()
        sections = data.get('sections') or {}
        try:
            page_html, sections = render_product_page_from_sections(
                product_family=product_family,
                title=title or '产品页面',
                short_name=short_name or title or '产品页面',
                category=category,
                image_url=image_url or _first_image_from_sections(sections),
                summary=summary,
                sections=sections,
                source_text=(data.get('source_text') or data.get('context_text') or ''),
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'预览生成失败: {exc}'}), 500
        return jsonify({'success': True, 'sections': sections, 'page_html': page_html})

    @app.route('/api/products/ai-create-from-sections', methods=['POST'])
    @app.route('/api/bio-products/ai-create-from-sections', methods=['POST'])
    @login_required
    def ai_create_product_from_sections():
        """Save a product page file from structured sections."""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied

        data = request.get_json(force=True, silent=True) or {}
        product_family = _get_product_family_from_request()
        title = (data.get('title') or '').strip()
        short_name = (data.get('short_name') or '').strip() or title
        category = (data.get('category') or ('sensor' if product_family == 'bio' else 'detector')).strip()
        slug = (data.get('slug') or '').strip().lower()
        summary = (data.get('summary') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        sections = data.get('sections') or {}

        if not title or not category or not slug:
            return jsonify({'success': False, 'message': '请填写标题、分类和链接标识'}), 400
        if not re.fullmatch(r'[a-z0-9_]+', slug):
            return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400
        if category not in ALLOWED_PRODUCT_CATEGORIES:
            return jsonify({'success': False, 'message': '产品分类不合法'}), 400

        try:
            page_html, sections = render_product_page_from_sections(
                product_family=product_family,
                title=title,
                short_name=short_name,
                category=category,
                image_url=image_url or _first_image_from_sections(sections),
                summary=summary,
                sections=sections,
                source_text=(data.get('source_text') or data.get('context_text') or ''),
            )
        except Exception as exc:
            return jsonify({'success': False, 'message': f'页面生成失败: {exc}'}), 500

        products_dir = _get_products_dir_by_family(product_family)
        products_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{slug}.html'
        filepath = products_dir / filename
        if filepath.exists():
            return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409
        filepath.write_text(page_html, encoding='utf-8')
        link = f'{_get_products_web_prefix_by_family(product_family)}/{filename}'

        draft_id = _safe_draft_id(data.get('draft_id') or '')
        draft = None
        if draft_id:
            with PRODUCT_AI_DRAFTS_LOCK:
                payload = _read_product_ai_drafts_payload()
                items = payload.get('items', [])
                existing, idx = _find_product_ai_draft(items, draft_id, product_family)
                if existing is not None:
                    draft, _ = _normalize_product_ai_draft({
                        **existing,
                        'title': title,
                        'short_name': short_name,
                        'category': category,
                        'summary': summary or sections.get('description', ''),
                        'source_text': data.get('source_text') or data.get('context_text') or existing.get('source_text', ''),
                        'image_urls': sections.get('images', []),
                        'sections': sections,
                        'page_html': page_html,
                        'status': 'published',
                        'mode': 'structured',
                        'published_link': link,
                    }, family=product_family, existing=existing)
                    items[idx] = draft
                    payload['items'] = items
                    _write_product_ai_drafts_payload(payload)

        return jsonify({'success': True, 'filename': filename, 'link': link, 'sections': sections, 'page_html': page_html, 'draft': draft})

    @app.route('/api/products/ai-generate-html', methods=['POST'])
    @app.route('/api/bio-products/ai-generate-html', methods=['POST'])
    @login_required
    def ai_generate_product_html():
        """以页面模板为参考，通过 AI 生成完整产品页代码。"""
        data = request.json or {}
        product_family = _get_product_family_from_request()
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
            product_family=product_family,
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
    @app.route('/api/bio-products/ai-upload-images', methods=['POST'])
    @login_required
    def ai_upload_product_images():
        """将 AI 生成的产品图片上传到产品图片目录。"""
        product_family = _get_product_family_from_request()
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

        target_dir = _get_products_dir_by_family(product_family) / model_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        web_prefix = _get_products_web_prefix_by_family(product_family)

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
            urls.append(f'{web_prefix}/{model_folder}/{filename}')
            counter += 1

        return jsonify({'success': True, 'folder': model_folder, 'urls': urls})

    @app.route('/api/products/ai-generate-html-stream', methods=['POST'])
    @app.route('/api/bio-products/ai-generate-html-stream', methods=['POST'])
    @login_required
    def ai_generate_product_html_stream():
        """以流式方式生成完整产品 HTML，并支持自动续写。"""
        data = request.json or {}
        product_family = _get_product_family_from_request()
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
            product_family=product_family,
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
    @app.route('/api/bio-products/ai-revise-html-stream', methods=['POST'])
    @login_required
    def ai_revise_product_html_stream():
        """按用户指令流式修订已生成的 HTML。"""
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
    @app.route('/api/bio-products/ai-revise-html', methods=['POST'])
    @login_required
    def ai_revise_product_html():
        """按用户指令修订已生成的 HTML，作为非流式兜底。"""
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
    @app.route('/api/bio-products/ai-create-html', methods=['POST'])
    @login_required
    def ai_create_product_from_html():
        """将 AI 生成的完整 HTML 保存为产品页文件。"""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied
        data = request.json or {}
        product_family = _get_product_family_from_request()
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

        products_dir = _get_products_dir_by_family(product_family)
        products_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{slug}.html'
        filepath = products_dir / filename
        if filepath.exists():
            return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409
        filepath.write_text(enriched_html, encoding='utf-8')
        return jsonify({
            'success': True,
            'filename': filename,
            'link': f'{_get_products_web_prefix_by_family(product_family)}/{filename}',
        })

    @app.route('/api/products/ai-generate-fields', methods=['POST'])
    @login_required
    def ai_generate_product_template_fields():
        """通过产品页编码 AI 生成模板字段。"""
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
        """使用 AI 生成的模板字段创建产品 HTML。"""
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
        """通过后台可视化表单创建气体传感产品详情页。"""
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
        """获取单个气体传感产品详情，供后台可视化编辑。"""
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
        """更新已有的气体传感产品详情页。"""
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
        """为后台实时预览渲染完整产品页 HTML。"""
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

    @app.route('/api/products/code/download')
    @app.route('/api/bio-products/code/download')
    @login_required
    def download_product_code():
        """根据产品 ID 下载 HTML 源码。"""
        product_id = (request.args.get('id') or '').strip()
        filepath, slug = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f'{slug}.html',
            mimetype='text/html',
        )

    @app.route('/api/products/code/upload', methods=['POST'])
    @app.route('/api/bio-products/code/upload', methods=['POST'])
    @login_required
    def upload_product_code():
        """根据产品 ID 上传并覆盖 HTML 源码。"""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied

        product_id = (request.form.get('id') or '').strip()
        upload_file = request.files.get('file')
        filepath, _ = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        if not upload_file or not upload_file.filename:
            return jsonify({'success': False, 'message': '未选择上传文件'}), 400
        if not str(upload_file.filename).lower().endswith('.html'):
            return jsonify({'success': False, 'message': '仅支持上传 .html 文件'}), 400

        raw = upload_file.read()
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError:
            content = raw.decode('utf-8', errors='ignore')
        if '<html' not in content.lower():
            return jsonify({'success': False, 'message': '上传内容不是有效的HTML文件'}), 400

        filepath.write_text(ensure_product_responsive_guards(content), encoding='utf-8')
        return jsonify({'success': True, 'message': '覆盖上传成功'})

    @app.route('/api/products/delete', methods=['POST'])
    @login_required
    def delete_product_item():
        """删除单个气体传感或定制化产品页及相关后台配置。"""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied

        body = request.get_json(force=True, silent=True) or {}
        product_id = str(body.get('id') or '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        if product_id.startswith('../biosensing/'):
            return jsonify({'success': False, 'message': '该接口仅支持删除【氢气产品】列表中的产品'}), 400

        filepath, slug = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        if filepath.name in _dep('excluded_product_files') or filepath.name == 'index.html':
            return jsonify({'success': False, 'message': '该页面不允许删除'}), 400

        try:
            filepath.unlink()
        except Exception as exc:
            return jsonify({'success': False, 'message': f'删除文件失败: {exc}'}), 500

        _cleanup_deleted_product_references(product_id)
        return jsonify({
            'success': True,
            'message': '产品和页面代码已删除',
            'id': product_id,
            'slug': slug,
            'filename': filepath.name,
        })

    @app.route('/api/products/page-fields', methods=['GET'])
    @login_required
    def get_product_page_fields():
        """获取产品页中可编辑的模板字段。"""
        product_id = (request.args.get('id') or '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        filepath, _ = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        parsed = parse_gassensing_product_detail(filepath)
        if not parsed:
            return jsonify({'success': False, 'message': '无法解析产品页面'}), 500
        return jsonify({'success': True, 'productId': product_id, 'fields': parsed.get('template_fields', {})})

    @app.route('/api/products/page-fields', methods=['POST'])
    @login_required
    def save_product_page_fields():
        """将可编辑模板字段写回产品页。"""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied

        body = request.get_json(force=True, silent=True) or {}
        product_id = str(body.get('productId') or '').strip()
        new_fields = body.get('fields') or {}
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        if not isinstance(new_fields, dict):
            return jsonify({'success': False, 'message': '字段格式错误'}), 400

        filepath, _ = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        parsed = parse_gassensing_product_detail(filepath)
        if not parsed:
            return jsonify({'success': False, 'message': '无法解析产品页面'}), 500

        merged_fields = parsed.get('template_fields', {})
        merged_fields.update(new_fields)
        page_html, _ = render_gassensing_product_html(
            title=new_fields.get('【产品名字】') or new_fields.get('【这里是产品名字】') or parsed.get('title', ''),
            short_name=parsed.get('short_name', ''),
            category=parsed.get('category', 'module'),
            image_url=new_fields.get('【主图链接】') or parsed.get('image_url', ''),
            summary=new_fields.get('【产品描述】') or parsed.get('summary', ''),
            content_html=parsed.get('content_html', ''),
            template_fields=merged_fields,
        )
        filepath.write_text(page_html, encoding='utf-8')
        return jsonify({'success': True, 'message': '保存成功'})

    @app.route('/api/products/page-sections', methods=['GET'])
    @app.route('/api/bio-products/page-sections', methods=['GET'])
    @login_required
    def get_product_page_sections():
        """提取现代 `vs-*` 产品页中的全部可编辑区块。"""
        product_id = (request.args.get('id') or '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        filepath, _ = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        try:
            page_html = filepath.read_text(encoding='utf-8', errors='ignore')
            sections = extract_vs_product_sections(page_html)
            return jsonify({'success': True, 'productId': product_id, 'sections': sections})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'解析失败: {exc}'}), 500

    @app.route('/api/products/page-sections', methods=['POST'])
    @app.route('/api/bio-products/page-sections', methods=['POST'])
    @login_required
    def save_product_page_sections():
        """用编辑后的区块内容修补现代 `vs-*` 产品页 HTML。"""
        super_admin_denied = _dep('require_super_admin_api')()
        if super_admin_denied:
            return super_admin_denied

        body = request.get_json(force=True, silent=True) or {}
        product_id = str(body.get('productId') or '').strip()
        sections = body.get('sections') or {}
        if not product_id:
            return jsonify({'success': False, 'message': '缺少产品ID'}), 400
        if not isinstance(sections, dict):
            return jsonify({'success': False, 'message': '数据格式错误'}), 400

        filepath, _ = resolve_product_html_path_by_id(product_id)
        if not filepath or not filepath.exists():
            return jsonify({'success': False, 'message': '产品文件不存在'}), 404
        try:
            page_html = filepath.read_text(encoding='utf-8', errors='ignore')
            patched = patch_vs_product_sections(page_html, sections)
            patched = ensure_product_responsive_guards(patched)
            filepath.write_text(patched, encoding='utf-8')
            return jsonify({'success': True, 'message': '保存成功'})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'保存失败: {exc}'}), 500


def extract_vs_product_sections(page_html: str) -> dict:
    """提取现代 `vs-*` 风格产品页中的全部可编辑区块，并返回结构化区块数据。"""
    c = page_html or ''

    def strip(fragment):
        text = re.sub(r'<[^>]+>', '', fragment or '', flags=re.S)
        return html.unescape(text).strip()

    # --- 标题 ---
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', c, re.S | re.I)
    title = strip(h1.group(1)) if h1 else ''

    # --- 首屏描述 ---
    desc_m = re.search(r'<p[^>]*class="[^"]*vs-product-hero__desc[^"]*"[^>]*>(.*?)</p>', c, re.S | re.I)
    description = strip(desc_m.group(1)) if desc_m else ''

    # --- 图片：画廊缩略图 ---
    thumbs_block = re.search(
        r'<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>(.*?)</div>\s*</div>',
        c, re.S | re.I
    )
    images = []
    if thumbs_block:
        images = re.findall(r'onclick="changeImage\(this,\s*[\'"]([^\'"]+)[\'"]', thumbs_block.group(1), re.I)
        if not images:
            images = re.findall(r'<img[^>]*src="([^"]+)"', thumbs_block.group(1), re.I)
    if not images:
        main_img = re.search(r'<img[^>]*id="mainImage"[^>]*src="([^"]+)"', c, re.I)
        if main_img:
            images = [main_img.group(1)]

    # --- 产品亮点区块 ---
    feat_ul = re.search(r'<ul[^>]*class="[^"]*vs-feature-list[^"]*"[^>]*>(.*?)</ul>', c, re.S | re.I)
    highlights = []
    if feat_ul:
        items = re.findall(r'<li[^>]*>(.*?)</li>', feat_ul.group(1), re.S | re.I)
        highlights = [strip(x) for x in items if strip(x)]

    # --- 产品详情（单段长文） ---
    detail_m = re.search(
        r'产品详情\s*</h2>\s*<div[^>]*class="[^"]*vs-product-section__content[^"]*"[^>]*>(.*?)</div>',
        c, re.S | re.I
    )
    detail = ''
    if detail_m:
        ps = re.findall(r'<p[^>]*>(.*?)</p>', detail_m.group(1), re.S | re.I)
        parts = [strip(p) for p in ps if strip(p)]
        detail = '\n\n'.join(parts)
    if not detail:
        # 兜底：尝试从正文区域提取。
        article = re.search(r'<article[^>]*>(.*?)</article>', c, re.S | re.I)
        if article:
            detail = strip(article.group(1))

    # --- 产品优势区块 ---
    adv_section = re.search(
        r'产品优势\s*</h2>(.*?)</section>',
        c, re.S | re.I
    )
    advantages = []
    if adv_section:
        cards = re.findall(
            r'<div[^>]*class="[^"]*vs-advantage-card[^"]*"[^>]*>(.*?)</div>\s*(?=<div[^>]*class="[^"]*vs-advantage-card|</div>)',
            adv_section.group(1), re.S | re.I
        )
        if not cards:
            # 尝试更宽松的匹配方式。
            grid_m = re.search(r'<div[^>]*class="[^"]*vs-advantages-grid[^"]*"[^>]*>(.*)', adv_section.group(1), re.S | re.I)
            if grid_m:
                cards = re.findall(r'<div[^>]*class="[^"]*vs-advantage-card[^"]*"[^>]*>(.*?)</div>\s*\n', grid_m.group(1), re.S | re.I)
        for card in cards:
            icon_m = re.search(r'<i[^>]*class="([^"]*)"', card, re.I)
            h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p_m = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            advantages.append({
                'icon': (icon_m.group(1) if icon_m else ''),
                'title': strip(h4_m.group(1)) if h4_m else '',
                'desc': strip(p_m.group(1)) if p_m else '',
            })

    # 更稳妥的做法：直接用正则提取全部优势卡片。
    if not advantages:
        all_adv_cards = re.findall(
            r'<div[^>]*class="[^"]*vs-advantage-card[^"]*"[^>]*>(.*?)</div>(?=\s*(?:<div|</div>))',
            c, re.S | re.I
        )
        for card in all_adv_cards:
            icon_m = re.search(r'<i[^>]*class="([^"]*)"', card, re.I)
            h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p_m = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            if h4_m:
                advantages.append({
                    'icon': (icon_m.group(1) if icon_m else ''),
                    'title': strip(h4_m.group(1)),
                    'desc': strip(p_m.group(1)) if p_m else '',
                })

    # --- 应用简介与条目区块 ---
    app_section_m = re.search(r'主要应用\s*</h2>(.*?)</section>', c, re.S | re.I)
    app_intro = ''
    applications = []
    if app_section_m:
        app_inner = app_section_m.group(1)
        intro_m = re.search(r'<div[^>]*class="[^"]*vs-applications-intro[^"]*"[^>]*>(.*?)</div>', app_inner, re.S | re.I)
        if intro_m:
            app_intro = strip(intro_m.group(1))
        art_items = re.findall(r'<article[^>]*class="[^"]*vs-application-highlight[^"]*"[^>]*>(.*?)</article>', app_inner, re.S | re.I)
        for art in art_items:
            icon_m = re.search(r'<i[^>]*class="([^"]*)"', art, re.I)
            h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', art, re.S | re.I)
            p_m = re.search(r'<p[^>]*>(.*?)</p>', art, re.S | re.I)
            sc_m = re.search(r'<div[^>]*class="[^"]*vs-application-scenarios[^"]*"[^>]*>(.*?)</div>', art, re.S | re.I)
            applications.append({
                'icon': (icon_m.group(1) if icon_m else ''),
                'title': strip(h4_m.group(1)) if h4_m else '',
                'desc': strip(p_m.group(1)) if p_m else '',
                'scenario': strip(sc_m.group(1)) if sc_m else '',
            })
        if not applications:
            app_cards = re.findall(r'<div[^>]*class="[^"]*vs-application-card[^"]*"[^>]*>(.*?)</div>\s*</div>', app_inner, re.S | re.I)
            for card in app_cards:
                img_m = re.search(r'<img[^>]*src="([^"]+)"', card, re.I)
                icon_m = re.search(r'<i[^>]*class="([^"]*)"', card, re.I)
                h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
                p_m = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
                applications.append({
                    'icon': (icon_m.group(1) if icon_m else ''),
                    'title': strip(h4_m.group(1)) if h4_m else '',
                    'desc': strip(p_m.group(1)) if p_m else '',
                    'scenario': '',
                    'img': (img_m.group(1) if img_m else ''),
                })

    # --- 规格参数表区块 ---
    specs_m = re.search(r'<table[^>]*class="[^"]*vs-specs-table[^"]*"[^>]*>(.*?)</table>', c, re.S | re.I)
    specs = []
    if specs_m:
        rows = re.findall(
            r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
            specs_m.group(1), re.S | re.I
        )
        for raw_k, raw_v in rows:
            k = strip(raw_k)
            v = strip(raw_v)
            if k:
                specs.append({'key': k, 'value': v})

    # --- 相关新闻 ---
    news_sec = re.search(r'<section[^>]*class="[^"]*vs-related-news[^"]*"[^>]*>(.*?)</section>', c, re.S | re.I)
    news = []
    if news_sec:
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', news_sec.group(1), re.S | re.I):
            attrs = m.group(1) or ''
            body = m.group(2) or ''
            cls_m = re.search(r'class="([^"]*)"', attrs, re.I)
            if not cls_m or 'vs-news-item' not in cls_m.group(1):
                continue
            href_m = re.search(r'href="([^"]*)"', attrs, re.I)
            img_m = re.search(r'<img[^>]*src="([^"]+)"', body, re.I)
            h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', body, re.S | re.I)
            p_m = re.search(r'<p[^>]*>(.*?)</p>', body, re.S | re.I)
            news.append({
                'href': href_m.group(1) if href_m else '#',
                'img': img_m.group(1) if img_m else '',
                'title': strip(h4_m.group(1)) if h4_m else '',
                'desc': strip(p_m.group(1)) if p_m else '',
            })

    # --- 相关产品 ---
    related_sec = re.search(r'<section[^>]*class="[^"]*vs-related-products[^"]*"[^>]*>(.*?)</section>', c, re.S | re.I)
    related_products = []
    if related_sec:
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', related_sec.group(1), re.S | re.I):
            attrs = m.group(1) or ''
            body = m.group(2) or ''
            cls_m = re.search(r'class="([^"]*)"', attrs, re.I)
            if not cls_m or 'vs-related-item' not in cls_m.group(1):
                continue
            href_m = re.search(r'href="([^"]*)"', attrs, re.I)
            img_m = re.search(r'<img[^>]*src="([^"]+)"', body, re.I)
            h4_m = re.search(r'<h4[^>]*>(.*?)</h4>', body, re.S | re.I)
            related_products.append({
                'href': href_m.group(1) if href_m else '#',
                'img': img_m.group(1) if img_m else '',
                'title': strip(h4_m.group(1)) if h4_m else '',
            })

    # --- CTA 区块 ---
    cta_m = re.search(r'<section[^>]*class="[^"]*vs-cta-section[^"]*"[^>]*>(.*?)</section>', c, re.S | re.I)
    cta_title = ''
    cta_desc = ''
    if cta_m:
        ct = re.search(r'<h3[^>]*>(.*?)</h3>', cta_m.group(1), re.S | re.I)
        cd = re.search(r'<p[^>]*>(.*?)</p>', cta_m.group(1), re.S | re.I)
        cta_title = strip(ct.group(1)) if ct else ''
        cta_desc = strip(cd.group(1)) if cd else ''

    return {
        'title': title,
        'description': description,
        'images': images,
        'highlights': highlights,
        'detail': detail,
        'advantages': advantages,
        'app_intro': app_intro,
        'applications': applications,
        'specs': specs,
        'news': news,
        'related_products': related_products,
        'cta_title': cta_title,
        'cta_desc': cta_desc,
    }


def patch_vs_product_sections(page_html: str, sections: dict) -> str:
    """用给定区块内容修补现代 `vs-*` 风格产品页 HTML，并仅更新已提供的区块。"""
    c = page_html or ''

    def esc(text: str) -> str:
        return html.escape(str(text or '').strip(), quote=True)

    def esc_text(text: str) -> str:
        """对 HTML 文本内容做转义，不用于属性值。"""
        return esc(text)

    # --- 标题 ---
    if 'title' in sections:
        new_title = esc_text(sections['title'])
        # 产品 Hero 区内的 H1。
        c = re.sub(
            r'(<h1[^>]*>)(.*?)(</h1>)',
            lambda m: m.group(1) + new_title + m.group(3),
            c, count=1, flags=re.S | re.I
        )
        # 页面标题标签。
        c = re.sub(
            r'(<title[^>]*>)(.*?)(\s*-\s*元芯传感\s*</title>|</title>)',
            lambda m: m.group(1) + new_title + (' - 元芯传感' if '元芯传感' in m.group(0) else '') + '</title>',
            c, count=1, flags=re.S | re.I
        )

    # --- 描述 ---
    if 'description' in sections:
        new_desc = esc_text(sections['description'])
        c = re.sub(
            r'(<p[^>]*class="[^"]*vs-product-hero__desc[^"]*"[^>]*>)(.*?)(</p>)',
            lambda m: m.group(1) + new_desc + m.group(3),
            c, count=1, flags=re.S | re.I
        )

    # --- 图片 ---
    if 'images' in sections:
        imgs = [str(x or '').strip() for x in sections['images'] if str(x or '').strip()]
        if imgs:
            # 替换主图元素的地址属性。
            main_src = esc(imgs[0])
            c = re.sub(
                r'(<img[^>]*id="mainImage"[^>]*src=")([^"]*)"',
                lambda m: m.group(1) + main_src + '"',
                c, count=1, flags=re.I
            )
            # 替换画廊缩略图区块。
            thumbs_match = re.search(
                r'(<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>)(.*?)(</div>\s*</div>)',
                c, re.S | re.I
            )
            if thumbs_match:
                new_thumbs = ''
                for i, src in enumerate(imgs):
                    safe_src = esc(src)
                    active_cls = ' active' if i == 0 else ''
                    new_thumbs += (
                        f'\n                            <div class="vs-gallery-thumb{active_cls}"\n'
                        f'                                onclick="changeImage(this, \'{safe_src}\')">\n'
                        f'                                <img src="{safe_src}"\n'
                        f'                                    alt="产品图{i + 1}">\n'
                        f'                            </div>'
                    )
                c = c[:thumbs_match.start(2)] + new_thumbs + '\n                        ' + c[thumbs_match.start(3):]

    # --- 亮点 ---
    if 'highlights' in sections:
        items = [str(x or '').strip() for x in sections['highlights'] if str(x or '').strip()]
        feat_match = re.search(
            r'(<ul[^>]*class="[^"]*vs-feature-list[^"]*"[^>]*>)(.*?)(</ul>)',
            c, re.S | re.I
        )
        if feat_match:
            new_items = '\n'.join(f'                            <li>{esc_text(x)}</li>' for x in items)
            c = c[:feat_match.start(2)] + '\n' + new_items + '\n                        ' + c[feat_match.start(3):]

    # --- 详情 ---
    if 'detail' in sections:
        new_detail_text = str(sections['detail'] or '').strip()
        paragraphs = [p.strip() for p in new_detail_text.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [new_detail_text] if new_detail_text else []
        new_detail_html = '\n'.join(f'                    <p>{esc_text(p)}</p>' for p in paragraphs)
        detail_match = re.search(
            r'(产品详情\s*</h2>\s*<div[^>]*class="[^"]*vs-product-section__content[^"]*"[^>]*>)(.*?)(</div>)',
            c, re.S | re.I
        )
        if detail_match:
            c = c[:detail_match.start(2)] + '\n' + new_detail_html + '\n                ' + c[detail_match.start(3):]

    # --- 优势 ---
    if 'advantages' in sections:
        adv_list = sections['advantages']
        if isinstance(adv_list, list):
            adv_grid_match = re.search(
                r'(<div[^>]*class="[^"]*vs-advantages-grid[^"]*"[^>]*>)(.*?)(</div>\s*\n\s*</div>\s*\n\s*</section>)',
                c, re.S | re.I
            )
            if adv_grid_match:
                new_cards = ''
                for card in adv_list:
                    icon = str(card.get('icon') or 'fas fa-check-circle')
                    title_t = esc_text(str(card.get('title') or ''))
                    desc_t = esc_text(str(card.get('desc') or ''))
                    new_cards += (
                        f'\n                    <div class="vs-advantage-card">\n'
                        f'                        <i class="{esc(icon)}"></i>\n'
                        f'                        <h4>{title_t}</h4>\n'
                        f'                        <p>{desc_t}</p>\n'
                        f'                    </div>'
                    )
                c = c[:adv_grid_match.start(2)] + new_cards + '\n\n                ' + c[adv_grid_match.start(3):]

    # --- 应用简介 ---
    if 'app_intro' in sections:
        new_intro = esc_text(sections['app_intro'])
        c = re.sub(
            r'(<div[^>]*class="[^"]*vs-applications-intro[^"]*"[^>]*>)(.*?)(</div>)',
            lambda m: m.group(1) + '\n                    ' + new_intro + '\n                ' + m.group(3),
            c, count=1, flags=re.S | re.I
        )

    # --- 应用场景 ---
    if 'applications' in sections:
        app_list = sections['applications']
        if isinstance(app_list, list):
            app_grid_match = re.search(
                r'(<div[^>]*class="[^"]*vs-application-highlights[^"]*"[^>]*>)(.*?)(</div>\s*\n\s*</div>\s*\n\s*</section>)',
                c, re.S | re.I
            )
            if app_grid_match:
                new_arts = ''
                for app in app_list:
                    icon = str(app.get('icon') or 'fas fa-circle')
                    title_t = esc_text(str(app.get('title') or ''))
                    desc_t = esc_text(str(app.get('desc') or ''))
                    sc_t = esc_text(str(app.get('scenario') or ''))
                    new_arts += (
                        f'\n                    <article class="vs-application-highlight">\n'
                        f'                        <div class="vs-application-content">\n'
                        f'                            <div class="vs-application-content__head">\n'
                        f'                                <i class="{esc(icon)}"></i>\n'
                        f'                                <h4>{title_t}</h4>\n'
                        f'                            </div>\n'
                        f'                            <p>{desc_t}</p>\n'
                        f'                            <div class="vs-application-scenarios">{sc_t}</div>\n'
                        f'                        </div>\n'
                        f'                    </article>'
                    )
                c = c[:app_grid_match.start(2)] + new_arts + '\n                ' + c[app_grid_match.start(3):]
            else:
                legacy_grid_match = re.search(
                    r'(<div[^>]*class="[^"]*vs-applications-grid[^"]*"[^>]*>)(.*?)(</div>\s*\n\s*</div>\s*\n\s*</section>)',
                    c, re.S | re.I
                )
                if legacy_grid_match:
                    source_images = sections.get('images') if isinstance(sections.get('images'), list) else []
                    new_cards = ''
                    for idx, app in enumerate(app_list):
                        icon = str(app.get('icon') or 'fas fa-circle')
                        title_t = esc_text(str(app.get('title') or ''))
                        desc_t = esc_text(str(app.get('desc') or ''))
                        fallback_img = source_images[(idx + 1) % len(source_images)] if source_images else ''
                        img = esc(str(app.get('img') or fallback_img or '/assets/images/logo.png'))
                        new_cards += (
                            f'\n                    <div class="vs-application-card">\n'
                            f'                        <div class="vs-app-img-wrap">\n'
                            f'                            <img src="{img}" alt="{title_t}">\n'
                            f'                        </div>\n'
                            f'                        <div class="vs-application-label">\n'
                            f'                            <h4><i class="{esc(icon)}"></i> {title_t}</h4>\n'
                            f'                            <p>{desc_t}</p>\n'
                            f'                        </div>\n'
                            f'                    </div>'
                        )
                    c = c[:legacy_grid_match.start(2)] + new_cards + '\n                ' + c[legacy_grid_match.start(3):]

    # --- 规格参数 ---
    if 'specs' in sections:
        spec_list = sections['specs']
        if isinstance(spec_list, list):
            specs_match = re.search(
                r'(<table[^>]*class="[^"]*vs-specs-table[^"]*"[^>]*>)(.*?)(</table>)',
                c, re.S | re.I
            )
            if specs_match:
                new_rows = ''
                for row in spec_list:
                    k = esc_text(str(row.get('key') or ''))
                    v = esc_text(str(row.get('value') or ''))
                    new_rows += (
                        f'\n                    <tr>\n'
                        f'                        <td>{k}</td>\n'
                        f'                        <td>{v}</td>\n'
                        f'                    </tr>'
                    )
                c = c[:specs_match.start(2)] + new_rows + '\n                ' + c[specs_match.start(3):]

    # --- 新闻 ---
    if 'news' in sections:
        news_list = sections['news']
        if isinstance(news_list, list):
            news_grid_match = re.search(
                r'(<div[^>]*class="[^"]*vs-news-grid[^"]*"[^>]*>)(.*?)(</div>\s*\n\s*</div>\s*\n\s*</section>)',
                c, re.S | re.I
            )
            if news_grid_match:
                new_news = ''
                for item in news_list:
                    href = esc(str(item.get('href') or '#'))
                    img = esc(str(item.get('img') or ''))
                    title_t = esc_text(str(item.get('title') or ''))
                    desc_t = esc_text(str(item.get('desc') or ''))
                    new_news += (
                        f'\n                    <a href="{href}" class="vs-news-item">\n'
                        f'                        <img src="{img}" alt="新闻图片">\n'
                        f'                        <div class="vs-news-item__content">\n'
                        f'                            <h4>{title_t}</h4>\n'
                        f'                            <p>{desc_t}</p>\n'
                        f'                        </div>\n'
                        f'                    </a>'
                    )
                c = c[:news_grid_match.start(2)] + new_news + '\n                ' + c[news_grid_match.start(3):]

    # --- 相关产品 ---
    if 'related_products' in sections:
        related_list = sections['related_products']
        if isinstance(related_list, list):
            related_grid_match = re.search(
                r'(<div[^>]*class="[^"]*vs-related-grid[^"]*"[^>]*>)(.*?)(</div>\s*\n\s*</div>\s*\n\s*</section>)',
                c, re.S | re.I
            )
            if related_grid_match:
                new_related = ''
                for item in related_list:
                    href = esc(str(item.get('href') or '#'))
                    img = esc(str(item.get('img') or '/assets/images/logo.png'))
                    title_t = esc_text(str(item.get('title') or ''))
                    new_related += (
                        f'\n                    <a href="{href}" class="vs-related-item">\n'
                        f'                        <img src="{img}" alt="{title_t}">\n'
                        f'                        <h4>{title_t}</h4>\n'
                        f'                    </a>'
                    )
                c = c[:related_grid_match.start(2)] + new_related + '\n                ' + c[related_grid_match.start(3):]

    # --- CTA ---
    if 'cta_title' in sections:
        new_cta_title = esc_text(sections['cta_title'])
        c = re.sub(
            r'(<section[^>]*class="[^"]*vs-cta-section[^"]*"[^>]*>.*?<h3[^>]*>)(.*?)(</h3>)',
            lambda m: m.group(1) + new_cta_title + m.group(3),
            c, count=1, flags=re.S | re.I
        )
    if 'cta_desc' in sections:
        new_cta_desc = esc_text(sections['cta_desc'])
        c = re.sub(
            r'(<section[^>]*class="[^"]*vs-cta-section[^"]*"[^>]*>.*?<p[^>]*>)(.*?)(</p>)',
            lambda m: m.group(1) + new_cta_desc + m.group(3),
            c, count=1, flags=re.S | re.I
        )

    return c


__all__ = [
    'extract_product_meta_from_html',
    'extract_vs_product_sections',
    'patch_vs_product_sections',
    'register_product_editor_routes',
    'render_product_page_from_sections',
]
