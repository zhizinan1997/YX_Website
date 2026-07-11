"""
应用级配置、运行时初始化与缓存辅助模块。

本模块提供Flask应用的全局配置、运行时初始化和缓存相关的工具函数，
是整个后端应用的核心配置中心。

主要功能：
1. 应用实例创建（create_app）
   - 初始化Flask应用实例
   - 配置Session安全策略
   - 设置日志记录
   - 配置北京时区

2. 安全配置（ensure_required_runtime_config）
   - 验证生产环境必需的安全配置
   - 检查SECRET_KEY的强度
   - 验证管理员密码强度
   - 确保PUBLIC_BASE_URL正确配置

3. 密钥管理（load_or_create_secret_key）
   - 从环境变量加载密钥
   - 自动生成并持久化密钥
   - 生产环境强制验证密钥强度

4. 配置管理（get_config, update_config）
   - 读写站点配置文件
   - 支持环境变量和配置文件双重配置
   - 环境变量优先级高于配置文件

5. 缓存优化（cached_json_response）
   - 提供带ETag的JSON响应
   - 支持stale-while-revalidate缓存策略
   - 减少重复计算和传输

6. 常量定义
   - 文件上传白名单配置
   - 站点SEO元数据配置
   - 媒体缓存控制策略
   - 北京时区时间工具

文件路径约定：
- DATA_DIR: data/ - 数据存储目录
- CDN_ASSETS_DIR: cdn_assets/ - CDN资源目录
- 各类上传目录：hero、partners、product_cards、news等

作者：元芯传感技术团队
"""

import hashlib
import json
import logging
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from app.request_security import get_public_base_url


APP_ROOT = Path(__file__).resolve().parents[1]
APP_ENV = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or '').strip().lower()
DEV_ENV_NAMES = {'dev', 'development', 'local', 'test', 'testing'}
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
WEAK_ADMIN_PASSWORDS = {'admin123', 'admin', '123456', 'password'}
PLACEHOLDER_SECRET_KEYS = {'your-secret-key-change-in-production'}
ADMIN_USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
PUBLIC_STATIC_EXACT_FILES = {'index.html', 'robots.txt'}
PUBLIC_STATIC_ROOT_DIRS = {'pages', 'assets', 'cdn_assets', 'admin'}
PRIVATE_STATIC_PREFIXES = (
    'data',
    'update_logs',
    'app',
    'tools',
    '.git',
)


def is_development_mode() -> bool:
    if APP_ENV in DEV_ENV_NAMES:
        return True
    try:
        main_file = Path(getattr(sys.modules.get('__main__'), '__file__', '')).resolve()
    except Exception:
        return False
    return main_file == (APP_ROOT / 'server.py')


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    return default



def load_or_create_secret_key() -> str:
    """从环境变量或本地持久化文件中加载密钥。"""
    env_secret = (os.environ.get('SECRET_KEY') or '').strip()
    if env_secret:
        if env_secret in PLACEHOLDER_SECRET_KEYS or len(env_secret) < 32:
            raise RuntimeError('生产环境 SECRET_KEY 无效，请提供至少 32 位且非占位值的 SECRET_KEY。')
        return env_secret

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
        # 最后兜底：使用仅驻留内存的随机密钥，重启后会重新生成。
        return secrets.token_urlsafe(48)


