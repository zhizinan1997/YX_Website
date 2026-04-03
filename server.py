"""
Flask server for YX Website with feedback form backend and admin panel.
Supports both local development and Docker deployment.
Includes AI Chatbot with knowledge base support.
"""
import os
import json
import time
import hashlib
import hmac
import threading
import secrets
import base64
import socket
import re
import uuid
import mimetypes
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from urllib.parse import quote, urlparse, unquote

from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string, Response, send_file
from werkzeug.utils import secure_filename
from app.admin_audit import (
    ADMIN_LOGIN_LOG_LOCK,
    append_admin_login_log,
    configure_admin_audit,
    load_admin_login_logs,
    resolve_ip_location,
)
from app.routes.admin import (
    ADMIN_PERMISSION_KEYS,
    ADMIN_SESSION_SCHEMA_VERSION,
    get_turnstile_settings,
    register_admin_routes,
    resolve_permission_for_path,
    verify_turnstile_token,
)
from app.routes.ai_chatbot import (
    call_openai_api,
    get_chatbot_config,
    get_product_page_ai_config,
    get_product_page_ai_system_prompt,
    register_ai_chatbot_routes,
)
from app.routes.backup import register_backup_routes
from app.routes.home_content import get_hero_config, register_home_content_routes
from app.routes.jobs_content import clean_job_text, register_jobs_content_routes
from app.routes.navigation_content import register_navigation_content_routes
from app.routes.news_content import (
    get_all_news_items,
    normalize_news_plain_text,
    register_news_content_routes,
    render_markdown,
    sanitize_news_html_fragment,
    sanitize_news_image_url,
    sanitize_news_link_url,
)
from app.routes.product_settings import (
    _normalize_related_news_links,
    get_bio_product_settings,
    get_product_settings,
    infer_default_bio_industry_categories,
    infer_default_industry_categories,
    register_product_settings_routes,
    save_bio_product_settings,
    save_product_settings,
)
from app.routes.product_editor import (
    extract_product_meta_from_html,
    extract_vs_product_sections,
    patch_vs_product_sections,
    register_product_editor_routes,
    parse_gassensing_product_detail,
    render_gassensing_product_html,
)
from app.routes.cdn_assets import register_cdn_assets_routes
from app.routes.media_delivery import normalize_remote_video_url, register_media_delivery_routes
from app.routes.public_site import register_public_site_routes
from app.routes.site_analytics import register_site_analytics_routes
from app.routes.showcase_content import (
    build_product_link,
    get_h2_home_config,
    register_showcase_content_routes,
)

# Optional imports for PDF parsing and OpenAI
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: PyPDF2 not installed. PDF knowledge base support disabled.")

try:
    import httpx
    HTTPX_SUPPORT = True
except ImportError:
    HTTPX_SUPPORT = False
    print("Warning: httpx not installed. Using requests instead.")

try:
    import requests
    REQUESTS_SUPPORT = True
except ImportError:
    REQUESTS_SUPPORT = False

try:
    import markdown as md
    MARKDOWN_SUPPORT = True
except ImportError:
    MARKDOWN_SUPPORT = False

try:
    from PIL import Image, ImageOps, features as PIL_FEATURES
    PIL_SUPPORT = True
except ImportError:
    PIL_SUPPORT = False
    Image = None
    ImageOps = None
    PIL_FEATURES = None

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


APP_ROOT = Path(__file__).parent.resolve()
APP_ENV = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or '').strip().lower()
DEV_ENV_NAMES = {'dev', 'development', 'local', 'test', 'testing'}
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
WEAK_ADMIN_PASSWORDS = {'admin123', 'admin', '123456', 'password'}
PLACEHOLDER_SECRET_KEYS = {'your-secret-key-change-in-production'}
PUBLIC_STATIC_EXACT_FILES = {'index.html', 'robots.txt'}
PUBLIC_STATIC_ROOT_DIRS = {'pages', 'assets', 'cdn_assets'}
PRIVATE_STATIC_PREFIXES = (
    'data',
    'update_logs',
    'app',
    'tools',
    '.git',
)


def is_development_mode() -> bool:
    return APP_ENV in DEV_ENV_NAMES or __name__ == '__main__'


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    return default


def normalize_public_base_url(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        return ''
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        value = f'https://{value}'
    try:
        parsed = urlparse(value)
    except Exception:
        return ''
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return ''
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'.rstrip('/')


def get_public_base_url() -> str:
    return normalize_public_base_url(os.environ.get('PUBLIC_BASE_URL', ''))


def load_or_create_secret_key() -> str:
    """Load secret key from env or persistent local file."""
    env_secret = (os.environ.get('SECRET_KEY') or '').strip()
    if env_secret:
        if env_secret in PLACEHOLDER_SECRET_KEYS or len(env_secret) < 32:
            raise RuntimeError('生产环境 SECRET_KEY 无效，请提供至少 32 位且非占位值的 SECRET_KEY。')
        return env_secret

    if not is_development_mode():
        raise RuntimeError('生产环境必须通过环境变量提供 SECRET_KEY。')

    secret_file = APP_ROOT / 'data' / '.flask_secret_key'
    try:
        if secret_file.exists():
            existing = (secret_file.read_text(encoding='utf-8') or '').strip()
            if len(existing) >= 32:
                return existing

        secret_file.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(48)
        secret_file.write_text(generated, encoding='utf-8')
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        return generated
    except Exception:
        # Final fallback: random in-memory secret (will rotate on restart).
        return secrets.token_urlsafe(48)


def create_app():
    """Create Flask app instance."""
    flask_app = Flask(__name__, static_folder=None)
    flask_app.secret_key = load_or_create_secret_key()
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = (os.environ.get('SESSION_COOKIE_SAMESITE') or 'Lax').strip() or 'Lax'
    secure_cookie_flag = (os.environ.get('SESSION_COOKIE_SECURE') or '').strip().lower()
    if secure_cookie_flag in ('1', 'true', 'yes', 'on'):
        flask_app.config['SESSION_COOKIE_SECURE'] = True
    elif secure_cookie_flag in ('0', 'false', 'no', 'off'):
        flask_app.config['SESSION_COOKIE_SECURE'] = False
    else:
        flask_app.config['SESSION_COOKIE_SECURE'] = get_public_base_url().startswith('https://')
    return flask_app


app = create_app()
CHEM_SUBSCRIPT_SCRIPT_SRC = '/assets/js/chem-subscript.js'
SITE_ANALYTICS_SCRIPT_SRC = '/assets/js/site-analytics.js'
SITE_BRAND_NAME = '元芯传感'
SITE_COMPANY_NAME = '湖南元芯传感科技有限责任公司'
SITE_DISPLAY_NAME = '湖南元芯传感科技'
SITE_DEFAULT_DESCRIPTION = (
    '湖南元芯传感科技有限责任公司聚焦氢气传感、生物传感与工业安全监测，'
    '提供气体检测、纯度分析、检漏、环境监测及定制化传感解决方案。'
)
SITE_LOGO_PATH = '/cdn_assets/images/common/site-favicon.png'
SEO_DEFAULT_ROBOTS = 'index,follow,max-image-preview:large'
SEO_SECTION_DESCRIPTIONS = (
    ('/pages/gassensing/cases/', '元芯传感分享氢能与工业场景下的真实应用案例，涵盖泄漏监测、安全预警、纯度分析与现场巡检等实践经验。'),
    ('/pages/gassensing/', '元芯传感提供氢气检测、纯度分析、露点监测、示踪检漏与可燃气体监测等产品，覆盖工业安全与氢能应用场景。'),
    ('/pages/biosensing/', '元芯传感提供碳基生物传感平台、检测芯片、工作站与定制服务，服务医疗检测、生命科学与科研应用。'),
    ('/pages/solutions/', '元芯传感围绕氢能、电力、储能、工业检漏与环境监测等场景，提供可落地的行业解决方案与工程化支持。'),
    ('/pages/measurement/', '元芯传感围绕氢气、可燃气体、湿度、压力、露点与溶解氢等测量对象，提供高可靠监测与预警方案。'),
    ('/pages/customization/', '元芯传感提供半导体器件、微纳工艺与传感器相关的定制化开发服务，支持从方案设计到样品落地。'),
    ('/pages/news/', '查看元芯传感在氢安全、生物传感、产业动态、技术解读与企业资讯方面的最新内容。'),
    ('/pages/about/', '了解元芯传感的发展历程、技术背景、企业文化与核心能力，认识这家聚焦先进传感技术的创新企业。'),
    ('/pages/contact/', '联系元芯传感获取产品咨询、解决方案支持、合作对接与售后服务信息。'),
    ('/pages/research/', '元芯传感提供传感器开发、微纳加工与产学研协同支持，服务科研团队与产业化项目。'),
    ('/pages/services/', '元芯传感提供传感器开发、测试、应用验证与科研服务，帮助客户推进从样机到场景落地。'),
    ('/pages/careers/', '了解元芯传感的人才理念、成长空间、招聘岗位与合作招募信息。'),
    ('/pages/honors/', '查看元芯传感在行业应用、项目成果与典型案例方面的展示内容。'),
)
SEO_BREADCRUMB_LABELS = {
    'pages': '',
    'gassensing': '气体传感',
    'biosensing': '生物传感',
    'solutions': '解决方案',
    'measurement': '测量对象',
    'customization': '定制服务',
    'news': '洞察与资讯',
    'about': '关于我们',
    'contact': '联系我们',
    'research': '科研服务',
    'services': '科研服务',
    'careers': '加入我们',
    'honors': '应用案例',
    'cases': '应用案例',
}
SEO_BREADCRUMB_TARGETS = {
    'gassensing': '/pages/gassensing/',
    'biosensing': '/pages/biosensing/',
    'solutions': '/pages/solutions/solutions-index.html',
    'customization': '/pages/customization/',
    'news': '/pages/news/news.html',
    'about': '/pages/about/about.html',
    'contact': '/pages/contact/contact.html',
    'research': '/pages/research/index.html',
    'services': '/pages/services/service.html',
    'careers': '/pages/careers/jobs.html',
    'honors': '/pages/honors/honor.html',
    'cases': '/pages/gassensing/service-cases.html',
}

# Configuration
DATA_DIR = APP_ROOT / 'data'
MESSAGES_DIR = DATA_DIR / 'messages'
MESSAGES_META_FILE = DATA_DIR / 'messages_meta.json'
KNOWLEDGE_DIR = DATA_DIR / 'knowledge'
CHATBOT_CONVERSATION_LOG_FILE = DATA_DIR / 'chatbot_conversation_logs.jsonl'
RATE_LIMIT_FILE = DATA_DIR / 'rate_limits.json'
CONFIG_FILE = DATA_DIR / 'config.json'
CDN_ASSETS_DIR = APP_ROOT / 'cdn_assets'
SITE_FAVICON_RELATIVE_PATH = Path('images/common/site-favicon.png')
HERO_DIR = DATA_DIR / 'hero'
HERO_UPLOADS_DIR = HERO_DIR / 'uploads'
HERO_CONFIG_FILE = HERO_DIR / 'hero.json'
HERO_DERIVED_DIR = HERO_DIR / 'derived'
HERO_DERIVED_MANIFEST_FILE = HERO_DERIVED_DIR / 'manifest.json'
PARTNERS_DIR = DATA_DIR / 'partners'
PARTNERS_UPLOADS_DIR = PARTNERS_DIR / 'uploads'
PARTNERS_CONFIG_FILE = PARTNERS_DIR / 'partners.json'
PRODUCT_CARD_DIR = DATA_DIR / 'product_cards'
PRODUCT_CARD_UPLOADS_DIR = PRODUCT_CARD_DIR / 'uploads'
NEWS_FEATURED_FILE = DATA_DIR / 'news_featured.json'
NEWS_VISIBILITY_FILE = DATA_DIR / 'news_visibility.json'
PRODUCT_FEATURED_FILE = DATA_DIR / 'product_featured.json'
SOLUTIONS_FEATURED_FILE = DATA_DIR / 'solutions_featured.json'
HOME_SECTION_VISIBILITY_FILE = DATA_DIR / 'home_section_visibility.json'
JOBS_FILE = DATA_DIR / 'jobs.json'
H2_HOME_FILE = DATA_DIR / 'h2_home.json'
H2_HOME_VIDEO_UPLOADS_DIR = DATA_DIR / 'h2_home_videos'
HYDROGEN_SOLUTIONS_CONFIG_FILE = DATA_DIR / 'hydrogen_solutions_config.json'
NEWS_UPLOADS_DIR = DATA_DIR / 'news_uploads'
RESUME_UPLOADS_DIR = DATA_DIR / 'resumes'
if ZoneInfo is not None:
    try:
        BEIJING_TZ = ZoneInfo('Asia/Shanghai')
    except Exception:
        BEIJING_TZ = timezone(timedelta(hours=8))
else:
    BEIJING_TZ = timezone(timedelta(hours=8))

# Ensure directories exist
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
HERO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
HERO_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
PARTNERS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PRODUCT_CARD_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
H2_HOME_VIDEO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
NEWS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESUME_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_MAX = 5  # Max submissions per IP per hour
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# Ensure directories exist
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_HERO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.mp4'}
ALLOWED_HERO_MIME_TYPES = {'image/png', 'image/jpeg', 'video/mp4'}
ALLOWED_H2_HOME_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.ogg', '.ogv'}
ALLOWED_H2_HOME_VIDEO_MIME_TYPES = {'video/mp4', 'video/webm', 'video/ogg'}
ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.doc', '.docx'}
BACKUP_META_FILES = {'backup_manifest.json'}
BACKUP_EXCLUDED_DIR_NAMES = {
    '.git',
    '.hg',
    '.svn',
    '.idea',
    '.vscode',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '__pycache__',
    'node_modules',
    '.venv',
    'venv',
    'backups',
    '.DS_Store'
}
BACKUP_EXCLUDED_FILE_NAMES = {
    '.DS_Store'
}
BACKUP_EXCLUDED_SUFFIXES = (
    '.pyc',
    '.pyo',
    '.swp',
    '.tmp',
    '.temp'
)
ALLOWED_PARTNER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_PARTNER_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp'}
ALLOWED_PRODUCT_CARD_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_PRODUCT_CARD_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp'}
ALLOWED_NEWS_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
ALLOWED_NEWS_IMAGE_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
ALLOWED_AI_PRODUCT_IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif',
    '.tif', '.tiff', '.avif', '.heic', '.heif'
}
ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/webp', 'image/bmp', 'image/gif',
    'image/tiff', 'image/avif', 'image/heic', 'image/heif'
}
MEDIA_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'
CONFIG_JSON_CACHE_SECONDS = 120
CONFIG_JSON_STALE_SECONDS = 600
HERO_DERIVED_WIDTHS = (768, 1280, 1920)
HERO_DERIVED_FORMATS = ('avif', 'webp')
HERO_SOURCE_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.avif'}
try:
    ADMIN_SESSION_MAX_AGE_SECONDS = max(300, int((os.environ.get('ADMIN_SESSION_MAX_AGE_SECONDS') or '28800').strip()))
