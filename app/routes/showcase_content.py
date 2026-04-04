"""首页展示位与氢气首页内容路由模块。

负责精选产品、精选方案、氢气首页配置、案例与测量对象展示。
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from flask import jsonify, request, session

# 模块级依赖容器，在 configure/register 阶段一次性注入。
_DEPS = {}
MEASUREMENT_PRODUCT_LIMIT = 4
MEASUREMENT_PAGE_ORDER = [
    'measurement-environment-hydrogen',
    'measurement-hydrogen',
    'measurement-dissolved-hydrogen',
    'measurement-oil-water',
    'measurement-hydrogen-tracking',
    'measurement-humidity',
    'measurement-hydrogen-warning',
    'measurement-combustible-gas',
    'measurement-dewpoint',
    'measurement-pressure',
]



# 依赖注入配置入口。
def configure_showcase_content(
    *,
    pages_dir,
    cached_json_response,
    sanitize_public_media_url,
    sanitize_public_text,
    sanitize_public_link_url,
    validate_uploaded_video_extension,
    product_featured_file,
    solutions_featured_file,
    hydrogen_solutions_config_file,
    h2_home_file,
    h2_home_video_uploads_dir,
    allowed_h2_home_video_extensions,
    get_products_with_settings_data,
    get_gassensing_products_with_settings,
    get_all_case_items,
    extract_solution_meta_from_html,
):
    """配置首页展示内容模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update({
        'pages_dir': Path(pages_dir),
        'cached_json_response': cached_json_response,
        'sanitize_public_media_url': sanitize_public_media_url,
        'sanitize_public_text': sanitize_public_text,
        'sanitize_public_link_url': sanitize_public_link_url,
        'validate_uploaded_video_extension': validate_uploaded_video_extension,
        'product_featured_file': Path(product_featured_file),
        'solutions_featured_file': Path(solutions_featured_file),
        'hydrogen_solutions_config_file': Path(hydrogen_solutions_config_file),
        'h2_home_file': Path(h2_home_file),
        'h2_home_video_uploads_dir': Path(h2_home_video_uploads_dir),
        'allowed_h2_home_video_extensions': set(allowed_h2_home_video_extensions or set()),
        'get_products_with_settings_data': get_products_with_settings_data,
        'get_gassensing_products_with_settings': get_gassensing_products_with_settings,
        'get_all_case_items': get_all_case_items,
        'extract_solution_meta_from_html': extract_solution_meta_from_html,
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'Showcase content dependency not configured: {name}')
    return value


def get_featured_products_config():
    """加载精选产品配置。"""
    default_config = {'ids': []}
    product_featured_file = _dep('product_featured_file')
    if product_featured_file.exists():
        try:
            config = json.loads(product_featured_file.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('ids', []), list):
                return config
        except Exception:
            pass
    product_featured_file.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


def save_featured_products_config(new_config):
    """保存精选产品配置。"""
    ids = new_config.get('ids', [])
    if not isinstance(ids, list):
        ids = []
    seen = set()
    normalized = []
    for product_id in ids:
        if not product_id or not isinstance(product_id, str):
            continue
        if product_id in seen:
            continue
        seen.add(product_id)
        normalized.append(product_id)
    saved = {'ids': normalized[:3]}
    _dep('product_featured_file').write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def get_featured_solutions_config():
    """加载精选解决方案配置。"""
    default_config = {'ids': []}
    solutions_featured_file = _dep('solutions_featured_file')
    if solutions_featured_file.exists():
        try:
            config = json.loads(solutions_featured_file.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('ids', []), list):
                return config
        except Exception:
            pass
    solutions_featured_file.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


def save_featured_solutions_config(new_config):
    """保存精选解决方案配置。"""
    ids = new_config.get('ids', [])
    if not isinstance(ids, list):
        ids = []
    seen = set()
    normalized = []
    for solution_id in ids:
        if not solution_id or not isinstance(solution_id, str):
            continue
        if solution_id in seen:
            continue
        seen.add(solution_id)
        normalized.append(solution_id)
    saved = {'ids': normalized[:3]}
    _dep('solutions_featured_file').write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def build_product_link(product):
    """根据产品 ID 构建公开产品链接路径。"""
    product_id = product.get('id', '')
    if product_id.startswith('../customization/'):
        slug = product_id.replace('../customization/', '').strip('/')
        return f'pages/customization/{slug}.html'
    if product_id.startswith('../biosensing/'):
        slug = product_id.replace('../biosensing/', '').strip('/')
        return f'pages/biosensing/{slug}.html'
    return f'pages/gassensing/{product_id}.html'


def build_solution_link(solution):
    return f"pages/solutions/{solution.get('id', '')}.html"


def _measurement_pages_dir() -> Path:
    return _dep('pages_dir') / 'measurement'


def _extract_measurement_page_title(filepath: Path) -> str:
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return filepath.stem

    breadcrumb_match = re.search(
        r'<p[^>]*class="[^"]*jjfa-breadcrumb[^"]*"[^>]*>.*?<span>(.*?)</span>',
        content,
        re.I | re.S,
    )
    if breadcrumb_match:
        crumb_title = re.sub(r'<[^>]+>', ' ', breadcrumb_match.group(1))
        crumb_title = re.sub(r'\s+', ' ', crumb_title).strip()
        if crumb_title:
            return _dep('sanitize_public_text')(crumb_title, max_length=120)

    match = re.search(r'<title[^>]*>(.*?)</title>', content, re.I | re.S)
    raw_title = match.group(1).strip() if match else filepath.stem
    title = re.sub(r'\s*-\s*元芯传感\s*$', '', raw_title)
    title = re.sub(r'\s+', ' ', title).strip()
    return _dep('sanitize_public_text')(title or filepath.stem, max_length=160)


def get_measurement_page_items():
    pages = []
    measurement_dir = _measurement_pages_dir()
    if not measurement_dir.exists():
        return pages

    order_map = {page_id: idx for idx, page_id in enumerate(MEASUREMENT_PAGE_ORDER)}
    for filepath in sorted(measurement_dir.glob('*.html')):
        page_id = filepath.stem
        pages.append({
            'id': page_id,
            'filename': filepath.name,
            'title': _extract_measurement_page_title(filepath),
            'path': f'pages/measurement/{filepath.name}',
            '_order': order_map.get(page_id, len(order_map) + len(pages)),
        })

    pages.sort(key=lambda item: (item.get('_order', 999), item.get('title', ''), item.get('filename', '')))
    for item in pages:
        item.pop('_order', None)
    return pages


def _normalize_measurement_products_map(raw_map):
    mapping = raw_map if isinstance(raw_map, dict) else {}
    valid_page_ids = {item.get('id') for item in get_measurement_page_items() if item.get('id')}
    valid_product_ids = {
        product.get('id')
        for product in _dep('get_gassensing_products_with_settings')()
        if product.get('id') and not product.get('hidden')
    }
    cleaned = {}
    for page_id, product_ids in mapping.items():
        if not isinstance(page_id, str) or page_id not in valid_page_ids:
            continue
        ids = product_ids if isinstance(product_ids, list) else []
        seen = set()
        normalized = []
        for product_id in ids:
            if not isinstance(product_id, str) or product_id not in valid_product_ids or product_id in seen:
                continue
            seen.add(product_id)
            normalized.append(product_id)
            if len(normalized) >= MEASUREMENT_PRODUCT_LIMIT:
                break
        cleaned[page_id] = normalized
    return cleaned


def _serialize_public_product_item(item):
    if not item:
        return None
    title = item.get('cardTitle') or item.get('displayName') or item.get('shortName') or item.get('name') or item.get('id', '')
    desc = item.get('cardSummary') or item.get('description', '')
    return {
        'id': item.get('id'),
        'title': _dep('sanitize_public_text')(title, max_length=120),
        'image': _dep('sanitize_public_media_url')(item.get('cardImage') or item.get('image', ''), enforce_remote_public=False),
        'desc': _dep('sanitize_public_text')(desc, max_length=220),
        'link': _dep('sanitize_public_link_url')(build_product_link(item), default='#'),
        'category': _dep('sanitize_public_text')(item.get('category', ''), max_length=40),
    }


def get_all_solution_items():
    """获取 pages/solutions 目录下的全部解决方案项。"""
    solutions_dir = _dep('pages_dir') / 'solutions'
    items = []
    if solutions_dir.exists():
        for filepath in sorted(solutions_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            item = _dep('extract_solution_meta_from_html')(filepath)
            if item:
                item['link'] = _dep('sanitize_public_link_url')(build_solution_link(item), default='#')
                items.append(item)
    return items


def get_h2_home_config():
    """加载氢气首页配置。"""
    default_config = {'items': [], 'products': [], 'cases': [], 'news': [], 'measurementProducts': {}}
    h2_home_file = _dep('h2_home_file')
    if h2_home_file.exists():
        try:
            config = json.loads(h2_home_file.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('items', []), list):
                items = []
                for item in config.get('items', []):
                    if not isinstance(item, dict):
                        continue
                    url = _dep('sanitize_public_media_url')(item.get('url', ''), enforce_remote_public=False)
                    if not url:
                        continue
                    items.append({
                        'id': item.get('id') or str(uuid.uuid4()),
                        'url': url,
                    })
                return {
                    'items': items,
                    'products': config.get('products', []) if isinstance(config.get('products', []), list) else [],
                    'cases': config.get('cases', []) if isinstance(config.get('cases', []), list) else [],
                    'news': config.get('news', []) if isinstance(config.get('news', []), list) else [],
                    'measurementProducts': _normalize_measurement_products_map(config.get('measurementProducts', {})),
                }
        except Exception:
            pass
    h2_home_file.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding='utf-8')
    return default_config


def save_h2_home_config(config):
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = _dep('sanitize_public_media_url')(item.get('url', ''), enforce_remote_public=True)
        if not url:
            continue
        cleaned.append({
            'id': item.get('id') or str(uuid.uuid4()),
            'url': url,
        })
    existing = get_h2_home_config()
    saved = {
        'items': cleaned,
        'products': existing.get('products', []),
        'cases': existing.get('cases', []),
        'news': existing.get('news', []),
        'measurementProducts': existing.get('measurementProducts', {}),
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_products(product_ids):
    if not isinstance(product_ids, list):
        product_ids = []
    cleaned = []
    seen = set()
    for product_id in product_ids:
        if not product_id or not isinstance(product_id, str):
            continue
        if product_id in seen:
            continue
        seen.add(product_id)
        cleaned.append(product_id)
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': cleaned[:3],
        'cases': existing.get('cases', []),
        'news': existing.get('news', []),
        'measurementProducts': existing.get('measurementProducts', {}),
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_cases(items):
    """保存氢气首页案例，并支持可选自定义文案。"""
    if not isinstance(items, list):
        items = []
    cleaned = []
    seen = set()
    sanitize_public_text = _dep('sanitize_public_text')
    for item in items:
        if not isinstance(item, dict):
            if isinstance(item, str) and item and item not in seen:
                seen.add(item)
                cleaned.append({'id': item, 'customSubtitle': '', 'customTitle': ''})
            continue
        case_id = item.get('id')
        if not case_id or not isinstance(case_id, str):
            continue
        if case_id in seen:
            continue
        seen.add(case_id)
        cleaned.append({
            'id': case_id,
            'customSubtitle': sanitize_public_text(item.get('customSubtitle', ''), max_length=40),
            'customTitle': sanitize_public_text(item.get('customTitle', ''), max_length=120),
        })
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': existing.get('products', []),
        'cases': cleaned[:6],
        'news': existing.get('news', []),
        'measurementProducts': existing.get('measurementProducts', {}),
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_measurement_products(items):
    mapping = {}
    source = items if isinstance(items, list) else []
    for item in source:
        if not isinstance(item, dict):
            continue
        page_id = item.get('id')
        if not isinstance(page_id, str) or not page_id.strip():
            continue
        product_ids = item.get('productIds', [])
        mapping[page_id.strip()] = product_ids if isinstance(product_ids, list) else []

    cleaned = _normalize_measurement_products_map(mapping)
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': existing.get('products', []),
        'cases': existing.get('cases', []),
        'news': existing.get('news', []),
        'measurementProducts': cleaned,
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


HYDROGEN_SOLUTION_DEFINITIONS = [
    {'id': 'electrolysis_online_leak', 'title': '电解水制氢过程在线分析与泄漏监测解决方案'},
    {'id': 'station_vehicle_safety', 'title': '加氢站与燃料电池车氢监测协同安全解决方案'},
    {'id': 'lab_multidimensional_monitoring', 'title': '涉氢实验室多维度气体泄漏立体监测系统'},
    {'id': 'city_pipeline_home_safety', 'title': '城市能源输氢管网与用氢家庭安全解决方案'},
    {'id': 'trace_hydrogen_leak_detection', 'title': '微量氢气泄漏检测解决方案'},
    {'id': 'generator_h2_purity_leak', 'title': '氢冷发电机氢气纯度分析与泄漏监测解决方案'},
    {'id': 'stator_cooling_water_h2', 'title': '发电机组定冷水氢检测解决方案'},
    {'id': 'nuclear_dissolved_h2', 'title': '核电站水中溶解氢监测解决方案'},
    {'id': 'transformer_oil_h2', 'title': '变压器油中氢浓度检测解决方案'},
    {'id': 'general_pipe_container_leak', 'title': '管道容器通用检漏解决方案'},
    {'id': 'refrigerant_industry_leak', 'title': '冷媒行业检漏解决方案'},
    {'id': 'energy_storage_thermal_runaway_warning', 'title': '储能锂电池热失控预警解决方案'},
    {'id': 'environment_gas_monitoring', 'title': '环境气体监测解决方案'},
]

DEFAULT_HYDROGEN_SOLUTION_PRODUCTS = {
    'electrolysis_online_leak': ['mc_ol_h1', 'mc_ld_h2', 'mc_hla_01', 'mc_pgd_01'],
    'station_vehicle_safety': ['mc_ld_h2', 'mc_hp_1_0', 'mc_wd_01', 'mc_hla_01'],
    'lab_multidimensional_monitoring': ['mc_ld_ph2', 'mc_ld_h2', 'mc_wd_01', 'mc_pdr_01'],
    'city_pipeline_home_safety': ['mc_hha_01', 'mc_hla_01', 'mc_pgd_01', 'mc_ld_nh2'],
    'trace_hydrogen_leak_detection': ['mc_td_01', 'mc_ld_nh2', 'mc_ld_h2', 'mc_ld_ph2'],
    'generator_h2_purity_leak': ['mc_ol_h1', 'mc_hla_01', 'mc_ld_h2', 'mc_pgd_01'],
    'stator_cooling_water_h2': ['mc_pgd_01', 'mc_ol_h1', 'mc_hla_01', 'mc_ld_h2'],
    'nuclear_dissolved_h2': ['mc_pgd_01', 'mc_ol_h1', 'mc_hla_01', 'mc_wd_01'],
    'transformer_oil_h2': ['mc_pgd_01', 'mc_ld_h2', 'mc_hla_01', 'mc_td_01'],
    'general_pipe_container_leak': ['mc_td_01', 'mc_ld_nh2', 'mc_ld_h2', 'mc_ld_ph2'],
    'refrigerant_industry_leak': ['mc_hla_01', 'mc_wd_01', 'mc_ld_h2', 'mc_td_01'],
    'energy_storage_thermal_runaway_warning': ['mc_hla_01', 'mc_ld_h2', 'mc_ld_ph2', 'mc_pgd_01'],
    'environment_gas_monitoring': ['mc_gd_01', 'mc_pgd_01', 'mc_pdr_01', 'mc_tm_01'],
}


def get_hydrogen_solution_definitions():
    return [dict(item) for item in HYDROGEN_SOLUTION_DEFINITIONS]


def get_hydrogen_solution_product_pool():
    """获取可用于氢气解决方案关联配置的产品池。"""
    pool = []
    for product in _dep('get_products_with_settings_data')():
        product_id = str(product.get('id', '')).strip()
        if not product_id or product_id == 'all-products':
            continue
        if product_id.startswith('../biosensing/'):
            continue
        pool.append(product)
    return pool


def normalize_hydrogen_solution_products_config(raw_config):
    """规范化已存储的氢气解决方案关联产品配置，确保每个方案都有 1 到 4 个有效产品 ID。"""
    pool = get_hydrogen_solution_product_pool()
    ordered_pool_ids = [str(item.get('id', '')).strip() for item in pool if str(item.get('id', '')).strip()]
    available_ids = set(ordered_pool_ids)

    raw_map = {}
    if isinstance(raw_config, dict):
        if isinstance(raw_config.get('solutions'), list):
            for item in raw_config.get('solutions', []):
                if not isinstance(item, dict):
                    continue
                solution_id = str(item.get('id', '')).strip()
                if solution_id:
                    raw_map[solution_id] = item.get('relatedProductIds', [])
        else:
            for solution_id, value in raw_config.items():
                if not isinstance(solution_id, str):
                    continue
                raw_map[solution_id] = value

    normalized_solutions = []
    fallback_pool_ids = ordered_pool_ids[:4]

    for definition in get_hydrogen_solution_definitions():
        solution_id = definition['id']
        candidate_ids = raw_map.get(solution_id, [])
        if not isinstance(candidate_ids, list):
            candidate_ids = []
        cleaned_ids = []
        seen = set()
        for product_id in candidate_ids:
            current_id = str(product_id or '').strip()
            if not current_id or current_id in seen or current_id not in available_ids:
                continue
            seen.add(current_id)
            cleaned_ids.append(current_id)
            if len(cleaned_ids) >= 4:
                break

        if not cleaned_ids:
            default_ids = DEFAULT_HYDROGEN_SOLUTION_PRODUCTS.get(solution_id, [])
            for product_id in default_ids:
                if product_id in available_ids and product_id not in cleaned_ids:
                    cleaned_ids.append(product_id)
                if len(cleaned_ids) >= 4:
                    break

        if not cleaned_ids:
            cleaned_ids = fallback_pool_ids[:4]

        normalized_solutions.append({
            'id': solution_id,
            'relatedProductIds': cleaned_ids[:4],
        })

    return {'solutions': normalized_solutions}


def get_hydrogen_solution_products_config():
    config_file = _dep('hydrogen_solutions_config_file')
    if config_file.exists():
        try:
            raw = json.loads(config_file.read_text(encoding='utf-8'))
        except Exception:
            raw = {}
    else:
        raw = {}
    return normalize_hydrogen_solution_products_config(raw)


def save_hydrogen_solution_products_config(new_config):
    normalized = normalize_hydrogen_solution_products_config(new_config)
    _dep('hydrogen_solutions_config_file').write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return normalized


def to_solution_product_card(product):
    title = product.get('displayName') or product.get('shortName') or product.get('name') or product.get('id', '')
    image = (product.get('cardImage') or '').strip() or (product.get('image') or '').strip()
    summary = (product.get('cardSummary') or '').strip() or (product.get('description') or '').strip()
    link = '/' + build_product_link(product).lstrip('/')
    return {
        'id': product.get('id', ''),
        'title': _dep('sanitize_public_text')(title, max_length=120),
        'image': _dep('sanitize_public_media_url')(image, enforce_remote_public=False),
        'summary': _dep('sanitize_public_text')(summary, max_length=220),
        'link': _dep('sanitize_public_link_url')(link, default='#'),
    }


def build_hydrogen_solution_public_payload():
    config = get_hydrogen_solution_products_config()
    config_map = {
        str(item.get('id', '')).strip(): item.get('relatedProductIds', [])
        for item in config.get('solutions', []) if isinstance(item, dict)
    }
    pool = get_hydrogen_solution_product_pool()
    product_map = {str(item.get('id', '')).strip(): item for item in pool if str(item.get('id', '')).strip()}

    payload = []
    for definition in get_hydrogen_solution_definitions():
        solution_id = definition['id']
        related_ids = config_map.get(solution_id, [])
        related_products = []
        for product_id in related_ids:
            product = product_map.get(str(product_id).strip())
            if not product:
                continue
            related_products.append(to_solution_product_card(product))
            if len(related_products) >= 4:
                break
        payload.append({
            'id': solution_id,
            'title': definition['title'],
            'relatedProducts': related_products,
        })
    return payload



# 路由注册入口。
def register_showcase_content_routes(
    app,
    *,
    login_required,
    pages_dir,
    cached_json_response,
    sanitize_public_media_url,
    sanitize_public_text,
    sanitize_public_link_url,
    validate_uploaded_video_extension,
    product_featured_file,
    solutions_featured_file,
    hydrogen_solutions_config_file,
    h2_home_file,
    h2_home_video_uploads_dir,
    allowed_h2_home_video_extensions,
    get_products_with_settings_data,
    get_gassensing_products_with_settings,
    get_all_case_items,
    extract_solution_meta_from_html,
):
    """注册首页展示位与氢气首页相关路由。"""
    configure_showcase_content(
        pages_dir=pages_dir,
        cached_json_response=cached_json_response,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_video_extension=validate_uploaded_video_extension,
        product_featured_file=product_featured_file,
        solutions_featured_file=solutions_featured_file,
        hydrogen_solutions_config_file=hydrogen_solutions_config_file,
        h2_home_file=h2_home_file,
        h2_home_video_uploads_dir=h2_home_video_uploads_dir,
        allowed_h2_home_video_extensions=allowed_h2_home_video_extensions,
        get_products_with_settings_data=get_products_with_settings_data,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_all_case_items=get_all_case_items,
        extract_solution_meta_from_html=extract_solution_meta_from_html,
    )

    @app.route('/api/solutions/hydrogen/config')
    def get_hydrogen_solutions_public_config():
        """获取行业解决方案页面使用的公开配置，按方案返回关联产品。"""
        return jsonify({'solutions': build_hydrogen_solution_public_payload()})

    @app.route('/api/admin/hydrogen-solutions/config')
    @login_required
    def get_hydrogen_solutions_admin_config():
        """获取后台配置载荷，包含方案列表、已选产品 ID 与候选产品项。"""
        products = get_hydrogen_solution_product_pool()
        product_options = []
        for product in products:
            product_id = str(product.get('id', '')).strip()
            if not product_id:
                continue
            product_options.append({
                'id': product_id,
                'title': product.get('displayName') or product.get('shortName') or product.get('name') or product_id,
                'image': (product.get('cardImage') or '').strip() or (product.get('image') or '').strip(),
            })
        return jsonify({
            'success': True,
            'definitions': get_hydrogen_solution_definitions(),
            'config': get_hydrogen_solution_products_config(),
            'products': product_options,
        })

    @app.route('/api/admin/hydrogen-solutions/config', methods=['POST'])
    @login_required
    def update_hydrogen_solutions_admin_config():
        """持久化保存后台编辑的方案关联产品 ID。"""
        data = request.json or {}
        saved = save_hydrogen_solution_products_config(data)
        return jsonify({'success': True, 'config': saved})

    @app.route('/api/products/featured')
    def get_featured_products():
        config = get_featured_products_config()
        ids = config.get('ids', [])
        products = [product for product in _dep('get_products_with_settings_data')() if not product.get('hidden')]
        product_map = {product.get('id'): product for product in products if product.get('id')}
        featured = [product_map.get(product_id) for product_id in ids if product_map.get(product_id)]

        if len(featured) < 3:
            for item in products:
                if item in featured:
                    continue
                featured.append(item)
                if len(featured) >= 3:
                    break

        items = []
        for item in featured[:3]:
            if not item:
                continue
            title = item.get('displayName') or item.get('shortName') or item.get('name') or item.get('id', '')
            items.append({
                'id': item.get('id'),
                'title': _dep('sanitize_public_text')(title, max_length=120),
                'image': _dep('sanitize_public_media_url')(item.get('cardImage') or item.get('image', ''), enforce_remote_public=False),
                'desc': _dep('sanitize_public_text')(item.get('cardSummary') or item.get('description', ''), max_length=220),
                'link': build_product_link(item),
            })
        return jsonify({'items': items})

    @app.route('/api/products/featured', methods=['POST'])
    @login_required
    def update_featured_products():
        data = request.json or {}
        config = save_featured_products_config(data)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/products/gassensing')
    @login_required
    def get_gassensing_products():
        products = _dep('get_gassensing_products_with_settings')()
        return jsonify({'products': products, 'count': len(products)})

    @app.route('/api/cases/gassensing')
    @login_required
    def get_gassensing_cases():
        items = _dep('get_all_case_items')()
        return jsonify({'items': items, 'count': len(items)})

    @app.route('/api/solutions/all')
    @login_required
    def get_all_solutions():
        return jsonify({'items': get_all_solution_items()})

    @app.route('/api/solutions/featured')
    def get_featured_solutions():
        config = get_featured_solutions_config()
        ids = config.get('ids', [])
        items = get_all_solution_items()
        item_map = {item.get('id'): item for item in items if item.get('id')}
        featured = [item_map.get(solution_id) for solution_id in ids if item_map.get(solution_id)]

        if len(featured) < 3:
            for item in items:
                if item in featured:
                    continue
                featured.append(item)
                if len(featured) >= 3:
                    break

        output = []
        for item in featured[:3]:
            if not item:
                continue
            output.append({
                'id': item.get('id'),
                'title': _dep('sanitize_public_text')(item.get('title', ''), max_length=120),
                'image': _dep('sanitize_public_media_url')(item.get('image', ''), enforce_remote_public=False),
                'desc': _dep('sanitize_public_text')(item.get('desc', ''), max_length=220),
                'link': _dep('sanitize_public_link_url')(item.get('link', build_solution_link(item)), default='#'),
            })
        return jsonify({'items': output})

    @app.route('/api/solutions/featured', methods=['POST'])
    @login_required
    def update_featured_solutions():
        data = request.json or {}
        config = save_featured_solutions_config(data)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/h2-home', methods=['GET'])
    def get_h2_home():
        payload = get_h2_home_config()
        if session.get('admin_logged_in'):
            response = jsonify(payload)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return _dep('cached_json_response')(payload)

    @app.route('/api/h2-home/upload-video', methods=['POST'])
    @login_required
    def upload_h2_home_video():
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = _dep('validate_uploaded_video_extension')(
            file,
            allowed_extensions=_dep('allowed_h2_home_video_extensions'),
        )
        if not ext:
            return jsonify({'success': False, 'message': '只支持 MP4/WEBM/OGG 视频文件'}), 400

        saved_name = f'{uuid.uuid4().hex}{ext}'
        save_path = _dep('h2_home_video_uploads_dir') / saved_name
        file.save(str(save_path))
        return jsonify({
            'success': True,
            'item': {
                'id': uuid.uuid4().hex,
                'url': f'/media/h2-home/{saved_name}',
                'source': 'upload',
            },
        })

    @app.route('/api/h2-home', methods=['POST'])
    @login_required
    def update_h2_home():
        data = request.json or {}
        config = save_h2_home_config(data)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/h2-home/products', methods=['GET'])
    def get_h2_home_products():
        config = get_h2_home_config()
        ids = config.get('products', [])
        products = [product for product in _dep('get_gassensing_products_with_settings')() if not product.get('hidden')]
        product_map = {product.get('id'): product for product in products if product.get('id')}
        featured = [product_map.get(product_id) for product_id in ids if product_map.get(product_id)]
        if len(featured) < 3:
            for item in products:
                if item in featured:
                    continue
                featured.append(item)
                if len(featured) >= 3:
                    break

        items = []
        for item in featured[:3]:
            if not item:
                continue
            serialized = _serialize_public_product_item(item)
            if serialized:
                items.append(serialized)
        return jsonify({'items': items})

    @app.route('/api/h2-home/products', methods=['POST'])
    @login_required
    def update_h2_home_products():
        data = request.json or {}
        ids = data.get('ids', [])
        config = save_h2_home_products(ids)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/h2-home/cases', methods=['GET'])
    def get_h2_home_cases():
        config = get_h2_home_config()
        case_configs = config.get('cases', [])
        items = _dep('get_all_case_items')()
        item_map = {item.get('id'): item for item in items if item.get('id')}

        output = []
        used_ids = set()
        for case_cfg in case_configs:
            if isinstance(case_cfg, dict):
                case_id = case_cfg.get('id')
                custom_subtitle = _dep('sanitize_public_text')(case_cfg.get('customSubtitle', ''), max_length=40)
                custom_title = _dep('sanitize_public_text')(case_cfg.get('customTitle', ''), max_length=120)
            elif isinstance(case_cfg, str):
                case_id = case_cfg
                custom_subtitle = ''
                custom_title = ''
            else:
                continue

            item = item_map.get(case_id)
            if not item:
                continue
            used_ids.add(case_id)
            output.append({
                'id': item.get('id'),
                'title': _dep('sanitize_public_text')(item.get('title', ''), max_length=120),
                'image': _dep('sanitize_public_media_url')(item.get('image', ''), enforce_remote_public=False),
                'desc': _dep('sanitize_public_text')(item.get('desc', ''), max_length=220),
                'link': _dep('sanitize_public_link_url')(item.get('link', ''), default='#'),
                'customSubtitle': custom_subtitle,
                'customTitle': custom_title,
            })

        if len(output) < 6:
            for item in items:
                if item.get('id') in used_ids:
                    continue
                output.append({
                    'id': item.get('id'),
                    'title': _dep('sanitize_public_text')(item.get('title', ''), max_length=120),
                    'image': _dep('sanitize_public_media_url')(item.get('image', ''), enforce_remote_public=False),
                    'desc': _dep('sanitize_public_text')(item.get('desc', ''), max_length=220),
                    'link': _dep('sanitize_public_link_url')(item.get('link', ''), default='#'),
                    'customSubtitle': '',
                    'customTitle': '',
                })
                if len(output) >= 6:
                    break
        return jsonify({'items': output[:6]})

    @app.route('/api/h2-home/measurement-products', methods=['GET'])
    def get_h2_home_measurement_products():
        slug = str(request.args.get('slug') or '').strip()
        config = get_h2_home_config()
        measurement_map = config.get('measurementProducts', {})
        pages = get_measurement_page_items()

        if slug:
            page = next((item for item in pages if item.get('id') == slug), None)
            product_ids = measurement_map.get(slug, [])
            products = [product for product in _dep('get_gassensing_products_with_settings')() if not product.get('hidden')]
            product_map = {product.get('id'): product for product in products if product.get('id')}
            items = []
            for product_id in product_ids:
                serialized = _serialize_public_product_item(product_map.get(product_id))
                if serialized:
                    items.append(serialized)
            payload = {
                'slug': slug,
                'title': page.get('title', '') if page else '',
                'items': items,
            }
        else:
            payload = {
                'pages': [
                    {
                        **page,
                        'selectedIds': measurement_map.get(page.get('id'), []),
                    }
                    for page in pages
                ],
                'count': len(pages),
            }

        if session.get('admin_logged_in'):
            response = jsonify(payload)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return _dep('cached_json_response')(payload)

    @app.route('/api/h2-home/measurement-products', methods=['POST'])
    @login_required
    def update_h2_home_measurement_products():
        data = request.json or {}
        items = data.get('items', [])
        config = save_h2_home_measurement_products(items)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/h2-home/cases', methods=['POST'])
    @login_required
    def update_h2_home_cases():
        data = request.json or {}
        items = data.get('items', [])
        if not items and data.get('ids'):
            items = [{'id': case_id} for case_id in data.get('ids', [])]
        config = save_h2_home_cases(items)
        return jsonify({'success': True, 'config': config})