def create_app():
    """创建 Flask 应用实例。"""
    # 把 Flask 的 root_path 固定到项目根目录，确保既有的静态文件、
    # 后台页面和模板查找行为与拆分前保持一致。
    flask_app = Flask(__name__, static_folder=None, root_path=str(APP_ROOT))
    flask_app.secret_key = load_or_create_secret_key()
    try:
        max_upload_bytes = int((os.environ.get('MAX_CONTENT_LENGTH') or str(128 * 1024 * 1024)).strip())
    except Exception:
        max_upload_bytes = 128 * 1024 * 1024
    flask_app.config['MAX_CONTENT_LENGTH'] = max(10 * 1024 * 1024, max_upload_bytes)
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = (os.environ.get('SESSION_COOKIE_SAMESITE') or 'Lax').strip() or 'Lax'
    flask_app.config['SESSION_COOKIE_PERMANENT'] = False
    secure_cookie_flag = (os.environ.get('SESSION_COOKIE_SECURE') or '').strip().lower()
    if secure_cookie_flag in ('1', 'true', 'yes', 'on'):
        flask_app.config['SESSION_COOKIE_SECURE'] = True
    elif secure_cookie_flag in ('0', 'false', 'no', 'off'):
        flask_app.config['SESSION_COOKIE_SECURE'] = False
    else:
        flask_app.config['SESSION_COOKIE_SECURE'] = get_public_base_url().startswith('https://')
    
    app_log_file = os.environ.get('FLASK_LOG_FILE', '').strip()
    if not app_log_file:
        app_log_file = str(APP_ROOT / 'data' / 'app.log')
    log_dir = os.path.dirname(app_log_file)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            app_log_file = str(APP_ROOT / 'app.log')
    log_handler_max_bytes = int(os.environ.get('FLASK_LOG_MAX_BYTES', str(10 * 1024 * 1024)))
    log_handler_backup_count = int(os.environ.get('FLASK_LOG_BACKUP_COUNT', '5'))
    try:
        from logging.handlers import RotatingFileHandler
        log_level = os.environ.get('FLASK_LOG_LEVEL', 'INFO').upper()
        log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        file_handler = RotatingFileHandler(
            app_log_file,
            maxBytes=log_handler_max_bytes,
            backupCount=log_handler_backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        file_handler.setLevel(getattr(logging, log_level, logging.INFO))
        flask_app.logger.addHandler(file_handler)
        app_log_lvl = getattr(logging, log_level, logging.INFO)
        flask_app.logger.setLevel(app_log_lvl)
        logging.getLogger('werkzeug').setLevel(app_log_lvl)
        logging.getLogger('werkzeug').addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup log file: {e}")
    
    return flask_app



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

# 核心路径与配置常量
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
LEGACY_NEWS_UPLOADS_DIR = DATA_DIR / 'news_uploads'
NEWS_UPLOADS_DIR = CDN_ASSETS_DIR / 'news'
RESUME_UPLOADS_DIR = DATA_DIR / 'resumes'
if ZoneInfo is not None:
    try:
        BEIJING_TZ = ZoneInfo('Asia/Shanghai')
    except Exception:
        BEIJING_TZ = timezone(timedelta(hours=8))
else:
    BEIJING_TZ = timezone(timedelta(hours=8))

os.environ.setdefault('TZ', 'Asia/Shanghai')
try:
    time.tzset()
except AttributeError:
    pass


def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)

# 预创建运行过程中会用到的目录
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
HERO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
HERO_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
PARTNERS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PRODUCT_CARD_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
H2_HOME_VIDEO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_NEWS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
NEWS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESUME_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_MAX = 5  # Max submissions per IP per hour
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# 预创建消息目录
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
MEDIA_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000'
CONFIG_JSON_CACHE_SECONDS = 120
CONFIG_JSON_STALE_SECONDS = 600
HERO_DERIVED_WIDTHS = (768, 1280, 1920)
HERO_DERIVED_FORMATS = ('avif', 'webp')
HERO_SOURCE_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.avif'}
def _read_timeout_seconds(env_names, default_value, minimum_value=300):
    for env_name in env_names:
        raw_value = (os.environ.get(env_name) or '').strip()
        if not raw_value:
            continue
        try:
            return max(minimum_value, int(raw_value))
        except Exception:
            continue
    return max(minimum_value, int(default_value))


ADMIN_SESSION_IDLE_TIMEOUT_SECONDS = _read_timeout_seconds(
    ('ADMIN_SESSION_IDLE_TIMEOUT_SECONDS', 'ADMIN_SESSION_MAX_AGE_SECONDS'),
    7200,
)
ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS = _read_timeout_seconds(
    ('ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS',),
    86400,
)
# Backward-compatible alias for existing imports and deployments.
ADMIN_SESSION_MAX_AGE_SECONDS = ADMIN_SESSION_IDLE_TIMEOUT_SECONDS


