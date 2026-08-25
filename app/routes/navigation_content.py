"""
导航预览与推荐内容路由模块。

本模块提供网站导航相关的预览和管理功能，包括：
1. 导航预览数据
2. 解决方案入口
3. 研究入口
4. 推荐位内容
5. 行业导航分类

主要功能：
1. 导航预览
   - 预览各区块内容
   - 本地文件路径解析
   - 元数据提取

2. 推荐位管理
   - 推荐产品列表
   - 推荐方案列表
   - 配置文件持久化

3. 测量对象管理
   - 测量对象分类
   - 对象列表管理
   - 配置保存

4. 行业导航
   - 行业分类列表
   - 分类配置
   - 导航数据聚合

导航区块：
- 气体传感
- 解决方案
- 研究服务
- 测量对象
- 定制服务
- 生物传感

作者：元芯传感技术团队
"""

import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import jsonify, request

from app.atomic_io import atomic_write_text

from app.public_urls import canonicalize_public_url

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
    """为本地 HTML 文件构建公开 Web 目录前缀。"""
    site_root = APP_ROOT.resolve()
    try:
        relative_dir = filepath.resolve().parent.relative_to(site_root).as_posix()
    except ValueError:
        return '/'
    return f'/{relative_dir}' if relative_dir else '/'


def resolve_local_nav_target_path(url):
    """在可能时将导航目标 URL 解析为本地 HTML 文件。"""
    raw_url = canonicalize_public_url(str(url or '').strip(), resolve_page_relative=True)
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

    if normalized.endswith('/'):
        normalized += 'index.html'
    elif not normalized.lower().endswith('.html'):
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
    """尽力从 HTML 页面中提取预览图。"""
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
    """规范化导航卡片使用的简短预览文本。"""
    raw = re.sub(r'\s+', ' ', html.unescape(str(text or ''))).strip()
    if not raw:
        return ''
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip(' ，。；、,.?') + '…'


def extract_generic_page_preview_desc(filepath):
    """尽力从本地 HTML 页面中提取简短摘要。"""
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
    """推断导航目标的标题、预览图和摘要。"""
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
    """根据目标页面为导航链接推断预览图。"""
    return str(infer_nav_target_preview(url).get('image') or '')


def serialize_nav_industry_category_items(items):
    """为行业导航项附加可用的预览图。"""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
        if not name or not url:
            continue
        entry = {'name': name, 'url': url}
        custom_image = str(item.get('image') or '').strip()
        if custom_image:
            entry['image'] = custom_image
        else:
            inferred_image = infer_nav_target_image(url)
            if inferred_image:
                entry['image'] = inferred_image
        serialized.append(entry)
    return serialized


def is_safe_recommendation_url(url: str) -> bool:
    """允许相对路径和 http(s) 链接，阻止 script/data 等协议。"""
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
    """规范化推荐位列表，仅保留有效条目。"""
    normalized = []
    if not isinstance(items, list):
        return normalized

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
        if not name or not is_safe_recommendation_url(url):
            continue
        normalized.append({'name': name, 'url': url})
    return normalized


def get_default_measurement_targets():
    """获取 Mega Menu 默认测量对象数据。"""
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


def get_measurement_pages():
    """获取测量页面目录下的页面列表。"""
    pages_dir = APP_ROOT / 'pages' / 'measurement'
    if not pages_dir.exists():
        return []

    pages = []
    for filepath in sorted(pages_dir.glob('*.html')):
        filename = filepath.stem
        url = f'../measurement/{filename}.html'

        page_title = filename.replace('measurement-', '').replace('-', ' ').title()

        try:
            content = filepath.read_text(encoding='utf-8')
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
            if title_match:
                page_title = html.unescape(title_match.group(1).strip())
                page_title = re.sub(r'\s*[-|].*$', '', page_title).strip()
        except Exception:
            pass

        pages.append({
            'name': page_title,
            'url': url,
            'file': filename
        })

    return pages


def get_solutions_pages():
    """获取解决方案页面目录下的页面列表。"""
    pages_dir = APP_ROOT / 'pages' / 'solutions'
    if not pages_dir.exists():
        return []

    pages = []
    for filepath in sorted(pages_dir.glob('*.html')):
        filename = filepath.stem
        url = f'/pages/solutions/{filename}.html'

        page_title = filename.replace('solutions-', '').replace('industry-', '').replace('-', ' ').title()

        try:
            content = filepath.read_text(encoding='utf-8')
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
            if title_match:
                page_title = html.unescape(title_match.group(1).strip())
                page_title = re.sub(r'\s*[-|].*$', '', page_title).strip()
        except Exception:
            pass

        pages.append({
            'name': page_title,
            'url': url,
            'file': filename
        })

    return pages


def normalize_measurement_target_items(items):
    """规范化测量对象条目，仅保留有效项。"""
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
        if not name or not is_safe_recommendation_url(url):
            continue
        entry = {'name': name, 'url': url}
        image = str(item.get('image') or '').strip()
        if image:
            entry['image'] = image
        normalized.append(entry)
    return normalized


def serialize_measurement_target_items(items):
    """为测量对象条目附加可用的预览图，并将相对路径规范化为绝对路径。"""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
        if not name or not url:
            continue
        entry = {'name': name, 'url': url}
        custom_image = str(item.get('image') or '').strip()
        if custom_image:
            entry['image'] = custom_image
        else:
            inferred_image = infer_nav_target_image(url)
            if inferred_image:
                entry['image'] = inferred_image
        serialized.append(entry)
    return serialized


