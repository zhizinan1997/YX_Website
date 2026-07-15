"""
产品设置与行业筛选路由模块。

本模块提供产品配置和行业筛选的管理功能，包括：
1. 产品配置管理
2. 分类图片上传
3. 行业筛选设置
4. 产品卡片图片

主要功能：
1. 产品配置
   - 产品显示名称
   - 产品卡片信息（标题、图片、摘要）
   - 产品排序
   - 产品隐藏/显示
   - 产品分类
   - 行业分类

2. 行业筛选
   - 气体传感行业分类
   - 生物传感行业分类
   - 分类配置管理

3. 分类图片
   - 上传分类图片
   - 分类图片URL管理
   - 分类图片删除

4. 产品卡片
   - 卡片图片上传到对应 CDN 素材目录
   - 卡片配置保存
   - 自动生成缩略图

行业分类：
- 氢能源产品
- 智慧电力产品
- 工业检漏产品
- 科研服务产品
- 定制类产品

产品分类菜单：
- 传感器
- 检测模块
- 检测仪
- 报警器

作者：元芯传感技术团队
"""

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import jsonify, request, send_from_directory

from app.asset_versioning import get_asset_version, inject_version_into_url
from app.upload_utils import get_uploaded_file_size

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
MAX_PRODUCT_CARD_IMAGE_BYTES = 10 * 1024 * 1024
_SEO_SUBMISSION_LOCK = threading.Lock()
_SEO_SUBMISSION_RECENT = {}
_SEO_SUBMISSION_STATUS = {'last_run': 0, 'last_urls': [], 'indexnow': 'not_configured', 'baidu': 'not_configured'}


def _public_product_path(product_id: str, *, bio: bool = False) -> str:
    clean = str(product_id or '').strip()
    if not clean:
        return ''
    if clean.startswith('../biosensing/') or bio:
        return f'/pages/biosensing/{clean.rsplit("/", 1)[-1]}.html'
    if clean.startswith('../customization/'):
        return f'/pages/customization/{clean.rsplit("/", 1)[-1]}.html'
    return f'/pages/gassensing/{clean}.html'


def _semantic_image_upload_name(original_name: str, extension: str) -> str:
    stem = Path(str(original_name or 'product-image')).stem.lower().strip()
    stem = re.sub(r'[^a-z0-9]+', '-', stem).strip('-')[:72] or 'product-image'
    return f'{stem}-{uuid.uuid4().hex[:10]}{extension}'