def ensure_required_runtime_config():
    """Validate required runtime security config outside development."""
    if is_development_mode():
        return

    errors = []
    secret_key = (os.environ.get('SECRET_KEY') or '').strip()
    public_base_url = get_public_base_url()
    admin_username = (os.environ.get('ADMIN_USERNAME') or 'admin').strip()
    admin_hash = (os.environ.get('ADMIN_PASSWORD_HASH') or '').strip()
    admin_password = (os.environ.get('ADMIN_PASSWORD') or '').strip()
    hidden_admin_username = (os.environ.get('HIDDEN_ADMIN_USERNAME') or '').strip()
    hidden_admin_hash = (os.environ.get('HIDDEN_ADMIN_PASSWORD_HASH') or '').strip()
    hidden_admin_password = (os.environ.get('HIDDEN_ADMIN_PASSWORD') or '').strip()
    allow_weak_admin_passwords = env_bool('ALLOW_WEAK_ADMIN_PASSWORDS', False)

    if not secret_key:
        errors.append('缺少 SECRET_KEY')
    elif secret_key in PLACEHOLDER_SECRET_KEYS or len(secret_key) < 32:
        errors.append('SECRET_KEY 必须至少 32 位且不能使用占位值')

    if not public_base_url:
        errors.append('缺少合法的 PUBLIC_BASE_URL')

    has_bootstrapped_admin = False
    has_bootstrapped_hidden_admin = False
    admin_users_file = DATA_DIR / 'admin_users.json'
    admin_users_file_exists = admin_users_file.exists()
    admin_users_read_error = ''
    if admin_users_file_exists:
        try:
            payload = json.loads(admin_users_file.read_text(encoding='utf-8'))
            users = payload.get('users', []) if isinstance(payload, dict) else []
            has_bootstrapped_admin = any(
                isinstance(item, dict)
                and str(item.get('role') or '') == 'super_admin'
                and str(item.get('password_hash') or '').strip()
                for item in users
            )
            has_bootstrapped_hidden_admin = any(
                isinstance(item, dict)
                and str(item.get('role') or '') == 'super_admin'
                and bool(item.get('hidden', False))
                and str(item.get('password_hash') or '').strip()
                for item in users
            )
        except Exception as exc:
            admin_users_read_error = str(exc)
            has_bootstrapped_admin = False
            has_bootstrapped_hidden_admin = False

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

    hidden_admin_config_enabled = bool(hidden_admin_username or hidden_admin_hash or hidden_admin_password)
    if hidden_admin_config_enabled and not hidden_admin_username:
        errors.append('缺少 HIDDEN_ADMIN_USERNAME：启用隐藏超级管理员时必须提供用户名')
    if hidden_admin_username and not ADMIN_USERNAME_PATTERN.match(hidden_admin_username):
        errors.append('HIDDEN_ADMIN_USERNAME 格式不合法：仅支持 3-32 位字母、数字、下划线、点、短横线')
    if hidden_admin_config_enabled and hidden_admin_username and hidden_admin_username == admin_username:
        errors.append('HIDDEN_ADMIN_USERNAME 不能与 ADMIN_USERNAME 相同')
    if (
        hidden_admin_password
        and hidden_admin_password in WEAK_ADMIN_PASSWORDS
        and not allow_weak_admin_passwords
        and not has_bootstrapped_hidden_admin
        and not hidden_admin_hash
    ):
        message = 'HIDDEN_ADMIN_PASSWORD 不能使用弱口令'
        if admin_users_file_exists:
            if admin_users_read_error:
                message += f'；且无法读取 {admin_users_file}：{admin_users_read_error}'
            else:
                message += f'；且 {admin_users_file} 中未检测到带 password_hash 的隐藏 super_admin'
        else:
            message += f'；且未找到 {admin_users_file}'
        errors.append(message)
    if hidden_admin_config_enabled and not has_bootstrapped_hidden_admin and not hidden_admin_hash and not hidden_admin_password:
        message = '缺少隐藏超级管理员初始化凭据：请提供 HIDDEN_ADMIN_PASSWORD_HASH 或一次性 HIDDEN_ADMIN_PASSWORD'
        if admin_users_file_exists:
            if admin_users_read_error:
                message += f'；另外无法读取 {admin_users_file}：{admin_users_read_error}'
            else:
                message += f'；并且 {admin_users_file} 中未检测到有效的隐藏 super_admin'
        else:
            message += f'；并且未找到 {admin_users_file}'
        errors.append(message)

    if errors:
        raise RuntimeError('生产环境安全配置不完整：' + '；'.join(errors))