def get_default_solution_nav_items():
    """获取气体导航默认解决方案链接。"""
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
    """获取气体导航默认研究方向链接。"""
    return {
        'items': [
            {'name': '传感器微纳加工', 'url': '/pages/research/micro-nano.html'},
            {'name': '一站式原型开发', 'url': '/pages/research/development.html'},
            {'name': '产学研深度合作', 'url': '/pages/research/cooperation.html'},
        ]
    }


def serialize_solution_nav_items(items):
    """为解决方案导航项附加预览图和摘要。"""
    serialized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
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
    """构建解决方案导航预览数据。"""
    return {'items': serialize_solution_nav_items(get_default_solution_nav_items().get('items', []))}


def get_research_nav_items():
    """构建研究方向导航预览数据。"""
    return {'items': serialize_solution_nav_items(get_default_research_nav_items().get('items', []))}


def get_default_featured_case_nav_items():
    """获取气体导航 Mega Menu 默认精选案例链接。"""
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
    """构建精选案例导航预览数据。"""
    return {'items': serialize_solution_nav_items(get_default_featured_case_nav_items().get('items', []))}


def get_default_nav_industry_categories():
    """获取气体导航 Mega Menu 默认行业分类链接。"""
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
    """规范化行业分类条目，仅保留有效项。"""
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        url = canonicalize_public_url(item.get('url'), resolve_page_relative=True)
        if not name or not is_safe_recommendation_url(url):
            continue
        entry = {'name': name, 'url': url}
        image = str(item.get('image') or '').strip()
        if image:
            entry['image'] = image
        normalized.append(entry)
    return normalized


def get_nav_industry_categories():
    """加载气体导航行业分类设置。"""
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
    """保存气体导航行业分类设置。"""
    atomic_write_text(
        NAV_INDUSTRY_CATEGORIES_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def get_measurement_targets():
    """加载测量对象设置。"""
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
    """保存测量对象设置。"""
    atomic_write_text(
        MEASUREMENT_TARGETS_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def get_default_recommendations():
    """获取默认推荐位数据。"""
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
    """加载推荐位设置。"""
    data = None
    if RECOMMENDATIONS_FILE.exists():
        try:
            data = json.loads(RECOMMENDATIONS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    if not isinstance(data, dict):
        data = get_default_recommendations()
    return {
        'latestReleases': normalize_recommendation_items(data.get('latestReleases', [])),
        'applicationAreas': normalize_recommendation_items(data.get('applicationAreas', [])),
    }


def save_recommendations(data):
    """保存推荐位设置。"""
    atomic_write_text(RECOMMENDATIONS_FILE, json.dumps(data, ensure_ascii=False, indent=2))



# 路由注册入口。
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
    """注册导航预览、推荐位与导航结构相关路由。"""
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
        """获取 Mega Menu 推荐位数据。"""
        return jsonify(get_recommendations())

    @app.route('/api/recommendations', methods=['POST'])
    @login_required
    def update_recommendations_api():
        """更新 Mega Menu 推荐位数据。"""
        data = request.get_json(silent=True) or {}
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
        """获取 Mega Menu 测量对象数据。"""
        return jsonify(get_measurement_targets())

    @app.route('/api/nav-solution-previews', methods=['GET'])
    def get_solution_nav_items_api():
        """获取气体导航解决方案预览项。"""
        return jsonify(get_solution_nav_items())

    @app.route('/api/nav-research-previews', methods=['GET'])
    def get_research_nav_items_api():
        """获取气体导航研究方向预览项。"""
        return jsonify(get_research_nav_items())

    @app.route('/api/nav-featured-cases', methods=['GET'])
    def get_featured_case_nav_items_api():
        """获取气体导航精选案例预览项。"""
        return jsonify(get_featured_case_nav_items())

    @app.route('/api/measurement-pages', methods=['GET'])
    def get_measurement_pages_api():
        """获取下拉选择用的测量页面列表。"""
        return jsonify({'pages': get_measurement_pages()})

    @app.route('/api/measurement-targets', methods=['POST'])
    @login_required
    def save_measurement_targets_api():
        """更新 Mega Menu 测量对象数据。"""
        data = request.get_json(silent=True) or {}
        items = normalize_measurement_target_items(data.get('items', []))
        if not items:
            return jsonify({'success': False, 'message': '请至少提供 1 条有效测量对象（名称 + 相对路径或 http(s) 链接）'}), 400

        payload = {'items': items}
        save_measurement_targets(payload)
        return jsonify({'success': True, 'items': serialize_measurement_target_items(items)})

    @app.route('/api/solutions-pages', methods=['GET'])
    def get_solutions_pages_api():
        """获取下拉选择用的解决方案页面列表。"""
        return jsonify({'pages': get_solutions_pages()})

    @app.route('/api/nav-industry-categories', methods=['GET'])
    def fetch_nav_industry_categories_api():
        """获取气体导航行业分类数据。"""
        return jsonify(get_nav_industry_categories())

    @app.route('/api/nav-industry-categories', methods=['POST'])
    @login_required
    def save_nav_industry_categories_api():
        """更新气体导航行业分类数据。"""
        data = request.get_json(silent=True) or {}
        items = normalize_nav_industry_category_items(data.get('items', []))
        if not items:
            return jsonify({'success': False, 'message': '请至少提供 1 条有效行业分类（名称 + 相对路径或 http(s) 链接）'}), 400

        payload = {'items': items}
        save_nav_industry_categories(payload)
        return jsonify({'success': True, 'items': serialize_nav_industry_category_items(items)})