except Exception:
    ADMIN_SESSION_MAX_AGE_SECONDS = 28800


def ensure_required_runtime_config():
    if is_development_mode():
        return

    errors = []
    secret_key = (os.environ.get('SECRET_KEY') or '').strip()
    public_base_url = get_public_base_url()
    admin_hash = (os.environ.get('ADMIN_PASSWORD_HASH') or '').strip()
    admin_password = (os.environ.get('ADMIN_PASSWORD') or '').strip()
    allow_weak_admin_passwords = env_bool('ALLOW_WEAK_ADMIN_PASSWORDS', False)

    if not secret_key:
        errors.append('缺少 SECRET_KEY')
    elif secret_key in PLACEHOLDER_SECRET_KEYS or len(secret_key) < 32:
        errors.append('SECRET_KEY 必须至少 32 位且不能使用占位值')

    if not public_base_url:
        errors.append('缺少合法的 PUBLIC_BASE_URL')

    has_bootstrapped_admin = False
    admin_users_file = DATA_DIR / 'admin_users.json'
    admin_users_file_exists = admin_users_file.exists()
    admin_users_read_error = ''
    if admin_users_file_exists:
        try:
            payload = json.loads(admin_users_file.read_text(encoding='utf-8'))
            users = payload.get('users', []) if isinstance(payload, dict) else []
            has_bootstrapped_admin = any(
                isinstance(item, dict) and str(item.get('role') or '') == 'super_admin' and str(item.get('password_hash') or '').strip()
                for item in users
            )
        except Exception as exc:
            admin_users_read_error = str(exc)
            has_bootstrapped_admin = False

    if (
        admin_password
        and admin_password in WEAK_ADMIN_PASSWORDS
        and not allow_weak_admin_passwords
        and not has_bootstrapped_admin
        and not admin_hash
    ):
        message = 'ADMIN_PASSWORD 不能使用弱口令'
        if admin_users_file_exists:
            if admin_users_read_error:
                message += f'；且无法读取 {admin_users_file}：{admin_users_read_error}'
            else:
                message += f'；且 {admin_users_file} 中未检测到带 password_hash 的 super_admin'
        else:
            message += f'；且未找到 {admin_users_file}'
        errors.append(message)

    if not has_bootstrapped_admin and not admin_hash and not admin_password:
        message = '缺少管理员初始化凭据：请提供 ADMIN_PASSWORD_HASH 或一次性 ADMIN_PASSWORD'
        if admin_users_file_exists:
            if admin_users_read_error:
                message += f'；另外无法读取 {admin_users_file}：{admin_users_read_error}'
            else:
                message += f'；并且 {admin_users_file} 中未检测到有效的 super_admin'
        else:
            message += f'；并且未找到 {admin_users_file}'
        errors.append(message)

    if errors:
        raise RuntimeError('生产环境安全配置不完整：' + '；'.join(errors))


ensure_required_runtime_config()

ANTI_CRAWL_STRICT_PRIVATE_PREFIXES = (
    '/admin',
    '/api/admin',
    '/data/',
    '/update_logs/',
)
ANTI_CRAWL_RESOURCE_PREFIXES = (
    '/assets/',
    '/cdn_assets/',
    '/media/',
)
ANTI_CRAWL_BOT_UA_KEYWORDS = (
    'bot',
    'spider',
    'crawler',
    'scrapy',
    'curl',
    'wget',
    'python-requests',
    'httpx',
    'okhttp',
    'java/',
    'go-http-client',
    'axios',
    'headless',
    'phantomjs',
    'playwright',
    'selenium',
    'slurp',
    'bingpreview',
    'googlebot',
    'baiduspider',
    'yandex',
    'duckduckbot',
    'semrush',
    'ahrefs',
    'mj12bot',
    'facebookexternalhit',
    'twitterbot',
    'bytespider',
    'petalbot',
    'sogou',
    'gptbot',
    'ccbot',
    'claudebot',
)
SEARCH_ENGINE_BOT_UA_KEYWORDS = (
    'googlebot',
    'bingbot',
    'bingpreview',
    'baiduspider',
    'sogou',
    '360spider',
    'yandex',
    'duckduckbot',
    'slurp',
    'bytespider',
    'petalbot',
)
STRICT_ANTI_CRAWL_HEADERS = 'noindex, nofollow, noarchive, nosnippet, noimageindex'
PUBLIC_HTML_CONTENT_SECURITY_POLICY = "base-uri 'self'; frame-ancestors 'self'; object-src 'none'"
PUBLIC_REFERRER_POLICY = 'strict-origin-when-cross-origin'
NEWS_SAFE_HTML_TAGS = {
    'p', 'br', 'div', 'span',
    'strong', 'b', 'em', 'i', 'u', 's', 'sup', 'sub',
    'ul', 'ol', 'li',
    'dl', 'dt', 'dd',
    'blockquote', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'a', 'img', 'video', 'source',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th',
    'code', 'pre',
}
NEWS_DROPPED_HTML_TAGS = {
    'script', 'style', 'iframe', 'object', 'embed',
    'form', 'input', 'button', 'textarea', 'select', 'option',
    'svg', 'math', 'meta', 'link',
}
NEWS_VOID_HTML_TAGS = {'br', 'hr', 'img', 'source'}
REMOTE_FETCH_BLOCKED_HOSTS = {
    'localhost',
    'localhost.localdomain',
    '127.0.0.1',
    '::1',
}

def infer_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'video/mp4':
        return '.mp4'
    return ''

def infer_partner_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    return ''

def infer_h2_home_video_extension_from_mime(mime: str) -> str:
    if mime == 'video/mp4':
        return '.mp4'
    if mime == 'video/webm':
        return '.webm'
    if mime == 'video/ogg':
        return '.ogv'
    return ''

def infer_product_card_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    return ''

def infer_news_image_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    if mime == 'image/gif':
        return '.gif'
    if mime == 'image/svg+xml':
        return '.svg'
    return ''


def infer_ai_product_image_extension_from_mime(mime: str) -> str:
    mime = (mime or '').split(';')[0].strip().lower()
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    if mime == 'image/bmp':
        return '.bmp'
    if mime == 'image/gif':
        return '.gif'
    if mime == 'image/tiff':
        return '.tif'
    if mime == 'image/avif':
        return '.avif'
    if mime == 'image/heic':
        return '.heic'
    if mime == 'image/heif':
        return '.heif'
    return ''