NEWS_SAFE_HTML_TAGS = {
    'p', 'br', 'div', 'span', 'font',
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


def build_json_etag(payload) -> str:
    """为 JSON 载荷构建稳定的 ETag。"""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha1(serialized.encode('utf-8')).hexdigest()


def cached_json_response(payload, max_age: int = CONFIG_JSON_CACHE_SECONDS, stale_seconds: int = CONFIG_JSON_STALE_SECONDS):
    """返回带条件缓存头的 JSON 响应。"""
    response = jsonify(payload)
    response.set_etag(build_json_etag(payload))
    response.headers['Cache-Control'] = f'public, max-age={max_age}, stale-while-revalidate={stale_seconds}'
    response.make_conditional(request)
    return response

def get_config():
    """从配置文件或默认值中读取站点配置。"""
    default_config = {
        'admin_username': os.environ.get('ADMIN_USERNAME', 'admin'),
        'admin_password_hash': (os.environ.get('ADMIN_PASSWORD_HASH') or '').strip(),
        'admin_password': (os.environ.get('ADMIN_PASSWORD') or ('admin123' if is_development_mode() else '')).strip(),
        'hidden_admin_username': (os.environ.get('HIDDEN_ADMIN_USERNAME') or '').strip(),
        'hidden_admin_password_hash': (os.environ.get('HIDDEN_ADMIN_PASSWORD_HASH') or '').strip(),
        'hidden_admin_password': (os.environ.get('HIDDEN_ADMIN_PASSWORD') or '').strip(),
        'cdn_enabled': env_bool('CDN_ENABLED', False),
        'cdn_domain': (os.environ.get('CDN_DOMAIN') or os.environ.get('CDN_ASSET_BASE_URL') or '').strip(),
        'turnstile_enabled': env_bool('TURNSTILE_ENABLED', False),
        'turnstile_site_key': (os.environ.get('TURNSTILE_SITE_KEY') or '').strip(),
        'turnstile_secret_key': (os.environ.get('TURNSTILE_SECRET_KEY') or '').strip(),
        'turnstile_proxy_fallback_enabled': env_bool('TURNSTILE_PROXY_FALLBACK_ENABLED', False),
        'turnstile_proxy_url': (os.environ.get('TURNSTILE_PROXY_URL') or '').strip(),
        'admin_login_geo_enabled': env_bool('ADMIN_LOGIN_GEO_ENABLED', True),
        'admin_login_geo_continents': {
            'asia': 'allow',
            'europe': 'deny',
            'africa': 'deny',
            'north-america': 'deny',
            'south-america': 'deny',
            'oceania': 'deny',
            'antarctica': 'deny',
        },
        'admin_login_geo_countries': {
            'CN': 'allow',
            'HK': 'allow',
            'MO': 'allow',
            'TW': 'allow',
        },
        'email_auth_enabled': env_bool('EMAIL_AUTH_ENABLED', False),
        'smtp_host': (os.environ.get('SMTP_HOST') or '').strip(),
        'smtp_port': int((os.environ.get('SMTP_PORT') or '465').strip() or '465'),
        'smtp_username': (os.environ.get('SMTP_USERNAME') or '').strip(),
        'smtp_password_or_app_code': (os.environ.get('SMTP_PASSWORD_OR_APP_CODE') or '').strip(),
        'smtp_use_ssl': env_bool('SMTP_USE_SSL', True),
        'smtp_use_tls': env_bool('SMTP_USE_TLS', False),
        'smtp_from_name': (os.environ.get('SMTP_FROM_NAME') or '').strip(),
        'smtp_from_email': (os.environ.get('SMTP_FROM_EMAIL') or '').strip(),
        'smtp_notice_email': (os.environ.get('SMTP_NOTICE_EMAIL') or '').strip(),
        'smtp_password_set_at': (os.environ.get('SMTP_PASSWORD_SET_AT') or '').strip(),
        'smtp_password_expires_at': (os.environ.get('SMTP_PASSWORD_EXPIRES_AT') or '').strip(),
    }
    
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            for key in (
                'admin_username',
                'admin_password_hash',
                'admin_password',
                'hidden_admin_username',
                'hidden_admin_password_hash',
                'hidden_admin_password',
            ):
                env_value = str(default_config.get(key, '') or '').strip()
                file_value = str(config.get(key, '') or '').strip() if isinstance(config, dict) else ''
                if env_value and not file_value:
                    merged[key] = env_value
            return merged
        except Exception:
            pass
            
    # 文件不存在时，先落一份默认配置
    CONFIG_FILE.write_text(json.dumps(default_config, indent=2), encoding='utf-8')
    return default_config

def update_config(new_config):
    """更新并保存站点配置。"""
    config = get_config()
    config.update(new_config)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return config
