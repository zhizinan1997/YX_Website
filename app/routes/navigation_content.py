"""Navigation preview and recommendation routes."""

import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import jsonify, request

APP_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APP_ROOT / 'data'
RECOMMENDATIONS_FILE = DATA_DIR / 'recommendations.json'
MEASUREMENT_TARGETS_FILE = DATA_DIR / 'measurement_targets.json'
NAV_INDUSTRY_CATEGORIES_FILE = DATA_DIR / 'nav_industry_categories.json'

_NORMALIZE_SCANNED_IMAGE_PATH = lambda image, web_dir_prefix: image or ''
_EXTRACT_SOLUTION_META_FROM_HTML = lambda _filepath: None
_EXTRACT_CASE_META_FROM_HTML = lambda _filepath: None
_EXTRACT_PRODUCT_META_FROM_HTML = lambda _filepath: None

NAV_PREVIEW_PAGE_SECTIONS = (
    'gassensing',
    'solutions',
    'research',
    'measurement',
    'customization',
    'biosensing',
)


def get_web_dir_prefix_for_filepath(filepath):
    """Build the public web directory prefix for a local HTML file."""
    site_root = APP_ROOT.resolve()
    try:
        relative_dir = filepath.resolve().parent.relative_to(site_root).as_posix()
    except ValueError:
        return '/'
    return f'/{relative_dir}' if relative_dir else '/'


def resolve_local_nav_target_path(url):
    """Resolve a nav target URL to a local HTML file when possible."""
    raw_url = str(url or '').strip()
    if not raw_url or re.match(r'^https?://', raw_url, re.I):
        return None

    parsed = urlparse(raw_url)
    raw_path = unquote((parsed.path or '').strip()).replace('\\', '/')
    if not raw_path:
        return None

    if raw_path.startswith('/'):
        normalized = raw_path.lstrip('/')
    else:
        normalized = raw_path
        while normalized.startswith('./'):
            normalized = normalized[2:]
        while normalized.startswith('../'):
            normalized = normalized[3:]
        if not normalized.startswith('pages/') and any(
            normalized.startswith(section + '/') for section in NAV_PREVIEW_PAGE_SECTIONS
        ):
            normalized = 'pages/' + normalized

    if not normalized.lower().endswith('.html'):
        return None

    candidate = (APP_ROOT / normalized).resolve()
    try:
        candidate.relative_to(APP_ROOT)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def extract_generic_page_preview_image(filepath):
    """Extract a best-effort preview image from an HTML page."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''

    meta_match = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
        content,
        re.I,
    )
    if meta_match:
        return meta_match.group(1).strip()

    hero_match = re.search(
        r'background-image\s*:\s*(?:linear-gradient\([^;]*?\)\s*,\s*)?url\([\'"]?([^\'")]+)[\'"]?\)',
        content,
        re.I | re.S,
    )
    if hero_match:
        return hero_match.group(1).strip()

    for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.I):
        src = str(match.group(1) or '').strip()
        if not src:
            continue
        if any(token in src.lower() for token in ['icon', 'logo', 'arrow', 'btn', 'button']):
            continue
        return src
    return ''


def normalize_nav_preview_text(text, limit=88):
    """Normalize preview text for compact nav cards."""
    raw = re.sub(r'\s+', ' ', html.unescape(str(text or ''))).strip()
    if not raw:
        return ''
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip(' ，。；、,.?') + '…'


def extract_generic_page_preview_desc(filepath):
    """Extract a short best-effort summary from a local HTML page."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''

    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        content,
        re.I,
    )
    if meta_match:
        return normalize_nav_preview_text(meta_match.group(1), limit=92)

    p_match = re.search(r'<p\b[^>]*>(.*?)</p>', content, re.I | re.S)
    if not p_match:
        return ''

    text = re.sub(r'<[^>]+>', ' ', p_match.group(1))
    return normalize_nav_preview_text(text, limit=92)


