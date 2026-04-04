"""产品目录聚合路由模块。

负责扫描产品页面、合并产品设置、聚合案例并输出产品目录接口。
"""

from __future__ import annotations

import re
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

from flask import jsonify

# 模块级依赖容器，在 configure/register 阶段一次性注入。
_DEPS = {}

EXCLUDED_PRODUCT_FILES = {
    'index.html',
    'all-products.html',
    'online-store.html',
    'service-cases.html',
    'gas_sensors.html',
    'gas_sensors_page_2.html',
    'gas_sensors_page_3.html',
    'products_mems.html',
    'products_handheld.html',
    'products_systems.html',
    'products_modules.html',
}

DEFAULT_PRODUCT_CATEGORIES = {
    'mcs_iot_platform': 'iot',
    'hum_sniffer': 'module',
    'h2_sniffer': 'module',
    'ld_h2_detector': 'detector',
    'mc_wd_wearable_alarm': 'alarm',
    'mchp_vehicle_h2': 'module',
    'mc_hla_fixed_alarm': 'alarm',
    'mchs_palladium_h2': 'sensor',
    'mchf_carbon_fet_h2': 'sensor',
    'mchc_catalytic_h2': 'sensor',
    'mchm_h2_sensor': 'sensor',
    'mc_hfev_module': 'module',
    'h2_detection_probe': 'probe',
    'mc_td_leak_detector': 'detector',
    'mcect_electrochemical_h2': 'sensor',
    'mctcx_thermal_h2': 'sensor',
    'portable_gas_test_module': 'module',
    'smart_gas_mixing_system': 'system',
    '../customization/custom_gas_sensing_module': 'service',
    '../customization/custom_instrument_dev': 'service',
    '../customization/micronano_fabrication': 'service',
}

_PRODUCTS_CACHE_LOCK = threading.Lock()
_PRODUCTS_CACHE = {'data': None, 'expires_at': 0.0}
_PRODUCTS_CACHE_TTL = 30



