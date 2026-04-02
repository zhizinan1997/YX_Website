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
import html
import mimetypes
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from urllib.parse import quote, urlparse, unquote

from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string, Response, stream_with_context, send_file
from werkzeug.utils import secure_filename
from app.routes.admin import ADMIN_PERMISSION_KEYS, register_admin_routes, resolve_permission_for_path
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
from app.routes.news_content import (
    get_all_news_items,
    normalize_news_plain_text,
    register_news_content_routes,
    render_markdown,
    sanitize_news_html_fragment,
    sanitize_news_image_url,
    sanitize_news_link_url,
)
from app.routes.product_editor import extract_product_meta_from_html, register_product_editor_routes
from app.routes.public_site import register_public_site_routes
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
ADMIN_LOGIN_LOG_FILE = DATA_DIR / 'admin_login_logs.json'
ADMIN_LOGIN_LOG_LOCK = threading.Lock()
ADMIN_IP_LOCATION_CACHE = {}
ADMIN_IP_LOCATION_LOCK = threading.Lock()
ADMIN_IP_LOCATION_CACHE_MAX = 2048
ADMIN_IP_LOCATION_CACHE_TTL_SUCCESS = 7 * 24 * 3600
ADMIN_IP_LOCATION_CACHE_TTL_UNKNOWN = 15 * 60
SITE_ANALYTICS_LOG_FILE = DATA_DIR / 'site_analytics_events.jsonl'
SITE_ANALYTICS_LOCK = threading.Lock()
SITE_ANALYTICS_MAX_BATCH_SIZE = 25
SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH = 80
SITE_ANALYTICS_MAX_TEXT_LENGTH = 300
SITE_ANALYTICS_MAX_PATH_LENGTH = 260
SITE_ANALYTICS_ALLOWED_EVENT_TYPES = {'pageview', 'event', 'session_end'}
SITE_ANALYTICS_CONVERSION_EVENTS = {
    'contact_submit',
    'job_apply',
    'quote_request',
    'request_demo',
    'download_brochure',
    'phone_click',
    'email_click',
}
SITE_ANALYTICS_SEARCH_HOST_KEYWORDS = (
    'google.',
    'bing.',
    'baidu.',
    'yahoo.',
    'yandex.',
    'duckduckgo.',
    'sogou.',
    'so.com',
)
SITE_ANALYTICS_SOCIAL_HOST_KEYWORDS = (
    'facebook.',
    'instagram.',
    'linkedin.',
    'reddit.',
    'twitter.',
    'x.com',
    't.co',
    'weibo.',
    'zhihu.',
)

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
CDN_CONNECTIVITY_CHECK_HEADERS = {
    # Use a browser-like request profile so CDN/WAF and our own anti-crawl
    # rules do not misclassify the connectivity probe as a bot request.
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/123.0.0.0 Safari/537.36'
    ),
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}
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
        except:
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


def normalize_cdn_domain(raw_value: str) -> str:
    """Normalize CDN base domain to '<scheme>://<host>[:port]'."""
    value = (raw_value or '').strip()
    if not value:
        return ''

    if value.startswith('//'):
        value = f"https:{value}"
    elif not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        value = f"https://{value}"

    try:
        parsed = urlparse(value)
    except Exception:
        return ''

    if parsed.scheme not in {'http', 'https'}:
        return ''
    if not parsed.netloc:
        return ''

    return f"{parsed.scheme}://{parsed.netloc}".rstrip('/')


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


def get_cdn_settings() -> dict:
    """Read CDN acceleration settings from config."""
    config = get_config()
    domain = normalize_cdn_domain(str(config.get('cdn_domain') or ''))
    enabled = bool(config.get('cdn_enabled', False)) and bool(domain)
    return {
        'cdn_enabled': enabled,
        'cdn_domain': domain
    }

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


def _analytics_clean_text(value, max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH):
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text[:max_length]


def _analytics_clean_id(value, max_length=64):
    text = _analytics_clean_text(value, max_length=max_length)
    if not text:
        return ''
    return re.sub(r'[^a-zA-Z0-9._:-]', '', text)[:max_length]


