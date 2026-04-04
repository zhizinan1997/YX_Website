"""产品设置与行业筛选路由模块。

负责产品配置、分类图片、行业筛选、产品卡片图片上传与设置保存。
"""

import json
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import jsonify, request, send_from_directory

APP_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APP_ROOT / 'data'
PRODUCT_SETTINGS_FILE = DATA_DIR / 'product_settings.json'
PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'product_industry_filters.json'
BIO_PRODUCT_SETTINGS_FILE = DATA_DIR / 'bio_product_settings.json'
BIO_PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'bio_product_industry_filters.json'
PRODUCT_CATEGORY_IMAGES_FILE = DATA_DIR / 'product_category_images.json'

_SANITIZE_PUBLIC_PRODUCT_SETTINGS = lambda settings: settings if isinstance(settings, dict) else {}
_SANITIZE_PUBLIC_TEXT = lambda value, **_kwargs: str(value or '')
_SANITIZE_PUBLIC_MEDIA_URL = lambda value, **_kwargs: value or ''
_SANITIZE_PUBLIC_LINK_URL = lambda value, **_kwargs: value or ''
_GET_PRODUCTS_WITH_SETTINGS_DATA = lambda: []
_GET_BIOSENSING_PRODUCTS_WITH_SETTINGS_DATA = lambda: []

DEFAULT_INDUSTRY_FILTERS = [
    {'key': 'hydrogen', 'name': '氢能源产品'},
    {'key': 'power', 'name': '智慧电力产品'},
    {'key': 'leak', 'name': '工业检漏产品'},
    {'key': 'research', 'name': '科研服务产品'},
    {'key': 'custom', 'name': '定制类产品'},
]

DEFAULT_BIO_INDUSTRY_FILTERS = [
    {'key': 'sensor', 'name': '生物传感产品'},
    {'key': 'chip', 'name': '生物芯片'},
    {'key': 'instrument', 'name': '检测仪器'},
    {'key': 'platform', 'name': '传感平台'},
    {'key': 'device', 'name': '器件'},
    {'key': 'service', 'name': '定制服务'},
]

PRODUCT_MENU_CATEGORIES = [
    {'key': 'sensor', 'name': '传感器', 'url': '/pages/gassensing/all-products.html?filter=sensor'},
    {'key': 'module', 'name': '检测模块', 'url': '/pages/gassensing/all-products.html?filter=module'},
    {'key': 'detector', 'name': '检测仪', 'url': '/pages/gassensing/all-products.html?filter=detector'},
    {'key': 'alarm', 'name': '报警器', 'url': '/pages/gassensing/all-products.html?filter=alarm'},
    {'key': 'system', 'name': '监测系统', 'url': '/pages/gassensing/all-products.html?filter=system'},
    {'key': 'iot', 'name': '物联网平台', 'url': '/pages/gassensing/all-products.html?filter=iot'},
    {'key': 'service', 'name': '定制服务', 'url': '/pages/gassensing/all-products.html?filter=service'},
]