def infer_nav_target_preview(url):
    """Infer title, preview image, and short summary for a nav target."""
    filepath = resolve_local_nav_target_path(url)
    if not filepath:
        return {'title': '', 'image': '', 'desc': ''}

    try:
        relative_path = filepath.resolve().relative_to(APP_ROOT).as_posix()
    except ValueError:
        relative_path = ''

    preview = None
    if relative_path.startswith('pages/solutions/'):
        preview = _EXTRACT_SOLUTION_META_FROM_HTML(filepath)
    elif relative_path.startswith('pages/gassensing/cases/'):
        preview = _EXTRACT_CASE_META_FROM_HTML(filepath)
    elif (
        relative_path.startswith('pages/gassensing/')
        or relative_path.startswith('pages/customization/')
        or relative_path.startswith('pages/biosensing/')
    ):
        preview = _EXTRACT_PRODUCT_META_FROM_HTML(filepath)

    image = ''
    title = ''
    desc = ''
    if isinstance(preview, dict):
        image = str(preview.get('image') or '').strip()
        title = str(
            preview.get('title')
            or preview.get('name')
            or preview.get('shortName')
            or preview.get('displayName')
            or ''
        ).strip()
        desc = str(preview.get('desc') or preview.get('summary') or '').strip()
    if not image:
        image = extract_generic_page_preview_image(filepath)
    if not desc:
        desc = extract_generic_page_preview_desc(filepath)

    return {
        'title': normalize_nav_preview_text(title, limit=40),
        'image': _NORMALIZE_SCANNED_IMAGE_PATH(image, get_web_dir_prefix_for_filepath(filepath)),
        'desc': normalize_nav_preview_text(desc, limit=92),
    }


def infer_nav_target_image(url):
    """Infer a preview image for a nav link from its target page."""
    return str(infer_nav_target_preview(url).get('image') or '')


def serialize_nav_industry_category_items(items):
    """Attach preview images to nav industry items when available."""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not url:
            continue
        entry = {'name': name, 'url': url}
        image = infer_nav_target_image(url)
        if image:
            entry['image'] = image
        serialized.append(entry)
    return serialized


def is_safe_recommendation_url(url: str) -> bool:
    """Allow relative paths and http(s) links; block script/data protocols."""
    value = (url or '').strip().lower()
    if not value:
        return False
    if value.startswith('javascript:') or value.startswith('data:'):
        return False
    if value.startswith('http://') or value.startswith('https://'):
        return True
    if value.startswith('/') or value.startswith('./') or value.startswith('../'):
        return True
    if '://' in value:
        return False
    return bool(re.match(r'^[a-z0-9._/-]+\.[a-z0-9]+([?#].*)?$', value))


def normalize_recommendation_items(items):
    """Normalize recommendation item list and keep only valid entries."""
    normalized = []
    if not isinstance(items, list):
        return normalized

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not is_safe_recommendation_url(url):
            continue
        normalized.append({'name': name, 'url': url})
    return normalized


def get_default_measurement_targets():
    """Default measurement targets for mega menu."""
    return {
        'items': [
            {'name': '环境氢', 'url': '../measurement/measurement-environment-hydrogen.html'},
            {'name': '氢纯度', 'url': '../measurement/measurement-hydrogen.html'},
            {'name': '水中氢', 'url': '../measurement/measurement-dissolved-hydrogen.html'},
            {'name': '油中氢', 'url': '../measurement/measurement-oil-water.html'},
            {'name': '氢预警', 'url': '../measurement/measurement-hydrogen-warning.html'},
            {'name': '氢示踪', 'url': '../measurement/measurement-hydrogen-tracking.html'},
            {'name': '微量水', 'url': '../measurement/measurement-humidity.html'},
            {'name': '可燃气体', 'url': '../measurement/measurement-combustible-gas.html'},
        ]
    }


def normalize_measurement_target_items(items):
    """Normalize measurement target items and keep only valid entries."""
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not is_safe_recommendation_url(url):
            continue
        normalized.append({'name': name, 'url': url})
    return normalized


def serialize_measurement_target_items(items):
    """Attach preview images to measurement target items when available."""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not url:
            continue
        entry = {'name': name, 'url': url}
        image = infer_nav_target_image(url)
        if image:
            entry['image'] = image
        serialized.append(entry)
    return serialized


def get_default_solution_nav_items():
    """Default gas nav solution links."""
    return {
        'items': [
            {'name': '氢能源产业链', 'url': '/pages/solutions/industry-hydrogen.html'},
            {'name': '智慧电力安全', 'url': '/pages/solutions/industry-power-safety.html'},
            {'name': '工业检漏监测', 'url': '/pages/solutions/industry-leak-detection.html'},
            {'name': '绿色能源存储', 'url': '/pages/solutions/industry-energy-storage.html'},
            {'name': '大气环境监测', 'url': '/pages/solutions/industry-environment.html'},
        ]
    }


def get_default_research_nav_items():
    """Default gas nav research links."""
    return {
        'items': [
            {'name': '传感器微纳加工', 'url': '/pages/research/micro-nano.html'},
            {'name': '一站式原型开发', 'url': '/pages/research/development.html'},
            {'name': '产学研深度合作', 'url': '/pages/research/cooperation.html'},
        ]
    }


def serialize_solution_nav_items(items):
    """Attach preview image and summary to solution nav items."""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not url:
            continue
        preview = infer_nav_target_preview(url)
        entry = {'name': name, 'url': url}
        title = str(preview.get('title') or '').strip()
        image = str(preview.get('image') or '').strip()
        desc = str(preview.get('desc') or '').strip()
        if title:
            entry['title'] = title
        if image:
            entry['image'] = image
        if desc:
            entry['desc'] = desc
        serialized.append(entry)
    return serialized