def _analytics_extract_host(raw_url: str) -> str:
    text = _analytics_clean_text(raw_url, max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    if not text:
        return ''
    try:
        parsed = urlparse(text)
    except Exception:
        return ''
    host = (parsed.netloc or '').strip().lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


def _analytics_normalize_path(raw_value: str) -> str:
    text = _analytics_clean_text(raw_value, max_length=SITE_ANALYTICS_MAX_PATH_LENGTH)
    if not text:
        return '/'
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            text = parsed.path or '/'
    except Exception:
        pass
    if not text.startswith('/'):
        text = f'/{text.lstrip("./")}'
    text = re.sub(r'/+', '/', text)
    return text[:SITE_ANALYTICS_MAX_PATH_LENGTH] or '/'


def _analytics_classify_device(user_agent: str) -> str:
    ua = str(user_agent or '').lower()
    if not ua:
        return 'unknown'
    tablet_keywords = ('ipad', 'tablet', 'kindle', 'playbook', 'sm-t', 'nexus 7', 'nexus 10')
    mobile_keywords = ('mobile', 'android', 'iphone', 'ipod', 'windows phone', 'blackberry', 'opera mini')
    if any(keyword in ua for keyword in tablet_keywords):
        return 'tablet'
    if any(keyword in ua for keyword in mobile_keywords):
        return 'mobile'
    return 'desktop'


def _analytics_classify_os(user_agent: str) -> str:
    ua = str(user_agent or '').lower()
    if not ua:
        return 'unknown'
    if 'harmonyos' in ua or 'hongmeng' in ua or 'hmos' in ua:
        return 'harmonyos'
    if 'windows nt' in ua or 'win64' in ua or 'wow64' in ua:
        return 'windows'
    if 'android' in ua:
        return 'android'
    if 'iphone' in ua or 'ipad' in ua or 'ipod' in ua or 'cpu iphone os' in ua or 'cpu os' in ua:
        return 'ios'
    if 'mac os x' in ua or 'macintosh' in ua:
        return 'macos'
    if 'linux' in ua:
        return 'linux'
    return 'unknown'


_ANALYTICS_CHINA_PROVINCE_ALIASES = (
    ('北京市', ('北京', '北京市', 'beijing', 'peking')),
    ('上海市', ('上海', '上海市', 'shanghai')),
    ('天津市', ('天津', '天津市', 'tianjin')),
    ('重庆市', ('重庆', '重庆市', 'chongqing')),
    ('河北省', ('河北', '河北省', 'hebei')),
    ('山西省', ('山西', '山西省', 'shanxi')),
    ('辽宁省', ('辽宁', '辽宁省', 'liaoning')),
    ('吉林省', ('吉林', '吉林省', 'jilin')),
    ('黑龙江省', ('黑龙江', '黑龙江省', 'heilongjiang')),
    ('江苏省', ('江苏', '江苏省', 'jiangsu')),
    ('浙江省', ('浙江', '浙江省', 'zhejiang')),
    ('安徽省', ('安徽', '安徽省', 'anhui')),
    ('福建省', ('福建', '福建省', 'fujian')),
    ('江西省', ('江西', '江西省', 'jiangxi')),
    ('山东省', ('山东', '山东省', 'shandong')),
    ('河南省', ('河南', '河南省', 'henan')),
    ('湖北省', ('湖北', '湖北省', 'hubei')),
    ('湖南省', ('湖南', '湖南省', 'hunan')),
    ('广东省', ('广东', '广东省', 'guangdong')),
    ('海南省', ('海南', '海南省', 'hainan')),
    ('四川省', ('四川', '四川省', 'sichuan')),
    ('贵州省', ('贵州', '贵州省', 'guizhou')),
    ('云南省', ('云南', '云南省', 'yunnan')),
    ('陕西省', ('陕西', '陕西省', 'shaanxi')),
    ('甘肃省', ('甘肃', '甘肃省', 'gansu')),
    ('青海省', ('青海', '青海省', 'qinghai')),
    ('台湾省', ('台湾', '台湾省', 'taiwan')),
    ('内蒙古自治区', ('内蒙古', '内蒙古自治区', 'inner mongolia', 'nei mongol')),
    ('广西壮族自治区', ('广西', '广西壮族自治区', 'guangxi', 'guangxi zhuang autonomous region')),
    ('西藏自治区', ('西藏', '西藏自治区', 'tibet', 'xizang', 'tibet autonomous region')),
    ('宁夏回族自治区', ('宁夏', '宁夏回族自治区', 'ningxia', 'ningxia hui autonomous region')),
    ('新疆维吾尔自治区', ('新疆', '新疆维吾尔自治区', 'xinjiang', 'xinjiang uygur autonomous region')),
    ('香港特别行政区', ('香港', '香港特别行政区', 'hong kong', 'hong kong sar', 'hong kong special administrative region', 'hongkong')),
    ('澳门特别行政区', ('澳门', '澳门特别行政区', 'macau', 'macao', 'macao sar', 'macao special administrative region')),
)


def _analytics_normalize_ascii_words(text: str) -> str:
    compact = re.sub(r'[^a-z]+', ' ', str(text or '').lower())
    compact = re.sub(r'\s+', ' ', compact).strip()
    return f' {compact} ' if compact else ''


def _analytics_build_geo_lookup_key(text: str) -> str:
    raw = str(text or '').strip().lower()
    if not raw:
        return ''
    if re.search(r'[a-z]', raw):
        return _analytics_normalize_ascii_words(raw).strip()
    return re.sub(r'[\s/|,_\-·，、()（）]+', '', raw)


_ANALYTICS_NON_GEO_LOCATION_LABELS = {
    '未知',
    'unknown',
    'n/a',
    '-',
    '本机回环地址',
    '内网地址',
    '未指定地址',
    '保留地址',
    '组播地址',
}

_ANALYTICS_CONTINENT_LABELS = {
    'asia': '亚洲',
    'europe': '欧洲',
    'north-america': '北美洲',
    'south-america': '南美洲',
    'africa': '非洲',
    'oceania': '大洋洲',
}

_ANALYTICS_COUNTRY_CONTINENT_ALIASES = {
    'asia': (
        '中国', 'china',
        '日本', 'japan',
        '韩国', '南韩', '大韩民国', 'south korea', 'republic of korea', 'korea',
        '朝鲜', 'north korea', 'democratic people s republic of korea',
        '蒙古', 'mongolia',
        '新加坡', 'singapore',
        '马来西亚', 'malaysia',
        '泰国', 'thailand',
        '越南', 'vietnam',
        '印度尼西亚', '印尼', 'indonesia',
        '菲律宾', 'philippines',
        '印度', 'india',
        '巴基斯坦', 'pakistan',
        '孟加拉国', 'bangladesh',
        '斯里兰卡', 'sri lanka',
        '尼泊尔', 'nepal',
        '不丹', 'bhutan',
        '缅甸', 'myanmar',
        '老挝', 'laos',
        '柬埔寨', 'cambodia',
        '文莱', 'brunei',
        '东帝汶', 'timor leste',
        '哈萨克斯坦', 'kazakhstan',
        '乌兹别克斯坦', 'uzbekistan',
        '吉尔吉斯斯坦', 'kyrgyzstan',
        '塔吉克斯坦', 'tajikistan',
        '土库曼斯坦', 'turkmenistan',
        '阿富汗', 'afghanistan',
        '伊朗', 'iran',
        '伊拉克', 'iraq',
        '沙特阿拉伯', 'saudi arabia',
        '阿联酋', '阿拉伯联合酋长国', 'united arab emirates', 'uae',
        '卡塔尔', 'qatar',
        '科威特', 'kuwait',
        '巴林', 'bahrain',
        '阿曼', 'oman',
        '也门', 'yemen',
        '约旦', 'jordan',
        '黎巴嫩', 'lebanon',
        '叙利亚', 'syria',
        '以色列', 'israel',
        '巴勒斯坦', 'palestine',
        '土耳其', 'turkey',
        '格鲁吉亚', 'georgia',
        '亚美尼亚', 'armenia',
        '阿塞拜疆', 'azerbaijan',
        '塞浦路斯', 'cyprus',
        '马尔代夫', 'maldives',
    ),
    'europe': (
        '英国', '英格兰', '大不列颠', '联合王国', 'united kingdom', 'uk', 'britain', 'great britain', 'england',
        '爱尔兰', 'ireland',
        '法国', 'france',
        '德国', 'germany',
        '荷兰', '尼德兰', 'netherlands', 'holland',
        '比利时', 'belgium',
        '卢森堡', 'luxembourg',
        '瑞士', 'switzerland',
        '奥地利', 'austria',
        '意大利', 'italy',
        '西班牙', 'spain',
        '葡萄牙', 'portugal',
        '丹麦', 'denmark',
        '挪威', 'norway',
        '瑞典', 'sweden',
        '芬兰', 'finland',
        '冰岛', 'iceland',
        '波兰', 'poland',
        '捷克', '捷克共和国', 'czechia', 'czech republic',
        '斯洛伐克', 'slovakia',
        '匈牙利', 'hungary',
        '罗马尼亚', 'romania',
        '保加利亚', 'bulgaria',
        '希腊', 'greece',
        '克罗地亚', 'croatia',
        '斯洛文尼亚', 'slovenia',
        '塞尔维亚', 'serbia',
        '波斯尼亚和黑塞哥维那', '波黑', 'bosnia and herzegovina',
        '黑山', 'montenegro',
        '北马其顿', 'north macedonia',
        '阿尔巴尼亚', 'albania',
        '摩尔多瓦', 'moldova',
        '乌克兰', 'ukraine',
        '白俄罗斯', 'belarus',
        '立陶宛', 'lithuania',
        '拉脱维亚', 'latvia',
        '爱沙尼亚', 'estonia',
        '俄罗斯', 'russia', 'russian federation',
    ),
    'north-america': (
        '美国', '美利坚合众国', 'united states', 'united states of america', 'usa',
        '加拿大', 'canada',
        '墨西哥', 'mexico',
        '格陵兰', 'greenland',
        '古巴', 'cuba',
        '多米尼加共和国', 'dominican republic',
        '海地', 'haiti',
        '牙买加', 'jamaica',
        '危地马拉', 'guatemala',
        '伯利兹', 'belize',
        '洪都拉斯', 'honduras',
        '萨尔瓦多', 'el salvador',
        '尼加拉瓜', 'nicaragua',
        '哥斯达黎加', 'costa rica',
        '巴拿马', 'panama',
        '巴哈马', 'bahamas',
        '特立尼达和多巴哥', 'trinidad and tobago',
        '巴巴多斯', 'barbados',
        '波多黎各', 'puerto rico',
    ),
    'south-america': (
        '巴西', 'brazil',
        '阿根廷', 'argentina',
        '智利', 'chile',
        '秘鲁', 'peru',
        '哥伦比亚', 'colombia',
        '委内瑞拉', 'venezuela',
        '厄瓜多尔', 'ecuador',
        '玻利维亚', 'bolivia',
        '巴拉圭', 'paraguay',
        '乌拉圭', 'uruguay',
        '圭亚那', 'guyana',
        '苏里南', 'suriname',
        '法属圭亚那', 'french guiana',
    ),
    'africa': (
        '南非', 'south africa',
        '埃及', 'egypt',
        '尼日利亚', 'nigeria',
        '肯尼亚', 'kenya',
        '埃塞俄比亚', 'ethiopia',
        '坦桑尼亚', 'tanzania',
        '阿尔及利亚', 'algeria',
        '摩洛哥', 'morocco',
        '突尼斯', 'tunisia',
        '利比亚', 'libya',
        '苏丹', 'sudan',
        '南苏丹', 'south sudan',
        '加纳', 'ghana',
        '乌干达', 'uganda',
        '安哥拉', 'angola',
        '喀麦隆', 'cameroon',
        '科特迪瓦', '象牙海岸', 'cote d ivoire', 'ivory coast',
        '塞内加尔', 'senegal',
        '津巴布韦', 'zimbabwe',
        '赞比亚', 'zambia',
        '博茨瓦纳', 'botswana',
        '纳米比亚', 'namibia',
        '莫桑比克', 'mozambique',
        '马达加斯加', 'madagascar',
        '毛里求斯', 'mauritius',
        '卢旺达', 'rwanda',
        '刚果', 'congo',
        '刚果民主共和国', '民主刚果', 'democratic republic of the congo', 'dr congo',
        '加蓬', 'gabon',
    ),
    'oceania': (
        '澳大利亚', 'australia',
        '新西兰', 'new zealand',
        '巴布亚新几内亚', 'papua new guinea',
        '斐济', 'fiji',
        '萨摩亚', 'samoa',
        '汤加', 'tonga',
        '所罗门群岛', 'solomon islands',
        '瓦努阿图', 'vanuatu',
        '密克罗尼西亚', 'micronesia',
        '关岛', 'guam',
        '新喀里多尼亚', 'new caledonia',
    ),
}

_ANALYTICS_COUNTRY_TO_CONTINENT = {}
for _continent_key, _aliases in _ANALYTICS_COUNTRY_CONTINENT_ALIASES.items():
    for _alias in _aliases:
        _lookup_key = _analytics_build_geo_lookup_key(_alias)
        if _lookup_key:
            _ANALYTICS_COUNTRY_TO_CONTINENT[_lookup_key] = _continent_key


def _analytics_extract_china_province(location_text: str) -> str:
    text = str(location_text or '').strip()
    if not text:
        return ''
    normalized = re.sub(r'\s+', '', text)
    ascii_words = _analytics_normalize_ascii_words(text)
    if not normalized and not ascii_words:
        return ''

    for province_name, aliases in _ANALYTICS_CHINA_PROVINCE_ALIASES:
        for alias in aliases:
            alias_text = str(alias or '').strip()
            if not alias_text:
                continue
            if re.search(r'[A-Za-z]', alias_text):
                alias_words = _analytics_normalize_ascii_words(alias_text)
                if alias_words and alias_words in ascii_words:
                    return province_name
            elif alias_text in normalized:
                return province_name
    return ''


def _analytics_extract_record_province(item) -> str:
    province = _analytics_clean_text(item.get('province'), max_length=32)
    if province:
        return province
    location = _analytics_clean_text(item.get('location'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    derived = _analytics_extract_china_province(location)
    return _analytics_clean_text(derived, max_length=32)


def _analytics_extract_country_from_location(location_text: str) -> str:
    text = str(location_text or '').strip()
    if not text or text in _ANALYTICS_NON_GEO_LOCATION_LABELS:
        return ''
    if _analytics_extract_china_province(text):
        return '中国'
    first_segment = str(text.split('/', 1)[0] or '').strip()
    if not first_segment or first_segment in _ANALYTICS_NON_GEO_LOCATION_LABELS:
        return ''
    return first_segment


def _analytics_extract_record_country(item) -> str:
    country = _analytics_clean_text(item.get('country'), max_length=64)
    if country:
        if _analytics_extract_china_province(country):
            return '中国'
        return country
    location = _analytics_clean_text(item.get('location'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    return _analytics_clean_text(_analytics_extract_country_from_location(location), max_length=64)


def _analytics_resolve_continent_from_country(country_text: str) -> str:
    lookup_key = _analytics_build_geo_lookup_key(country_text)
    if not lookup_key:
        return ''
    return _ANALYTICS_COUNTRY_TO_CONTINENT.get(lookup_key, '')


def _analytics_resolve_visit_geo(ip_text: str):
    ip_value = str(ip_text or '').strip()
    if not ip_value:
        return {
            'ip': '',
            'location': '未知',
            'province': '',
            'country': '',
            'is_china': False,
        }
    location = resolve_ip_location(ip_value)
    province = _analytics_extract_china_province(location)
    is_china = bool(province)
    country = '中国' if is_china else _analytics_extract_country_from_location(location)
    return {
        'ip': ip_value,
        'location': location or '未知',
        'province': province,
        'country': country,
        'is_china': is_china,
    }


def _analytics_classify_source(referrer: str, utm_source: str, utm_medium: str, current_host: str) -> str:
    source = _analytics_clean_text(utm_source, max_length=64).lower()
    medium = _analytics_clean_text(utm_medium, max_length=64).lower()
    if source or medium:
        if 'social' in medium or source in {'facebook', 'instagram', 'linkedin', 'twitter', 'x', 'weibo', 'zhihu'}:
            return 'social'
        if medium in {'cpc', 'ppc', 'paid', 'paidsearch', 'sem'}:
            return 'paid'
        if medium in {'email', 'newsletter', 'edm'}:
            return 'email'
        if medium in {'affiliate'}:
            return 'affiliate'
        if medium in {'display', 'banner'}:
            return 'display'
        if medium in {'organic', 'seo'}:
            return 'search'
        return 'campaign'

    host = _analytics_extract_host(referrer)
    if not host:
        return 'direct'

    base_host = str(current_host or '').split(':', 1)[0].strip().lower()
    if base_host and (host == base_host or host.endswith(f'.{base_host}')):
        return 'internal'
    if any(keyword in host for keyword in SITE_ANALYTICS_SEARCH_HOST_KEYWORDS):
        return 'search'
    if any(keyword in host for keyword in SITE_ANALYTICS_SOCIAL_HOST_KEYWORDS):
        return 'social'
    return 'referral'


def _analytics_is_conversion_event(event_name: str) -> bool:
    name = _analytics_clean_text(event_name, max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
    if not name:
        return False
    if name in SITE_ANALYTICS_CONVERSION_EVENTS:
        return True
    if name.startswith('conversion_'):
        return True
    return False


def _analytics_is_conversion_page(page_path: str) -> bool:
    path = _analytics_normalize_path(page_path).lower()
    markers = ('/thank-you', '/thanks', '/success', '/submitted', '/done')
    return any(marker in path for marker in markers)


def _analytics_build_fallback_visitor_id(ip_text: str, user_agent: str) -> str:
    payload = f'{ip_text}|{user_agent}'.encode('utf-8', errors='ignore')
    return hashlib.sha256(payload).hexdigest()[:24]


def _analytics_to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _analytics_to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _analytics_day_key(ts: int) -> str:
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(BEIJING_TZ)
    return dt.strftime('%Y-%m-%d')


def _analytics_sanitize_event(raw_event, request_host: str, request_ua: str, request_ip: str):
    if not isinstance(raw_event, dict):
        return None

    event_type = _analytics_clean_text(raw_event.get('event_type') or raw_event.get('type'), max_length=24).lower()
    if event_type not in SITE_ANALYTICS_ALLOWED_EVENT_TYPES:
        return None

    page_path = _analytics_normalize_path(raw_event.get('page_path') or raw_event.get('path') or '/')
    if page_path.startswith('/admin'):
        return None

    page_title = _analytics_clean_text(raw_event.get('page_title') or raw_event.get('title'), max_length=120)
    referrer = _analytics_clean_text(raw_event.get('referrer'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    event_name = _analytics_clean_text(raw_event.get('event_name') or raw_event.get('name'), max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
    visitor_id = _analytics_clean_id(raw_event.get('visitor_id'), max_length=64)
    session_id = _analytics_clean_id(raw_event.get('session_id'), max_length=64)

    if not visitor_id:
        visitor_id = _analytics_build_fallback_visitor_id(request_ip, request_ua)
    if not session_id:
        session_id = f's_{visitor_id[:12]}'

    utm = raw_event.get('utm', {})
    utm_source = ''
    utm_medium = ''
    if isinstance(utm, dict):
        utm_source = _analytics_clean_text(utm.get('source'), max_length=64).lower()
        utm_medium = _analytics_clean_text(utm.get('medium'), max_length=64).lower()

    source = _analytics_classify_source(referrer, utm_source, utm_medium, request_host)
    device = _analytics_classify_device(request_ua)
    os_name = _analytics_classify_os(request_ua)
    geo = _analytics_resolve_visit_geo(request_ip)
    session_duration_sec = max(0, _analytics_to_int(raw_event.get('session_duration_sec'), default=0))
    scroll_depth = max(0, min(100, _analytics_to_int(raw_event.get('scroll_depth'), default=0)))
    event_value = _analytics_to_float(raw_event.get('event_value'), default=0.0)

    now_ts = int(time.time())
    return {
        'ts': now_ts,
        'day': _analytics_day_key(now_ts),
        'event_type': event_type,
        'event_name': event_name,
        'event_value': event_value,
        'page_path': page_path,
        'page_title': page_title,
        'referrer': referrer,
        'referrer_host': _analytics_extract_host(referrer),
        'source': source,
        'device': device,
        'os': os_name,
        'ip': geo.get('ip') or '',
        'location': geo.get('location') or '未知',
        'province': geo.get('province') or '',
        'country': geo.get('country') or '',
        'visitor_id': visitor_id,
        'session_id': session_id,
        'session_duration_sec': session_duration_sec,
        'scroll_depth': scroll_depth,
    }


def _append_site_analytics_records(records):
    safe_records = [item for item in (records or []) if isinstance(item, dict)]
    if not safe_records:
        return 0
    SITE_ANALYTICS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SITE_ANALYTICS_LOCK:
        with SITE_ANALYTICS_LOG_FILE.open('a', encoding='utf-8') as fp:
            for item in safe_records:
                fp.write(json.dumps(item, ensure_ascii=False, separators=(',', ':')) + '\n')
    return len(safe_records)


def _iter_site_analytics_records():
    if not SITE_ANALYTICS_LOG_FILE.exists():
        return []
    with SITE_ANALYTICS_LOCK:
        try:
            lines = SITE_ANALYTICS_LOG_FILE.read_text(encoding='utf-8').splitlines()
        except Exception:
            return []
    output = []
    for line in lines:
        row = str(line or '').strip()
        if not row:
            continue
        try:
            obj = json.loads(row)
        except Exception:
            continue
        if isinstance(obj, dict):
            output.append(obj)
    return output


def build_site_analytics_report(range_days=30):
    now_local = datetime.now(BEIJING_TZ)
    range_raw = str(range_days or '').strip().lower()
    is_last_24h = range_raw in {'24h', 'last24h', '24hour', '24hours'}

    bucket_keys = []
    buckets = {}
    range_days_value = 30
    range_key = '30d'
    range_label = '最近 30 天'

    if is_last_24h:
        range_days_value = 1
        range_key = '24h'
        range_label = '最近24小时'
        current_hour = now_local.replace(minute=0, second=0, microsecond=0)
        start_hour = current_hour - timedelta(hours=23)
        since_ts = int(start_hour.astimezone(timezone.utc).timestamp())
        for idx in range(24):
            point = start_hour + timedelta(hours=idx)
            bucket_key = point.strftime('%Y-%m-%d %H:00')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = {
                'pageviews': 0,
                'conversions': 0,
                'events': 0,
                'visitors': set(),
                'sessions': set(),
            }

        def resolve_bucket_key(ts: int) -> str:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(BEIJING_TZ)
            return dt.strftime('%Y-%m-%d %H:00')

    else:
        try:
            days = int(range_days)
        except Exception:
            days = 30
        if days not in (7, 30, 90, 180):
            days = 30
        range_days_value = days
        range_key = f'{days}d'
        range_label = f'最近 {days} 天'

        start_date = now_local.date() - timedelta(days=days - 1)
        start_dt_local = datetime.combine(start_date, datetime.min.time(), tzinfo=BEIJING_TZ)
        since_ts = int(start_dt_local.astimezone(timezone.utc).timestamp())
        for idx in range(days):
            d = start_date + timedelta(days=idx)
            bucket_key = d.strftime('%Y-%m-%d')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = {
                'pageviews': 0,
                'conversions': 0,
                'events': 0,
                'visitors': set(),
                'sessions': set(),
            }

        def resolve_bucket_key(ts: int) -> str:
            return _analytics_day_key(ts)

    sessions = {}
    pages = {}
    event_counter = {}
    visitor_set = set()
    recent_events = []

    records = _iter_site_analytics_records()
    for item in records:
        ts = _analytics_to_int(item.get('ts'), default=0)
        if ts < since_ts:
            continue
        bucket_key = resolve_bucket_key(ts)
        if bucket_key not in buckets:
            continue

        event_type = _analytics_clean_text(item.get('event_type'), max_length=24).lower()
        event_name = _analytics_clean_text(item.get('event_name'), max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
        page_path = _analytics_normalize_path(item.get('page_path') or '/')
        page_title = _analytics_clean_text(item.get('page_title'), max_length=120)
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_extract_record_province(item)
        country = _analytics_extract_record_country(item)
        ip_addr = _analytics_clean_text(item.get('ip'), max_length=45)
        visitor_id = _analytics_clean_id(item.get('visitor_id'), max_length=64)
        session_id = _analytics_clean_id(item.get('session_id'), max_length=64)
        if not visitor_id:
            visitor_id = 'anonymous'
        if not session_id:
            session_id = f'anon_{visitor_id}_{_analytics_day_key(ts)}'

        visitor_set.add(visitor_id)
        buckets[bucket_key]['visitors'].add(visitor_id)
        buckets[bucket_key]['sessions'].add(session_id)

        sess = sessions.get(session_id)
        if not sess:
            sess = {
                'session_id': session_id,
                'visitor_id': visitor_id,
                'first_ts': ts,
                'last_ts': ts,
                'pageviews': 0,
                'conversions': 0,
                'reported_duration_sec': 0,
                'source': source,
                'device': device,
                'os': os_name,
                'province': province,
                'country': country,
                'ip': ip_addr,
            }
            sessions[session_id] = sess
        else:
            sess['first_ts'] = min(sess['first_ts'], ts)
            sess['last_ts'] = max(sess['last_ts'], ts)
            if sess.get('source') in {'', 'direct', 'internal', 'unknown'} and source not in {'', 'unknown'}:
                sess['source'] = source
            if sess.get('device') in {'', 'unknown'} and device not in {'', 'unknown'}:
                sess['device'] = device
            if sess.get('os') in {'', 'unknown'} and os_name not in {'', 'unknown'}:
                sess['os'] = os_name
            if not sess.get('province') and province:
                sess['province'] = province
            if not sess.get('country') and country:
                sess['country'] = country
            if not sess.get('ip') and ip_addr:
                sess['ip'] = ip_addr

        if event_type == 'pageview':
            sess['pageviews'] += 1
            buckets[bucket_key]['pageviews'] += 1

            page_stats = pages.get(page_path)
            if not page_stats:
                page_stats = {
                    'path': page_path,
                    'title': page_title,
                    'pageviews': 0,
                    'visitors': set(),
                    'sessions': set(),
                }
                pages[page_path] = page_stats
            page_stats['pageviews'] += 1
            page_stats['visitors'].add(visitor_id)
            page_stats['sessions'].add(session_id)
            if not page_stats.get('title') and page_title:
                page_stats['title'] = page_title

            if _analytics_is_conversion_page(page_path):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'event':
            buckets[bucket_key]['events'] += 1
            if event_name:
                event_counter[event_name] = event_counter.get(event_name, 0) + 1
            if _analytics_is_conversion_event(event_name):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'session_end':
            reported_duration = max(0, _analytics_to_int(item.get('session_duration_sec'), default=0))
            sess['reported_duration_sec'] = max(sess.get('reported_duration_sec', 0), reported_duration)

        event_label = event_name or event_type or 'event'
        recent_events.append({
            'timestamp': datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S'),
            'type': event_type or 'event',
            'name': event_label,
            'path': page_path,
            'source': source or '-',
            'device': device or '-',
        })

    recent_events = recent_events[-25:]

    tracked_sessions = [item for item in sessions.values() if int(item.get('pageviews') or 0) > 0]
    total_sessions = len(tracked_sessions)
    total_pageviews = sum(int(item.get('pageviews') or 0) for item in tracked_sessions)
    total_conversions = sum(int(item.get('conversions') or 0) for item in tracked_sessions)
    conversion_sessions = sum(1 for item in tracked_sessions if int(item.get('conversions') or 0) > 0)
    bounce_sessions = sum(1 for item in tracked_sessions if int(item.get('pageviews') or 0) <= 1)

    total_duration = 0
    for item in tracked_sessions:
        observed_duration = max(0, int(item.get('last_ts') or 0) - int(item.get('first_ts') or 0))
        reported_duration = max(0, int(item.get('reported_duration_sec') or 0))
        duration_sec = max(observed_duration, reported_duration)
        duration_sec = min(duration_sec, 12 * 3600)
        total_duration += duration_sec

    avg_session_duration_sec = (total_duration / total_sessions) if total_sessions else 0.0
    bounce_rate = (bounce_sessions * 100.0 / total_sessions) if total_sessions else 0.0
    conversion_rate = (conversion_sessions * 100.0 / total_sessions) if total_sessions else 0.0

    source_counter = {}
    device_counter = {}
    os_counter = {}
    province_counter = {}
    continent_counter = {}
    for item in tracked_sessions:
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_clean_text(item.get('province'), max_length=32)
        country = _analytics_clean_text(item.get('country'), max_length=64)
        source_counter[source] = source_counter.get(source, 0) + 1
        device_counter[device] = device_counter.get(device, 0) + 1
        os_counter[os_name] = os_counter.get(os_name, 0) + 1
        if province:
            province_counter[province] = province_counter.get(province, 0) + 1
        continent_key = _analytics_resolve_continent_from_country(country)
        if country and country != '中国' and continent_key:
            continent_counter[continent_key] = continent_counter.get(continent_key, 0) + 1

    source_rows = [
        {
            'source': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in source_counter.items()
    ]
    source_rows.sort(key=lambda item: item['sessions'], reverse=True)

    device_rows = [
        {
            'device': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in device_counter.items()
    ]
    device_rows.sort(key=lambda item: item['sessions'], reverse=True)

    os_rows = [
        {
            'os': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in os_counter.items()
    ]
    os_rows.sort(key=lambda item: item['sessions'], reverse=True)

    province_rows = [
        {
            'province': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in province_counter.items()
    ]
    province_rows.sort(key=lambda item: item['sessions'], reverse=True)

    overseas_sessions = sum(continent_counter.values())
    continent_rows = [
        {
            'continent_key': key,
            'continent': _ANALYTICS_CONTINENT_LABELS.get(key, key),
            'sessions': value,
            'ratio': round((value * 100.0 / overseas_sessions), 2) if overseas_sessions else 0.0,
        }
        for key, value in continent_counter.items()
    ]
    continent_rows.sort(key=lambda item: item['sessions'], reverse=True)

    china_map_data = [
        {
            'name': item['province'],
            'value': item['sessions'],
        }
        for item in province_rows
    ]

    top_pages = []
    for path_key, stats in pages.items():
        top_pages.append({
            'path': path_key,
            'title': stats.get('title') or '',
            'pageviews': int(stats.get('pageviews') or 0),
            'unique_visitors': len(stats.get('visitors', set())),
            'sessions': len(stats.get('sessions', set())),
        })
    top_pages.sort(key=lambda item: item['pageviews'], reverse=True)
    top_pages = top_pages[:12]

    top_events = [{'name': name, 'count': count} for name, count in event_counter.items()]
    top_events.sort(key=lambda item: item['count'], reverse=True)
    top_events = top_events[:12]

    trend = []
    for bucket_key in bucket_keys:
        row = buckets.get(bucket_key, {})
        trend.append({
            'date': bucket_key,
            'pageviews': int(row.get('pageviews') or 0),
            'unique_visitors': len(row.get('visitors', set())),
            'sessions': len(row.get('sessions', set())),
            'conversions': int(row.get('conversions') or 0),
            'events': int(row.get('events') or 0),
        })

    return {
        'range_days': range_days_value,
        'range_key': range_key,
        'range_label': range_label,
        'generated_at': datetime.now(BEIJING_TZ).isoformat(timespec='seconds'),
        'summary': {
            'pageviews': total_pageviews,
            'unique_visitors': len(visitor_set),
            'sessions': total_sessions,
            'avg_session_duration_sec': round(avg_session_duration_sec, 2),
            'bounce_rate': round(bounce_rate, 2),
            'conversion_events': total_conversions,
            'conversion_sessions': conversion_sessions,
            'conversion_rate': round(conversion_rate, 2),
        },
        'source_breakdown': source_rows,
        'device_breakdown': device_rows,
        'os_breakdown': os_rows,
        'province_breakdown': province_rows,
        'continent_breakdown': continent_rows,
        'china_map_data': china_map_data,
        'top_pages': top_pages,
        'top_events': top_events,
        'trend': trend,
        'recent_events': recent_events,
    }


def load_admin_login_logs():
    """Load admin login logs from file."""
    default_data = {'items': []}
    if ADMIN_LOGIN_LOG_FILE.exists():
        try:
            data = json.loads(ADMIN_LOGIN_LOG_FILE.read_text(encoding='utf-8'))
            items = data.get('items', [])
            if not isinstance(items, list):
                items = []
            normalized = [item for item in items if isinstance(item, dict)]
            return normalized
        except Exception:
            pass
    ADMIN_LOGIN_LOG_FILE.write_text(
        json.dumps(default_data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return []


def save_admin_login_logs(items):
    """Persist admin login logs to file."""
    safe_items = [item for item in (items or []) if isinstance(item, dict)]
    ADMIN_LOGIN_LOG_FILE.write_text(
        json.dumps({'items': safe_items}, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def _build_location_text(*parts):
    cleaned = []
    seen = set()
    for value in parts:
        text = str(value or '').strip()
        if not text or text in {'-', '--'}:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    if not cleaned:
        return '未知'
    return ' / '.join(cleaned)


def _http_get_json(url: str, timeout: float = 2.5):
    headers = {
        'User-Agent': 'YX-Website-Admin/1.0',
        'Accept': 'application/json,text/plain,*/*',
    }

    if REQUESTS_SUPPORT:
        try:
            res = requests.get(url, timeout=timeout, headers=headers)
            if res.ok:
                return res.json()
        except Exception:
            pass

    if HTTPX_SUPPORT:
        try:
            res = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True)
            if 200 <= res.status_code < 300:
                return res.json()
        except Exception:
            pass

    return None


def _fetch_ip_location_from_ipwhois(ip: str):
    data = _http_get_json(f'https://ipwho.is/{ip}?lang=zh', timeout=2.6)
    if not isinstance(data, dict):
        return ''
    if data.get('success') is False:
        return ''
    connection = data.get('connection') if isinstance(data.get('connection'), dict) else {}
    return _build_location_text(
        data.get('country') or data.get('country_code'),
        data.get('region'),
        data.get('city'),
        connection.get('isp') or connection.get('org'),
    )


def _fetch_ip_location_from_ipapi_co(ip: str):
    data = _http_get_json(f'https://ipapi.co/{ip}/json/', timeout=2.6)
    if not isinstance(data, dict):
        return ''
    if data.get('error') is True:
        return ''
    return _build_location_text(
        data.get('country_name') or data.get('country'),
        data.get('region'),
        data.get('city'),
        data.get('org') or data.get('asn'),
    )


def _fetch_ip_location_from_ip_api(ip: str):
    data = _http_get_json(
        f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp',
        timeout=2.6
    )
    if not isinstance(data, dict):
        return ''
    if data.get('status') != 'success':
        return ''
    return _build_location_text(
        data.get('country'),
        data.get('regionName'),
        data.get('city'),
        data.get('isp'),
    )


def fetch_ip_location(ip):
    """Resolve geo location for a public IP by external service."""
    ip_text = str(ip or '').strip()
    if not ip_text:
        return '未知'

    for resolver in (
        _fetch_ip_location_from_ipwhois,
        _fetch_ip_location_from_ipapi_co,
        _fetch_ip_location_from_ip_api,
    ):
        try:
            location = str(resolver(ip_text) or '').strip()
        except Exception:
            location = ''
        if location and location != '未知':
            return location
    return '未知'


def _is_unknown_location(value: str) -> bool:
    text = str(value or '').strip().lower()
    return not text or text in {'未知', 'unknown', 'n/a', '-'}


def resolve_ip_location(ip):
    """Get a readable location text for IP."""
    ip_text = str(ip or '').strip()
    if not ip_text:
        return '未知'

    now_ts = int(time.time())
    with ADMIN_IP_LOCATION_LOCK:
        cached = ADMIN_IP_LOCATION_CACHE.get(ip_text)
        if isinstance(cached, dict):
            cached_location = str(cached.get('location') or '').strip()
            expires_at = int(cached.get('expires_at', 0) or 0)
            if cached_location and expires_at > now_ts:
                return cached_location
        elif isinstance(cached, str) and cached.strip() and not _is_unknown_location(cached):
            # Backward compatibility for legacy in-memory cache format.
            return cached.strip()

    location = '未知'
    try:
        ip_obj = ipaddress.ip_address(ip_text)
        if ip_obj.is_loopback:
            location = '本机回环地址'
        elif ip_obj.is_private:
            location = '内网地址'
        elif ip_obj.is_unspecified:
            location = '未指定地址'
        elif ip_obj.is_reserved:
            location = '保留地址'
        elif ip_obj.is_multicast:
            location = '组播地址'
        else:
            location = fetch_ip_location(ip_text)
    except ValueError:
        location = '未知'

    ttl = ADMIN_IP_LOCATION_CACHE_TTL_UNKNOWN if _is_unknown_location(location) else ADMIN_IP_LOCATION_CACHE_TTL_SUCCESS
    cache_item = {
        'location': str(location or '未知').strip() or '未知',
        'expires_at': now_ts + ttl,
    }

    with ADMIN_IP_LOCATION_LOCK:
        if len(ADMIN_IP_LOCATION_CACHE) >= ADMIN_IP_LOCATION_CACHE_MAX:
            # Prefer clearing expired entries first; if still large then reset.
            expired_keys = []
            for key, value in ADMIN_IP_LOCATION_CACHE.items():
                if isinstance(value, dict):
                    if int(value.get('expires_at', 0) or 0) <= now_ts:
                        expired_keys.append(key)
            for key in expired_keys:
                ADMIN_IP_LOCATION_CACHE.pop(key, None)
            if len(ADMIN_IP_LOCATION_CACHE) >= ADMIN_IP_LOCATION_CACHE_MAX:
                ADMIN_IP_LOCATION_CACHE.clear()
        ADMIN_IP_LOCATION_CACHE[ip_text] = cache_item
    return cache_item['location']


def now_beijing_iso():
    """Current datetime string in Asia/Shanghai timezone."""
    return datetime.now(BEIJING_TZ).isoformat(timespec='seconds')


def append_admin_login_log(operation, success, username='', detail=''):
    """Append one immutable admin login-operation log record."""
    ip = get_client_ip()
    log_item = {
        'id': uuid.uuid4().hex,
        'ip': ip,
        'location': resolve_ip_location(ip),
        'success': bool(success),
        'timestamp': now_beijing_iso(),
        'operation': str(operation or '后台操作').strip(),
        'username': str(username or '').strip(),
        'detail': str(detail or '').strip()
    }

    with ADMIN_LOGIN_LOG_LOCK:
        items = load_admin_login_logs()
        items.append(log_item)
        save_admin_login_logs(items)


def check_rate_limit(ip: str) -> bool:
    """Check if IP is within rate limit. Returns True if allowed."""
    now = time.time()
    
    # Load rate limits
    rate_limits = {}
    if RATE_LIMIT_FILE.exists():
        try:
            rate_limits = json.loads(RATE_LIMIT_FILE.read_text(encoding='utf-8'))
        except:
            rate_limits = {}
    
    # Clean old entries and check current IP
    ip_hash = hashlib.md5(ip.encode()).hexdigest()
    if ip_hash in rate_limits:
        # Filter entries within the window
        entries = [t for t in rate_limits[ip_hash] if now - t < RATE_LIMIT_WINDOW]
        rate_limits[ip_hash] = entries
        
        if len(entries) >= RATE_LIMIT_MAX:
            return False
    else:
        rate_limits[ip_hash] = []
    
    # Add new entry
    rate_limits[ip_hash].append(now)
    
    # Save rate limits
    RATE_LIMIT_FILE.write_text(json.dumps(rate_limits), encoding='utf-8')
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

        # Backward compatibility for old sessions created before RBAC fields exist.
        if 'admin_is_super_admin' not in session and 'admin_permissions' not in session:
            session['admin_is_super_admin'] = True
            session['admin_permissions'] = list(ADMIN_PERMISSION_KEYS)

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
def normalize_remote_video_url(raw_url: str) -> str:
    """Normalize remote video URL for allowlist checks."""
    if not raw_url:
        return ''
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return ''
    if parsed.scheme not in {'http', 'https'}:
        return ''
    if not parsed.netloc:
        return ''
    # Remove fragment only; keep query params because some CDNs require them.
    return parsed._replace(fragment='').geturl()


def _collect_remote_urls_from_items(items) -> set:
    allowed = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = normalize_remote_video_url(item.get('url', ''))
        ok = False
        if url:
            ok, _, url = validate_safe_remote_fetch_url(url)
        if url and ok:
            allowed.add(url)
    return allowed


def get_allowed_remote_media_urls() -> set:
    """Allow proxying only URLs configured in H2-home and home-hero media lists."""
    allowed = set()
    h2_config = get_h2_home_config()
    hero_config = get_hero_config(HERO_CONFIG_FILE, sanitize_public_media_url)
    allowed.update(_collect_remote_urls_from_items(h2_config.get('items', [])))
    allowed.update(_collect_remote_urls_from_items(hero_config.get('items', [])))
    return allowed


@app.route('/api/video-proxy')
def proxy_video():
    """Same-origin media proxy for cross-origin CDN sources."""
    raw_url = (request.args.get('url') or '').strip()
    target_url = normalize_remote_video_url(raw_url)
    if not target_url:
        return jsonify({'success': False, 'message': '媒体地址不合法'}), 400

    allowed_urls = get_allowed_remote_media_urls()
    if target_url not in allowed_urls:
        return jsonify({'success': False, 'message': '该视频地址未授权代理'}), 403
    ok, reason, safe_target_url = validate_safe_remote_fetch_url(target_url)
    if not ok:
        return jsonify({'success': False, 'message': reason or '媒体地址不安全'}), 400

    if not REQUESTS_SUPPORT:
        return jsonify({'success': False, 'message': '服务器缺少 requests 依赖，无法代理媒体'}), 500

    upstream_headers = {}
    range_header = request.headers.get('Range')
    if range_header:
        upstream_headers['Range'] = range_header

    try:
        upstream = requests.get(
            safe_target_url,
            headers=upstream_headers,
            stream=True,
            timeout=(8, 120),
            allow_redirects=False
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'代理媒体失败: {e}'}), 502

    passthrough_headers = [
        'Content-Type', 'Content-Length', 'Content-Range',
        'Accept-Ranges', 'ETag', 'Last-Modified', 'Cache-Control'
    ]
    response_headers = {}
    for key in passthrough_headers:
        value = upstream.headers.get(key)
        if value:
            response_headers[key] = value
    if not response_headers.get('Cache-Control'):
        response_headers['Cache-Control'] = 'public, max-age=86400'
    response_headers['Access-Control-Allow-Origin'] = '*'

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(stream_with_context(generate()), status=upstream.status_code, headers=response_headers)
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
        image = sanitize_public_media_url(parser.first_img, enforce_remote_public=False)

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
    site_root = Path(__file__).parent.resolve()
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

    site_root = Path(__file__).parent.resolve()
    candidate = (site_root / normalized).resolve()
    try:
        candidate.relative_to(site_root)
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
        re.I
    )
    if meta_match:
        return meta_match.group(1).strip()

    hero_match = re.search(
        r'background-image\s*:\s*(?:linear-gradient\([^;]*?\)\s*,\s*)?url\([\'"]?([^\'")]+)[\'"]?\)',
        content,
        re.I | re.S
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
    return raw[: max(0, limit - 1)].rstrip(' ，。；、,.;') + '…'


def extract_generic_page_preview_desc(filepath):
    """Extract a short best-effort summary from a local HTML page."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''

    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        content,
        re.I
    )
    if meta_match:
        return normalize_nav_preview_text(meta_match.group(1), limit=92)

    p_match = re.search(r'<p\b[^>]*>(.*?)</p>', content, re.I | re.S)
    if not p_match:
        return ''

    text = re.sub(r'<[^>]+>', ' ', p_match.group(1))
    return normalize_nav_preview_text(text, limit=92)


def infer_nav_target_preview(url):
    """Infer title, preview image and short summary for a nav target."""
    filepath = resolve_local_nav_target_path(url)
    if not filepath:
        return {'title': '', 'image': '', 'desc': ''}

    site_root = Path(__file__).parent.resolve()
    try:
        relative_path = filepath.resolve().relative_to(site_root).as_posix()
    except ValueError:
        relative_path = ''

    preview = None
    if relative_path.startswith('pages/solutions/'):
        preview = extract_solution_meta_from_html(filepath)
    elif relative_path.startswith('pages/gassensing/cases/'):
        preview = extract_case_meta_from_html(filepath)
    elif (
        relative_path.startswith('pages/gassensing/')
        or relative_path.startswith('pages/customization/')
        or relative_path.startswith('pages/biosensing/')
    ):
        preview = extract_product_meta_from_html(filepath)

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
        'image': normalize_scanned_image_path(image, get_web_dir_prefix_for_filepath(filepath)),
        'desc': normalize_nav_preview_text(desc, limit=92)
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


# ============ Product Menu Settings API ============

PRODUCT_SETTINGS_FILE = DATA_DIR / 'product_settings.json'
PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'product_industry_filters.json'
BIO_PRODUCT_SETTINGS_FILE = DATA_DIR / 'bio_product_settings.json'
BIO_PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'bio_product_industry_filters.json'

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


def normalize_filter_key(raw_key, fallback_index=0):
    """Normalize filter key to lowercase ascii slug."""
    key = (raw_key or '').strip().lower()
    key = re.sub(r'[^a-z0-9_-]+', '-', key)
    key = re.sub(r'-{2,}', '-', key).strip('-')
    if not key:
        key = f'industry-{fallback_index + 1}'
    return key


def build_industry_filter_preview_map():
    """Pick the first visible product image for each industry filter."""
    preview_map = {}
    try:
        products = get_products_with_settings_data()
    except Exception:
        return preview_map

    for product in products:
        if not isinstance(product, dict) or product.get('hidden'):
            continue
        image = str((product.get('cardImage') or product.get('image') or '')).strip()
        if not image:
            continue
        categories = product.get('industryCategories', [])
        if not isinstance(categories, list) or not categories:
            categories = infer_default_industry_categories(product)
        for raw_key in categories:
            key = normalize_filter_key(raw_key)
            if key and key not in preview_map:
                preview_map[key] = image
    return preview_map


def get_industry_filters():
    """Load industry filters for all-products page."""
    categories = []
    if PRODUCT_INDUSTRY_FILTERS_FILE.exists():
        try:
            data = json.loads(PRODUCT_INDUSTRY_FILTERS_FILE.read_text(encoding='utf-8'))
            categories = data.get('categories', [])
        except Exception:
            categories = []

    cleaned = []
    used = set()
    for idx, item in enumerate(categories):
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        key = normalize_filter_key(item.get('key'), idx)
        if key in used:
            key = normalize_filter_key(f'{key}-{idx + 1}', idx)
        used.add(key)
        cleaned.append({'key': key, 'name': name})

    if not cleaned:
        cleaned = [dict(item) for item in DEFAULT_INDUSTRY_FILTERS]

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
    """Persist industry filters and clean stale product mappings."""
    raw_categories = data.get('categories', []) if isinstance(data, dict) else []
    cleaned = []
    used = set()
    for idx, item in enumerate(raw_categories):
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        key = normalize_filter_key(item.get('key'), idx)
        if key in used:
            key = normalize_filter_key(f'{key}-{idx + 1}', idx)
        used.add(key)
        cleaned.append({'key': key, 'name': name})

    if not cleaned:
        cleaned = [dict(item) for item in DEFAULT_INDUSTRY_FILTERS]

    saved = {'categories': cleaned}
    PRODUCT_INDUSTRY_FILTERS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    valid_keys = {item['key'] for item in cleaned}
    settings = get_product_settings()
    changed = False
    for product_id, cfg in settings.items():
        if not isinstance(cfg, dict):
            continue
        original = cfg.get('industryCategories', [])
        if not isinstance(original, list):
            continue
        filtered = [k for k in original if k in valid_keys]
        if filtered != original:
            cfg['industryCategories'] = filtered
            changed = True
    if changed:
        save_product_settings(settings)

    return saved


def infer_default_industry_categories(product):
    """Infer initial industry categories for products with no custom mapping."""
    pid = str(product.get('id', ''))
    name = str(product.get('name', ''))
    desc = str(product.get('description', ''))
    text = f'{name} {desc}'
    categories = []

    if pid.startswith('../customization/'):
        categories.append('custom')
    else:
        categories.append('hydrogen')

    if any(x in text for x in ['电力', '变电', '输电', '发电']):
        categories.append('power')
    if any(x in text for x in ['检漏', '泄漏', '漏气', '真空']):
        categories.append('leak')
    if any(x in text for x in ['科研', '实验室', '微纳', '开发', '产学研']):
        categories.append('research')
    if product.get('category') == 'service':
        categories.append('research')

    # keep order, remove duplicates
    deduped = []
    for key in categories:
        if key not in deduped:
            deduped.append(key)
    return deduped

def get_product_settings():
    """Load product settings (custom names, new badges)."""
    if PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return sanitize_public_product_settings(raw)
        except:
            pass
    return {}


def get_bio_product_settings():
    """Load biosensing product settings (custom names, new badges)."""
    if BIO_PRODUCT_SETTINGS_FILE.exists():
        try:
            raw = json.loads(BIO_PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
            return sanitize_public_product_settings(raw)
        except Exception:
            pass
    return {}


def save_product_settings(settings):
    """Save product settings."""
    cleaned = sanitize_public_product_settings(settings)
    PRODUCT_SETTINGS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')


def save_bio_product_settings(settings):
    """Save biosensing product settings."""
    cleaned = sanitize_public_product_settings(settings)
    BIO_PRODUCT_SETTINGS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')


def _normalize_related_news_links(value):
    """Normalize product related news setting to max 2 unique links."""
    if isinstance(value, list):
        raw_list = value
    elif isinstance(value, str):
        raw_list = [x.strip() for x in re.split(r'[\n,;]+', value) if x and x.strip()]
    else:
        raw_list = []

    cleaned = []
    seen = set()
    for item in raw_list:
        link = sanitize_public_link_url(item or '')
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


@app.route('/api/products/settings', methods=['GET'])
def get_product_settings_api():
    """Get product menu settings."""
    return jsonify(get_product_settings())


@app.route('/api/bio-products/settings', methods=['GET'])
def get_bio_product_settings_api():
    """Get biosensing product menu settings."""
    return jsonify(get_bio_product_settings())


@app.route('/api/products/settings', methods=['POST'])
@login_required
def update_product_settings_api():
    """Update product menu settings."""
    data = request.json or {}
    
    settings = get_product_settings()
    
    product_id = data.get('id')
    if not product_id:
        return jsonify({'success': False, 'message': '缺少产品ID'}), 400
    
    if product_id not in settings:
        settings[product_id] = {}
    
    if 'displayName' in data:
        settings[product_id]['displayName'] = sanitize_public_text(data['displayName'], max_length=120)
    
    if 'isNew' in data:
        settings[product_id]['isNew'] = bool(data['isNew'])
    
    if 'hidden' in data:
        settings[product_id]['hidden'] = bool(data['hidden'])
    
    if 'sortOrder' in data:
        settings[product_id]['sortOrder'] = int(data['sortOrder'])

    if 'cardTitle' in data:
        settings[product_id]['cardTitle'] = sanitize_public_text(data['cardTitle'], max_length=120)

    if 'cardImage' in data:
        settings[product_id]['cardImage'] = sanitize_public_media_url(
            data['cardImage'],
            enforce_remote_public=False
        )

    if 'cardSummary' in data:
        settings[product_id]['cardSummary'] = sanitize_public_text(data['cardSummary'], max_length=220)

    if 'categories' in data:
        # 支持多分类数组
        settings[product_id]['categories'] = list(data['categories']) if isinstance(data['categories'], list) else [data['categories']]

    if 'industryCategories' in data:
        # 领域分类（all-products 页面筛选）
        settings[product_id]['industryCategories'] = list(data['industryCategories']) if isinstance(data['industryCategories'], list) else [data['industryCategories']]

    if 'relatedNews' in data:
        settings[product_id]['relatedNews'] = _normalize_related_news_links(data['relatedNews'])
    
    save_product_settings(settings)
    return jsonify({'success': True, 'settings': settings})


@app.route('/api/bio-products/settings', methods=['POST'])
@login_required
def update_bio_product_settings_api():
    """Update biosensing product settings."""
    data = request.json or {}

    settings = get_bio_product_settings()

    product_id = data.get('id')
    if not product_id:
        return jsonify({'success': False, 'message': '缺少产品ID'}), 400

    if product_id not in settings:
        settings[product_id] = {}

    if 'displayName' in data:
        settings[product_id]['displayName'] = sanitize_public_text(data['displayName'], max_length=120)

    if 'isNew' in data:
        settings[product_id]['isNew'] = bool(data['isNew'])

    if 'hidden' in data:
        settings[product_id]['hidden'] = bool(data['hidden'])

    if 'sortOrder' in data:
        settings[product_id]['sortOrder'] = int(data['sortOrder'])

    if 'cardTitle' in data:
        settings[product_id]['cardTitle'] = sanitize_public_text(data['cardTitle'], max_length=120)

    if 'cardImage' in data:
        settings[product_id]['cardImage'] = sanitize_public_media_url(
            data['cardImage'],
            enforce_remote_public=False
        )

    if 'cardSummary' in data:
        settings[product_id]['cardSummary'] = sanitize_public_text(data['cardSummary'], max_length=220)

    if 'categories' in data:
        settings[product_id]['categories'] = list(data['categories']) if isinstance(data['categories'], list) else [data['categories']]

    if 'industryCategories' in data:
        settings[product_id]['industryCategories'] = list(data['industryCategories']) if isinstance(data['industryCategories'], list) else [data['industryCategories']]

    if 'relatedNews' in data:
        settings[product_id]['relatedNews'] = _normalize_related_news_links(data['relatedNews'])

    save_bio_product_settings(settings)
    return jsonify({'success': True, 'settings': settings})


@app.route('/api/products/settings/sort', methods=['POST'])
@login_required
def update_product_sort_order():
    """Batch update product sort order."""
    data = request.json or {}
    order = data.get('order', [])  # List of product IDs in desired order
    
    if not order:
        return jsonify({'success': False, 'message': '缺少排序数据'}), 400
    
    settings = get_product_settings()
    
    for idx, product_id in enumerate(order):
        if product_id not in settings:
            settings[product_id] = {}
        settings[product_id]['sortOrder'] = idx
    
    save_product_settings(settings)
    return jsonify({'success': True, 'message': f'已更新 {len(order)} 个产品的排序'})


@app.route('/api/bio-products/settings/sort', methods=['POST'])
@login_required
def update_bio_product_sort_order():
    """Batch update biosensing product sort order."""
    data = request.json or {}
    order = data.get('order', [])

    if not order:
        return jsonify({'success': False, 'message': '缺少排序数据'}), 400

    settings = get_bio_product_settings()

    for idx, product_id in enumerate(order):
        if product_id not in settings:
            settings[product_id] = {}
        settings[product_id]['sortOrder'] = idx

    save_bio_product_settings(settings)
    return jsonify({'success': True, 'message': f'已更新 {len(order)} 个产品的排序'})


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


@app.route('/api/products/with-settings')
def get_products_with_settings():
    """Get products with merged settings."""
    products = get_products_with_settings_data()
    return jsonify({'products': products, 'count': len(products)})


def infer_default_bio_industry_categories(product):
    """Infer default biosensing industry categories for products with no custom mapping."""
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


def get_products_with_settings_data():
    """Collect products with merged settings."""
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
    return products


def get_gassensing_products_with_settings():
    """Only products from gassensing directory."""
    products = [p for p in get_products_with_settings_data() if not str(p.get('id', '')).startswith('../')]
    return products


def build_bio_industry_filter_preview_map():
    """Pick the first visible biosensing product image for each industry filter."""
    preview_map = {}
    try:
        products = get_biosensing_products_with_settings_data()
    except Exception:
        return preview_map

    for product in products:
        if not isinstance(product, dict) or product.get('hidden'):
            continue
        image = str((product.get('cardImage') or product.get('image') or '')).strip()
        if not image:
            continue
        categories = product.get('industryCategories', [])
        if not isinstance(categories, list) or not categories:
            categories = infer_default_bio_industry_categories(product)
        for raw_key in categories:
            key = normalize_filter_key(raw_key)
            if key and key not in preview_map:
                preview_map[key] = image
    return preview_map


def get_bio_industry_filters():
    """Load biosensing industry filters for biosensing index page."""
    categories = []
    if BIO_PRODUCT_INDUSTRY_FILTERS_FILE.exists():
        try:
            data = json.loads(BIO_PRODUCT_INDUSTRY_FILTERS_FILE.read_text(encoding='utf-8'))
            categories = data.get('categories', [])
        except Exception:
            categories = []

    cleaned = []
    used = set()
    for idx, item in enumerate(categories):
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        key = normalize_filter_key(item.get('key'), idx)
        if key in used:
            key = normalize_filter_key(f'{key}-{idx + 1}', idx)
        used.add(key)
        cleaned.append({'key': key, 'name': name})

    if not cleaned:
        cleaned = [dict(item) for item in DEFAULT_BIO_INDUSTRY_FILTERS]
    elif not any(item.get('key') == 'sensor' for item in cleaned):
        cleaned.insert(0, {'key': 'sensor', 'name': '生物传感产品'})

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
    """Persist biosensing industry filters and clean stale product mappings."""
    raw_categories = data.get('categories', []) if isinstance(data, dict) else []
    cleaned = []
    used = set()
    for idx, item in enumerate(raw_categories):
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        key = normalize_filter_key(item.get('key'), idx)
        if key in used:
            key = normalize_filter_key(f'{key}-{idx + 1}', idx)
        used.add(key)
        cleaned.append({'key': key, 'name': name})

    if not cleaned:
        cleaned = [dict(item) for item in DEFAULT_BIO_INDUSTRY_FILTERS]
    elif not any(item.get('key') == 'sensor' for item in cleaned):
        cleaned.insert(0, {'key': 'sensor', 'name': '生物传感产品'})

    saved = {'categories': cleaned}
    BIO_PRODUCT_INDUSTRY_FILTERS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2),
        encoding='utf-8'
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
        filtered = [k for k in original if k in valid_keys]
        if filtered != original:
            cfg['industryCategories'] = filtered
            changed = True
    if changed:
        save_bio_product_settings(settings)

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
        img_match = re.search(r'<img\\s+[^>]*src=\"([^\"]+)\"', content)
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


# ============ Mega Menu Recommendations API ============

RECOMMENDATIONS_FILE = DATA_DIR / 'recommendations.json'
MEASUREMENT_TARGETS_FILE = DATA_DIR / 'measurement_targets.json'
NAV_INDUSTRY_CATEGORIES_FILE = DATA_DIR / 'nav_industry_categories.json'


def is_safe_recommendation_url(url: str) -> bool:
    """Allow relative paths and http(s) links; block script/data protocols."""
    u = (url or '').strip().lower()
    if not u:
        return False
    if u.startswith('javascript:') or u.startswith('data:'):
        return False
    if u.startswith('http://') or u.startswith('https://'):
        return True
    if u.startswith('/') or u.startswith('./') or u.startswith('../'):
        return True
    # allow plain relative files like "pages/gassensing/xxx.html"
    if '://' in u:
        return False
    if re.match(r'^[a-z0-9._/-]+\.[a-z0-9]+([?#].*)?$', u):
        return True
    return False


def normalize_recommendation_items(items):
    """Normalize recommendation item list and keep only valid entries."""
    normalized = []
    if not isinstance(items, list):
        return normalized

    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        url = (item.get('url') or '').strip()
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
            {'name': '氢失踪', 'url': '../measurement/measurement-hydrogen-tracking.html'},
            {'name': '微量水', 'url': '../measurement/measurement-humidity.html'},
            {'name': '可燃气体', 'url': '../measurement/measurement-combustible-gas.html'}
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
        name = (item.get('name') or '').strip()
        url = (item.get('url') or '').strip()
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
            {'name': '大气环境监测', 'url': '/pages/solutions/industry-environment.html'}
        ]
    }


def get_default_research_nav_items():
    """Default gas nav research links."""
    return {
        'items': [
            {'name': '传感器微纳加工', 'url': '/pages/research/micro-nano.html'},
            {'name': '一站式原型开发', 'url': '/pages/research/development.html'},
            {'name': '产学研深度合作', 'url': '/pages/research/cooperation.html'}
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
            {'name': '柴油机真空检漏', 'url': '/pages/gassensing/cases/case-13-diesel-engine.html'}
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
            {'name': '石油化工', 'url': '/pages/gassensing/cases/case-5-chemical-plant.html'}
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
        name = (item.get('name') or '').strip()
        url = (item.get('url') or '').strip()
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
        encoding='utf-8'
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
        encoding='utf-8'
    )

def get_default_recommendations():
    """Default recommendations data."""
    return {
        'latestReleases': [
            {'name': 'MC-LD-H2 氢气泄漏检测仪', 'url': '../gassensing/mc_ld_h2.html'},
            {'name': 'MC-HLA-01 固定式氢气报警器', 'url': '../gassensing/mc_hla_01.html'},
            {'name': 'MC-HHA-01 手持式氢气报警器', 'url': '../gassensing/mc_hha_01.html'},
            {'name': 'MC-WD-01 可穿戴氢气报警器', 'url': '../gassensing/mc_wd_01.html'}
        ],
        'applicationAreas': [
            {'name': '加氢站安全监测', 'url': '../solutions/industry-hydrogen.html'},
            {'name': '燃料电池车辆', 'url': '../solutions/hydrogen.html'}
        ]
    }

def get_recommendations():
    """Load recommendations settings."""
    if RECOMMENDATIONS_FILE.exists():
        try:
            return json.loads(RECOMMENDATIONS_FILE.read_text(encoding='utf-8'))
        except:
            pass
    return get_default_recommendations()

def save_recommendations(data):
    """Save recommendations settings."""
    RECOMMENDATIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


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
@app.route('/api/categories')
def get_categories_api():
    """Get all product categories for mega menu."""
    # 名称必须与 assets/js/gassensing-products.js 中的 filters 保持一致
    categories = [
        {'key': 'sensor', 'name': '传感器', 'url': '/pages/gassensing/all-products.html?filter=sensor'},
        {'key': 'module', 'name': '检测模块', 'url': '/pages/gassensing/all-products.html?filter=module'},
        {'key': 'detector', 'name': '检测仪', 'url': '/pages/gassensing/all-products.html?filter=detector'},
        {'key': 'alarm', 'name': '报警器', 'url': '/pages/gassensing/all-products.html?filter=alarm'},
        {'key': 'system', 'name': '监测系统', 'url': '/pages/gassensing/all-products.html?filter=system'},
        {'key': 'iot', 'name': '物联网平台', 'url': '/pages/gassensing/all-products.html?filter=iot'},
        {'key': 'service', 'name': '定制服务', 'url': '/pages/gassensing/all-products.html?filter=service'},
    ]
    return jsonify({'categories': categories})


@app.route('/api/products/industry-filters', methods=['GET'])
def get_industry_filters_api():
    """Get all-products industry filters."""
    return jsonify(get_industry_filters())


@app.route('/api/bio-products/industry-filters', methods=['GET'])
def get_bio_industry_filters_api():
    """Get biosensing industry filters."""
    return jsonify(get_bio_industry_filters())


@app.route('/api/products/industry-filters', methods=['POST'])
@login_required
def save_industry_filters_api():
    """Update all-products industry filters."""
    data = request.json or {}
    saved = save_industry_filters(data)
    return jsonify({'success': True, 'categories': saved.get('categories', [])})


@app.route('/api/bio-products/industry-filters', methods=['POST'])
@login_required
def save_bio_industry_filters_api():
    """Update biosensing industry filters."""
    data = request.json or {}
    saved = save_bio_industry_filters(data)
    return jsonify({'success': True, 'categories': saved.get('categories', [])})


# ============ API Routes ============


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Handle feedback form submission."""
    ip = get_client_ip()
    
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
        'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
        'name': data.get('txtUserName', '').strip() or '匿名',
        'phone': phone,
        'email': data.get('txtUserEmail', '').strip(),
        'qq': data.get('txtUserQQ', '').strip(),
        'title': data.get('txtTitle', '').strip() or '无标题',
        'content': content,
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


@app.route('/api/cdn/settings', methods=['GET'])
@login_required
def get_cdn_settings_api():
    """Get CDN acceleration settings."""
    return jsonify(get_cdn_settings())


@app.route('/api/cdn/settings', methods=['POST'])
@login_required
def update_cdn_settings_api():
    """Update CDN acceleration settings."""
    if not is_same_origin_request(request):
        return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

    data = request.json or {}
    enabled = bool(data.get('cdn_enabled', False))
    domain = normalize_cdn_domain(str(data.get('cdn_domain') or ''))

    if enabled and not domain:
        return jsonify({'success': False, 'message': '启用加速时必须填写有效 CDN 域名'}), 400
    if domain:
        ok, reason, _ = validate_safe_remote_fetch_url(f'{domain}/')
        if not ok:
            return jsonify({'success': False, 'message': reason or 'CDN 域名不安全'}), 400

    updates = {
        'cdn_enabled': enabled,
        'cdn_domain': domain
    }
    update_config(updates)
    return jsonify({'success': True, 'message': 'CDN 设置已保存', 'settings': get_cdn_settings()})


@app.route('/api/cdn/test', methods=['POST'])
@login_required
def test_cdn_settings_api():
    """Connectivity test for CDN domain."""
    if not is_same_origin_request(request):
        return jsonify({'success': False, 'message': '请求来源校验失败，请刷新页面后重试'}), 403

    data = request.json or {}
    settings = get_cdn_settings()
    domain = normalize_cdn_domain(str(data.get('cdn_domain') or settings.get('cdn_domain') or ''))
    asset_path = str(data.get('asset_path') or '/cdn_assets/images/common/f1dcc87cdcca.png').strip()
    if not asset_path.startswith('/'):
        asset_path = f"/{asset_path}"
    if not asset_path.startswith('/cdn_assets/'):
        asset_path = '/cdn_assets/images/common/f1dcc87cdcca.png'

    if not domain:
        return jsonify({'success': False, 'message': '请先填写有效 CDN 域名'}), 400

    url = f"{domain}{asset_path}"
    ok, reason, safe_url = validate_safe_remote_fetch_url(url)
    if not ok:
        return jsonify({'success': False, 'message': reason or 'CDN 检测地址不安全'}), 400
    result = {
        'url': safe_url,
        'head_status': None,
        'get_status': None,
        'reachable': False,
        'error': ''
    }

    try:
        if REQUESTS_SUPPORT:
            try:
                head_res = requests.head(
                    safe_url,
                    headers=CDN_CONNECTIVITY_CHECK_HEADERS,
                    allow_redirects=False,
                    timeout=(4, 8)
                )
                result['head_status'] = int(head_res.status_code)
                if 200 <= head_res.status_code < 400:
                    result['reachable'] = True
            except Exception:
                pass

            try:
                get_res = requests.get(
                    safe_url,
                    headers={
                        **CDN_CONNECTIVITY_CHECK_HEADERS,
                        'Range': 'bytes=0-2047',
                    },
                    stream=True,
                    timeout=(4, 10),
                    allow_redirects=False
                )
                result['get_status'] = int(get_res.status_code)
                if get_res.status_code in (200, 206):
                    result['reachable'] = True
            except Exception as e:
                if not result.get('error'):
                    result['error'] = str(e)
        elif HTTPX_SUPPORT:
            try:
                head_res = httpx.head(
                    safe_url,
                    headers=CDN_CONNECTIVITY_CHECK_HEADERS,
                    follow_redirects=False,
                    timeout=8.0
                )
                result['head_status'] = int(head_res.status_code)
                if 200 <= head_res.status_code < 400:
                    result['reachable'] = True
            except Exception:
                pass

            try:
                get_res = httpx.get(
                    safe_url,
                    headers={
                        **CDN_CONNECTIVITY_CHECK_HEADERS,
                        'Range': 'bytes=0-2047',
                    },
                    follow_redirects=False,
                    timeout=10.0
                )
                result['get_status'] = int(get_res.status_code)
                if get_res.status_code in (200, 206):
                    result['reachable'] = True
            except Exception as e:
                if not result.get('error'):
                    result['error'] = str(e)
        else:
            result['error'] = '缺少 HTTP 客户端依赖（requests/httpx）'
    except Exception as e:
        result['error'] = str(e)

    message = 'CDN 可访问' if result['reachable'] else 'CDN 连通性失败'
    return jsonify({'success': result['reachable'], 'message': message, 'result': result})


@app.route('/api/cdn/switch-header', methods=['GET', 'HEAD'])
def get_cdn_switch_header():
    """
    Internal endpoint for gateway auth_request.
    Returns lightweight headers indicating CDN switch state.
    """
    settings = get_cdn_settings()
    response = Response(status=204)
    response.headers['X-CDN-Enabled'] = '1' if settings.get('cdn_enabled') else '0'
    response.headers['X-CDN-Domain'] = settings.get('cdn_domain', '')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/cdn_assets/<path:asset_path>', methods=['GET', 'HEAD'])
def serve_cdn_asset_with_redirect(asset_path):
    """
    Main-site CDN assets entry:
    - CDN enabled: redirect client to CDN domain (offload bandwidth from main site)
    - CDN disabled: serve local cdn_assets file
    """
    relative_path = str(asset_path or '').lstrip('/')
    if not relative_path:
        return jsonify({'error': '文件路径不能为空'}), 400

    settings = get_cdn_settings()
    cdn_domain = str(settings.get('cdn_domain') or '').strip()
    cdn_enabled = bool(settings.get('cdn_enabled', False)) and bool(cdn_domain)
    cdn_entry_request = str(request.headers.get('X-YX-CDN-Entry') or '').strip() == '1'

    if cdn_enabled and not cdn_entry_request:
        forwarded_host = _first_forwarded_value(request.headers.get('X-Forwarded-Host', ''))
        current_host = (forwarded_host or request.host or '').strip().lower()
        cdn_host = (urlparse(cdn_domain).netloc or '').strip().lower()

        # Prevent accidental same-host redirect loops.
        if cdn_host and current_host != cdn_host:
            target = f"{cdn_domain}/cdn_assets/{quote(relative_path, safe='/')}"
            raw_qs = (request.query_string or b'').decode('utf-8', errors='ignore').strip()
            if raw_qs:
                target = f"{target}?{raw_qs}"
            response = redirect(target, code=302)
            # Avoid stale cache when toggling CDN switch in admin.
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['Vary'] = 'Host'
            return response

    response = send_from_directory(str(CDN_ASSETS_DIR), relative_path)
    response.headers['Cache-Control'] = MEDIA_IMMUTABLE_CACHE_CONTROL
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/api/analytics/collect', methods=['POST'])
def collect_site_analytics():
    """Collect public website analytics events."""
    content_len = int(request.content_length or 0)
    if content_len and content_len > 64 * 1024:
        return jsonify({'success': False, 'message': 'payload too large'}), 413

    payload = request.get_json(silent=True) or {}
    raw_events = []
    if isinstance(payload, dict) and isinstance(payload.get('events'), list):
        raw_events = payload.get('events') or []
    elif isinstance(payload, dict):
        raw_events = [payload]

    if not raw_events:
        return jsonify({'success': False, 'message': 'no events'}), 400

    request_host = str(request.host or '').split(':', 1)[0].strip().lower()
    request_ua = str(request.headers.get('User-Agent') or '').strip()
    request_ip = get_client_ip()

    records = []
    for raw in raw_events[:SITE_ANALYTICS_MAX_BATCH_SIZE]:
        item = _analytics_sanitize_event(raw, request_host=request_host, request_ua=request_ua, request_ip=request_ip)
        if item:
            records.append(item)

    accepted = _append_site_analytics_records(records)
    return jsonify({'success': True, 'accepted': accepted})


@app.route('/api/admin/site-reports', methods=['GET'])
@login_required
def get_site_reports_admin():
    """Get website analytics report for admin dashboard."""
    range_days = request.args.get('range_days', 30)
    report = build_site_analytics_report(range_days=range_days)
    return jsonify({'success': True, **report})


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