def infer_ai_product_image_extension_from_bytes(sample: bytes) -> str:
    """Best-effort image extension sniffing from file header bytes."""
    sample = sample or b''
    if sample.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if len(sample) >= 3 and sample[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if sample.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if sample.startswith(b'BM'):
        return '.bmp'
    if len(sample) >= 12 and sample[:4] == b'RIFF' and sample[8:12] == b'WEBP':
        return '.webp'
    if sample.startswith((b'II*\x00', b'MM\x00*')):
        return '.tif'
    if len(sample) >= 12 and sample[4:8] == b'ftyp':
        brand = sample[8:12].lower()
        if brand in {b'avif', b'avis'}:
            return '.avif'
        if brand in {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}:
            return '.heic'
    lower = sample[:512].decode('utf-8', errors='ignore').lower()
    if '<svg' in lower:
        return '.svg'
    return ''


def normalize_ai_product_image_extension(filename: str, mime: str, sample: bytes) -> str:
    """Normalize uploaded image extension with filename/mime/signature fallback."""
    ext = Path((filename or '')).suffix.lower()
    if ext == '.jpe':
        ext = '.jpg'
    if ext in ALLOWED_AI_PRODUCT_IMAGE_EXTENSIONS:
        return ext

    inferred = infer_ai_product_image_extension_from_mime(mime)
    if inferred:
        return inferred

    mime_clean = (mime or '').split(';')[0].strip().lower()
    guessed = (mimetypes.guess_extension(mime_clean) or '').lower() if mime_clean else ''
    if guessed == '.jpe':
        guessed = '.jpg'
    if guessed in ALLOWED_AI_PRODUCT_IMAGE_EXTENSIONS:
        return guessed

    inferred_by_bytes = infer_ai_product_image_extension_from_bytes(sample)
    if inferred_by_bytes in ALLOWED_AI_PRODUCT_IMAGE_EXTENSIONS:
        return inferred_by_bytes

    return ''


def _normalized_ext(value: str) -> str:
    ext = str(value or '').strip().lower()
    if ext == '.jpe':
        return '.jpg'
    return ext


def peek_upload_bytes(file_storage, max_bytes: int = 8192) -> bytes:
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return b''
    try:
        current_pos = stream.tell()
    except Exception:
        current_pos = None
    try:
        sample = stream.read(max_bytes)
    except Exception:
        sample = b''
    try:
        if current_pos is not None:
            stream.seek(current_pos)
        else:
            stream.seek(0)
    except Exception:
        pass
    return sample or b''


def infer_video_extension_from_bytes(sample: bytes) -> str:
    sample = sample or b''
    if len(sample) >= 12 and sample[4:8] == b'ftyp':
        return '.mp4'
    if sample.startswith(b'\x1aE\xdf\xa3'):
        return '.webm'
    if sample.startswith(b'OggS'):
        return '.ogv'
    return ''


def validate_uploaded_image_extension(file_storage, *, allowed_extensions: set[str]) -> str:
    filename = getattr(file_storage, 'filename', '') or ''
    mime = (getattr(file_storage, 'mimetype', '') or getattr(file_storage, 'content_type', '') or '').lower()
    sample = peek_upload_bytes(file_storage)
    detected_ext = _normalized_ext(infer_ai_product_image_extension_from_bytes(sample))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename).suffix.lower())
    if named_ext == '.svg':
        detected_ext = infer_ai_product_image_extension_from_bytes(sample)
        if _normalized_ext(detected_ext) == '.svg' and named_ext in allowed_extensions:
            return named_ext
    if named_ext in allowed_extensions and named_ext in {'.svg'} and _normalized_ext(detected_ext) == named_ext:
        return named_ext
    return ''


def validate_image_bytes(filename: str, mime: str, content: bytes, *, allowed_extensions: set[str]) -> str:
    detected_ext = _normalized_ext(infer_ai_product_image_extension_from_bytes(content[:8192]))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename or '').suffix.lower())
    mime_ext = _normalized_ext(infer_news_image_extension_from_mime((mime or '').lower()))
    if named_ext in allowed_extensions and named_ext == detected_ext:
        return named_ext
    if mime_ext in allowed_extensions and mime_ext == detected_ext:
        return mime_ext
    return ''


def validate_uploaded_video_extension(file_storage, *, allowed_extensions: set[str]) -> str:
    filename = getattr(file_storage, 'filename', '') or ''
    sample = peek_upload_bytes(file_storage)
    detected_ext = _normalized_ext(infer_video_extension_from_bytes(sample))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename).suffix.lower())
    return named_ext if named_ext in allowed_extensions and named_ext == detected_ext else ''


def validate_uploaded_pdf(file_storage) -> bool:
    sample = peek_upload_bytes(file_storage)
    return bool(sample.startswith(b'%PDF-'))


def validate_uploaded_resume(file_storage) -> bool:
    ext = _normalized_ext(Path((getattr(file_storage, 'filename', '') or '')).suffix.lower())
    sample = peek_upload_bytes(file_storage)
    if ext == '.pdf':
        return sample.startswith(b'%PDF-')
    if ext == '.doc':
        return sample.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if ext == '.docx':
        return sample.startswith(b'PK\x03\x04')
    return False


def extract_resume_storage_name(message: dict) -> str:
    if not isinstance(message, dict):
        return ''
    stored_name = str(message.get('resume_stored_filename') or '').strip()
    if stored_name:
        safe_name = Path(unquote(stored_name)).name
        return safe_name if safe_name == unquote(stored_name) else ''
    resume_url = str(message.get('resume_url') or '').strip()
    if resume_url.startswith('/media/resumes/'):
        tail = unquote(resume_url.split('/media/resumes/', 1)[1]).strip()
        safe_name = Path(tail).name
        return safe_name if safe_name == tail else ''
    return ''


def build_resume_download_url(message: dict) -> str:
    message_id = str((message or {}).get('id') or '').strip()
    if not message_id:
        return ''
    if not extract_resume_storage_name(message):
        return ''
    return f'/api/messages/{quote(message_id)}/resume'