def get_product_category_images():
    """获取产品分类图片映射。"""
    if PRODUCT_CATEGORY_IMAGES_FILE.exists():
        try:
            data = json.loads(PRODUCT_CATEGORY_IMAGES_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_product_category_images(images_data):
    """保存产品分类图片映射。"""
    PRODUCT_CATEGORY_IMAGES_FILE.write_text(
        json.dumps(images_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def get_product_categories_with_images():
    """获取附带自定义图片的产品分类列表。"""
    images = get_product_category_images()
    categories = []
    for item in PRODUCT_MENU_CATEGORIES:
        key = item.get('key', '')
        categories.append({
            'key': key,
            'name': item.get('name', ''),
            'url': item.get('url', ''),
            'image': images.get(key, '')
        })
    return categories


def normalize_filter_key(raw_key, fallback_index=0):
    """将筛选键规范化为小写 ASCII slug。"""
    key = (raw_key or '').strip().lower()
    key = re.sub(r'[^a-z0-9_-]+', '-', key)
    key = re.sub(r'-{2,}', '-', key).strip('-')
    if not key:
        key = f'industry-{fallback_index + 1}'
    return key


def infer_default_industry_categories(product):
    """为未自定义映射的产品推断初始行业分类。"""
    pid = str(product.get('id', ''))
    name = str(product.get('name', ''))
    desc = str(product.get('description', ''))
    text = f'{name} {desc}'
    categories = []

    if pid.startswith('../customization/'):
        categories.append('custom')
    else:
        categories.append('hydrogen')

    if any(token in text for token in ['电力', '变电', '输电', '发电']):
        categories.append('power')
    if any(token in text for token in ['检漏', '泄漏', '漏气', '真空']):
        categories.append('leak')
    if any(token in text for token in ['科研', '实验室', '微纳', '开发', '产学研']):
        categories.append('research')
    if product.get('category') == 'service':
        categories.append('research')

    deduped = []
    for key in categories:
        if key not in deduped:
            deduped.append(key)
    return deduped


def infer_default_bio_industry_categories(product):
    """为未自定义映射的生物传感产品推断默认行业分类。"""
    name = str(product.get('name', ''))
    desc = str(product.get('description', ''))
    text = f'{name} {desc}'
    categories = ['sensor']

    if any(token in text for token in ['芯片', 'chip', 'Chip']):
        categories.append('chip')
    if any(token in text for token in ['检测仪', '工作站', '手持', '离子']):
        categories.append('instrument')
    if '平台' in text:
        categories.append('platform')
    if any(token in text for token in ['器件', 'IGZO', 'TFT']):
        categories.append('device')
    if any(token in text for token in ['定制', '服务']):
        categories.append('service')

    deduped = []
    for key in categories:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _normalize_related_news_links(value):
    """将产品相关新闻设置规范化为最多 2 个唯一链接。"""
    if isinstance(value, list):
        raw_list = value
    elif isinstance(value, str):
        raw_list = [x.strip() for x in re.split(r'[\n,;]+', value) if x and x.strip()]
    else:
        raw_list = []

    cleaned = []
    seen = set()
    for item in raw_list:
        link = _SANITIZE_PUBLIC_LINK_URL(item or '')
        if not link:
            continue
        if link.startswith('../../'):
            link = '/' + link.replace('../../', '', 1)
        elif link.startswith('../'):
            link = '/' + link.replace('../', '', 1)
        elif link.startswith('pages/'):
            link = '/' + link
        if link in seen:
            continue
        seen.add(link)
        cleaned.append(link)
        if len(cleaned) >= 2:
            break
    return cleaned


def get_product_settings():
    """加载产品设置，如自定义名称和新品标记。"""
    if PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return _SANITIZE_PUBLIC_PRODUCT_SETTINGS(raw)
        except Exception:
            pass
    return {}


def get_bio_product_settings():
    """加载生物传感产品设置，如自定义名称和新品标记。"""
    if BIO_PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(BIO_PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return _SANITIZE_PUBLIC_PRODUCT_SETTINGS(raw)
        except Exception:
            pass
    return {}


def save_product_settings(settings):
    """保存产品设置。"""
    cleaned = _SANITIZE_PUBLIC_PRODUCT_SETTINGS(settings)
    PRODUCT_SETTINGS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')


def save_bio_product_settings(settings):
    """保存生物传感产品设置。"""
    cleaned = _SANITIZE_PUBLIC_PRODUCT_SETTINGS(settings)
    BIO_PRODUCT_SETTINGS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')


def _build_filter_preview_map(products, fallback_categories):
    preview_map = {}
    for product in products:
        if not isinstance(product, dict) or product.get('hidden'):
            continue
        image = str((product.get('cardImage') or product.get('image') or '')).strip()
        if not image:
            continue
        categories = product.get('industryCategories', [])
        if not isinstance(categories, list) or not categories:
            categories = fallback_categories(product)
        for raw_key in categories:
            key = normalize_filter_key(raw_key)
            if key and key not in preview_map:
                preview_map[key] = image
    return preview_map


def build_industry_filter_preview_map():
    """为每个行业筛选项选取第一张可见产品图。"""
    try:
        products = _GET_PRODUCTS_WITH_SETTINGS_DATA()
    except Exception:
        return {}
    return _build_filter_preview_map(products, infer_default_industry_categories)


def build_bio_industry_filter_preview_map():
    """为每个生物传感行业筛选项选取第一张可见产品图。"""
    try:
        products = _GET_BIOSENSING_PRODUCTS_WITH_SETTINGS_DATA()
    except Exception:
        return {}
    return _build_filter_preview_map(products, infer_default_bio_industry_categories)


def _normalize_filter_items(raw_items, default_items, ensure_item=None):
    cleaned = []
    used = set()
    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        key = normalize_filter_key(item.get('key'), idx)
        if key in used:
            key = normalize_filter_key(f'{key}-{idx + 1}', idx)
        used.add(key)
        cleaned.append({'key': key, 'name': name})

    if not cleaned:
        cleaned = [dict(item) for item in default_items]
    elif ensure_item and not any(item.get('key') == ensure_item['key'] for item in cleaned):
        cleaned.insert(0, dict(ensure_item))
    return cleaned


def get_industry_filters():
    """加载全产品页的行业筛选配置。"""
    categories = []
    if PRODUCT_INDUSTRY_FILTERS_FILE.exists():
        try:
            data = json.loads(PRODUCT_INDUSTRY_FILTERS_FILE.read_text(encoding='utf-8'))
            categories = data.get('categories', [])
        except Exception:
            categories = []

    cleaned = _normalize_filter_items(categories, DEFAULT_INDUSTRY_FILTERS)
    preview_map = build_industry_filter_preview_map()
    enriched = []
    for item in cleaned:
        entry = dict(item)
        entry['url'] = f"/pages/gassensing/all-products.html?filter={quote(entry['key'])}"
        image = preview_map.get(entry['key'], '')
        if image:
            entry['image'] = image
        enriched.append(entry)
    return {'categories': enriched}


def save_industry_filters(data):
    """保存行业筛选配置，并清理过期的产品映射。"""
    raw_categories = data.get('categories', []) if isinstance(data, dict) else []
    cleaned = _normalize_filter_items(raw_categories, DEFAULT_INDUSTRY_FILTERS)

    saved = {'categories': cleaned}
    PRODUCT_INDUSTRY_FILTERS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    valid_keys = {item['key'] for item in cleaned}
    settings = get_product_settings()
    changed = False
    for _, cfg in settings.items():
        if not isinstance(cfg, dict):
            continue
        original = cfg.get('industryCategories', [])
        if not isinstance(original, list):
            continue
        filtered = [key for key in original if key in valid_keys]
        if filtered != original:
            cfg['industryCategories'] = filtered
            changed = True
    if changed:
        save_product_settings(settings)
    return saved


def get_bio_industry_filters():
    """加载生物传感索引页的行业筛选配置。"""
    categories = []
    if BIO_PRODUCT_INDUSTRY_FILTERS_FILE.exists():
        try:
            data = json.loads(BIO_PRODUCT_INDUSTRY_FILTERS_FILE.read_text(encoding='utf-8'))
            categories = data.get('categories', [])
        except Exception:
            categories = []

    cleaned = _normalize_filter_items(
        categories,
        DEFAULT_BIO_INDUSTRY_FILTERS,
        ensure_item={'key': 'sensor', 'name': '生物传感产品'},
    )
    preview_map = build_bio_industry_filter_preview_map()
    enriched = []
    for item in cleaned:
        entry = dict(item)
        entry['url'] = f"/pages/biosensing/?filter={quote(entry['key'])}"
        image = preview_map.get(entry['key'], '')
        if image:
            entry['image'] = image
        enriched.append(entry)
    return {'categories': enriched}


def save_bio_industry_filters(data):
    """保存生物传感行业筛选配置，并清理过期的产品映射。"""
    raw_categories = data.get('categories', []) if isinstance(data, dict) else []
    cleaned = _normalize_filter_items(
        raw_categories,
        DEFAULT_BIO_INDUSTRY_FILTERS,
        ensure_item={'key': 'sensor', 'name': '生物传感产品'},
    )

    saved = {'categories': cleaned}
    BIO_PRODUCT_INDUSTRY_FILTERS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    valid_keys = {item['key'] for item in cleaned}
    settings = get_bio_product_settings()
    changed = False
    for _, cfg in settings.items():
        if not isinstance(cfg, dict):
            continue
        original = cfg.get('industryCategories', [])
        if not isinstance(original, list):
            continue
        filtered = [key for key in original if key in valid_keys]
        if filtered != original:
            cfg['industryCategories'] = filtered
            changed = True
    if changed:
        save_bio_product_settings(settings)
    return saved


def _apply_product_settings_updates(settings, data):
    product_id = data.get('id')
    if not product_id:
        return None, ('缺少产品ID', 400)

    if product_id not in settings:
        settings[product_id] = {}

    if 'displayName' in data:
        settings[product_id]['displayName'] = _SANITIZE_PUBLIC_TEXT(data['displayName'], max_length=120)
    if 'isNew' in data:
        settings[product_id]['isNew'] = bool(data['isNew'])
    if 'hidden' in data:
        settings[product_id]['hidden'] = bool(data['hidden'])
    if 'sortOrder' in data:
        try:
            settings[product_id]['sortOrder'] = int(data['sortOrder'])
        except (ValueError, TypeError):
            settings[product_id]['sortOrder'] = 999
    if 'cardTitle' in data:
        settings[product_id]['cardTitle'] = _SANITIZE_PUBLIC_TEXT(data['cardTitle'], max_length=120)
    if 'cardImage' in data:
        settings[product_id]['cardImage'] = _SANITIZE_PUBLIC_MEDIA_URL(
            data['cardImage'],
            enforce_remote_public=False,
        )
    if 'cardSummary' in data:
        settings[product_id]['cardSummary'] = _SANITIZE_PUBLIC_TEXT(data['cardSummary'], max_length=220)
    if 'categories' in data:
        settings[product_id]['categories'] = list(data['categories']) if isinstance(data['categories'], list) else [data['categories']]
    if 'industryCategories' in data:
        settings[product_id]['industryCategories'] = (
            list(data['industryCategories'])
            if isinstance(data['industryCategories'], list)
            else [data['industryCategories']]
        )
    if 'relatedNews' in data:
        settings[product_id]['relatedNews'] = _normalize_related_news_links(data['relatedNews'])
    return settings, None


def _apply_sort_order(settings, order):
    if not order:
        return None, ('缺少排序数据', 400)

    for idx, product_id in enumerate(order):
        if product_id not in settings:
            settings[product_id] = {}
        settings[product_id]['sortOrder'] = idx
    return settings, None



# 路由注册入口。
def register_product_settings_routes(
    app,
    *,
    login_required,
    data_dir,
    sanitize_public_product_settings,
    sanitize_public_text,
    sanitize_public_media_url,
    sanitize_public_link_url,
    get_products_with_settings_data,
    get_biosensing_products_with_settings_data,
    product_card_uploads_dir,
    allowed_product_card_extensions,
    validate_uploaded_image_extension,
):
    """注册产品设置与行业筛选相关路由。"""
    global DATA_DIR, PRODUCT_SETTINGS_FILE, PRODUCT_INDUSTRY_FILTERS_FILE
    global BIO_PRODUCT_SETTINGS_FILE, BIO_PRODUCT_INDUSTRY_FILTERS_FILE
    global _SANITIZE_PUBLIC_PRODUCT_SETTINGS, _SANITIZE_PUBLIC_TEXT
    global _SANITIZE_PUBLIC_MEDIA_URL, _SANITIZE_PUBLIC_LINK_URL
    global _GET_PRODUCTS_WITH_SETTINGS_DATA, _GET_BIOSENSING_PRODUCTS_WITH_SETTINGS_DATA

    DATA_DIR = Path(data_dir)
    PRODUCT_SETTINGS_FILE = DATA_DIR / 'product_settings.json'
    PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'product_industry_filters.json'
    BIO_PRODUCT_SETTINGS_FILE = DATA_DIR / 'bio_product_settings.json'
    BIO_PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'bio_product_industry_filters.json'
    _SANITIZE_PUBLIC_PRODUCT_SETTINGS = sanitize_public_product_settings
    _SANITIZE_PUBLIC_TEXT = sanitize_public_text
    _SANITIZE_PUBLIC_MEDIA_URL = sanitize_public_media_url
    _SANITIZE_PUBLIC_LINK_URL = sanitize_public_link_url
    _GET_PRODUCTS_WITH_SETTINGS_DATA = get_products_with_settings_data
    _GET_BIOSENSING_PRODUCTS_WITH_SETTINGS_DATA = get_biosensing_products_with_settings_data
    product_card_uploads_path = Path(product_card_uploads_dir)
    allowed_card_extensions = set(allowed_product_card_extensions or set())

    @app.route('/api/products/card-image/upload', methods=['POST'])
    @app.route('/api/bio-products/card-image/upload', methods=['POST'])
    @login_required
    def upload_product_card_image():
        """上传产品卡片图片并返回可访问 URL。"""
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = validate_uploaded_image_extension(file, allowed_extensions=allowed_card_extensions)
        if not ext:
            return jsonify({'success': False, 'message': '仅支持 PNG/JPG/JPEG/WEBP 图片'}), 400

        saved_name = f'{uuid.uuid4().hex}{ext}'
        save_path = product_card_uploads_path / saved_name
        file.save(save_path)
        return jsonify({
            'success': True,
            'url': f'/media/product-cards/{saved_name}',
        })

    @app.route('/media/product-cards/<path:filename>')
    def serve_product_card_media(filename):
        """提供已上传的产品卡片图片访问。"""
        return send_from_directory(product_card_uploads_path, filename)

    @app.route('/api/products/settings', methods=['GET'])
    def get_product_settings_api():
        """获取产品菜单设置。"""
        return jsonify(get_product_settings())

    @app.route('/api/bio-products/settings', methods=['GET'])
    def get_bio_product_settings_api():
        """获取生物传感产品菜单设置。"""
        return jsonify(get_bio_product_settings())

    @app.route('/api/products/settings', methods=['POST'])
    @login_required
    def update_product_settings_api():
        """更新产品菜单设置。"""
        data = request.json or {}
        settings, error = _apply_product_settings_updates(get_product_settings(), data)
        if error:
            return jsonify({'success': False, 'message': error[0]}), error[1]
        save_product_settings(settings)
        return jsonify({'success': True, 'settings': settings})

    @app.route('/api/bio-products/settings', methods=['POST'])
    @login_required
    def update_bio_product_settings_api():
        """更新生物传感产品设置。"""
        data = request.json or {}
        settings, error = _apply_product_settings_updates(get_bio_product_settings(), data)
        if error:
            return jsonify({'success': False, 'message': error[0]}), error[1]
        save_bio_product_settings(settings)
        return jsonify({'success': True, 'settings': settings})

    @app.route('/api/products/settings/sort', methods=['POST'])
    @login_required
    def update_product_sort_order():
        """批量更新产品排序。"""
        data = request.json or {}
        settings, error = _apply_sort_order(get_product_settings(), data.get('order', []))
        if error:
            return jsonify({'success': False, 'message': error[0]}), error[1]
        save_product_settings(settings)
        return jsonify({'success': True, 'message': f'已更新 {len(data.get("order", []))} 个产品的排序'})

    @app.route('/api/bio-products/settings/sort', methods=['POST'])
    @login_required
    def update_bio_product_sort_order():
        """批量更新生物传感产品排序。"""
        data = request.json or {}
        settings, error = _apply_sort_order(get_bio_product_settings(), data.get('order', []))
        if error:
            return jsonify({'success': False, 'message': error[0]}), error[1]
        save_bio_product_settings(settings)
        return jsonify({'success': True, 'message': f'已更新 {len(data.get("order", []))} 个产品的排序'})

    @app.route('/api/categories')
    def get_categories_api():
        """获取 Mega Menu 使用的全部产品分类。"""
        return jsonify({'categories': [dict(item) for item in PRODUCT_MENU_CATEGORIES]})

    @app.route('/api/categories/images', methods=['GET'])
    def get_category_images_api():
        """获取附带分类信息的产品分类图片。"""
        return jsonify({'categories': get_product_categories_with_images()})

    @app.route('/api/categories/images', methods=['POST'])
    @login_required
    def save_category_images_api():
        """保存产品分类图片。"""
        data = request.json or {}
        images = data.get('images', {})
        if not isinstance(images, dict):
            return jsonify({'success': False, 'message': '无效的图片数据'}), 400
        save_product_category_images(images)
        return jsonify({'success': True, 'categories': get_product_categories_with_images()})

    @app.route('/api/products/industry-filters', methods=['GET'])
    def get_industry_filters_api():
        """获取全产品页行业筛选配置。"""
        return jsonify(get_industry_filters())

    @app.route('/api/bio-products/industry-filters', methods=['GET'])
    def get_bio_industry_filters_api():
        """获取生物传感行业筛选配置。"""
        return jsonify(get_bio_industry_filters())

    @app.route('/api/products/industry-filters', methods=['POST'])
    @login_required
    def save_industry_filters_api():
        """更新全产品页行业筛选配置。"""
        data = request.json or {}
        saved = save_industry_filters(data)
        return jsonify({'success': True, 'categories': saved.get('categories', [])})

    @app.route('/api/bio-products/industry-filters', methods=['POST'])
    @login_required
    def save_bio_industry_filters_api():
        """更新生物传感行业筛选配置。"""
        data = request.json or {}
        saved = save_bio_industry_filters(data)
        return jsonify({'success': True, 'categories': saved.get('categories', [])})