def get_solution_nav_items():
    """Build solution nav preview data."""
    return {'items': serialize_solution_nav_items(get_default_solution_nav_items().get('items', []))}


def get_research_nav_items():
    """Build research nav preview data."""
    return {'items': serialize_solution_nav_items(get_default_research_nav_items().get('items', []))}


def get_default_featured_case_nav_items():
    """Default featured case links for gas nav mega menu."""
    return {
        'items': [
            {'name': '氢能重卡氢气检测', 'url': '/pages/gassensing/cases/case-1-truck.html'},
            {'name': '氢能源列车检测', 'url': '/pages/gassensing/cases/case-6-train.html'},
            {'name': '输氢管道人员安全', 'url': '/pages/gassensing/cases/case-4-pipeline-safety.html'},
            {'name': '科研实验室配气', 'url': '/pages/gassensing/cases/case-12-gas-system.html'},
            {'name': '柴油机真空检漏', 'url': '/pages/gassensing/cases/case-13-diesel-engine.html'},
        ]
    }


def get_featured_case_nav_items():
    """Build featured case nav preview data."""
    return {'items': serialize_solution_nav_items(get_default_featured_case_nav_items().get('items', []))}


def get_default_nav_industry_categories():
    """Default industry category links for gas nav mega menu."""
    return {
        'items': [
            {'name': '氢能源产业链', 'url': '/pages/solutions/industry-hydrogen.html'},
            {'name': '智慧电力安全', 'url': '/pages/solutions/industry-power-safety.html'},
            {'name': '工业检漏监测', 'url': '/pages/solutions/industry-leak-detection.html'},
            {'name': '绿色能源存储', 'url': '/pages/solutions/industry-energy-storage.html'},
            {'name': '大气环境监测', 'url': '/pages/solutions/industry-environment.html'},
            {'name': '石油化工', 'url': '/pages/gassensing/cases/case-5-chemical-plant.html'},
        ]
    }


def normalize_nav_industry_category_items(items):
    """Normalize industry category items and keep only valid entries."""
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = str(item.get('url') or '').strip()
        if not name or not is_safe_recommendation_url(url):
            continue
        normalized.append({'name': name, 'url': url})
    return normalized


def get_nav_industry_categories():
    """Load gas nav industry categories settings."""
    if NAV_INDUSTRY_CATEGORIES_FILE.exists():
        try:
            data = json.loads(NAV_INDUSTRY_CATEGORIES_FILE.read_text(encoding='utf-8'))
            items = normalize_nav_industry_category_items(data.get('items', []))
            if items:
                return {'items': serialize_nav_industry_category_items(items)}
        except Exception:
            pass
    return {'items': serialize_nav_industry_category_items(get_default_nav_industry_categories().get('items', []))}


def save_nav_industry_categories(data):
    """Save gas nav industry categories settings."""
    NAV_INDUSTRY_CATEGORIES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def get_measurement_targets():
    """Load measurement targets settings."""
    if MEASUREMENT_TARGETS_FILE.exists():
        try:
            data = json.loads(MEASUREMENT_TARGETS_FILE.read_text(encoding='utf-8'))
            items = normalize_measurement_target_items(data.get('items', []))
            if items:
                return {'items': serialize_measurement_target_items(items)}
        except Exception:
            pass
    return {'items': serialize_measurement_target_items(get_default_measurement_targets().get('items', []))}


def save_measurement_targets(data):
    """Save measurement targets settings."""
    MEASUREMENT_TARGETS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def get_default_recommendations():
    """Default recommendations data."""
    return {
        'latestReleases': [
            {'name': 'MC-LD-H2 氢气泄漏检测仪', 'url': '../gassensing/mc_ld_h2.html'},
            {'name': 'MC-HLA-01 固定式氢气报警器', 'url': '../gassensing/mc_hla_01.html'},
            {'name': 'MC-HHA-01 手持式氢气报警器', 'url': '../gassensing/mc_hha_01.html'},
            {'name': 'MC-WD-01 可穿戴氢气报警器', 'url': '../gassensing/mc_wd_01.html'},
        ],
        'applicationAreas': [
            {'name': '加氢站安全监测', 'url': '../solutions/industry-hydrogen.html'},
            {'name': '燃料电池车辆', 'url': '../solutions/hydrogen.html'},
        ],
    }


