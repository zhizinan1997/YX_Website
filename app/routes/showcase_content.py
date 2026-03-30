"""Homepage showcase routes: featured products/solutions and H2-home content."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from flask import jsonify, request, session

_DEPS = {}


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
    h2_home_file,
    h2_home_video_uploads_dir,
    allowed_h2_home_video_extensions,
    get_products_with_settings_data,
    get_gassensing_products_with_settings,
    get_all_case_items,
    extract_solution_meta_from_html,
):
    """Configure shared dependencies for showcase/homepage content."""
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
    """Load featured products config."""
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
    """Save featured products config."""
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
    """Load featured solutions config."""
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
    """Save featured solutions config."""
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
    """Build public product link path from product id."""
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


def get_all_solution_items():
    """Get all solution items from pages/solutions."""
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
    """Load hydrogen homepage config."""
    default_config = {'items': [], 'products': [], 'cases': [], 'news': []}
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
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_cases(items):
    """Save H2-home cases with optional custom copy."""
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
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


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
    h2_home_file,
    h2_home_video_uploads_dir,
    allowed_h2_home_video_extensions,
    get_products_with_settings_data,
    get_gassensing_products_with_settings,
    get_all_case_items,
    extract_solution_meta_from_html,
):
    """Register homepage showcase routes."""
    configure_showcase_content(
        pages_dir=pages_dir,
        cached_json_response=cached_json_response,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_video_extension=validate_uploaded_video_extension,
        product_featured_file=product_featured_file,
        solutions_featured_file=solutions_featured_file,
        h2_home_file=h2_home_file,
        h2_home_video_uploads_dir=h2_home_video_uploads_dir,
        allowed_h2_home_video_extensions=allowed_h2_home_video_extensions,
        get_products_with_settings_data=get_products_with_settings_data,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_all_case_items=get_all_case_items,
        extract_solution_meta_from_html=extract_solution_meta_from_html,
    )

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
            title = item.get('displayName') or item.get('shortName') or item.get('name') or item.get('id', '')
            items.append({
                'id': item.get('id'),
                'title': _dep('sanitize_public_text')(title, max_length=120),
                'image': _dep('sanitize_public_media_url')(item.get('image', ''), enforce_remote_public=False),
                'desc': _dep('sanitize_public_text')(item.get('description', ''), max_length=220),
                'link': _dep('sanitize_public_link_url')(build_product_link(item), default='#'),
            })
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

    @app.route('/api/h2-home/cases', methods=['POST'])
    @login_required
    def update_h2_home_cases():
        data = request.json or {}
        items = data.get('items', [])
        if not items and data.get('ids'):
            items = [{'id': case_id} for case_id in data.get('ids', [])]
        config = save_h2_home_cases(items)
        return jsonify({'success': True, 'config': config})