def queue_search_engine_submission(paths: list[str]):
    """Submit changed public URLs asynchronously when deployment credentials exist."""
    base_url = (os.environ.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        return
    now = time.time()
    urls = []
    with _SEO_SUBMISSION_LOCK:
        for path in paths:
            url = f'{base_url}{path}'
            if now - float(_SEO_SUBMISSION_RECENT.get(url, 0)) < 300:
                continue
            _SEO_SUBMISSION_RECENT[url] = now
            urls.append(url)
    if not urls:
        return

    def worker():
        indexnow_key = (os.environ.get('INDEXNOW_KEY') or '').strip()
        baidu_token = (os.environ.get('BAIDU_PUSH_TOKEN') or '').strip()
        host = base_url.split('://', 1)[-1].split('/', 1)[0]
        statuses = {'last_run': int(time.time()), 'last_urls': urls}
        if indexnow_key:
            try:
                body = json.dumps({'host': host, 'key': indexnow_key, 'urlList': urls}).encode('utf-8')
                request_obj = Request('https://api.indexnow.org/indexnow', data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
                with urlopen(request_obj, timeout=8) as response:
                    statuses['indexnow'] = f'ok:{response.status}'
            except Exception as exc:
                statuses['indexnow'] = f'error:{type(exc).__name__}'
        else:
            statuses['indexnow'] = 'not_configured'
        if baidu_token:
            try:
                endpoint = f'https://data.zz.baidu.com/urls?site={base_url}&token={quote(baidu_token)}'
                request_obj = Request(endpoint, data=('\n'.join(urls)).encode('utf-8'), headers={'Content-Type': 'text/plain'})
                with urlopen(request_obj, timeout=8) as response:
                    statuses['baidu'] = f'ok:{response.status}'
            except Exception as exc:
                statuses['baidu'] = f'error:{type(exc).__name__}'
        else:
            statuses['baidu'] = 'not_configured'
        with _SEO_SUBMISSION_LOCK:
            _SEO_SUBMISSION_STATUS.update(statuses)

    threading.Thread(target=worker, name='seo-url-submit', daemon=True).start()

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


def _versionize_product_images(settings: dict) -> dict:
    """为产品设置中的 cardImage / image 路径追加 mtime 版本号。

    只处理指向 /cdn_assets/ 或历史 /media/product-cards/ 的本地路径，
    外部 URL 和已有 ?v= 的路径保持不变。
    """
    if not isinstance(settings, dict):
        return settings
    for product_id, product in settings.items():
        if not isinstance(product, dict):
            continue
        for key in ('cardImage', 'image'):
            url = product.get(key)
            if not url or not isinstance(url, str):
                continue
            if 'v=' in url:
                continue
            if not url.startswith(('/cdn_assets/', '/media/product-cards/')):
                continue
            version = get_asset_version(url, APP_ROOT)
            if version:
                product[key] = inject_version_into_url(url, version)
    return settings


def get_product_settings():
    """加载产品设置，如自定义名称和新品标记。"""
    if PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return _versionize_product_images(_SANITIZE_PUBLIC_PRODUCT_SETTINGS(raw))
        except Exception:
            pass
    return {}


def get_bio_product_settings():
    """加载生物传感产品设置，如自定义名称和新品标记。"""
    if BIO_PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(BIO_PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return _versionize_product_images(_SANITIZE_PUBLIC_PRODUCT_SETTINGS(raw))
        except Exception:
            pass
    return {}


def save_product_settings(settings):
    """保存产品设置。"""
    cleaned = _SANITIZE_PUBLIC_PRODUCT_SETTINGS(settings)
    temp_path = PRODUCT_SETTINGS_FILE.with_suffix(PRODUCT_SETTINGS_FILE.suffix + f'.tmp-{uuid.uuid4().hex}')
    temp_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    temp_path.replace(PRODUCT_SETTINGS_FILE)
    try:
        from app.routes.product_catalog import invalidate_products_cache
        invalidate_products_cache()
    except Exception:
        pass


def save_bio_product_settings(settings):
    """保存生物传感产品设置。"""
    cleaned = _SANITIZE_PUBLIC_PRODUCT_SETTINGS(settings)
    temp_path = BIO_PRODUCT_SETTINGS_FILE.with_suffix(BIO_PRODUCT_SETTINGS_FILE.suffix + f'.tmp-{uuid.uuid4().hex}')
    temp_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    temp_path.replace(BIO_PRODUCT_SETTINGS_FILE)
    try:
        from app.routes.product_catalog import invalidate_products_cache
        invalidate_products_cache()
    except Exception:
        pass


def _default_consult_button_config():
    """咨询按钮（产品页橙色主按钮）默认配置。"""
    return {'phoneVisible': False, 'phoneText': ''}


def get_consult_button_config(settings):
    """从产品设置中读取咨询按钮配置，缺省返回默认结构。"""
    if not isinstance(settings, dict):
        return _default_consult_button_config()
    cfg = settings.get('consultButton')
    if not isinstance(cfg, dict):
        return _default_consult_button_config()
    return {
        'phoneVisible': bool(cfg.get('phoneVisible', False)),
        'phoneText': str(cfg.get('phoneText', '') or ''),
    }


def set_consult_button_config(settings, data):
    """将咨询按钮配置写入产品设置对象（原地修改）。"""
    phone_visible = bool(data.get('phoneVisible', False))
    phone_text = _SANITIZE_PUBLIC_TEXT(str(data.get('phoneText', '') or ''), max_length=60)
    settings['consultButton'] = {
        'phoneVisible': phone_visible,
        'phoneText': phone_text,
    }
    return settings


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
    seo_text_fields = {
        'seoTitle': 180,
        'seoDescription': 320,
        'sku': 120,
        'brand': 120,
        'manufacturer': 180,
        'seoCategory': 120,
        'imageAlt': 220,
        'imageTitle': 220,
        'imageCaption': 320,
    }
    for field, max_length in seo_text_fields.items():
        if field in data:
            settings[product_id][field] = _SANITIZE_PUBLIC_TEXT(data[field], max_length=max_length)
    if 'indexable' in data:
        settings[product_id]['indexable'] = bool(data['indexable'])
    if 'technicalProperties' in data:
        properties = []
        for item in data['technicalProperties'] if isinstance(data['technicalProperties'], list) else []:
            if not isinstance(item, dict):
                continue
            name = _SANITIZE_PUBLIC_TEXT(item.get('name', ''), max_length=120)
            value = _SANITIZE_PUBLIC_TEXT(item.get('value', ''), max_length=220)
            if name and value:
                properties.append({'name': name, 'value': value})
            if len(properties) >= 40:
                break
        settings[product_id]['technicalProperties'] = properties
    return settings, None


def _apply_sort_order(settings, order):
    if not isinstance(order, list) or not order:
        return None, ('缺少排序数据', 400)

    normalized_order = []
    seen = set()
    for raw_product_id in order:
        product_id = str(raw_product_id or '').strip()
        if not product_id:
            return None, ('排序数据包含无效产品', 400)
        if product_id in seen:
            return None, ('排序数据包含重复产品', 400)
        seen.add(product_id)
        normalized_order.append(product_id)

    for idx, product_id in enumerate(normalized_order):
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
    cdn_assets_dir=None,
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
    cdn_product_images_root = Path(cdn_assets_dir or (APP_ROOT / 'cdn_assets')) / 'images'
    allowed_card_extensions = set(allowed_product_card_extensions or set())

    def _resolve_product_card_upload_target():
        family_dir = 'biosensing' if request.path.startswith('/api/bio-products/') else 'gassensing'
        target_dir = cdn_product_images_root / family_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return family_dir, target_dir

    @app.route('/api/products/card-image/upload', methods=['POST'])
    @app.route('/api/bio-products/card-image/upload', methods=['POST'])
    @login_required
    def upload_product_card_image():
        """上传产品卡片图片到对应 CDN 目录并返回可访问 URL。"""
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = validate_uploaded_image_extension(file, allowed_extensions=allowed_card_extensions)
        if not ext:
            return jsonify({'success': False, 'message': '仅支持 PNG/JPG/JPEG/WEBP 图片'}), 400

        file_size = get_uploaded_file_size(file)
        if file_size is None:
            return jsonify({'success': False, 'message': '无法读取上传文件大小'}), 400
        if file_size > MAX_PRODUCT_CARD_IMAGE_BYTES:
            return jsonify({'success': False, 'message': '产品卡片图片不能超过 10MB'}), 413

        saved_name = _semantic_image_upload_name(file.filename, ext)
        family_dir, target_dir = _resolve_product_card_upload_target()
        save_path = target_dir / saved_name
        file.save(save_path)
        public_url = f'/cdn_assets/images/{family_dir}/{saved_name}'
        try:
            from app.routes.image_seo import register_uploaded_image
            register_uploaded_image(public_url, save_path, role='primary')
        except Exception:
            pass
        return jsonify({
            'success': True,
            'url': public_url,
            'folder': f'images/{family_dir}',
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
        queue_search_engine_submission([_public_product_path(data.get('id'))])
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
        queue_search_engine_submission([_public_product_path(data.get('id'), bio=True)])
        return jsonify({'success': True, 'settings': settings})

    @app.route('/api/products/seo-submission/status', methods=['GET'])
    @login_required
    def get_seo_submission_status():
        with _SEO_SUBMISSION_LOCK:
            return jsonify({'success': True, 'status': dict(_SEO_SUBMISSION_STATUS)})

    @app.route('/api/products/seo-status', methods=['GET'])
    @login_required
    def get_products_seo_status():
        family = str(request.args.get('family') or 'gas').strip().lower()
        products = (
            _GET_BIOSENSING_PRODUCTS_WITH_SETTINGS_DATA()
            if family == 'bio'
            else _GET_PRODUCTS_WITH_SETTINGS_DATA()
        )
        title_counts = {}
        description_counts = {}
        for product in products:
            title = str(product.get('seoTitle') or product.get('displayName') or product.get('name') or '').strip()
            description = str(product.get('seoDescription') or product.get('cardSummary') or product.get('description') or '').strip()
            title_counts[title] = title_counts.get(title, 0) + 1
            description_counts[description] = description_counts.get(description, 0) + 1
        rows = []
        for product in products:
            title = str(product.get('seoTitle') or product.get('displayName') or product.get('name') or '').strip()
            description = str(product.get('seoDescription') or product.get('cardSummary') or product.get('description') or '').strip()
            image = str(product.get('cardImage') or product.get('image') or '').strip()
            warnings = []
            if not description:
                warnings.append('missing_description')
            elif description_counts.get(description, 0) > 1:
                warnings.append('duplicate_description')
            if title_counts.get(title, 0) > 1:
                warnings.append('duplicate_title')
            if len(title) > 70:
                warnings.append('long_title')
            if not image:
                warnings.append('missing_image')
            if not str(product.get('sku') or product.get('shortName') or '').strip():
                warnings.append('missing_sku')
            if not str(product.get('imageAlt') or '').strip():
                warnings.append('missing_image_alt')
            if product.get('indexable') is False:
                warnings.append('noindex')
            rows.append({'id': product.get('id'), 'name': product.get('name'), 'warnings': warnings})
        return jsonify({'success': True, 'family': family, 'items': rows})

    @app.route('/api/products/consult-button', methods=['GET'])
    def get_product_consult_button_api():
        """获取气体产品页橙色按钮的电话配置（公开）。"""
        return jsonify(get_consult_button_config(get_product_settings()))

    @app.route('/api/products/consult-button', methods=['POST'])
    @login_required
    def update_product_consult_button_api():
        """更新气体产品页橙色按钮的电话配置。"""
        data = request.json or {}
        settings = get_product_settings()
        set_consult_button_config(settings, data)
        save_product_settings(settings)
        return jsonify({'success': True, 'config': get_consult_button_config(settings)})

    @app.route('/api/bio-products/consult-button', methods=['GET'])
    def get_bio_product_consult_button_api():
        """获取生物产品页橙色按钮的电话配置（公开）。"""
        return jsonify(get_consult_button_config(get_bio_product_settings()))

    @app.route('/api/bio-products/consult-button', methods=['POST'])
    @login_required
    def update_bio_product_consult_button_api():
        """更新生物产品页橙色按钮的电话配置。"""
        data = request.json or {}
        settings = get_bio_product_settings()
        set_consult_button_config(settings, data)
        save_bio_product_settings(settings)
        return jsonify({'success': True, 'config': get_consult_button_config(settings)})

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