def get_recommendations():
    """Load recommendations settings."""
    if RECOMMENDATIONS_FILE.exists():
        try:
            return json.loads(RECOMMENDATIONS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return get_default_recommendations()


def save_recommendations(data):
    """Save recommendations settings."""
    RECOMMENDATIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def register_navigation_content_routes(
    app,
    *,
    login_required,
    app_root,
    data_dir,
    normalize_scanned_image_path,
    extract_solution_meta_from_html,
    extract_case_meta_from_html,
    extract_product_meta_from_html,
):
    """Register navigation preview and recommendation routes."""
    global APP_ROOT, DATA_DIR, RECOMMENDATIONS_FILE, MEASUREMENT_TARGETS_FILE, NAV_INDUSTRY_CATEGORIES_FILE
    global _NORMALIZE_SCANNED_IMAGE_PATH, _EXTRACT_SOLUTION_META_FROM_HTML
    global _EXTRACT_CASE_META_FROM_HTML, _EXTRACT_PRODUCT_META_FROM_HTML

    APP_ROOT = Path(app_root).resolve()
    DATA_DIR = Path(data_dir)
    RECOMMENDATIONS_FILE = DATA_DIR / 'recommendations.json'
    MEASUREMENT_TARGETS_FILE = DATA_DIR / 'measurement_targets.json'
    NAV_INDUSTRY_CATEGORIES_FILE = DATA_DIR / 'nav_industry_categories.json'
    _NORMALIZE_SCANNED_IMAGE_PATH = normalize_scanned_image_path
    _EXTRACT_SOLUTION_META_FROM_HTML = extract_solution_meta_from_html
    _EXTRACT_CASE_META_FROM_HTML = extract_case_meta_from_html
    _EXTRACT_PRODUCT_META_FROM_HTML = extract_product_meta_from_html

    @app.route('/api/recommendations', methods=['GET'])
    def get_recommendations_api():
        """Get mega menu recommendations."""
        return jsonify(get_recommendations())

    @app.route('/api/recommendations', methods=['POST'])
    @login_required
    def update_recommendations_api():
        """Update mega menu recommendations."""
        data = request.json or {}
        recommendations = get_recommendations()

        if 'latestReleases' in data:
            latest = normalize_recommendation_items(data['latestReleases'])
            if not latest:
                return jsonify({'success': False, 'message': '最新发布链接无效，请使用相对路径或 http(s) 链接'}), 400
            recommendations['latestReleases'] = latest

        if 'applicationAreas' in data:
            apps = normalize_recommendation_items(data['applicationAreas'])
            if not apps:
                return jsonify({'success': False, 'message': '应用领域链接无效，请使用相对路径或 http(s) 链接'}), 400
            recommendations['applicationAreas'] = apps

        save_recommendations(recommendations)
        return jsonify({'success': True, 'recommendations': recommendations})

    @app.route('/api/measurement-targets', methods=['GET'])
    def get_measurement_targets_api():
        """Get mega menu measurement targets."""
        return jsonify(get_measurement_targets())

    @app.route('/api/nav-solution-previews', methods=['GET'])
    def get_solution_nav_items_api():
        """Get gas nav solution preview items."""
        return jsonify(get_solution_nav_items())

    @app.route('/api/nav-research-previews', methods=['GET'])
    def get_research_nav_items_api():
        """Get gas nav research preview items."""
        return jsonify(get_research_nav_items())

    @app.route('/api/nav-featured-cases', methods=['GET'])
    def get_featured_case_nav_items_api():
        """Get gas nav featured case preview items."""
        return jsonify(get_featured_case_nav_items())

    @app.route('/api/measurement-targets', methods=['POST'])
    @login_required
    def update_measurement_targets_api():
        """Update mega menu measurement targets."""
        data = request.json or {}
        items = normalize_measurement_target_items(data.get('items', []))
        if not items:
            return jsonify({'success': False, 'message': '请至少提供 1 条有效测量对象（名称 + 相对路径或 http(s) 链接）'}), 400

        payload = {'items': items}
        save_measurement_targets(payload)
        return jsonify({'success': True, 'items': serialize_measurement_target_items(items)})

    @app.route('/api/nav-industry-categories', methods=['GET'])
    def get_nav_industry_categories_api():
        """Get gas nav industry categories."""
        return jsonify(get_nav_industry_categories())

    @app.route('/api/nav-industry-categories', methods=['POST'])
    @login_required
    def update_nav_industry_categories_api():
        """Update gas nav industry categories."""
        data = request.json or {}
        items = normalize_nav_industry_category_items(data.get('items', []))
        if not items:
            return jsonify({'success': False, 'message': '请至少提供 1 条有效行业分类（名称 + 相对路径或 http(s) 链接）'}), 400

        payload = {'items': items}
        save_nav_industry_categories(payload)
        return jsonify({'success': True, 'items': serialize_nav_industry_category_items(items)})