def get_messages_meta():
    """Load persisted message meta data."""
    default_meta = {
        'deleted_count': 0
    }

    if MESSAGES_META_FILE.exists():
        try:
            meta = json.loads(MESSAGES_META_FILE.read_text(encoding='utf-8'))
            merged = {**default_meta, **(meta if isinstance(meta, dict) else {})}
            merged['deleted_count'] = max(0, int(merged.get('deleted_count', 0)))
            return merged
        except Exception:
            pass

    MESSAGES_META_FILE.write_text(json.dumps(default_meta, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_meta


def save_messages_meta(meta):
    """Persist message meta data."""
    safe_meta = {
        'deleted_count': max(0, int((meta or {}).get('deleted_count', 0)))
    }
    MESSAGES_META_FILE.write_text(json.dumps(safe_meta, indent=2, ensure_ascii=False), encoding='utf-8')
    return safe_meta


def build_json_etag(payload) -> str:
    """Build a stable ETag for JSON payloads."""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha1(serialized.encode('utf-8')).hexdigest()


def cached_json_response(payload, max_age: int = CONFIG_JSON_CACHE_SECONDS, stale_seconds: int = CONFIG_JSON_STALE_SECONDS):
    """Return JSON response with conditional ETag caching headers."""
    response = jsonify(payload)
    response.set_etag(build_json_etag(payload))
    response.headers['Cache-Control'] = f'public, max-age={max_age}, stale-while-revalidate={stale_seconds}'
    response.make_conditional(request)
    return response

def get_config():
    """Load config from file or defaults."""
    default_config = {
        'admin_username': os.environ.get('ADMIN_USERNAME', 'admin'),
        'admin_password_hash': (os.environ.get('ADMIN_PASSWORD_HASH') or '').strip(),
        'admin_password': (os.environ.get('ADMIN_PASSWORD') or ('admin123' if is_development_mode() else '')).strip(),
        'cdn_enabled': env_bool('CDN_ENABLED', False),
        'cdn_domain': (os.environ.get('CDN_DOMAIN') or os.environ.get('CDN_ASSET_BASE_URL') or '').strip(),
        'turnstile_enabled': env_bool('TURNSTILE_ENABLED', False),
        'turnstile_site_key': (os.environ.get('TURNSTILE_SITE_KEY') or '').strip(),
        'turnstile_secret_key': (os.environ.get('TURNSTILE_SECRET_KEY') or '').strip(),
    }
    
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            for key in ('admin_username', 'admin_password_hash', 'admin_password'):
                env_value = str(default_config.get(key, '') or '').strip()
                file_value = str(config.get(key, '') or '').strip() if isinstance(config, dict) else ''
                if env_value and not file_value:
                    merged[key] = env_value
            return merged
        except Exception:
            pass
            
    # Save default config if file doesn't exist
    CONFIG_FILE.write_text(json.dumps(default_config, indent=2), encoding='utf-8')
    return default_config

def update_config(new_config):
    """Update and save config."""
    config = get_config()
    config.update(new_config)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return config


def _normalize_origin(raw_value: str) -> str:
    value = str(raw_value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlparse(value)
    except Exception:
        return ''
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _first_forwarded_value(raw_value: str) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return ''
    return text.split(',')[0].strip()


def _normalize_ip_text(raw_value: str) -> str:
    """Normalize and validate an IP string (supports bracket/port forms)."""
    text = str(raw_value or '').strip()
    if not text or text.lower() == 'unknown':
        return ''

    candidate = text
    if text.startswith('[') and ']' in text:
        candidate = text[1:text.index(']')].strip()
    elif text.count(':') == 1 and '.' in text:
        # IPv4 with port, like 1.2.3.4:5678
        host, _, _port = text.rpartition(':')
        candidate = host.strip()

    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return ''


def _is_private_proxy_source(ip_text: str) -> bool:
    normalized = _normalize_ip_text(ip_text)
    if not normalized:
        return False
    try:
        ip_obj = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local)


def _should_trust_proxy_headers(req) -> bool:
    """Decide whether proxy headers should be trusted for this request."""
    return env_bool('TRUST_PROXY_HEADERS', False)


def _parse_forwarded_ip_chain(raw_value: str) -> list[str]:
    chain = []
    for part in str(raw_value or '').split(','):
        ip_text = _normalize_ip_text(part)
        if ip_text and ip_text not in chain:
            chain.append(ip_text)
    return chain


def _extract_client_ip_from_proxy_headers(req, direct_ip: str = '', x_real_ip: str = '') -> str:
    chain = _parse_forwarded_ip_chain(req.headers.get('X-Forwarded-For', ''))
    if chain:
        # Read right-to-left and skip proxy/internal hops first so a spoofed
        # client-supplied left-most XFF value cannot win over the real client IP.
        for ip_text in reversed(chain):
            if not _is_private_proxy_source(ip_text):
                return ip_text

        proxy_hints = {ip for ip in {direct_ip, x_real_ip} if ip}
        for ip_text in reversed(chain):
            if ip_text not in proxy_hints:
                return ip_text
        return chain[0]
    return ''


def _ip_is_publicly_routable(ip_text: str) -> bool:
    normalized = _normalize_ip_text(ip_text)
    if not normalized:
        return False
    try:
        ip_obj = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_safe_remote_fetch_url(raw_url: str) -> tuple[bool, str, str]:
    normalized = normalize_remote_video_url(raw_url)
    if not normalized:
        return False, '仅支持合法的 http/https 地址', ''

    try:
        parsed = urlparse(normalized)
    except Exception:
        return False, '链接格式不合法', ''

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, '链接缺少主机名', ''
    if parsed.username or parsed.password:
        return False, '链接中不允许包含账号信息', ''
    if hostname in REMOTE_FETCH_BLOCKED_HOSTS:
        return False, '禁止访问本机或保留地址', ''

    literal_ip = _normalize_ip_text(hostname)
    if literal_ip:
        if not _ip_is_publicly_routable(literal_ip):
            return False, '禁止访问内网或保留地址', ''
        return True, '', normalized

    try:
        records = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, '域名解析失败', ''
    except Exception:
        return False, '域名解析异常', ''

    resolved_ips = []
    for item in records:
        sockaddr = item[4] if len(item) >= 5 else ()
        if not sockaddr:
            continue
        ip_text = _normalize_ip_text(sockaddr[0])
        if ip_text and ip_text not in resolved_ips:
            resolved_ips.append(ip_text)

    if not resolved_ips:
        return False, '域名解析结果为空', ''
    if any(not _ip_is_publicly_routable(ip_text) for ip_text in resolved_ips):
        return False, '禁止访问内网或保留地址', ''
    return True, '', normalized


def _collect_allowed_origins(req) -> list[str]:
    allowed_origins = []

    def add_allowed(raw_origin: str):
        normalized = _normalize_origin(raw_origin)
        if normalized and normalized not in allowed_origins:
            allowed_origins.append(normalized)

    add_allowed(get_public_base_url())

    host_url = str(getattr(req, 'host_url', '') or '').strip()
    add_allowed(host_url)

    parsed_host = urlparse(host_url) if host_url else None
    host_netloc = (parsed_host.netloc or '').strip().lower() if parsed_host else ''
    host_scheme = (parsed_host.scheme or '').strip().lower() if parsed_host else ''
    if host_netloc:
        if host_scheme == 'http':
            add_allowed(f'https://{host_netloc}')
        elif host_scheme == 'https':
            add_allowed(f'http://{host_netloc}')

    if _should_trust_proxy_headers(req):
        xf_host = _first_forwarded_value(req.headers.get('X-Forwarded-Host', ''))
        xf_proto = _first_forwarded_value(req.headers.get('X-Forwarded-Proto', '')).lower()
        if xf_host:
            proto = xf_proto if xf_proto in {'http', 'https'} else (host_scheme or 'https')
            add_allowed(f'{proto}://{xf_host}')
            add_allowed(f'{"https" if proto == "http" else "http"}://{xf_host}')

    return allowed_origins


def is_same_origin_request(req) -> bool:
    """Basic CSRF guard for admin write actions."""
    allowed_origins = _collect_allowed_origins(req)
    if not allowed_origins:
        return False

    origin = _normalize_origin(req.headers.get('Origin', ''))
    if origin:
        return any(hmac.compare_digest(origin, item) for item in allowed_origins)

    referer = _normalize_origin(req.headers.get('Referer', ''))
    if referer:
        return any(hmac.compare_digest(referer, item) for item in allowed_origins)

    return False
def get_client_ip():
    """Get client IP address, considering proxy headers."""
    if _should_trust_proxy_headers(request):
        direct_ip = _normalize_ip_text(request.remote_addr or '')
        cf_ip = _normalize_ip_text(request.headers.get('CF-Connecting-IP', ''))
        if cf_ip and _ip_is_publicly_routable(cf_ip):
            return cf_ip

        x_real_ip = _normalize_ip_text(request.headers.get('X-Real-IP', ''))
        proxied_ip = _extract_client_ip_from_proxy_headers(request, direct_ip=direct_ip, x_real_ip=x_real_ip)
        if proxied_ip:
            return proxied_ip

        if x_real_ip and x_real_ip != direct_ip:
            return x_real_ip

    direct_ip = _normalize_ip_text(request.remote_addr or '')
    return direct_ip or (request.remote_addr or '127.0.0.1')


configure_admin_audit(
    data_dir=DATA_DIR,
    beijing_tz=BEIJING_TZ,
    requests_support=REQUESTS_SUPPORT,
    requests_module=requests if REQUESTS_SUPPORT else None,
    httpx_support=HTTPX_SUPPORT,
    httpx_module=httpx if HTTPX_SUPPORT else None,
    get_client_ip=get_client_ip,
)


_rate_limit_lock = threading.Lock()
_rate_limit_storage: dict[str, list[float]] = {}
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # seconds between full storage cleanups
_rate_limit_last_cleanup = 0.0


def check_rate_limit(ip: str) -> bool:
    """Check if IP is within rate limit. Returns True if allowed."""
    global _rate_limit_last_cleanup
    now = time.time()
    ip_key = str(ip or '').strip() or 'unknown'
    with _rate_limit_lock:
        # Periodic cleanup of expired entries to avoid memory growth
        if now - _rate_limit_last_cleanup > _RATE_LIMIT_CLEANUP_INTERVAL:
            keys_to_remove = [
                k for k, timestamps in _rate_limit_storage.items()
                if not any(now - t < RATE_LIMIT_WINDOW for t in timestamps)
            ]
            for k in keys_to_remove:
                del _rate_limit_storage[k]
            _rate_limit_last_cleanup = now

        entries = [t for t in _rate_limit_storage.get(ip_key, []) if now - t < RATE_LIMIT_WINDOW]
        if len(entries) >= RATE_LIMIT_MAX:
            _rate_limit_storage[ip_key] = entries
            return False
        entries.append(now)
        _rate_limit_storage[ip_key] = entries
    return True


def login_required(f):
    """Decorator to require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_api = (request.path or '').startswith('/api/')
        if not session.get('admin_logged_in'):
            if is_api:
                return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
            return redirect('/admin')
        now_ts = int(time.time())
        try:
            login_at = int(session.get('admin_login_at') or 0)
        except Exception:
            login_at = 0
        try:
            ttl = int(session.get('admin_session_ttl') or ADMIN_SESSION_MAX_AGE_SECONDS)
        except Exception:
            ttl = ADMIN_SESSION_MAX_AGE_SECONDS
        if ttl <= 0:
            ttl = ADMIN_SESSION_MAX_AGE_SECONDS
        if login_at <= 0 or now_ts - login_at > ttl:
            session.clear()
            if is_api:
                return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
            return redirect('/admin')

        # Invalidate sessions created with an older schema version.
        if session.get('admin_session_schema') != ADMIN_SESSION_SCHEMA_VERSION:
            session.clear()
            if is_api:
                return jsonify({'success': False, 'message': '会话版本已更新，请重新登录'}), 401
            return redirect('/admin')

        if (request.method or 'GET').upper() in WRITE_METHODS and not is_same_origin_request(request):
            if is_api:
                return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403
            return redirect('/admin')

        is_super_admin = bool(session.get('admin_is_super_admin', False))
        if is_super_admin:
            return f(*args, **kwargs)

        raw_permissions = session.get('admin_permissions', [])
        permissions = []
        if isinstance(raw_permissions, (list, tuple, set)):
            for item in raw_permissions:
                key = str(item or '').strip()
                if key in ADMIN_PERMISSION_KEYS and key not in permissions:
                    permissions.append(key)
        session['admin_permissions'] = permissions

        required_permission = resolve_permission_for_path(request.path or '', request.method or 'GET')
        denied = (
            required_permission == '__unknown__'
            or (required_permission and required_permission not in permissions)
        )
        if denied:
            if is_api:
                return jsonify({'success': False, 'message': '当前账号无权限访问该功能'}), 403
            return redirect('/admin')
        return f(*args, **kwargs)
    return decorated_function


def _current_admin_is_super_admin() -> bool:
    return bool(session.get('admin_logged_in')) and bool(session.get('admin_is_super_admin', False))


def require_super_admin_api():
    if _current_admin_is_super_admin():
        return None
    return jsonify({'success': False, 'message': '仅超级管理员可执行该操作'}), 403


def _path_matches_prefix(path_value: str, prefix: str) -> bool:
    path_text = str(path_value or '').strip() or '/'
    normalized = str(prefix or '').strip()
    if not normalized:
        return False
    base = normalized.rstrip('/')
    return path_text == base or path_text.startswith(normalized)


def _is_anti_crawl_strict_private_path(path_value: str) -> bool:
    path_text = str(path_value or '').strip() or '/'
    return any(_path_matches_prefix(path_text, item) for item in ANTI_CRAWL_STRICT_PRIVATE_PREFIXES)


def _is_anti_crawl_resource_path(path_value: str) -> bool:
    path_text = str(path_value or '').strip() or '/'
    return any(_path_matches_prefix(path_text, item) for item in ANTI_CRAWL_RESOURCE_PREFIXES)


def _looks_like_crawler_ua(raw_ua: str) -> bool:
    ua = str(raw_ua or '').strip().lower()
    if not ua:
        # Empty UA is treated as crawler in strict mode.
        return True
    return any(keyword in ua for keyword in ANTI_CRAWL_BOT_UA_KEYWORDS)


def _is_allowed_search_engine_ua(raw_ua: str) -> bool:
    ua = str(raw_ua or '').strip().lower()
    if not ua:
        return False
    return any(keyword in ua for keyword in SEARCH_ENGINE_BOT_UA_KEYWORDS)


@app.before_request
def strict_anti_crawl_guard():
    """Anti-crawl guard.
    - Strictly block crawler UAs on admin/private paths.
    - Keep search engines crawlable for public resources used in rendering.
    """
    path = request.path or '/'
    cdn_entry_request = str(request.headers.get('X-YX-CDN-Entry') or '').strip() == '1'
    if cdn_entry_request and _path_matches_prefix(path, '/cdn_assets/'):
        return None

    ua = request.headers.get('User-Agent', '')
    if not _looks_like_crawler_ua(ua):
        return None

    if _is_anti_crawl_strict_private_path(path):
        if path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403
        return Response('Forbidden', status=403, mimetype='text/plain')

    if _is_anti_crawl_resource_path(path) and not _is_allowed_search_engine_ua(ua):
        if path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403
        return Response('Forbidden', status=403, mimetype='text/plain')

    return None

def sanitize_public_text(value: str, *, max_length: int = 0) -> str:
    return normalize_news_plain_text(value, max_length=max_length)


def sanitize_public_date_text(value: str, *, max_length: int = 32) -> str:
    return normalize_news_plain_text(value, max_length=max_length)


def sanitize_public_link_url(raw_url: str, *, enforce_remote_public: bool = False, default: str = '') -> str:
    safe_url = sanitize_news_link_url(raw_url)
    if not safe_url:
        return default
    if enforce_remote_public and re.match(r'^https?://', safe_url, re.I):
        ok, _, normalized = validate_safe_remote_fetch_url(safe_url)
        if not ok:
            return default
        return normalized
    return safe_url


def sanitize_public_media_url(raw_url: str, *, enforce_remote_public: bool = False, default: str = '') -> str:
    safe_url = sanitize_news_image_url(raw_url)
    if not safe_url:
        return default
    if enforce_remote_public and re.match(r'^https?://', safe_url, re.I):
        ok, _, normalized = validate_safe_remote_fetch_url(safe_url)
        if not ok:
            return default
        return normalized
    return safe_url


def sanitize_public_product_settings(settings):
    raw = settings if isinstance(settings, dict) else {}
    cleaned = {}
    for product_id, cfg in raw.items():
        pid = str(product_id or '').strip()
        if not pid or not isinstance(cfg, dict):
            continue
        item = {}
        if 'displayName' in cfg:
            item['displayName'] = sanitize_public_text(cfg.get('displayName', ''), max_length=120)
        if 'isNew' in cfg:
            item['isNew'] = bool(cfg.get('isNew', False))
        if 'hidden' in cfg:
            item['hidden'] = bool(cfg.get('hidden', False))
        if 'sortOrder' in cfg:
            try:
                item['sortOrder'] = int(cfg.get('sortOrder', 999))
            except Exception:
                item['sortOrder'] = 999
        if 'cardTitle' in cfg:
            item['cardTitle'] = sanitize_public_text(cfg.get('cardTitle', ''), max_length=120)
        if 'cardImage' in cfg:
            item['cardImage'] = sanitize_public_media_url(
                cfg.get('cardImage', ''),
                enforce_remote_public=False
            )
        if 'cardSummary' in cfg:
            item['cardSummary'] = sanitize_public_text(cfg.get('cardSummary', ''), max_length=220)
        if 'categories' in cfg:
            values = cfg.get('categories', [])
            if not isinstance(values, list):
                values = [values]
            item['categories'] = [str(v or '').strip() for v in values if str(v or '').strip()]
        if 'industryCategories' in cfg:
            values = cfg.get('industryCategories', [])
            if not isinstance(values, list):
                values = [values]
            item['industryCategories'] = [str(v or '').strip() for v in values if str(v or '').strip()]
        if 'relatedNews' in cfg:
            item['relatedNews'] = _normalize_related_news_links(cfg.get('relatedNews', []))
        cleaned[pid] = item
    return cleaned


def sanitize_public_partner_items(items):
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = sanitize_public_media_url(item.get('url', ''), enforce_remote_public=False)
        if not url:
            continue
        cleaned.append({
            'id': str(item.get('id') or uuid.uuid4().hex),
            'url': url,
            'source': 'upload' if str(item.get('source') or '').lower() == 'upload' else 'url'
        })
    return cleaned


def resolve_product_html_path_by_id(product_id: str):
    """Resolve product id to local html path in pages directories."""
    pid = str(product_id or '').strip()
    base_dir = Path(__file__).parent / 'pages'
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
@app.route('/api/solutions/hydrogen/config')
def get_hydrogen_solutions_public_config():
    """Public config for industry solution pages (per-solution related products)."""
    return jsonify({'solutions': build_hydrogen_solution_public_payload()})


@app.route('/api/admin/hydrogen-solutions/config')
@login_required
def get_hydrogen_solutions_admin_config():
    """Admin config: solution list + selected related product ids + product options."""
    products = get_hydrogen_solution_product_pool()
    product_options = []
    for product in products:
        pid = str(product.get('id', '')).strip()
        if not pid:
            continue
        product_options.append({
            'id': pid,
            'title': product.get('displayName') or product.get('shortName') or product.get('name') or pid,
            'image': (product.get('cardImage') or '').strip() or (product.get('image') or '').strip()
        })
    return jsonify({
        'success': True,
        'definitions': get_hydrogen_solution_definitions(),
        'config': get_hydrogen_solution_products_config(),
        'products': product_options
    })


@app.route('/api/admin/hydrogen-solutions/config', methods=['POST'])
@login_required
def update_hydrogen_solutions_admin_config():
    """Persist admin-edited per-solution related product ids."""
    data = request.json or {}
    saved = save_hydrogen_solution_products_config(data)
    return jsonify({'success': True, 'config': saved})
# ============ Product Images API ============

@app.route('/api/products/images')
def get_product_images():
    """Get list of product images for particle effect."""
    images_dir = Path(__file__).parent / 'assets' / 'images' / 'products'
    images = []
    
    if images_dir.exists():
        # Get all png files and sort numerically
        for img_path in sorted(images_dir.glob('*.png'), key=lambda x: int(x.stem) if x.stem.isdigit() else 999):
            images.append(f'/assets/images/products/{img_path.name}')
    
    return jsonify({'images': images})


# ============ Auto Product Scan API ============

# 排除的文件（索引页、分类页等）
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
    'products_modules.html'
}

# 默认产品分类映射（基于 products-data.js）
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
    # 定制服务产品
    '../customization/custom_gas_sensing_module': 'service',
    '../customization/custom_instrument_dev': 'service',
    '../customization/micronano_fabrication': 'service',
}



def extract_solution_meta_from_html(filepath):
    """从解决方案HTML文件中提取基础信息"""
    from html.parser import HTMLParser

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

    def extract_background_image(html_content):
        """在缺少 <img> 封面时，回退提取英雄区 CSS 背景图。"""
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
            if candidate and not any(x in candidate.lower() for x in ['icon', 'logo', 'arrow', 'btn', 'button']):
                return candidate

        fallback_matches = re.findall(r'url\((["\']?)(.*?)\1\)', html_content, re.I | re.S)
        for _, candidate in fallback_matches:
            candidate = (candidate or '').strip()
            if candidate and not any(x in candidate.lower() for x in ['icon', 'logo', 'arrow', 'btn', 'button']):
                return candidate
        return ''

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        parser = SolutionMetaParser()
        parser.feed(content)

        item_id = filepath.stem
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
            'desc': sanitize_public_text(desc, max_length=220)
        }

    except Exception as e:
        print(f"Error parsing solution file {filepath}: {e}")
        return None


def normalize_scanned_image_path(image, web_dir_prefix):
    """Normalize extracted image path for cross-directory rendering."""
    img = str(image or '').strip()
    if not img:
        return ''
    if img.startswith(('http://', 'https://', '/', 'data:', 'blob:')):
        return img
    clean = img.lstrip('./')
    return f"{web_dir_prefix.rstrip('/')}/{clean}"


@app.route('/api/products')
def get_products():
    """自动扫描产品目录并返回产品列表"""
    base_dir = Path(__file__).parent / 'pages'
    gassensing_dir = base_dir / 'gassensing'
    customization_dir = base_dir / 'customization'
    biosensing_dir = base_dir / 'biosensing'
    products = []
    
    # 扫描 gassensing 目录
    if gassensing_dir.exists():
        for filepath in sorted(gassensing_dir.glob('*.html')):
            if filepath.name in EXCLUDED_PRODUCT_FILES:
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/gassensing')
                products.append(product)
    
    # 扫描 customization 目录（定制服务）
    if customization_dir.exists():
        for filepath in sorted(customization_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                # 为 customization 产品添加路径前缀
                product['id'] = '../customization/' + product['id']
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/customization')
                product['isCustomization'] = True
                products.append(product)

    # 扫描 biosensing 目录
    if biosensing_dir.exists():
        for filepath in sorted(biosensing_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['id'] = '../biosensing/' + product['id']
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/biosensing')
                product['isBiosensing'] = True
                products.append(product)
    
    # 按类别排序
    category_order = {'iot': 0, 'module': 1, 'sensor': 2, 'detector': 3, 'alarm': 4, 'system': 5, 'probe': 6, 'service': 7}
    products.sort(key=lambda p: (category_order.get(p.get('category', 'module'), 99), p.get('name', '')))
    
    return jsonify({'products': products, 'count': len(products)})


@app.route('/api/products/code/download')
@app.route('/api/bio-products/code/download')
@login_required
def download_product_code():
    """Download product html source by product id."""
    product_id = (request.args.get('id') or '').strip()
    filepath, slug = resolve_product_html_path_by_id(product_id)
    if not filepath or not filepath.exists():
        return jsonify({'success': False, 'message': '产品文件不存在'}), 404
    return send_file(
        filepath,
        as_attachment=True,
        download_name=f'{slug}.html',
        mimetype='text/html'
    )


@app.route('/api/products/code/upload', methods=['POST'])
@app.route('/api/bio-products/code/upload', methods=['POST'])
@login_required
def upload_product_code():
    """Upload and overwrite product html source by product id."""
    super_admin_denied = require_super_admin_api()
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

    filepath.write_text(content, encoding='utf-8')
    return jsonify({'success': True, 'message': '覆盖上传成功'})


def cleanup_deleted_product_references(product_id: str):
    """Remove deleted product references from admin-managed config files."""
    settings = get_product_settings()
    if product_id in settings:
        settings.pop(product_id, None)
        save_product_settings(settings)

    if PRODUCT_FEATURED_FILE.exists():
        try:
            raw = json.loads(PRODUCT_FEATURED_FILE.read_text(encoding='utf-8'))
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
                    PRODUCT_FEATURED_FILE.write_text(
                        json.dumps(raw, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )

    if HYDROGEN_SOLUTIONS_CONFIG_FILE.exists():
        save_hydrogen_solution_products_config(get_hydrogen_solution_products_config())


@app.route('/api/products/delete', methods=['POST'])
@login_required
def delete_product_item():
    """Delete one gassensing/customization product page and related admin config."""
    super_admin_denied = require_super_admin_api()
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
    if filepath.name in EXCLUDED_PRODUCT_FILES or filepath.name == 'index.html':
        return jsonify({'success': False, 'message': '该页面不允许删除'}), 400

    try:
        filepath.unlink()
    except Exception as exc:
        return jsonify({'success': False, 'message': f'删除文件失败: {exc}'}), 500

    cleanup_deleted_product_references(product_id)
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
    super_admin_denied = require_super_admin_api()
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
    # Merge new fields into existing template_fields
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
@login_required
def get_product_page_sections():
    """Extract all editable sections from a modern vs-* product page."""
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
    except Exception as e:
        return jsonify({'success': False, 'message': f'解析失败: {e}'}), 500


@app.route('/api/products/page-sections', methods=['POST'])
@login_required
def save_product_page_sections():
    """Patch a modern vs-* product page HTML with edited sections."""
    super_admin_denied = require_super_admin_api()
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
        filepath.write_text(patched, encoding='utf-8')
        return jsonify({'success': True, 'message': '保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存失败: {e}'}), 500


@app.route('/api/products/with-settings')
def get_products_with_settings():
    """Get products with merged settings."""
    products = get_products_with_settings_data()
    return jsonify({'products': products, 'count': len(products)})


def get_biosensing_products_with_settings_data():
    """Collect biosensing products merged with biosensing-specific settings."""
    base_dir = Path(__file__).parent / 'pages'
    biosensing_dir = base_dir / 'biosensing'
    products = []

    if biosensing_dir.exists():
        for filepath in sorted(biosensing_dir.glob('*.html')):
            if filepath.name in {'index.html', 'index_page_2.html'}:
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['id'] = '../biosensing/' + product['id']
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/biosensing')
                product['isBiosensing'] = True
                products.append(product)

    settings = get_bio_product_settings()
    for product in products:
        pid = product['id']
        product['name'] = sanitize_public_text(product.get('name', ''), max_length=120)
        product['shortName'] = sanitize_public_text(product.get('shortName', ''), max_length=120)
        product['description'] = sanitize_public_text(product.get('description', ''), max_length=220)
        product['image'] = sanitize_public_media_url(product.get('image', ''), enforce_remote_public=False)
        product['category'] = str(product.get('category', 'sensor') or 'sensor').strip() or 'sensor'

        if pid in settings:
            product['displayName'] = settings[pid].get('displayName', '')
            product['isNew'] = settings[pid].get('isNew', False)
            product['hidden'] = settings[pid].get('hidden', False)
            product['sortOrder'] = settings[pid].get('sortOrder', 999)
            product['cardTitle'] = settings[pid].get('cardTitle', '')
            product['cardImage'] = settings[pid].get('cardImage', '')
            product['cardSummary'] = settings[pid].get('cardSummary', '')
            product['relatedNews'] = _normalize_related_news_links(settings[pid].get('relatedNews', []))
            custom_categories = settings[pid].get('categories', [])
            if custom_categories:
                product['categories'] = custom_categories
            else:
                product['categories'] = [product.get('category', 'sensor')]
        else:
            product['displayName'] = ''
            product['isNew'] = False
            product['hidden'] = False
            product['sortOrder'] = 999
            product['cardTitle'] = ''
            product['cardImage'] = ''
            product['cardSummary'] = ''
            product['relatedNews'] = []
            product['categories'] = [product.get('category', 'sensor')]

        if pid in settings and isinstance(settings[pid].get('industryCategories'), list):
            product['industryCategories'] = settings[pid].get('industryCategories', [])
        else:
            product['industryCategories'] = infer_default_bio_industry_categories(product)

        product['displayName'] = sanitize_public_text(product.get('displayName', ''), max_length=120)
        product['cardTitle'] = sanitize_public_text(product.get('cardTitle', ''), max_length=120)
        product['cardSummary'] = sanitize_public_text(product.get('cardSummary', ''), max_length=220)
        product['cardImage'] = sanitize_public_media_url(product.get('cardImage', ''), enforce_remote_public=False)

    products.sort(key=lambda p: (p.get('sortOrder', 999), p.get('name', '')))
    return products


@app.route('/api/bio-products/with-settings')
def get_biosensing_products_with_settings_api():
    """Get biosensing products with merged biosensing settings."""
    products = get_biosensing_products_with_settings_data()
    return jsonify({'products': products, 'count': len(products)})


_products_cache_lock = threading.Lock()
_products_cache: dict = {'data': None, 'expires_at': 0.0}
_PRODUCTS_CACHE_TTL = 30  # seconds


def get_products_with_settings_data():
    """Collect products with merged settings (cached with 30s TTL)."""
    now = time.time()
    with _products_cache_lock:
        if _products_cache['data'] is not None and now < _products_cache['expires_at']:
            return _products_cache['data']
    # Get base products from both directories
    base_dir = Path(__file__).parent / 'pages'
    gassensing_dir = base_dir / 'gassensing'
    customization_dir = base_dir / 'customization'
    biosensing_dir = base_dir / 'biosensing'
    products = []

    # Scan gassensing directory
    if gassensing_dir.exists():
        for filepath in sorted(gassensing_dir.glob('*.html')):
            if filepath.name in EXCLUDED_PRODUCT_FILES:
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/gassensing')
                products.append(product)

    # Scan customization directory
    if customization_dir.exists():
        for filepath in sorted(customization_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['id'] = '../customization/' + product['id']
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/customization')
                product['isCustomization'] = True
                products.append(product)

    # Scan biosensing directory
    if biosensing_dir.exists():
        for filepath in sorted(biosensing_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['id'] = '../biosensing/' + product['id']
                product['image'] = normalize_scanned_image_path(product.get('image', ''), '/pages/biosensing')
                product['isBiosensing'] = True
                products.append(product)

    # Merge with settings
    settings = get_product_settings()
    for product in products:
        pid = product['id']
        product['name'] = sanitize_public_text(product.get('name', ''), max_length=120)
        product['shortName'] = sanitize_public_text(product.get('shortName', ''), max_length=120)
        product['description'] = sanitize_public_text(product.get('description', ''), max_length=220)
        product['image'] = sanitize_public_media_url(product.get('image', ''), enforce_remote_public=False)
        product['category'] = str(product.get('category', 'module') or 'module').strip() or 'module'
        if pid in settings:
            product['displayName'] = settings[pid].get('displayName', '')
            product['isNew'] = settings[pid].get('isNew', False)
            product['hidden'] = settings[pid].get('hidden', False)
            product['sortOrder'] = settings[pid].get('sortOrder', 999)
            product['cardTitle'] = settings[pid].get('cardTitle', '')
            product['cardImage'] = settings[pid].get('cardImage', '')
            product['cardSummary'] = settings[pid].get('cardSummary', '')
            product['relatedNews'] = _normalize_related_news_links(settings[pid].get('relatedNews', []))
            # 支持多分类：如果设置了 categories 数组则使用，否则使用原始的 category
            custom_categories = settings[pid].get('categories', [])
            if custom_categories:
                product['categories'] = custom_categories
            else:
                product['categories'] = [product.get('category', 'module')]
        else:
            product['displayName'] = ''
            product['isNew'] = False
            product['hidden'] = False
            product['sortOrder'] = 999
            product['cardTitle'] = ''
            product['cardImage'] = ''
            product['cardSummary'] = ''
            product['relatedNews'] = []
            product['categories'] = [product.get('category', 'module')]

        if pid in settings and isinstance(settings[pid].get('industryCategories'), list):
            product['industryCategories'] = settings[pid].get('industryCategories', [])
        else:
            product['industryCategories'] = infer_default_industry_categories(product)

        product['displayName'] = sanitize_public_text(product.get('displayName', ''), max_length=120)
        product['cardTitle'] = sanitize_public_text(product.get('cardTitle', ''), max_length=120)
        product['cardSummary'] = sanitize_public_text(product.get('cardSummary', ''), max_length=220)
        product['cardImage'] = sanitize_public_media_url(product.get('cardImage', ''), enforce_remote_public=False)

    # Sort by custom sortOrder first, then by name
    products.sort(key=lambda p: (p.get('sortOrder', 999), p.get('name', '')))
    with _products_cache_lock:
        _products_cache['data'] = products
        _products_cache['expires_at'] = time.time() + _PRODUCTS_CACHE_TTL
    return products


def get_gassensing_products_with_settings():
    """Only products from gassensing directory."""
    products = [p for p in get_products_with_settings_data() if not str(p.get('id', '')).startswith('../')]
    return products


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
    """Products that can be selected in hydrogen solution related-product config."""
    pool = []
    for product in get_products_with_settings_data():
        pid = str(product.get('id', '')).strip()
        if not pid or pid == 'all-products':
            continue
        if pid.startswith('../biosensing/'):
            continue
        pool.append(product)
    return pool


def normalize_hydrogen_solution_products_config(raw_config):
    """
    Normalize stored hydrogen-solution related-product config.
    Ensure every solution has 1-4 valid product ids.
    """
    pool = get_hydrogen_solution_product_pool()
    available_ids = {str(p.get('id', '')).strip() for p in pool if str(p.get('id', '')).strip()}

    raw_map = {}
    if isinstance(raw_config, dict):
        if isinstance(raw_config.get('solutions'), list):
            for item in raw_config.get('solutions', []):
                if not isinstance(item, dict):
                    continue
                sid = str(item.get('id', '')).strip()
                if sid:
                    raw_map[sid] = item.get('relatedProductIds', [])
        else:
            for sid, val in raw_config.items():
                if not isinstance(sid, str):
                    continue
                raw_map[sid] = val

    normalized_solutions = []
    fallback_pool_ids = [pid for pid in (
        str(p.get('id', '')).strip() for p in pool
    ) if pid][:4]

    for definition in get_hydrogen_solution_definitions():
        sid = definition['id']
        candidate_ids = raw_map.get(sid, [])
        if not isinstance(candidate_ids, list):
            candidate_ids = []
        cleaned_ids = []
        seen = set()
        for pid in candidate_ids:
            product_id = str(pid or '').strip()
            if not product_id or product_id in seen or product_id not in available_ids:
                continue
            seen.add(product_id)
            cleaned_ids.append(product_id)
            if len(cleaned_ids) >= 4:
                break

        if not cleaned_ids:
            default_ids = DEFAULT_HYDROGEN_SOLUTION_PRODUCTS.get(sid, [])
            for pid in default_ids:
                if pid in available_ids and pid not in cleaned_ids:
                    cleaned_ids.append(pid)
                if len(cleaned_ids) >= 4:
                    break

        if not cleaned_ids:
            cleaned_ids = fallback_pool_ids[:4]

        normalized_solutions.append({
            'id': sid,
            'relatedProductIds': cleaned_ids[:4]
        })

    return {'solutions': normalized_solutions}


def get_hydrogen_solution_products_config():
    if HYDROGEN_SOLUTIONS_CONFIG_FILE.exists():
        try:
            raw = json.loads(HYDROGEN_SOLUTIONS_CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            raw = {}
    else:
        raw = {}
    normalized = normalize_hydrogen_solution_products_config(raw)
    return normalized


def save_hydrogen_solution_products_config(new_config):
    normalized = normalize_hydrogen_solution_products_config(new_config)
    HYDROGEN_SOLUTIONS_CONFIG_FILE.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return normalized


def to_solution_product_card(product):
    title = product.get('displayName') or product.get('shortName') or product.get('name') or product.get('id', '')
    image = (product.get('cardImage') or '').strip() or (product.get('image') or '').strip()
    summary = (product.get('cardSummary') or '').strip() or (product.get('description') or '').strip()
    link = '/' + build_product_link(product).lstrip('/')
    return {
        'id': product.get('id', ''),
        'title': sanitize_public_text(title, max_length=120),
        'image': sanitize_public_media_url(image, enforce_remote_public=False),
        'summary': sanitize_public_text(summary, max_length=220),
        'link': sanitize_public_link_url(link, default='#')
    }


def build_hydrogen_solution_public_payload():
    config = get_hydrogen_solution_products_config()
    config_map = {
        str(item.get('id', '')).strip(): item.get('relatedProductIds', [])
        for item in config.get('solutions', []) if isinstance(item, dict)
    }
    pool = get_hydrogen_solution_product_pool()
    product_map = {str(p.get('id', '')).strip(): p for p in pool if str(p.get('id', '')).strip()}

    payload = []
    for definition in get_hydrogen_solution_definitions():
        sid = definition['id']
        related_ids = config_map.get(sid, [])
        related_products = []
        for pid in related_ids:
            product = product_map.get(str(pid).strip())
            if not product:
                continue
            related_products.append(to_solution_product_card(product))
            if len(related_products) >= 4:
                break
        payload.append({
            'id': sid,
            'title': definition['title'],
            'relatedProducts': related_products
        })
    return payload


def extract_case_meta_from_html(filepath):
    """Extract case meta: title, image, summary."""
    from html.parser import HTMLParser
    content = filepath.read_text(encoding='utf-8', errors='ignore')

    # Try to extract hero background image
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
        'id': filepath.name,
        'title': sanitize_public_text(title or filepath.stem, max_length=120),
        'image': sanitize_public_media_url(image, enforce_remote_public=False),
        'desc': sanitize_public_text(desc, max_length=220)
    }


def get_all_case_items():
    cases_dir = Path(__file__).parent / 'pages' / 'gassensing' / 'cases'
    items = []
    if cases_dir.exists():
        for filepath in sorted(cases_dir.glob('case-*.html')):
            item = extract_case_meta_from_html(filepath)
            if item:
                item['link'] = sanitize_public_link_url(f"pages/gassensing/cases/{filepath.name}", default='#')
                items.append(item)
    return items


# ============ Hero Carousel API ============

@app.route('/api/products/card-image/upload', methods=['POST'])
@app.route('/api/bio-products/card-image/upload', methods=['POST'])
@login_required
def upload_product_card_image():
    """Upload image file for product card and return accessible URL."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未找到上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    ext = validate_uploaded_image_extension(file, allowed_extensions=ALLOWED_PRODUCT_CARD_EXTENSIONS)
    if not ext:
        return jsonify({'success': False, 'message': '仅支持 PNG/JPG/JPEG/WEBP 图片'}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = PRODUCT_CARD_UPLOADS_DIR / saved_name
    file.save(save_path)

    return jsonify({
        'success': True,
        'url': f'/media/product-cards/{saved_name}'
    })


@app.route('/media/product-cards/<path:filename>')
def serve_product_card_media(filename):
    """Serve uploaded product card image files."""
    return send_from_directory(PRODUCT_CARD_UPLOADS_DIR, filename)
# ============ API Routes ============


def get_public_turnstile_config():
    return get_turnstile_settings(get_config() or {})


def extract_turnstile_token_from_request():
    form = request.form or {}
    for key in ('cf_turnstile_response', 'cf-turnstile-response', 'turnstileToken'):
        value = str(form.get(key, '') or '').strip()
        if value:
            return value

    data = request.get_json(silent=True) or {}
    if isinstance(data, dict):
        for key in ('cf_turnstile_response', 'cf-turnstile-response', 'turnstileToken'):
            value = str(data.get(key, '') or '').strip()
            if value:
                return value
    return ''


def require_public_turnstile_check(ip: str = ''):
    settings = get_public_turnstile_config()
    if not settings.get('enabled'):
        return None

    token = extract_turnstile_token_from_request()
    if not token:
        return jsonify({'success': False, 'message': '请先完成人机验证'}), 400

    ok, detail = verify_turnstile_token(
        secret_key=settings.get('secret_key', ''),
        token=token,
        remote_ip=ip or get_client_ip(),
    )
    if ok:
        return None
    return jsonify({'success': False, 'message': detail or '验证码校验失败，请重试'}), 400


@app.route('/api/turnstile/public', methods=['GET'])
def get_turnstile_public_api():
    """Public Turnstile config for site forms."""
    settings = get_public_turnstile_config()
    return jsonify({
        'enabled': bool(settings.get('enabled')),
        'site_key': settings.get('site_key', ''),
    })


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Handle feedback form submission."""
    ip = get_client_ip()

    turnstile_failed = require_public_turnstile_check(ip)
    if turnstile_failed:
        return turnstile_failed
    
    # Check rate limit
    if not check_rate_limit(ip):
        return jsonify({
            'success': False,
            'message': '提交过于频繁，请稍后再试。每小时最多提交5条留言。'
        }), 429
    
    # Get form data
    data = request.form if request.form else request.json or {}
    
    # Validate required fields
    phone = data.get('txtUserTel', '').strip()
    content = data.get('txtContent', '').strip()
    
    if not phone:
        return jsonify({'success': False, 'message': '请填写联系电话'}), 400
    if not content:
        return jsonify({'success': False, 'message': '请填写留言内容'}), 400
    
    # Create message object
    message = {
        'id': datetime.now().strftime('%Y%m%d%H%M%S%f') + secrets.token_hex(4),
        'name': (data.get('txtUserName', '').strip() or '匿名')[:100],
        'phone': phone[:30],
        'email': data.get('txtUserEmail', '').strip()[:200],
        'qq': data.get('txtUserQQ', '').strip()[:20],
        'title': (data.get('txtTitle', '').strip() or '无标题')[:200],
        'content': content[:5000],
        'is_read': False,
        'timestamp': datetime.now().isoformat(),
        'ip': ip
    }
    
    # Save message
    filename = f"{message['id']}.json"
    filepath = MESSAGES_DIR / filename
    filepath.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding='utf-8')
    
    return jsonify({
        'success': True,
        'message': '留言提交成功！我们会尽快回复您。'
    })


@app.route('/api/messages', methods=['GET'])
@login_required
def get_messages():
    """Get all messages for admin panel."""
    messages = []
    today = datetime.now().date().isoformat()
    today_count = 0
    read_count = 0
    job_count = 0
    for filepath in sorted(MESSAGES_DIR.glob('*.json'), reverse=True):
        try:
            msg = json.loads(filepath.read_text(encoding='utf-8'))
            resume_download_url = build_resume_download_url(msg)
            if resume_download_url:
                msg['resume_url'] = resume_download_url
            messages.append(msg)
            if str(msg.get('timestamp', '')).split('T')[0] == today:
                today_count += 1
            if msg.get('is_read'):
                read_count += 1
            if msg.get('message_type') == 'job_application':
                job_count += 1
        except:
            continue

    meta = get_messages_meta()
    stats = {
        'total_count': len(messages),
        'job_count': job_count,
        'today_count': today_count,
        'read_count': read_count,
        'deleted_count': int(meta.get('deleted_count', 0))
    }
    return jsonify({
        'messages': messages,
        'stats': stats
    })


@app.route('/api/messages/<message_id>', methods=['DELETE'])
@login_required
def delete_message(message_id):
    """Delete a message."""
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
        return jsonify({'success': False, 'message': '无效的留言 ID'}), 400
    filepath = MESSAGES_DIR / f"{message_id}.json"
    if filepath.exists():
        try:
            msg = json.loads(filepath.read_text(encoding='utf-8'))
            resume_name = extract_resume_storage_name(msg)
            if resume_name:
                resume_path = RESUME_UPLOADS_DIR / resume_name
                if resume_path.exists():
                    resume_path.unlink()
        except Exception:
            pass
        filepath.unlink()
        meta = get_messages_meta()
        meta['deleted_count'] = int(meta.get('deleted_count', 0)) + 1
        save_messages_meta(meta)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '留言不存在'}), 404


@app.route('/api/messages/<message_id>/read', methods=['POST'])
@login_required
def mark_message_read(message_id):
    """Mark one message as read."""
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
        return jsonify({'success': False, 'message': '无效的留言 ID'}), 400
    filepath = MESSAGES_DIR / f"{message_id}.json"
    if not filepath.exists():
        return jsonify({'success': False, 'message': '留言不存在'}), 404
    try:
        msg = json.loads(filepath.read_text(encoding='utf-8'))
        msg['is_read'] = True
        filepath.write_text(json.dumps(msg, ensure_ascii=False, indent=2), encoding='utf-8')
        return jsonify({'success': True})
    except Exception:
        return jsonify({'success': False, 'message': '更新失败'}), 500


@app.route('/api/messages/<message_id>/resume', methods=['GET'])
@login_required
def download_message_resume(message_id):
    """Download one applicant resume via authenticated admin endpoint."""
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
        return jsonify({'success': False, 'message': '无效的留言 ID'}), 400
    filepath = MESSAGES_DIR / f"{message_id}.json"
    if not filepath.exists():
        return jsonify({'success': False, 'message': '留言不存在'}), 404
    try:
        msg = json.loads(filepath.read_text(encoding='utf-8'))
    except Exception:
        return jsonify({'success': False, 'message': '留言数据损坏'}), 500

    resume_name = extract_resume_storage_name(msg)
    if not resume_name:
        return jsonify({'success': False, 'message': '未找到简历文件'}), 404

    resume_path = RESUME_UPLOADS_DIR / resume_name
    if not resume_path.exists() or not resume_path.is_file():
        return jsonify({'success': False, 'message': '简历文件不存在'}), 404

    download_name = secure_filename(str(msg.get('resume_filename') or '')) or resume_name
    response = send_file(
        resume_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetypes.guess_type(download_name)[0] or 'application/octet-stream',
        conditional=False,
    )
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/job-application', methods=['POST'])
def submit_job_application():
    """Handle job application form submission."""
    ip = get_client_ip()

    turnstile_failed = require_public_turnstile_check(ip)
    if turnstile_failed:
        return turnstile_failed

    if not check_rate_limit(ip):
        return jsonify({
            'success': False,
            'message': '提交过于频繁，请稍后再试。每小时最多提交5条。'
        }), 429

    data = request.form or {}
    required_fields = {
        'name': '姓名',
        'age': '年龄',
        'ethnicity': '民族',
        'gender': '性别',
        'address': '住址',
        'phone': '电话',
        'email': '邮箱',
        'education': '学历',
        'school': '毕业院校',
        'work_experience': '工作经历',
        'project_experience': '项目经历',
        'self_statement': '自我陈述'
    }

    cleaned = {}
    for key in required_fields:
        cleaned[key] = clean_job_text(data.get(key, ''))
        if not cleaned[key]:
            return jsonify({'success': False, 'message': f'请填写{required_fields[key]}'}), 400

    age_val = re.sub(r'\D+', '', cleaned['age'])
    if not age_val:
        return jsonify({'success': False, 'message': '年龄格式不正确'}), 400
    cleaned['age'] = age_val

    if len(cleaned['self_statement']) > 100:
        return jsonify({'success': False, 'message': '自我陈述请控制在100字以内'}), 400

    resume_file = request.files.get('resume_file')
    if not resume_file or not resume_file.filename:
        return jsonify({'success': False, 'message': '请上传简历文件（PDF或Word）'}), 400

    ext = Path(resume_file.filename).suffix.lower()
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        return jsonify({'success': False, 'message': '简历格式仅支持 PDF/DOC/DOCX'}), 400
    if not validate_uploaded_resume(resume_file):
        return jsonify({'success': False, 'message': '简历文件格式与扩展名不匹配'}), 400

    # 10MB limit
    resume_file.stream.seek(0, os.SEEK_END)
    size = resume_file.stream.tell()
    resume_file.stream.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'success': False, 'message': '简历文件过大（最大10MB）'}), 400

    now = datetime.now()
    message_id = now.strftime('%Y%m%d%H%M%S%f')
    safe_name = secure_filename(resume_file.filename) or f'resume{ext}'
    saved_name = f"{message_id}_{safe_name}"
    resume_path = RESUME_UPLOADS_DIR / saved_name
    resume_file.save(resume_path)

    message = {
        'id': message_id,
        'message_type': 'job_application',
        'job_id': clean_job_text(data.get('job_id', '')),
        'job_title': clean_job_text(data.get('job_title', '')),
        'name': cleaned['name'],
        'age': cleaned['age'],
        'ethnicity': cleaned['ethnicity'],
        'gender': cleaned['gender'],
        'address': cleaned['address'],
        'phone': cleaned['phone'],
        'email': cleaned['email'],
        'education': cleaned['education'],
        'school': cleaned['school'],
        'work_experience': cleaned['work_experience'],
        'project_experience': cleaned['project_experience'],
        'self_statement': cleaned['self_statement'],
        'resume_filename': safe_name,
        'resume_stored_filename': saved_name,
        'resume_url': f'/api/messages/{message_id}/resume',
        'is_read': False,
        'timestamp': now.isoformat(),
        'ip': ip
    }

    filepath = MESSAGES_DIR / f"{message_id}.json"
    filepath.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding='utf-8')

    return jsonify({
        'success': True,
        'message': '应聘信息提交成功，我们会尽快联系您。'
    })

register_backup_routes(
    app,
    login_required=login_required,
    project_root=Path(__file__).parent,
    backup_meta_files=BACKUP_META_FILES,
    backup_excluded_dir_names=BACKUP_EXCLUDED_DIR_NAMES,
    backup_excluded_file_names=BACKUP_EXCLUDED_FILE_NAMES,
    backup_excluded_suffixes=BACKUP_EXCLUDED_SUFFIXES,
)

register_cdn_assets_routes(
    app,
    cdn_assets_dir=CDN_ASSETS_DIR,
    site_config_file=Path(__file__).parent / "data" / "site_config.json"
)

register_media_delivery_routes(
    app,
    login_required=login_required,
    get_config=get_config,
    update_config=update_config,
    is_same_origin_request=is_same_origin_request,
    validate_safe_remote_fetch_url=validate_safe_remote_fetch_url,
    first_forwarded_value=_first_forwarded_value,
    get_h2_home_config=get_h2_home_config,
    get_hero_config=get_hero_config,
    hero_config_file=HERO_CONFIG_FILE,
    sanitize_public_media_url=sanitize_public_media_url,
    cdn_assets_dir=CDN_ASSETS_DIR,
    media_immutable_cache_control=MEDIA_IMMUTABLE_CACHE_CONTROL,
    requests_support=REQUESTS_SUPPORT,
    requests_module=requests if REQUESTS_SUPPORT else None,
    httpx_support=HTTPX_SUPPORT,
    httpx_module=httpx if HTTPX_SUPPORT else None,
)

register_site_analytics_routes(
    app,
    login_required=login_required,
    data_dir=DATA_DIR,
    get_client_ip=get_client_ip,
    resolve_ip_location=resolve_ip_location,
    beijing_tz=BEIJING_TZ,
)


# ============ Admin Routes ============

register_admin_routes(
    app,
    login_required=login_required,
    get_config=get_config,
    update_config=update_config,
    append_admin_login_log=append_admin_login_log,
    load_admin_login_logs=load_admin_login_logs,
    admin_login_log_lock=ADMIN_LOGIN_LOG_LOCK,
    project_root=Path(__file__).parent,
)

register_home_content_routes(
    app,
    login_required=login_required,
    cached_json_response=cached_json_response,
    sanitize_public_media_url=sanitize_public_media_url,
    validate_uploaded_video_extension=validate_uploaded_video_extension,
    validate_uploaded_image_extension=validate_uploaded_image_extension,
    allowed_partner_extensions=ALLOWED_PARTNER_EXTENSIONS,
    hero_config_file=HERO_CONFIG_FILE,
    hero_uploads_dir=HERO_UPLOADS_DIR,
    hero_derived_dir=HERO_DERIVED_DIR,
    hero_derived_manifest_file=HERO_DERIVED_MANIFEST_FILE,
    hero_source_image_extensions=HERO_SOURCE_IMAGE_EXTENSIONS,
    hero_derived_widths=HERO_DERIVED_WIDTHS,
    hero_derived_formats=HERO_DERIVED_FORMATS,
    h2_home_video_uploads_dir=H2_HOME_VIDEO_UPLOADS_DIR,
    partners_config_file=PARTNERS_CONFIG_FILE,
    partners_uploads_dir=PARTNERS_UPLOADS_DIR,
    home_section_visibility_file=HOME_SECTION_VISIBILITY_FILE,
    allowed_hero_extensions=ALLOWED_HERO_EXTENSIONS,
    media_immutable_cache_control=MEDIA_IMMUTABLE_CACHE_CONTROL,
    pil_support=PIL_SUPPORT,
    image_module=Image,
    image_ops_module=ImageOps,
    pil_features=PIL_FEATURES,
)

register_product_settings_routes(
    app,
    login_required=login_required,
    data_dir=DATA_DIR,
    sanitize_public_product_settings=sanitize_public_product_settings,
    sanitize_public_text=sanitize_public_text,
    sanitize_public_media_url=sanitize_public_media_url,
    sanitize_public_link_url=sanitize_public_link_url,
    get_products_with_settings_data=get_products_with_settings_data,
    get_biosensing_products_with_settings_data=get_biosensing_products_with_settings_data,
)

register_showcase_content_routes(
    app,
    login_required=login_required,
    pages_dir=Path(__file__).parent / 'pages',
    cached_json_response=cached_json_response,
    sanitize_public_media_url=sanitize_public_media_url,
    sanitize_public_text=sanitize_public_text,
    sanitize_public_link_url=sanitize_public_link_url,
    validate_uploaded_video_extension=validate_uploaded_video_extension,
    product_featured_file=PRODUCT_FEATURED_FILE,
    solutions_featured_file=SOLUTIONS_FEATURED_FILE,
    h2_home_file=H2_HOME_FILE,
    h2_home_video_uploads_dir=H2_HOME_VIDEO_UPLOADS_DIR,
    allowed_h2_home_video_extensions=ALLOWED_H2_HOME_VIDEO_EXTENSIONS,
    get_products_with_settings_data=get_products_with_settings_data,
    get_gassensing_products_with_settings=get_gassensing_products_with_settings,
    get_all_case_items=get_all_case_items,
    extract_solution_meta_from_html=extract_solution_meta_from_html,
)

register_navigation_content_routes(
    app,
    login_required=login_required,
    app_root=APP_ROOT,
    data_dir=DATA_DIR,
    normalize_scanned_image_path=normalize_scanned_image_path,
    extract_solution_meta_from_html=extract_solution_meta_from_html,
    extract_case_meta_from_html=extract_case_meta_from_html,
    extract_product_meta_from_html=extract_product_meta_from_html,
)

register_jobs_content_routes(
    app,
    login_required=login_required,
    jobs_file=JOBS_FILE,
    pages_dir=Path(__file__).parent / 'pages',
    sanitize_news_html_fragment=sanitize_news_html_fragment,
)

register_product_editor_routes(
    app,
    login_required=login_required,
    app_root=APP_ROOT,
    require_super_admin_api=require_super_admin_api,
    render_markdown=render_markdown,
    get_product_page_ai_config=get_product_page_ai_config,
    get_product_page_ai_system_prompt=get_product_page_ai_system_prompt,
    get_product_settings=get_product_settings,
    save_product_settings=save_product_settings,
    default_product_categories=DEFAULT_PRODUCT_CATEGORIES,
    normalize_ai_product_image_extension=normalize_ai_product_image_extension,
    infer_ai_product_image_extension_from_mime=infer_ai_product_image_extension_from_mime,
    allowed_ai_product_image_mime_types=ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES,
)

register_ai_chatbot_routes(
    app,
    login_required=login_required,
    get_config=get_config,
    update_config=update_config,
    require_super_admin_api=require_super_admin_api,
    get_client_ip=get_client_ip,
    resolve_ip_location=resolve_ip_location,
    sanitize_public_link_url=sanitize_public_link_url,
    validate_uploaded_pdf=validate_uploaded_pdf,
    knowledge_dir=KNOWLEDGE_DIR,
    conversation_log_file=CHATBOT_CONVERSATION_LOG_FILE,
    pdf_support=PDF_SUPPORT,
    pypdf2_module=PyPDF2 if PDF_SUPPORT else None,
    requests_support=REQUESTS_SUPPORT,
    requests_module=requests if REQUESTS_SUPPORT else None,
    httpx_support=HTTPX_SUPPORT,
    httpx_module=httpx if HTTPX_SUPPORT else None,
)

register_news_content_routes(
    app,
    login_required=login_required,
    pages_dir=Path(__file__).parent / 'pages',
    news_featured_file=NEWS_FEATURED_FILE,
    news_visibility_file=NEWS_VISIBILITY_FILE,
    news_uploads_dir=NEWS_UPLOADS_DIR,
    h2_home_file=H2_HOME_FILE,
    markdown_support=MARKDOWN_SUPPORT,
    markdown_module=md if MARKDOWN_SUPPORT else None,
    requests_support=REQUESTS_SUPPORT,
    requests_module=requests if REQUESTS_SUPPORT else None,
    httpx_support=HTTPX_SUPPORT,
    httpx_module=httpx if HTTPX_SUPPORT else None,
    allowed_news_image_extensions=ALLOWED_NEWS_IMAGE_EXTENSIONS,
    news_safe_html_tags=NEWS_SAFE_HTML_TAGS,
    news_dropped_html_tags=NEWS_DROPPED_HTML_TAGS,
    news_void_html_tags=NEWS_VOID_HTML_TAGS,
    validate_uploaded_image_extension=validate_uploaded_image_extension,
    validate_image_bytes=validate_image_bytes,
    validate_safe_remote_fetch_url=validate_safe_remote_fetch_url,
    sanitize_public_text=sanitize_public_text,
    sanitize_public_date_text=sanitize_public_date_text,
    sanitize_public_link_url=sanitize_public_link_url,
    sanitize_public_media_url=sanitize_public_media_url,
    get_h2_home_config=get_h2_home_config,
    get_product_settings=get_product_settings,
    normalize_related_news_links=_normalize_related_news_links,
    get_chatbot_config=get_chatbot_config,
    call_openai_api=call_openai_api,
)

register_public_site_routes(
    app,
    login_required=login_required,
    app_root=APP_ROOT,
    cdn_assets_dir=CDN_ASSETS_DIR,
    site_favicon_relative_path=SITE_FAVICON_RELATIVE_PATH,
    public_static_exact_files=PUBLIC_STATIC_EXACT_FILES,
    public_static_root_dirs=PUBLIC_STATIC_ROOT_DIRS,
    private_static_prefixes=PRIVATE_STATIC_PREFIXES,
    get_public_base_url=get_public_base_url,
    first_forwarded_value=_first_forwarded_value,
    is_anti_crawl_strict_private_path=_is_anti_crawl_strict_private_path,
    strict_anti_crawl_headers=STRICT_ANTI_CRAWL_HEADERS,
    public_html_content_security_policy=PUBLIC_HTML_CONTENT_SECURITY_POLICY,
    public_referrer_policy=PUBLIC_REFERRER_POLICY,
    chem_subscript_script_src=CHEM_SUBSCRIPT_SCRIPT_SRC,
    site_analytics_script_src=SITE_ANALYTICS_SCRIPT_SRC,
    site_brand_name=SITE_BRAND_NAME,
    site_company_name=SITE_COMPANY_NAME,
    site_display_name=SITE_DISPLAY_NAME,
    site_default_description=SITE_DEFAULT_DESCRIPTION,
    site_logo_path=SITE_LOGO_PATH,
    seo_default_robots=SEO_DEFAULT_ROBOTS,
    seo_section_descriptions=SEO_SECTION_DESCRIPTIONS,
    seo_breadcrumb_labels=SEO_BREADCRUMB_LABELS,
    seo_breadcrumb_targets=SEO_BREADCRUMB_TARGETS,
)


if __name__ == '__main__':
    print("=" * 50)
    print("YX Website Server")
    print("=" * 50)
    print(f"Local:   http://localhost:8000")
    print(f"Admin:   http://localhost:8000/admin")
    print(f"Data:    {MESSAGES_DIR.absolute()}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8000, debug=True)