# 依赖注入配置入口。
def configure_product_catalog(
    *,
    app_root,
    sanitize_public_text,
    sanitize_public_media_url,
    sanitize_public_link_url,
    extract_product_meta_from_html,
    get_product_settings,
    get_bio_product_settings,
    infer_default_industry_categories,
    infer_default_bio_industry_categories,
    normalize_related_news_links,
):
    """配置产品目录扫描模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update({
        'app_root': Path(app_root),
        'sanitize_public_text': sanitize_public_text,
        'sanitize_public_media_url': sanitize_public_media_url,
        'sanitize_public_link_url': sanitize_public_link_url,
        'extract_product_meta_from_html': extract_product_meta_from_html,
        'get_product_settings': get_product_settings,
        'get_bio_product_settings': get_bio_product_settings,
        'infer_default_industry_categories': infer_default_industry_categories,
        'infer_default_bio_industry_categories': infer_default_bio_industry_categories,
        'normalize_related_news_links': normalize_related_news_links,
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'Product catalog dependency not configured: {name}')
    return value


def _pages_dir() -> Path:
    return _dep('app_root') / 'pages'


def normalize_scanned_image_path(image, web_dir_prefix):
    """规范化扫描得到的图片路径，适配跨目录渲染。"""
    img = str(image or '').strip()
    if not img:
        return ''
    if img.startswith(('http://', 'https://', '/', 'data:', 'blob:')):
        return img
    clean = img.lstrip('./')
    return f"{web_dir_prefix.rstrip('/')}/{clean}"


def _scan_products_dir(
    directory: Path,
    *,
    web_dir_prefix: str,
    skip_names: set[str] | None = None,
    id_prefix: str = '',
    flag_key: str = '',
):
    items = []
    if not directory.exists():
        return items

    ignored = set(skip_names or set())
    extract_product_meta_from_html = _dep('extract_product_meta_from_html')
    for filepath in sorted(directory.glob('*.html')):
        if filepath.name in ignored:
            continue
        product = extract_product_meta_from_html(filepath)
        if not product:
            continue
        product['image'] = normalize_scanned_image_path(product.get('image', ''), web_dir_prefix)
        if id_prefix:
            product['id'] = f'{id_prefix}{product["id"]}'
        if flag_key:
            product[flag_key] = True
        items.append(product)
    return items


def _scan_public_products():
    pages_dir = _pages_dir()
    products = []
    products.extend(
        _scan_products_dir(
            pages_dir / 'gassensing',
            web_dir_prefix='/pages/gassensing',
            skip_names=EXCLUDED_PRODUCT_FILES,
        )
    )
    products.extend(
        _scan_products_dir(
            pages_dir / 'customization',
            web_dir_prefix='/pages/customization',
            skip_names={'index.html'},
            id_prefix='../customization/',
            flag_key='isCustomization',
        )
    )
    products.extend(
        _scan_products_dir(
            pages_dir / 'biosensing',
            web_dir_prefix='/pages/biosensing',
            skip_names={'index.html'},
            id_prefix='../biosensing/',
            flag_key='isBiosensing',
        )
    )
    return products


def _scan_biosensing_products():
    return _scan_products_dir(
        _pages_dir() / 'biosensing',
        web_dir_prefix='/pages/biosensing',
        skip_names={'index.html', 'index_page_2.html'},
        id_prefix='../biosensing/',
        flag_key='isBiosensing',
    )


def _merge_products_with_settings(products, settings, *, default_category: str, infer_default_industry_categories):
    sanitize_public_text = _dep('sanitize_public_text')
    sanitize_public_media_url = _dep('sanitize_public_media_url')
    normalize_related_news_links = _dep('normalize_related_news_links')

    for product in products:
        pid = product['id']
        product['name'] = sanitize_public_text(product.get('name', ''), max_length=120)
        product['shortName'] = sanitize_public_text(product.get('shortName', ''), max_length=120)
        product['description'] = sanitize_public_text(product.get('description', ''), max_length=220)
        product['image'] = sanitize_public_media_url(product.get('image', ''), enforce_remote_public=False)
        product['category'] = str(product.get('category', default_category) or default_category).strip() or default_category

        if pid in settings:
            product['displayName'] = settings[pid].get('displayName', '')
            product['isNew'] = settings[pid].get('isNew', False)
            product['hidden'] = settings[pid].get('hidden', False)
            product['sortOrder'] = settings[pid].get('sortOrder', 999)
            product['cardTitle'] = settings[pid].get('cardTitle', '')
            product['cardImage'] = settings[pid].get('cardImage', '')
            product['cardSummary'] = settings[pid].get('cardSummary', '')
            product['relatedNews'] = normalize_related_news_links(settings[pid].get('relatedNews', []))
            custom_categories = settings[pid].get('categories', [])
            if custom_categories:
                product['categories'] = custom_categories
            else:
                product['categories'] = [product.get('category', default_category)]
        else:
            product['displayName'] = ''
            product['isNew'] = False
            product['hidden'] = False
            product['sortOrder'] = 999
            product['cardTitle'] = ''
            product['cardImage'] = ''
            product['cardSummary'] = ''
            product['relatedNews'] = []
            product['categories'] = [product.get('category', default_category)]

        if pid in settings and isinstance(settings[pid].get('industryCategories'), list):
            product['industryCategories'] = settings[pid].get('industryCategories', [])
        else:
            product['industryCategories'] = infer_default_industry_categories(product)

        product['displayName'] = sanitize_public_text(product.get('displayName', ''), max_length=120)
        product['cardTitle'] = sanitize_public_text(product.get('cardTitle', ''), max_length=120)
        product['cardSummary'] = sanitize_public_text(product.get('cardSummary', ''), max_length=220)
        product['cardImage'] = sanitize_public_media_url(product.get('cardImage', ''), enforce_remote_public=False)

    products.sort(key=lambda item: (item.get('sortOrder', 999), item.get('name', '')))
    return products


def get_product_images_list():
    images_dir = _dep('app_root') / 'assets' / 'images' / 'products'
    images = []
    if images_dir.exists():
        for img_path in sorted(images_dir.glob('*.png'), key=lambda item: int(item.stem) if item.stem.isdigit() else 999):
            images.append(f'/assets/images/products/{img_path.name}')
    return images


def extract_solution_meta_from_html(filepath):
    """从解决方案 HTML 中提取基础预览字段。"""

    class SolutionMetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
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
            if tag == 'title':
                self.in_title = True
            elif tag == 'h1' and not self.found_h1:
                self.in_h1 = True
            elif tag == 'p' and self.found_h1 and not self.found_p:
                self.in_p = True
            elif tag == 'img' and not self.first_img and 'src' in attrs_dict:
                src = attrs_dict['src']
                if not any(token in src.lower() for token in ['icon', 'logo', 'arrow', 'btn', 'button']):
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

    def extract_background_image(html_content):
        hero_patterns = [
            r'\.jjfa-hero\s*\{.*?url\((["\']?)(.*?)\1\)',
            r'\.hero[^{]*\{.*?url\((["\']?)(.*?)\1\)',
            r'class=["\'][^"\']*hero[^"\']*["\'][^>]*style=["\'][^"\']*url\((["\']?)(.*?)\1\)',
        ]
        for pattern in hero_patterns:
            match = re.search(pattern, html_content, re.I | re.S)
            if not match:
                continue
            candidate = (match.group(2) or '').strip()
            if candidate and not any(token in candidate.lower() for token in ['icon', 'logo', 'arrow', 'btn', 'button']):
                return candidate

        fallback_matches = re.findall(r'url\((["\']?)(.*?)\1\)', html_content, re.I | re.S)
        for _, candidate in fallback_matches:
            candidate = (candidate or '').strip()
            if candidate and not any(token in candidate.lower() for token in ['icon', 'logo', 'arrow', 'btn', 'button']):
                return candidate
        return ''

    sanitize_public_text = _dep('sanitize_public_text')
    sanitize_public_media_url = _dep('sanitize_public_media_url')

    try:
        content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
        parser = SolutionMetaParser()
        parser.feed(content)

        item_id = Path(filepath).stem
        title = parser.first_h1 or parser.title.replace(' - 元芯传感', '').strip()
        if not title:
            return None

        desc = parser.first_p[:200] if parser.first_p else ''
        cover_image = parser.first_img or extract_background_image(content)
        image = sanitize_public_media_url(cover_image, enforce_remote_public=False)

        return {
            'id': item_id,
            'title': sanitize_public_text(title, max_length=120),
            'image': image,
            'desc': sanitize_public_text(desc, max_length=220),
        }
    except Exception as exc:
        print(f'Error parsing solution file {filepath}: {exc}')
        return None


def get_products_with_settings_data():
    """收集并合并产品设置后的产品数据，缓存 30 秒。"""
    now = time.time()
    with _PRODUCTS_CACHE_LOCK:
        if _PRODUCTS_CACHE['data'] is not None and now < _PRODUCTS_CACHE['expires_at']:
            return _PRODUCTS_CACHE['data']

    products = _scan_public_products()
    products = _merge_products_with_settings(
        products,
        _dep('get_product_settings')(),
        default_category='module',
        infer_default_industry_categories=_dep('infer_default_industry_categories'),
    )

    with _PRODUCTS_CACHE_LOCK:
        _PRODUCTS_CACHE['data'] = products
        _PRODUCTS_CACHE['expires_at'] = time.time() + _PRODUCTS_CACHE_TTL
    return products


def get_gassensing_products_with_settings():
    """仅返回 gassensing 目录下的产品数据。"""
    return [item for item in get_products_with_settings_data() if not str(item.get('id', '')).startswith('../')]


def get_biosensing_products_with_settings_data():
    """收集并合并生物传感专用设置后的产品数据。"""
    products = _scan_biosensing_products()
    return _merge_products_with_settings(
        products,
        _dep('get_bio_product_settings')(),
        default_category='sensor',
        infer_default_industry_categories=_dep('infer_default_bio_industry_categories'),
    )


def extract_case_meta_from_html(filepath):
    """提取案例元数据：标题、图片和摘要。"""
    content = Path(filepath).read_text(encoding='utf-8', errors='ignore')

    image = ''
    match = re.search(r'vs-case-hero[^{]*\{[^}]*url\([\"\\\']?([^)\\"\\\']+)[\"\\\']?\)', content, re.S)
    if match:
        image = match.group(1)

    class CaseParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ''
            self.in_h1 = False
            self.first_p = ''
            self.in_p = False
            self.found_h1 = False
            self.found_p = False

        def handle_starttag(self, tag, attrs):
            if tag == 'h1' and not self.found_h1:
                self.in_h1 = True
            elif tag == 'p' and not self.found_p:
                self.in_p = True

        def handle_data(self, data):
            data = data.strip()
            if self.in_h1:
                self.title += data
            elif self.in_p:
                self.first_p += data

        def handle_endtag(self, tag):
            if tag == 'h1':
                self.in_h1 = False
                self.found_h1 = True
            elif tag == 'p':
                self.in_p = False
                if self.first_p:
                    self.found_p = True

    parser = CaseParser()
    parser.feed(content)
    title = parser.title.strip()
    desc = parser.first_p.strip() if parser.first_p else ''
    if '浏览我们在各个行业' in desc:
        desc = ''

    if not image:
        img_match = re.search(r'<img\s+[^>]*src="([^"]+)"', content)
        if img_match:
            image = img_match.group(1)

    return {
        'id': Path(filepath).name,
        'title': _dep('sanitize_public_text')(title or Path(filepath).stem, max_length=120),
        'image': _dep('sanitize_public_media_url')(image, enforce_remote_public=False),
        'desc': _dep('sanitize_public_text')(desc, max_length=220),
    }


def get_all_case_items():
    cases_dir = _pages_dir() / 'gassensing' / 'cases'
    items = []
    if cases_dir.exists():
        for filepath in sorted(cases_dir.glob('case-*.html')):
            item = extract_case_meta_from_html(filepath)
            if item:
                item['link'] = _dep('sanitize_public_link_url')(f'pages/gassensing/cases/{filepath.name}', default='#')
                items.append(item)
    return items



# 路由注册入口。
def register_product_catalog_routes(
    app,
    *,
    app_root,
    sanitize_public_text,
    sanitize_public_media_url,
    sanitize_public_link_url,
    extract_product_meta_from_html,
    get_product_settings,
    get_bio_product_settings,
    infer_default_industry_categories,
    infer_default_bio_industry_categories,
    normalize_related_news_links,
):
    """注册产品目录扫描与聚合相关路由。"""
    configure_product_catalog(
        app_root=app_root,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_link_url=sanitize_public_link_url,
        extract_product_meta_from_html=extract_product_meta_from_html,
        get_product_settings=get_product_settings,
        get_bio_product_settings=get_bio_product_settings,
        infer_default_industry_categories=infer_default_industry_categories,
        infer_default_bio_industry_categories=infer_default_bio_industry_categories,
        normalize_related_news_links=normalize_related_news_links,
    )

    @app.route('/api/products/images')
    def get_product_images():
        return jsonify({'images': get_product_images_list()})

    @app.route('/api/products')
    def get_products():
        products = _scan_public_products()
        category_order = {
            'iot': 0,
            'module': 1,
            'sensor': 2,
            'detector': 3,
            'alarm': 4,
            'system': 5,
            'probe': 6,
            'service': 7,
        }
        products.sort(key=lambda item: (category_order.get(item.get('category', 'module'), 99), item.get('name', '')))
        return jsonify({'products': products, 'count': len(products)})

    @app.route('/api/products/with-settings')
    def get_products_with_settings():
        products = get_products_with_settings_data()
        return jsonify({'products': products, 'count': len(products)})

    @app.route('/api/bio-products/with-settings')
    def get_biosensing_products_with_settings_api():
        products = get_biosensing_products_with_settings_data()
        return jsonify({'products': products, 'count': len(products)})


__all__ = [
    'DEFAULT_PRODUCT_CATEGORIES',
    'EXCLUDED_PRODUCT_FILES',
    'extract_case_meta_from_html',
    'extract_solution_meta_from_html',
    'get_all_case_items',
    'get_biosensing_products_with_settings_data',
    'get_gassensing_products_with_settings',
    'get_product_images_list',
    'get_products_with_settings_data',
    'normalize_scanned_image_path',
    'register_product_catalog_routes',
]
