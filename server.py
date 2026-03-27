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
import re
import uuid
import html
import mimetypes
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from urllib.parse import quote, urlparse

from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string, Response, stream_with_context, send_file
from werkzeug.utils import secure_filename
from app.routes.admin import ADMIN_PERMISSION_KEYS, register_admin_routes, resolve_permission_for_path
from app.routes.backup import register_backup_routes

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
    PIL_FEATURES = None

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


def load_or_create_secret_key() -> str:
    """Load secret key from env or persistent local file."""
    env_secret = (os.environ.get('SECRET_KEY') or '').strip()
    if env_secret:
        return env_secret

    secret_file = Path(__file__).parent / 'data' / '.flask_secret_key'
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
    flask_app = Flask(__name__, static_folder='.', static_url_path='')
    flask_app.secret_key = load_or_create_secret_key()
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = (os.environ.get('SESSION_COOKIE_SAMESITE') or 'Lax').strip() or 'Lax'
    secure_cookie_flag = (os.environ.get('SESSION_COOKIE_SECURE') or '').strip().lower()
    flask_app.config['SESSION_COOKIE_SECURE'] = secure_cookie_flag in ('1', 'true', 'yes', 'on')
    return flask_app


app = create_app()
CHEM_SUBSCRIPT_SCRIPT_SRC = '/assets/js/chem-subscript.js'

# Configuration
DATA_DIR = Path(__file__).parent / 'data'
MESSAGES_DIR = DATA_DIR / 'messages'
MESSAGES_META_FILE = DATA_DIR / 'messages_meta.json'
KNOWLEDGE_DIR = DATA_DIR / 'knowledge'
RATE_LIMIT_FILE = DATA_DIR / 'rate_limits.json'
CONFIG_FILE = DATA_DIR / 'config.json'
CDN_ASSETS_DIR = Path(__file__).parent / 'cdn_assets'
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
ALLOWED_PARTNER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}
ALLOWED_PARTNER_MIME_TYPES = {'image/png', 'image/jpeg', 'image/svg+xml', 'image/webp'}
ALLOWED_PRODUCT_CARD_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_PRODUCT_CARD_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp'}
ALLOWED_NEWS_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
ALLOWED_NEWS_IMAGE_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/svg+xml'}
ALLOWED_AI_PRODUCT_IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.svg',
    '.tif', '.tiff', '.avif', '.heic', '.heif'
}
ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/webp', 'image/bmp', 'image/gif', 'image/svg+xml',
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
    if mime == 'image/svg+xml':
        return '.svg'
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
    if mime == 'image/svg+xml':
        return '.svg'
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

def get_hero_config():
    """Load hero carousel config from file or defaults."""
    default_config = {
        'interval_seconds': 5,
        'items': []
    }

    if HERO_CONFIG_FILE.exists():
        try:
            config = json.loads(HERO_CONFIG_FILE.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            items = merged.get('items', [])
            if not isinstance(items, list):
                items = []
            merged['items'] = [item for item in items if isinstance(item, dict)]
            return merged
        except Exception:
            pass

    HERO_CONFIG_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


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

def save_hero_config(new_config):
    """Validate and save hero carousel config."""
    config = get_hero_config()
    interval_seconds = new_config.get('interval_seconds', config.get('interval_seconds', 5))
    try:
        interval_seconds = int(interval_seconds)
    except Exception:
        interval_seconds = 5
    if interval_seconds < 1:
        interval_seconds = 1
    if interval_seconds > 60:
        interval_seconds = 60

    items = new_config.get('items', config.get('items', []))
    normalized_items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get('id') or uuid.uuid4().hex)
            item_type = (item.get('type') or 'image').lower()
            if item_type not in {'image', 'video'}:
                continue
            url = (item.get('url') or '').strip()
            if not url:
                continue
            source = (item.get('source') or 'url').lower()
            normalized_items.append({
                'id': item_id,
                'type': item_type,
                'url': url,
                'source': source
            })

    saved = {
        'interval_seconds': interval_seconds,
        'items': normalized_items
    }
    HERO_CONFIG_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def load_hero_derived_manifest():
    """Load hero derived-image manifest from disk."""
    default_manifest = {'version': 1, 'items': {}}
    if not HERO_DERIVED_MANIFEST_FILE.exists():
        return default_manifest
    try:
        payload = json.loads(HERO_DERIVED_MANIFEST_FILE.read_text(encoding='utf-8'))
    except Exception:
        return default_manifest
    if not isinstance(payload, dict):
        return default_manifest
    items = payload.get('items')
    if not isinstance(items, dict):
        items = {}
    return {'version': 1, 'items': items}


def save_hero_derived_manifest(manifest):
    """Persist hero derived-image manifest to disk."""
    payload = manifest if isinstance(manifest, dict) else {'version': 1, 'items': {}}
    HERO_DERIVED_MANIFEST_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


def hero_source_filename_from_url(url: str) -> str:
    """Extract local hero source filename from '/media/hero/<filename>' URL."""
    raw = (url or '').strip()
    if not raw.startswith('/media/hero/'):
        return ''
    return raw.replace('/media/hero/', '', 1).strip()


def _iter_hero_variant_filenames(entry):
    variants = (entry or {}).get('variants', {})
    if not isinstance(variants, dict):
        return []
    names = []
    for group in variants.values():
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            filename = str(item.get('filename') or '').strip()
            if filename:
                names.append(filename)
    return names


def remove_hero_variants_for_source(source_filename: str):
    """Delete derived variants for a source hero image and update manifest."""
    source_name = (source_filename or '').strip()
    if not source_name:
        return
    manifest = load_hero_derived_manifest()
    items = manifest.get('items', {})
    if not isinstance(items, dict):
        items = {}
    entry = items.pop(source_name, None)
    if entry:
        for variant_name in _iter_hero_variant_filenames(entry):
            variant_path = HERO_DERIVED_DIR / variant_name
            if variant_path.exists():
                try:
                    variant_path.unlink()
                except Exception:
                    pass
    manifest['items'] = items
    save_hero_derived_manifest(manifest)


def _hero_can_encode_avif() -> bool:
    if not PIL_SUPPORT or PIL_FEATURES is None:
        return False
    try:
        return bool(PIL_FEATURES.check('avif'))
    except Exception:
        return False


def generate_hero_variants_for_source(source_filename: str):
    """Generate AVIF/WebP responsive variants for one hero source image."""
    source_name = (source_filename or '').strip()
    if not source_name or not PIL_SUPPORT:
        return None
    source_path = HERO_UPLOADS_DIR / source_name
    if not source_path.exists() or source_path.suffix.lower() not in HERO_SOURCE_IMAGE_EXTENSIONS:
        return None

    try:
        with Image.open(source_path) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            src_width, src_height = img.size
            if src_width <= 0 or src_height <= 0:
                return None
            if img.mode in ('RGBA', 'LA') or ('transparency' in img.info):
                base_img = img.convert('RGBA')
            else:
                base_img = img.convert('RGB')
    except Exception:
        return None

    resample = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
    variant_widths = sorted({w for w in HERO_DERIVED_WIDTHS if isinstance(w, int) and w > 0})
    if src_width not in variant_widths:
        variant_widths.append(src_width)
    variant_widths = sorted({min(src_width, w) for w in variant_widths if w > 0})

    allow_avif = _hero_can_encode_avif()
    format_map = []
    for fmt in HERO_DERIVED_FORMATS:
        if fmt == 'avif' and not allow_avif:
            continue
        if fmt == 'webp':
            format_map.append(('webp', 'WEBP', {'quality': 80, 'method': 6}))
        elif fmt == 'avif':
            format_map.append(('avif', 'AVIF', {'quality': 50, 'speed': 6}))

    if not format_map:
        return None

    base_name = Path(source_name).stem
    variants = {}
    created_files = set()
    for fmt_name, pil_format, save_options in format_map:
        rows = []
        for width in variant_widths:
            width = int(width)
            if width <= 0:
                continue
            if width == src_width:
                resized = base_img.copy()
                height = src_height
            else:
                height = max(1, int(round(src_height * width / src_width)))
                resized = base_img.resize((width, height), resample)
            out_filename = f'{base_name}-w{width}.{fmt_name}'
            out_path = HERO_DERIVED_DIR / out_filename
            try:
                resized.save(out_path, pil_format, **save_options)
            except Exception:
                continue
            rows.append({'width': width, 'filename': out_filename})
            created_files.add(out_filename)
        if rows:
            rows.sort(key=lambda x: int(x.get('width', 0)))
            variants[fmt_name] = rows

    if not variants:
        return None

    manifest = load_hero_derived_manifest()
    items = manifest.get('items', {})
    if not isinstance(items, dict):
        items = {}
    old_entry = items.get(source_name, {})
    stale_files = set(_iter_hero_variant_filenames(old_entry)) - created_files
    for stale in stale_files:
        stale_path = HERO_DERIVED_DIR / stale
        if stale_path.exists():
            try:
                stale_path.unlink()
            except Exception:
                pass

    new_entry = {
        'width': int(src_width),
        'height': int(src_height),
        'variants': variants,
        'updated_at': int(time.time())
    }
    items[source_name] = new_entry
    manifest['items'] = items
    save_hero_derived_manifest(manifest)
    return new_entry


def build_hero_api_payload():
    """Build hero API payload with responsive image sources when available."""
    config = get_hero_config()
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []

    manifest_items = load_hero_derived_manifest().get('items', {})
    if not isinstance(manifest_items, dict):
        manifest_items = {}

    payload_items = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        if (item.get('type') or '').lower() != 'image':
            payload_items.append(item)
            continue

        fallback = str(item.get('url') or '').strip()
        item['fallback'] = fallback
        source_name = hero_source_filename_from_url(fallback)
        if not source_name:
            payload_items.append(item)
            continue

        entry = manifest_items.get(source_name)
        if not isinstance(entry, dict) and PIL_SUPPORT:
            entry = generate_hero_variants_for_source(source_name)
            if isinstance(entry, dict):
                manifest_items[source_name] = entry
        if not isinstance(entry, dict):
            payload_items.append(item)
            continue

        width = int(entry.get('width') or 0)
        height = int(entry.get('height') or 0)
        if width > 0:
            item['width'] = width
        if height > 0:
            item['height'] = height

        variants = entry.get('variants', {})
        if not isinstance(variants, dict):
            payload_items.append(item)
            continue

        sources = []
        for fmt in HERO_DERIVED_FORMATS:
            rows = variants.get(fmt, [])
            if not isinstance(rows, list) or not rows:
                continue
            srcset_parts = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                variant_name = str(row.get('filename') or '').strip()
                variant_width = int(row.get('width') or 0)
                if not variant_name or variant_width <= 0:
                    continue
                srcset_parts.append(f'/media/hero-derived/{variant_name} {variant_width}w')
            if not srcset_parts:
                continue
            sources.append({
                'type': f'image/{fmt}',
                'srcset': ', '.join(srcset_parts),
                'sizes': '100vw'
            })

        if sources:
            item['sources'] = sources
        payload_items.append(item)

    return {
        'interval_seconds': config.get('interval_seconds', 5),
        'items': payload_items
    }


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

def get_partners_config():
    """Load partners config from file or defaults."""
    default_config = {
        'items': []
    }

    if PARTNERS_CONFIG_FILE.exists():
        try:
            config = json.loads(PARTNERS_CONFIG_FILE.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            items = merged.get('items', [])
            if not isinstance(items, list):
                items = []
            merged['items'] = [item for item in items if isinstance(item, dict)]
            return merged
        except Exception:
            pass

    PARTNERS_CONFIG_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config

def save_partners_config(new_config):
    """Validate and save partners config."""
    config = get_partners_config()
    items = new_config.get('items', config.get('items', []))
    normalized_items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get('id') or uuid.uuid4().hex)
            url = (item.get('url') or '').strip()
            if not url:
                continue
            source = (item.get('source') or 'url').lower()
            normalized_items.append({
                'id': item_id,
                'url': url,
                'source': source
            })

    saved = {
        'items': normalized_items
    }
    PARTNERS_CONFIG_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved

def get_config():
    """Load config from file or defaults."""
    def _env_bool(name: str, default: bool = False) -> bool:
        raw = (os.environ.get(name) or '').strip().lower()
        if raw in {'1', 'true', 'yes', 'on'}:
            return True
        if raw in {'0', 'false', 'no', 'off'}:
            return False
        return default

    default_config = {
        'admin_username': os.environ.get('ADMIN_USERNAME', 'admin'),
        'admin_password_hash': (os.environ.get('ADMIN_PASSWORD_HASH') or '').strip(),
        'admin_password': os.environ.get('ADMIN_PASSWORD', 'admin123'),
        'cdn_enabled': _env_bool('CDN_ENABLED', False),
        'cdn_domain': (os.environ.get('CDN_DOMAIN') or os.environ.get('CDN_ASSET_BASE_URL') or '').strip(),
        'turnstile_enabled': _env_bool('TURNSTILE_ENABLED', False),
        'turnstile_site_key': (os.environ.get('TURNSTILE_SITE_KEY') or '').strip(),
        'turnstile_secret_key': (os.environ.get('TURNSTILE_SECRET_KEY') or '').strip(),
    }
    
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            return {**default_config, **config}
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
    raw = (os.environ.get('TRUST_PROXY_HEADERS') or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False

    remote_ip = _normalize_ip_text(getattr(req, 'remote_addr', '') or '')
    if not _is_private_proxy_source(remote_ip):
        return False

    # Auto-trust only when common proxy headers are present.
    return bool(
        str(req.headers.get('CF-Connecting-IP') or '').strip()
        or str(req.headers.get('X-Forwarded-For') or '').strip()
        or str(req.headers.get('X-Real-IP') or '').strip()
        or str(req.headers.get('X-Forwarded-Host') or '').strip()
    )


def is_same_origin_request(req) -> bool:
    """Basic CSRF guard for admin write actions."""
    allowed_origins = []

    def add_allowed(raw_origin: str):
        normalized = _normalize_origin(raw_origin)
        if normalized and normalized not in allowed_origins:
            allowed_origins.append(normalized)

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

    if not allowed_origins:
        return False

    origin = _normalize_origin(req.headers.get('Origin', ''))
    if origin:
        return any(hmac.compare_digest(origin, item) for item in allowed_origins)

    referer = _normalize_origin(req.headers.get('Referer', ''))
    if referer:
        return any(hmac.compare_digest(referer, item) for item in allowed_origins)

    # Allow non-browser clients with no Origin/Referer.
    return True


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
        cf_ip = _normalize_ip_text(request.headers.get('CF-Connecting-IP', ''))
        if cf_ip:
            return cf_ip

        xff = (request.headers.get('X-Forwarded-For') or '').strip()
        if xff:
            for part in xff.split(','):
                ip_text = _normalize_ip_text(part)
                if ip_text:
                    return ip_text

        x_real_ip = _normalize_ip_text(request.headers.get('X-Real-IP', ''))
        if x_real_ip:
            return x_real_ip

    direct_ip = _normalize_ip_text(request.remote_addr or '')
    return direct_ip or (request.remote_addr or '127.0.0.1')


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
        if not session.get('admin_logged_in'):
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
            return redirect('/admin')

        # Backward compatibility for old sessions created before RBAC fields exist.
        if 'admin_is_super_admin' not in session and 'admin_permissions' not in session:
            session['admin_is_super_admin'] = True
            session['admin_permissions'] = list(ADMIN_PERMISSION_KEYS)

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
            if (request.path or '').startswith('/api/'):
                return jsonify({'success': False, 'message': '当前账号无权限访问该功能'}), 403
            return redirect('/admin')
        return f(*args, **kwargs)
    return decorated_function


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


def _current_public_base_url() -> tuple[str, str]:
    """Build public base URL from forwarded headers when present."""
    forwarded_host = _first_forwarded_value(request.headers.get('X-Forwarded-Host', ''))
    host = (forwarded_host or request.host or '').strip()
    forwarded_proto = _first_forwarded_value(request.headers.get('X-Forwarded-Proto', '')).lower()
    scheme = forwarded_proto if forwarded_proto in {'http', 'https'} else (request.scheme or 'https')
    if not host:
        host = 'localhost:8000'
    return f'{scheme}://{host}', host.split(':', 1)[0]


def _collect_public_html_urls():
    """Collect public HTML URLs for sitemap generation."""
    root = Path(__file__).parent
    output = []
    seen = set()

    def add_url(path_text: str, file_path: Path, changefreq: str = 'weekly', priority: str = '0.7'):
        url_path = str(path_text or '').strip() or '/'
        if not url_path.startswith('/'):
            url_path = f'/{url_path}'
        if url_path in seen:
            return
        seen.add(url_path)
        try:
            lastmod = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).strftime('%Y-%m-%d')
        except Exception:
            lastmod = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
        output.append({
            'path': url_path,
            'lastmod': lastmod,
            'changefreq': changefreq,
            'priority': priority,
        })

    index_file = root / 'index.html'
    if index_file.exists():
        add_url('/', index_file, changefreq='daily', priority='1.0')

    pages_root = root / 'pages'
    if pages_root.exists():
        for html_file in sorted(pages_root.rglob('*.html')):
            rel = html_file.relative_to(root).as_posix()
            if rel.startswith('admin/'):
                continue
            url = f'/{rel}'
            if url.endswith('/index.html'):
                url = url[:-10] + '/'
            add_url(url, html_file, changefreq='weekly', priority='0.8' if '/news/' in url else '0.7')

    return output


@app.route('/robots.txt')
def robots_txt():
    """Robots rules optimized for indexing while protecting private paths."""
    base_url, host_no_port = _current_public_base_url()
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /api/admin',
        'Disallow: /data/',
        'Disallow: /update_logs/',
        '',
        '# Allow rendering resources for SEO',
        'Allow: /assets/',
        'Allow: /cdn_assets/',
        'Allow: /media/',
        '',
        'User-agent: bingbot',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /api/admin',
        'Disallow: /data/',
        'Disallow: /update_logs/',
        '',
        'User-agent: Baiduspider',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /api/admin',
        'Disallow: /data/',
        'Disallow: /update_logs/',
        '',
        f'Sitemap: {base_url}/sitemap.xml',
    ]
    if host_no_port:
        lines.append(f'Host: {host_no_port}')
    resp = Response('\n'.join(lines) + '\n', mimetype='text/plain')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.route('/sitemap.xml')
def sitemap_xml():
    """Dynamic sitemap for search engines."""
    base_url, _ = _current_public_base_url()
    entries = _collect_public_html_urls()
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for item in entries:
        path = str(item.get('path') or '/').strip() or '/'
        loc = html.escape(f'{base_url}{path}', quote=True)
        lastmod = html.escape(str(item.get('lastmod') or ''), quote=True)
        changefreq = html.escape(str(item.get('changefreq') or 'weekly'), quote=True)
        priority = html.escape(str(item.get('priority') or '0.7'), quote=True)
        rows.append('  <url>')
        rows.append(f'    <loc>{loc}</loc>')
        rows.append(f'    <lastmod>{lastmod}</lastmod>')
        rows.append(f'    <changefreq>{changefreq}</changefreq>')
        rows.append(f'    <priority>{priority}</priority>')
        rows.append('  </url>')
    rows.append('</urlset>')
    resp = Response('\n'.join(rows) + '\n', mimetype='application/xml')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.after_request
def inject_chem_subscript_script(response):
    """Inject chemical-formula subscript script into all HTML responses."""
    try:
        path = request.path or ''
        if _is_anti_crawl_strict_private_path(path):
            response.headers['X-Robots-Tag'] = STRICT_ANTI_CRAWL_HEADERS

        # Never inject into admin pages; admin has large inline scripts that may
        # contain literal "</body>" inside JS strings.
        if path.startswith('/admin'):
            return response

        content_type = (response.headers.get('Content-Type') or '').lower()
        if 'text/html' not in content_type:
            return response

        response.direct_passthrough = False
        html_body = response.get_data(as_text=True)
        if not html_body:
            return response

        script_tag = f'<script src="{CHEM_SUBSCRIPT_SCRIPT_SRC}" defer></script>'
        if CHEM_SUBSCRIPT_SCRIPT_SRC in html_body:
            return response

        lower_body = html_body.lower()
        body_pos = lower_body.rfind('</body>')
        html_pos = lower_body.rfind('</html>')

        if body_pos != -1:
            html_body = html_body[:body_pos] + script_tag + '\n' + html_body[body_pos:]
        elif html_pos != -1:
            html_body = html_body[:html_pos] + script_tag + '\n' + html_body[html_pos:]
        else:
            html_body += script_tag

        response.set_data(html_body)
    except Exception:
        # Keep responses unchanged if injection fails for any reason.
        pass
    return response



# ============ News API ============

def parse_news_from_html():
    """Parse news data from news.html file."""
    news_file = Path(__file__).parent / 'pages' / 'news' / 'news.html'
    if not news_file.exists():
        return {'enterprise': [], 'industry': [], 'science': []}
    
    try:
        from html.parser import HTMLParser
        
        class NewsParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.news_items = {'enterprise': [], 'industry': [], 'science': []}
                self.current_item = None
                self.current_tag = None
                self.in_card = False
                self.in_title = False
                self.in_meta = False
                self.in_desc = False
                self.current_category = None
            
            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                
                # Check for news card
                if tag == 'a' and 'vs-card' in attrs_dict.get('class', ''):
                    category = attrs_dict.get('data-category', '')
                    if category in self.news_items:
                        self.in_card = True
                        self.current_category = category
                        self.current_item = {
                            'link': attrs_dict.get('href', ''),
                            'title': '',
                            'date': '',
                            'desc': '',
                            'image': '',
                            'division': attrs_dict.get('data-division', '').strip()
                        }
                
                elif self.in_card:
                    if tag == 'img' and 'src' in attrs_dict:
                        if not self.current_item['image']:
                            self.current_item['image'] = attrs_dict['src']
                    elif tag == 'h3' and 'vs-card__title' in attrs_dict.get('class', ''):
                        self.in_title = True
                    elif tag == 'div' and 'vs-news-meta' in attrs_dict.get('class', ''):
                        self.in_meta = True
                    elif tag == 'p' and 'vs-card__desc' in attrs_dict.get('class', ''):
                        self.in_desc = True
                
                self.current_tag = tag
            
            def handle_endtag(self, tag):
                if tag == 'a' and self.in_card:
                    if self.current_item and self.current_category:
                        # Clean up the link path - make it relative to root
                        link = self.current_item['link']
                        if link.startswith('../../'):
                            link = link[6:]  # Remove ../../
                        self.current_item['link'] = link
                        self.news_items[self.current_category].append(self.current_item)
                    self.in_card = False
                    self.current_item = None
                    self.current_category = None
                elif tag == 'h3':
                    self.in_title = False
                elif tag == 'div' and self.in_meta:
                    self.in_meta = False
                elif tag == 'p':
                    self.in_desc = False
            
            def handle_data(self, data):
                if not self.current_item:
                    return
                data = data.strip()
                if not data:
                    return
                    
                if self.in_title:
                    self.current_item['title'] += data
                elif self.in_meta:
                    # Extract date (format like 2025-01-04)
                    import re
                    date_match = re.search(r'\d{4}-\d{2}-\d{2}', data)
                    if date_match:
                        self.current_item['date'] = date_match.group()
                elif self.in_desc:
                    self.current_item['desc'] += data
        
        html_content = news_file.read_text(encoding='utf-8')
        parser = NewsParser()
        parser.feed(html_content)
        return parser.news_items
        
    except Exception as e:
        print(f"Error parsing news: {e}")
        return {'enterprise': [], 'industry': [], 'science': []}

def get_next_news_id():
    """Get next numeric ID for news_show file."""
    news_dir = Path(__file__).parent / 'pages' / 'news'
    max_id = 0
    if news_dir.exists():
        for file in news_dir.glob('news_show.aspx_id_*.html'):
            match = re.search(r'news_show\\.aspx_id_(\\d+)\\.html', file.name)
            if match:
                try:
                    max_id = max(max_id, int(match.group(1)))
                except ValueError:
                    pass
    return max_id + 1

def build_news_article_html(title, date, image_url, content_html):
    """Render a news article HTML with consistent style."""
    safe_title = title.replace('"', '&quot;')
    hero_title = safe_title
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{hero_title} - 湖南元芯传感科技有限责任公司</title>
    
    <!-- YX Style V2.0 -->
    <link rel="stylesheet" href="../../assets/css/yx-style.css">
    
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        .article-hero {{
            position: relative;
            background: linear-gradient(135deg, rgba(0, 31, 63, 0.9) 0%, rgba(0, 31, 63, 0.7) 100%), url('../../assets/images/section2_bj.jpg') center/cover;
            height: 40vh;
            min-height: 300px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: white !important;
            padding: 0 20px;
        }}
        .article-hero__title {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 16px;
            max-width: 900px;
            line-height: 1.4;
        }}
        .article-hero__meta {{
            font-size: 16px;
            opacity: 0.8;
        }}
        .article-container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }}
        @media (min-width: 1920px) {{
            .article-container {{
                max-width: 1600px;
            }}
            .article-content {{
                font-size: 19px;
            }}
            .article-hero__title {{
                font-size: 48px;
            }}
        }}
        .article-content {{
            font-size: 17px;
            line-height: 1.9;
            color: #333;
        }}
        .article-content p {{
            margin-bottom: 20px;
        }}
        .article-content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 24px auto; display: block;
        }}
        .article-content strong {{
            color: var(--color-primary);
        }}
        .article-content ul, .article-content ol {{
            margin: 20px 0;
            padding-left: 30px;
        }}
        .article-content li {{
            margin-bottom: 10px;
        }}
        .article-nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 40px 0;
            border-top: 1px solid #eee;
            margin-top: 40px;
        }}
        .article-nav a {{
            color: var(--color-primary);
            text-decoration: none;
            font-weight: 500;
        }}
        .article-nav a:hover {{
            text-decoration: underline;
        }}
        .back-btn, a.back-btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: var(--color-primary);
            color: white !important;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
        }}
        .back-btn:hover {{
            background: var(--color-accent-blue);
            transform: translateY(-2px);
        }}
    </style>
  <!-- Site Search -->
  <link rel="stylesheet" href="../../assets/css/search.css">
</head>
<body>
    <!-- Header -->
    <header class="vs-header">
    <div class="vs-container vs-header__inner">
      <div style="display: flex; align-items: center">
        <a href="../../index.html" class="vs-logo">
          <img src="../../assets/images/logo.png" alt="Metachip Logo" style="filter: brightness(0) invert(1)" />
          METACHIP
        </a>
      </div>

      <nav class="vs-nav" style="margin-left: auto; margin-right: 40px;">
        <ul class="vs-nav__list">

          <li class="vs-nav__item">
            <a href="../biosensing/index.html?filter=sensor" class="vs-nav__link">生化传感事业部</a>
          </li>
          <li class="vs-nav__item">
            <a href="../gassensing/index.html" class="vs-nav__link">先进氢气传感解决方案</a>
          </li>
          <li class="vs-nav__item vs-nav__item--has-mega">
            <a href="../news/news.html" class="vs-nav__link">洞察与资讯</a>
          </li>
          <li class="vs-nav__item">
            <a href="../contact/contact.html" class="vs-nav__link">联系我们</a>
          </li>
        </ul>
      </nav>

      <div style="display: flex; gap: 24px; color: white; align-items: center">
        <a href="#" class="vs-search-trigger" title="搜索 (Ctrl+K)"><i class="fas fa-search"></i></a>
        <span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="../../index_en.html" style="font-size: 14px; font-weight: 500;">EN</a>
      </div>
    </div>
  </header>

    <section class="article-hero">
        <h1 class="article-hero__title">{hero_title}</h1>
        <div class="article-hero__meta">{date}</div>
    </section>

    <div class="article-container">
        <div class="article-content">
            <img src="{image_url}" alt="News">
            {content_html}
        </div>

        <div style="margin-top: 40px;">
            <a href="../news/news.html" class="back-btn"><i class="fas fa-arrow-left"></i> 返回资讯列表</a>
        </div>
    </div>

    <script src="../../assets/js/search.js"></script>
</body>
</html>"""

def render_markdown(content: str) -> str:
    """Render markdown to HTML."""
    if MARKDOWN_SUPPORT:
        return md.markdown(content, extensions=['extra', 'tables', 'sane_lists'])
    # Fallback: minimal markdown rendering
    lines = content.split('\n')
    html_lines = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_lines.append('</ul>')
            in_ul = False
        if in_ol:
            html_lines.append('</ol>')
            in_ol = False

    for raw in lines:
        line = raw.strip()
        if not line:
            close_lists()
            continue

        # Headings
        if line.startswith('### '):
            close_lists()
            html_lines.append(f'<h3>{line[4:]}</h3>')
            continue
        if line.startswith('## '):
            close_lists()
            html_lines.append(f'<h2>{line[3:]}</h2>')
            continue
        if line.startswith('# '):
            close_lists()
            html_lines.append(f'<h1>{line[2:]}</h1>')
            continue

        # Unordered list
        if line.startswith('- ') or line.startswith('* '):
            if in_ol:
                html_lines.append('</ol>')
                in_ol = False
            if not in_ul:
                html_lines.append('<ul>')
                in_ul = True
            html_lines.append(f'<li>{line[2:]}</li>')
            continue

        # Ordered list
        if re.match(r'^\d+\.\s+', line):
            if in_ul:
                html_lines.append('</ul>')
                in_ul = False
            if not in_ol:
                html_lines.append('<ol>')
                in_ol = True
            item = re.sub(r'^\d+\.\s+', '', line)
            html_lines.append(f'<li>{item}</li>')
            continue

        close_lists()

        # Inline formatting
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
        line = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1">', line)
        line = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', line)

        html_lines.append(f'<p>{line}</p>')

    close_lists()
    return '\n'.join(html_lines)

def parse_news_article_html(filepath: Path):
    """Parse a news article HTML to extract fields."""
    def extract_first_div_by_class(html_text: str, class_name: str) -> str:
        start_re = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>',
            re.I
        )
        start_match = start_re.search(html_text)
        if not start_match:
            return ''

        tag_re = re.compile(r'<div\b[^>]*>|</div\s*>', re.I)
        depth = 1
        content_start = start_match.end()
        for m in tag_re.finditer(html_text, content_start):
            tag = m.group(0)
            if tag.lower().startswith('</div'):
                depth -= 1
                if depth == 0:
                    return html_text[content_start:m.start()]
            else:
                depth += 1
        return ''

    if not filepath.exists():
        return None
    content = filepath.read_text(encoding='utf-8')
    title_match = re.search(r'<h1 class="article-hero__title">(.*?)</h1>', content, re.S)
    date_match = re.search(r'<div class="article-hero__meta">(.*?)</div>', content, re.S)
    title = title_match.group(1).strip() if title_match else ''
    date = date_match.group(1).strip() if date_match else ''
    body_html = extract_first_div_by_class(content, 'article-content').strip()
    # Only treat leading image as cover image.
    # For many historical pages, images are embedded inside body content and should not be stripped.
    leading_image_match = re.match(r'^\s*<img\s+[^>]*src="([^"]+)"[^>]*>\s*', body_html, re.I)
    if leading_image_match:
        image_url = leading_image_match.group(1)
        body_html = re.sub(r'^\s*<img\s+[^>]*>\s*', '', body_html, count=1, flags=re.I)
    else:
        image_url = ''
    body_text = body_html
    body_text = re.sub(r'(?i)<br\\s*/?>', '\n', body_text)
    body_text = re.sub(r'(?i)</p\\s*>', '\n', body_text)
    body_text = re.sub(r'(?i)</div\\s*>', '\n', body_text)
    body_text = re.sub(r'<[^>]+>', '', body_text)
    body_text = html.unescape(body_text)
    body_text = re.sub(r'\n{3,}', '\n\n', body_text).strip()
    return {
        'title': title,
        'date': date,
        'image_url': image_url,
        'content_html': body_html,
        'content_text': body_text
    }

def derive_news_cover_and_summary(content_html: str, image_url: str = '', summary: str = ''):
    """Fill optional cover image and summary from article content."""
    html_body = content_html or ''
    final_image = (image_url or '').strip()
    final_summary = (summary or '').strip()

    if not final_image:
        img_match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html_body, re.I)
        if img_match:
            final_image = img_match.group(1).strip()
    if not final_image:
        final_image = '/assets/images/logo.png'

    if not final_summary:
        # Prefer first paragraph text.
        para_match = re.search(r'<p\b[^>]*>(.*?)</p>', html_body, re.I | re.S)
        candidate = ''
        if para_match:
            candidate = para_match.group(1)
        else:
            # Fallback to first block content if no <p>.
            block_match = re.search(r'<(?:div|li|blockquote)\b[^>]*>(.*?)</(?:div|li|blockquote)>', html_body, re.I | re.S)
            if block_match:
                candidate = block_match.group(1)
            else:
                candidate = html_body

        candidate = re.sub(r'(?i)<br\s*/?>', '\n', candidate)
        candidate = re.sub(r'<[^>]+>', '', candidate)
        candidate = html.unescape(candidate).replace('\u00a0', ' ')
        candidate = re.sub(r'\s+', ' ', candidate).strip()
        final_summary = candidate

    return final_image, final_summary

def insert_news_card(news_html_path: Path, card_html: str) -> bool:
    """Insert a news card into news.html after the Page 1 marker."""
    if not news_html_path.exists():
        return False
    content = news_html_path.read_text(encoding='utf-8')
    marker = "<!-- Page 1 Items -->"
    idx = content.find(marker)
    if idx != -1:
        insert_pos = idx + len(marker)
        content = content[:insert_pos] + "\n" + card_html + content[insert_pos:]
        news_html_path.write_text(content, encoding='utf-8')
        return True
    # Fallback: insert before closing grid
    fallback = "</div>\n            </div>\n        </section>"
    idx = content.find(fallback)
    if idx != -1:
        content = content[:idx] + card_html + "\n" + content[idx:]
        news_html_path.write_text(content, encoding='utf-8')
        return True
    return False

def build_news_card_regex(filename: str):
    """Match a news card by filename across different href styles."""
    return re.compile(
        rf'<a\s+[^>]*href\s*=\s*["\'][^"\']*{re.escape(filename)}[^"\']*["\'][^>]*>.*?</a>',
        re.DOTALL | re.IGNORECASE
    )

def dedupe_news_cards(content: str, filename: str):
    """Remove duplicate cards for the same news filename, keeping the first."""
    pattern = build_news_card_regex(filename)
    matches = list(pattern.finditer(content))
    if len(matches) <= 1:
        return content, 0
    out = []
    last = 0
    removed = 0
    for idx, m in enumerate(matches):
        out.append(content[last:m.start()])
        if idx == 0:
            out.append(m.group(0))
        else:
            removed += 1
        last = m.end()
    out.append(content[last:])
    return ''.join(out), removed

def get_all_news_items():
    """Flatten all news items into a list preserving category order."""
    news_data = parse_news_from_html()
    hidden_links = get_hidden_news_links()
    ordered = []
    for cat in ['enterprise', 'industry', 'science']:
        for item in news_data.get(cat, []):
            link = item.get('link')
            ordered.append({**item, 'category': cat, 'hidden': link in hidden_links})
    return ordered

def get_hidden_news_links():
    """Load hidden news links."""
    default_config = {'hidden_links': []}
    if NEWS_VISIBILITY_FILE.exists():
        try:
            config = json.loads(NEWS_VISIBILITY_FILE.read_text(encoding='utf-8'))
            links = config.get('hidden_links', [])
            if isinstance(links, list):
                return set([l for l in links if isinstance(l, str)])
        except Exception:
            pass
    NEWS_VISIBILITY_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return set()

def save_hidden_news_links(links):
    """Save hidden news links."""
    cleaned = []
    for link in links:
        if link and isinstance(link, str):
            cleaned.append(link)
    data = {'hidden_links': cleaned}
    NEWS_VISIBILITY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return set(cleaned)

def get_featured_news_config():
    """Load featured news config (list of links)."""
    default_config = {'links': []}
    if NEWS_FEATURED_FILE.exists():
        try:
            config = json.loads(NEWS_FEATURED_FILE.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('links', []), list):
                return config
        except Exception:
            pass
    NEWS_FEATURED_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config

def save_featured_news_config(new_config):
    """Save featured news config."""
    links = new_config.get('links', [])
    if not isinstance(links, list):
        links = []
    # Keep unique, preserve order
    seen = set()
    normalized = []
    for link in links:
        if not link or not isinstance(link, str):
            continue
        if link in seen:
            continue
        seen.add(link)
        normalized.append(link)
    saved = {'links': normalized[:3]}
    NEWS_FEATURED_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def get_featured_products_config():
    """Load featured products config (list of ids)."""
    default_config = {'ids': []}
    if PRODUCT_FEATURED_FILE.exists():
        try:
            config = json.loads(PRODUCT_FEATURED_FILE.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('ids', []), list):
                return config
        except Exception:
            pass
    PRODUCT_FEATURED_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


def save_featured_products_config(new_config):
    """Save featured products config."""
    ids = new_config.get('ids', [])
    if not isinstance(ids, list):
        ids = []
    seen = set()
    normalized = []
    for pid in ids:
        if not pid or not isinstance(pid, str):
            continue
        if pid in seen:
            continue
        seen.add(pid)
        normalized.append(pid)
    saved = {'ids': normalized[:3]}
    PRODUCT_FEATURED_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def get_featured_solutions_config():
    """Load featured solutions config (list of ids)."""
    default_config = {'ids': []}
    if SOLUTIONS_FEATURED_FILE.exists():
        try:
            config = json.loads(SOLUTIONS_FEATURED_FILE.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('ids', []), list):
                return config
        except Exception:
            pass
    SOLUTIONS_FEATURED_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


def save_featured_solutions_config(new_config):
    """Save featured solutions config."""
    ids = new_config.get('ids', [])
    if not isinstance(ids, list):
        ids = []
    seen = set()
    normalized = []
    for sid in ids:
        if not sid or not isinstance(sid, str):
            continue
        if sid in seen:
            continue
        seen.add(sid)
        normalized.append(sid)
    saved = {'ids': normalized[:3]}
    SOLUTIONS_FEATURED_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved

def get_home_section_visibility_config():
    """Load homepage section visibility config."""
    default_config = {
        'partners': True,
        'products': True,
        'news': True,
        'solutions': True
    }
    if HOME_SECTION_VISIBILITY_FILE.exists():
        try:
            config = json.loads(HOME_SECTION_VISIBILITY_FILE.read_text(encoding='utf-8'))
            if isinstance(config, dict):
                return {
                    'partners': bool(config.get('partners', True)),
                    'products': bool(config.get('products', True)),
                    'news': bool(config.get('news', True)),
                    'solutions': bool(config.get('solutions', True))
                }
        except Exception:
            pass
    HOME_SECTION_VISIBILITY_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config

def save_home_section_visibility_config(new_config):
    """Save homepage section visibility config."""
    existing = get_home_section_visibility_config()
    saved = {
        'partners': bool(new_config.get('partners', existing.get('partners', True))),
        'products': bool(new_config.get('products', existing.get('products', True))),
        'news': bool(new_config.get('news', existing.get('news', True))),
        'solutions': bool(new_config.get('solutions', existing.get('solutions', True)))
    }
    HOME_SECTION_VISIBILITY_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


@app.route('/api/news')
def get_news():
    """Get news data grouped by category."""
    count = request.args.get('count', 2, type=int)
    category = request.args.get('category', None)
    
    news_data = parse_news_from_html()
    
    result = {}
    for cat, items in news_data.items():
        if category and cat != category:
            continue
        result[cat] = items[:count]
    
    return jsonify(result)


@app.route('/api/news/all')
@login_required
def get_all_news():
    """Get all news items for admin selection."""
    return jsonify({'items': get_all_news_items()})


@app.route('/api/news/featured')
def get_featured_news():
    """Get featured news items for homepage."""
    config = get_featured_news_config()
    links = config.get('links', [])
    items = get_all_news_items()
    hidden_links = get_hidden_news_links()
    item_map = {item.get('link'): item for item in items if item.get('link') and item.get('link') not in hidden_links}
    featured = [item_map.get(link) for link in links if item_map.get(link)]

    if len(featured) < 3:
        # Fill with latest items in order
        for item in items:
            if item.get('link') in hidden_links:
                continue
            if item in featured:
                continue
            featured.append(item)
            if len(featured) >= 3:
                break

    return jsonify({'items': featured[:3]})


@app.route('/api/news/featured', methods=['POST'])
@login_required
def update_featured_news():
    """Update featured news selection."""
    data = request.json or {}
    config = save_featured_news_config(data)
    return jsonify({'success': True, 'config': config})


def build_product_link(product):
    """Build product link path from product id."""
    pid = product.get('id', '')
    if pid.startswith('../customization/'):
        slug = pid.replace('../customization/', '').strip('/')
        return f"pages/customization/{slug}.html"
    if pid.startswith('../biosensing/'):
        slug = pid.replace('../biosensing/', '').strip('/')
        return f"pages/biosensing/{slug}.html"
    return f"pages/gassensing/{pid}.html"


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


def build_solution_link(solution):
    sid = solution.get('id', '')
    return f"pages/solutions/{sid}.html"


def get_all_solution_items():
    """Get all solutions items from pages/solutions."""
    solutions_dir = Path(__file__).parent / 'pages' / 'solutions'
    items = []
    if solutions_dir.exists():
        for filepath in sorted(solutions_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            item = extract_solution_meta_from_html(filepath)
            if item:
                item['link'] = build_solution_link(item)
                items.append(item)
    return items


def parse_jobs_from_html(html_text):
    """Parse jobs list from legacy job.aspx.html."""
    try:
        import re
        match = re.search(r'<ul class="jobs_list">(.*?)</ul>', html_text, re.S)
        if not match:
            return []
        block = match.group(1)
        items = re.findall(r'<li>(.*?)</li>', block, re.S)

        def clean(text):
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&nbsp;', ' ').replace('\xa0', ' ')
            return ' '.join(text.split()).strip()

        def after(label, text):
            if label in text:
                text = text.split(label, 1)[1]
            return text.replace(':', '').replace('：', '').strip()

        jobs = []
        for idx, li in enumerate(items, 1):
            show = re.search(r'<div class="jobs_show">(.*?)</div>', li, re.S)
            spans = re.findall(r'<span[^>]*>(.*?)</span>', show.group(1) if show else '', re.S)
            spans = [clean(s) for s in spans]
            title = after('职位名称', spans[0]) if len(spans) > 0 else ''
            department = after('招聘部门', spans[1]) if len(spans) > 1 else ''
            location = after('工作地点', spans[2]) if len(spans) > 2 else ''
            date = after('发布日期', spans[3]) if len(spans) > 3 else ''
            desc_match = re.search(r'<dl class="gwzz">(.*?)</dl>', li, re.S)
            content_html = desc_match.group(1).strip() if desc_match else ''
            jobs.append({
                'id': f'job_{idx}',
                'title': title,
                'department': department,
                'location': location,
                'date': date,
                'content_html': content_html,
                'visible': True
            })
        return jobs
    except Exception:
        return []


def clean_job_text(value: str) -> str:
    """Normalize legacy whitespace/HTML entities in job fields."""
    if value is None:
        return ''
    text = str(value)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'&nbsp;?', ' ', text, flags=re.IGNORECASE)
    text = html.unescape(text)
    text = text.replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def normalize_job_date(value: str) -> str:
    """Normalize date to YYYY-MM-DD for <input type=date> compatibility."""
    text = clean_job_text(value)
    if not text:
        return ''

    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if not m:
        m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return text


def normalize_job_record(item):
    """Sanitize one job object from storage/user input."""
    if not isinstance(item, dict):
        return None
    return {
        'id': clean_job_text(item.get('id') or ''),
        'title': clean_job_text(item.get('title') or ''),
        'department': clean_job_text(item.get('department') or ''),
        'location': clean_job_text(item.get('location') or ''),
        'date': normalize_job_date(item.get('date') or ''),
        'content_html': (item.get('content_html') or '').strip(),
        'visible': bool(item.get('visible', True))
    }


def load_jobs_data():
    if JOBS_FILE.exists():
        try:
            data = json.loads(JOBS_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('jobs', []), list):
                normalized_jobs = []
                changed = False
                for raw in data.get('jobs', []):
                    normalized = normalize_job_record(raw)
                    if not normalized:
                        changed = True
                        continue
                    normalized_jobs.append(normalized)
                    if normalized != raw:
                        changed = True
                normalized_data = {'jobs': normalized_jobs}
                if changed:
                    save_jobs_data(normalized_data)
                return normalized_data
        except Exception:
            pass

    legacy_path = Path(__file__).parent / 'pages' / 'careers' / 'job.aspx.html'
    jobs = []
    if legacy_path.exists():
        jobs = parse_jobs_from_html(legacy_path.read_text(encoding='utf-8', errors='ignore'))
    data = {'jobs': jobs}
    JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def save_jobs_data(data):
    JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def get_h2_home_config():
    """Load hydrogen homepage config."""
    default_config = {'items': [], 'products': [], 'cases': []}
    if H2_HOME_FILE.exists():
        try:
            config = json.loads(H2_HOME_FILE.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('items', []), list):
                return config
        except Exception:
            pass
    H2_HOME_FILE.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding='utf-8')
    return default_config


def save_h2_home_config(config):
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = (item.get('url') or '').strip()
        if not url:
            continue
        cleaned.append({
            'id': item.get('id') or str(uuid.uuid4()),
            'url': url
        })
    existing = get_h2_home_config()
    saved = {
        'items': cleaned,
        'products': existing.get('products', []),
        'cases': existing.get('cases', [])
    }
    H2_HOME_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_products(product_ids):
    if not isinstance(product_ids, list):
        product_ids = []
    cleaned = []
    seen = set()
    for pid in product_ids:
        if not pid or not isinstance(pid, str):
            continue
        if pid in seen:
            continue
        seen.add(pid)
        cleaned.append(pid)
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': cleaned[:3],
        'cases': existing.get('cases', [])
    }
    H2_HOME_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


def save_h2_home_cases(items):
    """Save h2 home cases with optional custom titles."""
    if not isinstance(items, list):
        items = []
    cleaned = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            # Legacy: if it's a string, treat as id
            if isinstance(item, str) and item:
                if item not in seen:
                    seen.add(item)
                    cleaned.append({'id': item, 'customSubtitle': '', 'customTitle': ''})
            continue
        cid = item.get('id')
        if not cid or not isinstance(cid, str):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        cleaned.append({
            'id': cid,
            'customSubtitle': item.get('customSubtitle', ''),
            'customTitle': item.get('customTitle', '')
        })
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': existing.get('products', []),
        'cases': cleaned[:6]
    }
    H2_HOME_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


@app.route('/api/products/featured')
def get_featured_products():
    """Get featured products for homepage."""
    config = get_featured_products_config()
    ids = config.get('ids', [])
    products = [p for p in get_products_with_settings_data() if not p.get('hidden')]
    product_map = {p.get('id'): p for p in products if p.get('id')}
    featured = [product_map.get(pid) for pid in ids if product_map.get(pid)]

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
            'title': title,
            'image': item.get('image', ''),
            'desc': item.get('description', ''),
            'link': build_product_link(item)
        })

    return jsonify({'items': items})


@app.route('/api/products/featured', methods=['POST'])
@login_required
def update_featured_products():
    """Update featured products selection."""
    data = request.json or {}
    config = save_featured_products_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/products/gassensing')
@login_required
def get_gassensing_products():
    """Get gassensing products only for admin selection."""
    products = get_gassensing_products_with_settings()
    return jsonify({'products': products, 'count': len(products)})


@app.route('/api/cases/gassensing')
@login_required
def get_gassensing_cases():
    items = get_all_case_items()
    return jsonify({'items': items, 'count': len(items)})


@app.route('/api/solutions/all')
@login_required
def get_all_solutions():
    """Get all solutions for admin selection."""
    return jsonify({'items': get_all_solution_items()})


@app.route('/api/solutions/hydrogen/config')
def get_hydrogen_solutions_public_config():
    """Public config for hydrogen solution page (per-solution related products)."""
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


@app.route('/api/solutions/featured')
def get_featured_solutions():
    """Get featured solutions for homepage."""
    config = get_featured_solutions_config()
    ids = config.get('ids', [])
    items = get_all_solution_items()
    item_map = {item.get('id'): item for item in items if item.get('id')}
    featured = [item_map.get(sid) for sid in ids if item_map.get(sid)]

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
            'title': item.get('title', ''),
            'image': item.get('image', ''),
            'desc': item.get('desc', ''),
            'link': item.get('link', build_solution_link(item))
        })

    return jsonify({'items': output})


@app.route('/api/solutions/featured', methods=['POST'])
@login_required
def update_featured_solutions():
    """Update featured solutions selection."""
    data = request.json or {}
    config = save_featured_solutions_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/jobs')
@login_required
def get_jobs_admin():
    """Get all jobs for admin."""
    data = load_jobs_data()
    return jsonify({'items': data.get('jobs', [])})


@app.route('/api/jobs', methods=['POST'])
@login_required
def save_job_admin():
    """Create or update a job."""
    data = request.json or {}
    title = clean_job_text(data.get('title') or '')
    department = clean_job_text(data.get('department') or '')
    location = clean_job_text(data.get('location') or '')
    date = normalize_job_date(data.get('date') or '')
    content_html = (data.get('content_html') or '').strip()
    visible = bool(data.get('visible', True))
    job_id = clean_job_text(data.get('id') or '')

    if not title or not department or not location or not date:
        return jsonify({'success': False, 'message': '请填写完整的职位信息'}), 400

    jobs_data = load_jobs_data()
    jobs = jobs_data.get('jobs', [])

    if job_id:
        updated = False
        for job in jobs:
            if job.get('id') == job_id:
                job.update({
                    'title': title,
                    'department': department,
                    'location': location,
                    'date': date,
                    'content_html': content_html,
                    'visible': visible
                })
                updated = True
                break
        if not updated:
            jobs.append({
                'id': job_id,
                'title': title,
                'department': department,
                'location': location,
                'date': date,
                'content_html': content_html,
                'visible': visible
            })
    else:
        new_id = f"job_{int(time.time()*1000)}"
        jobs.append({
            'id': new_id,
            'title': title,
            'department': department,
            'location': location,
            'date': date,
            'content_html': content_html,
            'visible': visible
        })

    jobs_data['jobs'] = jobs
    save_jobs_data(jobs_data)
    return jsonify({'success': True, 'items': jobs})


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
@login_required
def delete_job_admin(job_id):
    jobs_data = load_jobs_data()
    jobs = [j for j in jobs_data.get('jobs', []) if j.get('id') != job_id]
    jobs_data['jobs'] = jobs
    save_jobs_data(jobs_data)
    return jsonify({'success': True})


@app.route('/api/jobs/<job_id>/toggle', methods=['POST'])
@login_required
def toggle_job_admin(job_id):
    jobs_data = load_jobs_data()
    for job in jobs_data.get('jobs', []):
        if job.get('id') == job_id:
            job['visible'] = not bool(job.get('visible', True))
            save_jobs_data(jobs_data)
            return jsonify({'success': True, 'visible': job['visible']})
    return jsonify({'success': False, 'message': '未找到职位'}), 404


@app.route('/api/jobs/public')
def get_jobs_public():
    data = load_jobs_data()
    items = [j for j in data.get('jobs', []) if j.get('visible', True)]
    return jsonify({'items': items})


@app.route('/api/h2-home', methods=['GET'])
def get_h2_home():
    payload = get_h2_home_config()
    # Admin UI must always see fresh data right after uploads/saves.
    if session.get('admin_logged_in'):
        response = jsonify(payload)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return cached_json_response(payload)


@app.route('/api/h2-home/upload-video', methods=['POST'])
@login_required
def upload_h2_home_video():
    """Upload local video file for H2 homepage hero background."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    original_name = file.filename
    filename = secure_filename(original_name)
    ext = Path(filename).suffix.lower()
    mime = (file.mimetype or '').lower()

    if ext not in ALLOWED_H2_HOME_VIDEO_EXTENSIONS:
        inferred_ext = infer_h2_home_video_extension_from_mime(mime)
        if inferred_ext:
            ext = inferred_ext
        else:
            return jsonify({'success': False, 'message': '只支持 MP4/WEBM/OGG 视频文件'}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = H2_HOME_VIDEO_UPLOADS_DIR / saved_name
    file.save(str(save_path))

    return jsonify({
        'success': True,
        'item': {
            'id': uuid.uuid4().hex,
            'url': f"/media/h2-home/{saved_name}",
            'source': 'upload'
        }
    })


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
        if url:
            allowed.add(url)
    return allowed


def get_allowed_remote_media_urls() -> set:
    """Allow proxying only URLs configured in H2-home and home-hero media lists."""
    allowed = set()
    h2_config = get_h2_home_config()
    hero_config = get_hero_config()
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

    if not REQUESTS_SUPPORT:
        return jsonify({'success': False, 'message': '服务器缺少 requests 依赖，无法代理媒体'}), 500

    upstream_headers = {}
    range_header = request.headers.get('Range')
    if range_header:
        upstream_headers['Range'] = range_header

    try:
        upstream = requests.get(target_url, headers=upstream_headers, stream=True, timeout=(8, 120))
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
    products = [p for p in get_gassensing_products_with_settings() if not p.get('hidden')]
    product_map = {p.get('id'): p for p in products if p.get('id')}
    featured = [product_map.get(pid) for pid in ids if product_map.get(pid)]
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
            'title': title,
            'image': item.get('image', ''),
            'desc': item.get('description', ''),
            'link': build_product_link(item)
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
    items = get_all_case_items()
    item_map = {item.get('id'): item for item in items if item.get('id')}
    
    # Build output from configured cases
    output = []
    used_ids = set()
    
    for case_cfg in case_configs:
        # Support both new format (dict) and legacy format (string)
        if isinstance(case_cfg, dict):
            cid = case_cfg.get('id')
            custom_subtitle = case_cfg.get('customSubtitle', '')
            custom_title = case_cfg.get('customTitle', '')
        elif isinstance(case_cfg, str):
            cid = case_cfg
            custom_subtitle = ''
            custom_title = ''
        else:
            continue
            
        item = item_map.get(cid)
        if not item:
            continue
        used_ids.add(cid)
        output.append({
            'id': item.get('id'),
            'title': item.get('title', ''),
            'image': item.get('image', ''),
            'desc': item.get('desc', ''),
            'link': item.get('link', ''),
            'customSubtitle': custom_subtitle,
            'customTitle': custom_title
        })
    
    # Fill up to 6 with non-configured items
    if len(output) < 6:
        for item in items:
            if item.get('id') in used_ids:
                continue
            output.append({
                'id': item.get('id'),
                'title': item.get('title', ''),
                'image': item.get('image', ''),
                'desc': item.get('desc', ''),
                'link': item.get('link', ''),
                'customSubtitle': '',
                'customTitle': ''
            })
            if len(output) >= 6:
                break
    
    return jsonify({'items': output[:6]})


@app.route('/api/h2-home/cases', methods=['POST'])
@login_required
def update_h2_home_cases():
    data = request.json or {}
    items = data.get('items', [])
    # Legacy support: if 'ids' is provided instead of 'items'
    if not items and data.get('ids'):
        items = [{'id': cid} for cid in data.get('ids', [])]
    config = save_h2_home_cases(items)
    return jsonify({'success': True, 'config': config})


@app.route('/api/news/list')
@login_required
def get_news_list():
    """Get all news for admin selection."""
    items = get_all_news_items()
    return jsonify({'items': items, 'count': len(items)})


def normalize_news_link_for_product(link: str) -> str:
    raw = str(link or '').strip()
    if not raw:
        return ''
    if raw.startswith('../../'):
        return '/' + raw.replace('../../', '', 1)
    if raw.startswith('../'):
        return '/' + raw.replace('../', '', 1)
    if raw.startswith('pages/'):
        return '/' + raw
    return raw


@app.route('/api/products/related-news')
def get_product_related_news():
    """Get 2 related news for a product by settings; fallback to latest 2."""
    product_id = (request.args.get('id') or '').strip()
    if not product_id:
        return jsonify({'success': False, 'message': '缺少产品ID'}), 400

    all_items = [item for item in get_all_news_items() if not item.get('hidden')]
    normalized_items = []
    for item in all_items:
        normalized_link = normalize_news_link_for_product(item.get('link', ''))
        if not normalized_link:
            continue
        normalized_items.append({
            'link': normalized_link,
            'title': item.get('title', ''),
            'image': item.get('image', '') or '/assets/images/logo.png',
            'desc': item.get('summary') or item.get('desc') or '',
            '_date': item.get('date', '')
        })

    item_map = {item['link']: item for item in normalized_items}
    settings = get_product_settings()
    selected_links = _normalize_related_news_links((settings.get(product_id) or {}).get('relatedNews', []))

    selected_items = []
    for link in selected_links:
        normalized = normalize_news_link_for_product(link)
        if normalized in item_map:
            selected_items.append(item_map[normalized])

    if selected_items:
        selected_links_set = {item.get('link') for item in selected_items}
        def sort_key(item):
            date_str = str(item.get('_date') or '').strip()
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except Exception:
                return datetime.min
        latest_pool = sorted(normalized_items, key=sort_key, reverse=True)
        for item in latest_pool:
            if len(selected_items) >= 2:
                break
            if item.get('link') in selected_links_set:
                continue
            selected_items.append(item)
            selected_links_set.add(item.get('link'))
        for item in selected_items[:2]:
            item.pop('_date', None)
        return jsonify({'success': True, 'items': selected_items[:2]})

    def sort_key(item):
        date_str = str(item.get('_date') or '').strip()
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except Exception:
            return datetime.min

    latest = sorted(normalized_items, key=sort_key, reverse=True)[:2]
    for item in latest:
        item.pop('_date', None)
    return jsonify({'success': True, 'items': latest})


def get_all_news_items():
    """Scan news.html for all news items with metadata."""
    news_index = Path(__file__).parent / 'pages' / 'news' / 'news.html'
    if not news_index.exists():
        return []

    content = news_index.read_text(encoding='utf-8')

    from html.parser import HTMLParser

    class NewsListParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []
            self.current_item = None
            self.current_category = ''
            self.in_card = False
            self.in_title = False
            self.in_meta = False
            self.in_desc = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == 'a' and 'vs-card' in attrs_dict.get('class', ''):
                self.in_card = True
                self.current_category = (attrs_dict.get('data-category', '') or '').strip()
                self.current_item = {
                    'link': (attrs_dict.get('href', '') or '').strip(),
                    'image': '',
                    'date': '',
                    'title': '',
                    'desc': '',
                    'summary': '',
                    'category': self.current_category,
                    'division': (attrs_dict.get('data-division', '') or '').strip()
                }
                return

            if not self.in_card or not self.current_item:
                return

            if tag == 'img' and not self.current_item['image']:
                self.current_item['image'] = (attrs_dict.get('src', '') or '').strip()
            elif tag == 'h3' and 'vs-card__title' in attrs_dict.get('class', ''):
                self.in_title = True
            elif tag == 'div' and 'vs-news-meta' in attrs_dict.get('class', ''):
                self.in_meta = True
            elif tag == 'p' and 'vs-card__desc' in attrs_dict.get('class', ''):
                self.in_desc = True

        def handle_endtag(self, tag):
            if tag == 'a' and self.in_card:
                if self.current_item:
                    link = self.current_item.get('link', '')
                    if link.startswith('../../pages/news/'):
                        link = '/pages/news/' + link.replace('../../pages/news/', '')
                    self.current_item['link'] = link
                    self.current_item['summary'] = self.current_item.get('desc', '')
                    self.items.append(self.current_item)
                self.current_item = None
                self.current_category = ''
                self.in_card = False
                self.in_title = False
                self.in_meta = False
                self.in_desc = False
            elif tag == 'h3':
                self.in_title = False
            elif tag == 'div':
                self.in_meta = False
            elif tag == 'p':
                self.in_desc = False

        def handle_data(self, data):
            if not self.current_item:
                return
            text = (data or '').strip()
            if not text:
                return
            if self.in_title:
                self.current_item['title'] += text
            elif self.in_meta:
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
                if date_match:
                    self.current_item['date'] = date_match.group(0)
            elif self.in_desc:
                self.current_item['desc'] += text

    parser = NewsListParser()
    parser.feed(content)

    hidden_links = get_hidden_news_links()
    for item in parser.items:
        item['hidden'] = item.get('link') in hidden_links
    return parser.items


def save_h2_home_news(items):
    """Save h2 home news with optional custom fields."""
    if not isinstance(items, list):
        items = []
    cleaned = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get('link')
        if not link or not isinstance(link, str):
            continue
        if link in seen:
            continue
        seen.add(link)
        cleaned.append({
            'link': link,
            'customTag': item.get('customTag', ''),
            'customTitle': item.get('customTitle', ''),
            'customDesc': item.get('customDesc', '')
        })
    existing = get_h2_home_config()
    saved = {
        'items': existing.get('items', []),
        'products': existing.get('products', []),
        'cases': existing.get('cases', []),
        'news': cleaned[:3]
    }
    H2_HOME_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved


@app.route('/api/h2-home/news', methods=['GET'])
def get_h2_home_news():
    config = get_h2_home_config()
    news_configs = config.get('news', [])
    items = get_all_news_items()
    item_map = {item.get('link'): item for item in items if item.get('link')}
    
    output = []
    used_links = set()
    
    for news_cfg in news_configs:
        if isinstance(news_cfg, dict):
            link = news_cfg.get('link')
            custom_tag = news_cfg.get('customTag', '')
            custom_title = news_cfg.get('customTitle', '')
            custom_desc = news_cfg.get('customDesc', '')
        else:
            continue
            
        item = item_map.get(link)
        if not item:
            continue
        used_links.add(link)
        output.append({
            'link': item.get('link'),
            'title': item.get('title', ''),
            'image': item.get('image', ''),
            'date': item.get('date', ''),
            'summary': item.get('summary', ''),
            'customTag': custom_tag,
            'customTitle': custom_title,
            'customDesc': custom_desc
        })
    
    # Fill up to 3 with non-configured items
    if len(output) < 3:
        for item in items:
            if item.get('link') in used_links:
                continue
            output.append({
                'link': item.get('link'),
                'title': item.get('title', ''),
                'image': item.get('image', ''),
                'date': item.get('date', ''),
                'summary': item.get('summary', ''),
                'customTag': '',
                'customTitle': '',
                'customDesc': ''
            })
            if len(output) >= 3:
                break
    
    return jsonify({'items': output[:3]})


@app.route('/api/h2-home/news', methods=['POST'])
@login_required
def update_h2_home_news():
    data = request.json or {}
    items = data.get('items', [])
    config = save_h2_home_news(items)
    return jsonify({'success': True, 'config': config})


@app.route('/api/news/create', methods=['POST'])
@login_required
def create_news():
    """Create a news article and add to news list."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    date = (data.get('date') or '').strip()
    category = (data.get('category') or '').strip()
    division = (data.get('division') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))

    if not title or not date or not category or not division or not content:
        return jsonify({'success': False, 'message': '请填写标题、日期、分类、归属事业部和正文'}), 400

    if category not in {'enterprise', 'industry', 'science'}:
        return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

    # Build content HTML (Markdown supported)
    if content_is_html:
        content_html = content
    else:
        content_html = render_markdown(content)

    image_url, summary = derive_news_cover_and_summary(content_html, image_url, summary)

    # Create news file
    news_dir = Path(__file__).parent / 'pages' / 'news'
    news_dir.mkdir(parents=True, exist_ok=True)
    news_id = get_next_news_id()
    filename = f'news_show.aspx_id_{news_id}.html'
    filepath = news_dir / filename
    article_html = build_news_article_html(title, date, image_url, content_html)
    filepath.write_text(article_html, encoding='utf-8')

    # Insert card into news list
    card_html = f"""
                    <a href="../../pages/news/{filename}" class="vs-card" data-category="{category}" data-division="{html.escape(division, quote=True)}" data-hidden="false">
                        <div class="vs-card__img-wrapper">
                            <img src="{image_url}" alt="News Image">
                        </div>
                        <div class="vs-card__content">
                            <div class="vs-news-meta"><i class="far fa-calendar-alt"></i> {date}</div>
                            <h3 class="vs-card__title">{title}</h3>
                            <p class="vs-card__desc">{summary}</p>
                            <span class="vs-link-arrow">查看详情</span>
                        </div>
                    </a>
"""
    news_index = news_dir / 'news.html'
    inserted = insert_news_card(news_index, card_html)
    if not inserted:
        return jsonify({'success': False, 'message': '已创建资讯，但未能更新 news.html'}), 500

    return jsonify({'success': True, 'filename': filename, 'link': f'/pages/news/{filename}'})


@app.route('/api/news/visibility', methods=['POST'])
@login_required
def update_news_visibility():
    """Hide/show a news item."""
    data = request.json or {}
    link = (data.get('link') or '').strip()
    hidden = bool(data.get('hidden'))
    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400

    hidden_links = get_hidden_news_links()
    if hidden:
        hidden_links.add(link)
    else:
        hidden_links.discard(link)
    save_hidden_news_links(hidden_links)

    # Update news.html card attribute
    news_index = Path(__file__).parent / 'pages' / 'news' / 'news.html'
    if news_index.exists():
        content = news_index.read_text(encoding='utf-8')
        filename = Path(link).name
        card_pattern = build_news_card_regex(filename)
        card_match = card_pattern.search(content)
        if card_match:
            card_html = card_match.group(0)
            open_tag_match = re.search(r'<a\b[^>]*>', card_html, re.IGNORECASE)
            if open_tag_match:
                open_tag = open_tag_match.group(0)
                if 'data-hidden=' in open_tag:
                    open_tag = re.sub(
                        r'data-hidden\s*=\s*["\'](true|false)["\']',
                        f'data-hidden="{str(hidden).lower()}"',
                        open_tag,
                        flags=re.IGNORECASE
                    )
                else:
                    open_tag = open_tag[:-1] + f' data-hidden="{str(hidden).lower()}">'
                card_html = card_html[:open_tag_match.start()] + open_tag + card_html[open_tag_match.end():]
                content = content[:card_match.start()] + card_html + content[card_match.end():]
        news_index.write_text(content, encoding='utf-8')

    return jsonify({'success': True})


@app.route('/api/news/category', methods=['POST'])
@login_required
def update_news_category():
    """Quick update news category in news list card."""
    data = request.json or {}
    link = (data.get('link') or '').strip()
    category = (data.get('category') or '').strip()

    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400
    if category not in {'enterprise', 'industry', 'science'}:
        return jsonify({'success': False, 'message': '分类不合法'}), 400

    filename = Path(link).name
    news_index = Path(__file__).parent / 'pages' / 'news' / 'news.html'
    if not news_index.exists():
        return jsonify({'success': False, 'message': 'news.html 不存在'}), 404

    content = news_index.read_text(encoding='utf-8')
    card_pattern = build_news_card_regex(filename)
    card_match = card_pattern.search(content)
    if not card_match:
        return jsonify({'success': False, 'message': '未找到对应资讯卡片'}), 404

    card_html = card_match.group(0)
    open_tag_match = re.search(r'<a\b[^>]*>', card_html, re.IGNORECASE)
    if not open_tag_match:
        return jsonify({'success': False, 'message': '卡片格式异常'}), 500

    open_tag = open_tag_match.group(0)
    if 'data-category=' in open_tag:
        open_tag = re.sub(
            r'data-category\s*=\s*["\'][^"\']*["\']',
            f'data-category="{category}"',
            open_tag,
            flags=re.IGNORECASE
        )
    else:
        open_tag = open_tag[:-1] + f' data-category="{category}">'

    card_html = card_html[:open_tag_match.start()] + open_tag + card_html[open_tag_match.end():]
    content = content[:card_match.start()] + card_html + content[card_match.end():]
    news_index.write_text(content, encoding='utf-8')

    return jsonify({'success': True})


@app.route('/api/news/delete', methods=['POST'])
@login_required
def delete_news():
    """Delete a news article and remove from news list."""
    data = request.json or {}
    link = (data.get('link') or '').strip()
    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400

    filename = Path(link).name
    news_dir = Path(__file__).parent / 'pages' / 'news'
    filepath = news_dir / filename
    if filepath.exists():
        try:
            filepath.unlink()
        except Exception:
            pass

    # Remove card from news.html
    news_index = news_dir / 'news.html'
    if news_index.exists():
        content = news_index.read_text(encoding='utf-8')
        pattern = build_news_card_regex(filename)
        content, _ = pattern.subn('', content)
        news_index.write_text(content, encoding='utf-8')

    hidden_links = get_hidden_news_links()
    if link in hidden_links:
        hidden_links.discard(link)
        save_hidden_news_links(hidden_links)

    return jsonify({'success': True})


@app.route('/api/news/update', methods=['POST'])
@login_required
def update_news():
    """Update an existing news article and card."""
    data = request.json or {}
    link = (data.get('link') or '').strip()
    title = (data.get('title') or '').strip()
    date = (data.get('date') or '').strip()
    category = (data.get('category') or '').strip()
    division = (data.get('division') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))

    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400
    if not title or not date or not category or not division or not content:
        return jsonify({'success': False, 'message': '请填写标题、日期、分类、归属事业部和正文'}), 400
    if category not in {'enterprise', 'industry', 'science'}:
        return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

    if content_is_html:
        content_html = content
    else:
        content_html = render_markdown(content)

    image_url, summary = derive_news_cover_and_summary(content_html, image_url, summary)

    filename = Path(link).name
    news_dir = Path(__file__).parent / 'pages' / 'news'
    filepath = news_dir / filename
    if not filepath.exists():
        return jsonify({'success': False, 'message': '资讯文件不存在'}), 404

    article_html = build_news_article_html(title, date, image_url, content_html)
    filepath.write_text(article_html, encoding='utf-8')

    # Update card in news.html
    news_index = news_dir / 'news.html'
    if news_index.exists():
        content_text = news_index.read_text(encoding='utf-8')
        card_html = f"""
                    <a href="../../pages/news/{filename}" class="vs-card" data-category="{category}" data-division="{html.escape(division, quote=True)}" data-hidden="false">
                        <div class="vs-card__img-wrapper">
                            <img src="{image_url}" alt="News Image">
                        </div>
                        <div class="vs-card__content">
                            <div class="vs-news-meta"><i class="far fa-calendar-alt"></i> {date}</div>
                            <h3 class="vs-card__title">{title}</h3>
                            <p class="vs-card__desc">{summary}</p>
                            <span class="vs-link-arrow">查看详情</span>
                        </div>
                    </a>
"""
        pattern = build_news_card_regex(filename)
        content_text, count = pattern.subn(card_html, content_text, count=1)
        if count:
            content_text, _ = dedupe_news_cards(content_text, filename)
            news_index.write_text(content_text, encoding='utf-8')
        else:
            insert_news_card(news_index, card_html)

    return jsonify({'success': True, 'link': link})


@app.route('/api/news/detail')
@login_required
def get_news_detail():
    """Get a single news article details."""
    link = request.args.get('link', '').strip()
    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400
    filename = Path(link).name
    news_dir = Path(__file__).parent / 'pages' / 'news'
    filepath = news_dir / filename
    detail = parse_news_article_html(filepath)
    if not detail:
        return jsonify({'success': False, 'message': '资讯不存在'}), 404
    return jsonify({'success': True, 'detail': detail})


@app.route('/api/news/preview', methods=['POST'])
@login_required
def preview_news_content():
    """Render preview HTML for news content."""
    data = request.json or {}
    content = (data.get('content') or '').strip()
    is_html = bool(data.get('content_is_html', False))
    if is_html:
        html = content
    else:
        html = render_markdown(content)
    return jsonify({'success': True, 'html': html})

@app.route('/api/news/preview-page', methods=['POST'])
@login_required
def preview_news_page():
    """Render full news page HTML for 1:1 admin preview."""
    data = request.json or {}
    title = (data.get('title') or '').strip() or '标题预览'
    date = (data.get('date') or '').strip() or datetime.now().strftime('%Y-%m-%d')
    image_url = (data.get('image_url') or '').strip() or '/assets/images/logo.png'
    content = (data.get('content') or '').strip()
    is_html = bool(data.get('content_is_html', False))

    content_html = content if is_html else render_markdown(content)
    page_html = build_news_article_html(title, date, image_url, content_html)
    resize_bridge = """
<style>
/* Preview-only guard: prevent vh-based feedback loops in iframe auto-height */
html, body {
  min-height: 0 !important;
  height: auto !important;
}
body {
  overflow-x: hidden !important;
}
.article-hero {
  height: clamp(260px, 32vw, 420px) !important;
  min-height: 260px !important;
}
</style>
<div id="__preview_end_marker__" style="height:1px;width:100%;"></div>
<script>
(function () {
  function sendHeight() {
    var marker = document.getElementById('__preview_end_marker__');
    var h = 0;
    if (marker) {
      var rect = marker.getBoundingClientRect();
      h = Math.ceil((window.scrollY || window.pageYOffset || 0) + rect.top + rect.height);
    } else {
      var d = document.documentElement;
      var b = document.body;
      h = Math.max(
        d ? d.scrollHeight : 0,
        b ? b.scrollHeight : 0,
        d ? d.offsetHeight : 0,
        b ? b.offsetHeight : 0
      );
    }
    try { parent.postMessage({ type: 'news-preview-height', height: h }, '*'); } catch (e) {}
  }
  window.addEventListener('load', sendHeight);
  document.addEventListener('DOMContentLoaded', sendHeight);
  window.addEventListener('resize', sendHeight);
  setTimeout(sendHeight, 100);
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1200);
  if (document.images) {
    Array.prototype.forEach.call(document.images, function (img) {
      if (!img.complete) {
        img.addEventListener('load', sendHeight, { once: true });
        img.addEventListener('error', sendHeight, { once: true });
      }
    });
  }
  var mo = new MutationObserver(function () { sendHeight(); });
  mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
})();
</script>
"""
    if '</body>' in page_html:
        page_html = page_html.replace('</body>', resize_bridge + '\n</body>')
    else:
        page_html += resize_bridge
    return jsonify({'success': True, 'page_html': page_html})


@app.route('/api/news/ai-polish', methods=['POST'])
@login_required
def ai_polish_news():
    """Use AI to typeset news content without changing visible text."""
    def extract_visible_text(text: str, is_html: bool, collapse_whitespace: bool) -> str:
        s = text or ''
        if is_html:
            s = re.sub(r'(?is)<script.*?>.*?</script>', '', s)
            s = re.sub(r'(?is)<style.*?>.*?</style>', '', s)
            s = re.sub(r'(?i)<br\\s*/?>', '\n', s)
            s = re.sub(r'(?is)<[^>]+>', '', s)
        s = html.unescape(s)
        s = s.replace('\u00a0', ' ')
        if collapse_whitespace:
            s = re.sub(r'\s+', '', s)
        else:
            s = re.sub(r'\s+', ' ', s).strip()
        return s

    def get_first_diff_hint(before_text: str, after_text: str, window: int = 18):
        n = min(len(before_text), len(after_text))
        idx = 0
        while idx < n and before_text[idx] == after_text[idx]:
            idx += 1
        if idx >= n and len(before_text) == len(after_text):
            return 0, before_text[:window], after_text[:window]
        start = max(0, idx - window)
        end_before = min(len(before_text), idx + window)
        end_after = min(len(after_text), idx + window)
        return idx, before_text[start:end_before], after_text[start:end_after]

    def sanitize_ai_typeset_output(text: str, is_html: bool) -> str:
        s = (text or '').strip()
        if not s:
            return s
        # Remove markdown code fences if the model wrapped output.
        s = re.sub(r'^\s*```(?:html|markdown)?\s*', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s*```\s*$', '', s)

        # Remove common metadata prefixes accidentally generated by model.
        # Example:
        # 新闻标题：xxx
        # 摘要：xxx
        # 正文：...
        s = re.sub(r'^\s*(?:新闻标题|标题)\s*[：:].*?(?:\n|<br\s*/?>)+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^\s*摘要\s*[：:].*?(?:\n|<br\s*/?>)+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^\s*正文\s*[：:]\s*', '', s, flags=re.IGNORECASE)

        if is_html:
            # Some models prepend <p>标题：...</p><p>摘要：...</p>
            s = re.sub(r'^\s*<p>\s*(?:新闻标题|标题)\s*[：:].*?</p>\s*', '', s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r'^\s*<p>\s*摘要\s*[：:].*?</p>\s*', '', s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r'^\s*<p>\s*正文\s*[：:]\s*</p>\s*', '', s, flags=re.IGNORECASE | re.DOTALL)
        return s.strip()

    config = get_chatbot_config()
    if not config.get('enabled', True):
        return jsonify({'success': False, 'message': 'AI客服暂时不可用'}), 503
    if not config.get('api_key'):
        return jsonify({'success': False, 'message': 'AI客服未配置'}), 400

    data = request.json or {}
    title = (data.get('title') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', True))
    if not content:
        return jsonify({'success': False, 'message': '请输入正文内容'}), 400

    output_mode = 'HTML' if content_is_html else 'Markdown'
    system_prompt = (
        "你是一名企业资讯排版助手。你的任务只允许“排版”，不允许“改写”。"
        "必须严格保持输入正文的可见文字完全一致（不得增删改任何字、数字、标点、顺序）。"
        "可以调整段落结构、换行、列表、标题层级、强调样式。"
        f"输出格式必须是 {output_mode}。只输出排版后的正文片段本身。"
        "禁止输出“标题：”“摘要：”“正文：”等前缀，禁止输出解释。"
    )
    user_prompt = (
        f"上下文（仅供理解，不得输出）：标题={title}；摘要={summary}\n"
        f"待排版正文（仅此内容可输出）：\n{content}\n\n"
        f"请仅做排版并输出正文片段（{output_mode}）。"
    )
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]

    response, error = call_openai_api(messages, stream=False)
    if error:
        return jsonify({'success': False, 'message': error}), 500

    response = sanitize_ai_typeset_output(response or '', content_is_html)

    before_norm = extract_visible_text(content, content_is_html, collapse_whitespace=True)
    after_norm = extract_visible_text(response or '', content_is_html, collapse_whitespace=True)
    if before_norm != after_norm:
        before_human = extract_visible_text(content, content_is_html, collapse_whitespace=False)
        after_human = extract_visible_text(response or '', content_is_html, collapse_whitespace=False)
        diff_index, before_excerpt, after_excerpt = get_first_diff_hint(before_human, after_human)
        return jsonify({
            'success': True,
            'content': response or content,
            'changed_text': True,
            'warning': '检测到 AI 可能改写了部分正文，已直接替换。你可以使用“撤销替换”恢复。',
            'diff_index': diff_index,
            'before_excerpt': before_excerpt,
            'after_excerpt': after_excerpt
        })

    return jsonify({'success': True, 'content': response, 'changed_text': False})


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


# Legacy path: pages/gassensing/模板.html
# New default path: templates/gassensing-product-template.html
PRODUCT_TEMPLATE_FILES = (
    Path(__file__).parent / 'pages' / 'gassensing' / '模板.html',
    Path(__file__).parent / 'templates' / 'gassensing-product-template.html',
)
PRODUCT_AI_REFERENCE_FILE = Path(__file__).parent / 'pages' / 'gassensing' / 'mc_ld_h2.html'
PRODUCT_ADMIN_DATA_PREFIX = 'MC_PRODUCT_ADMIN_DATA:'


def get_product_template_html() -> str:
    """Load product page template HTML from legacy/new template paths."""
    for template_file in PRODUCT_TEMPLATE_FILES:
        if template_file.exists():
            return template_file.read_text(encoding='utf-8', errors='ignore')
    checked = ' | '.join(str(p) for p in PRODUCT_TEMPLATE_FILES)
    raise FileNotFoundError(f'产品模板不存在，已检查: {checked}')


def get_product_ai_reference_html() -> str:
    """Load AI generation reference HTML, fallback to generic template."""
    if PRODUCT_AI_REFERENCE_FILE.exists():
        return PRODUCT_AI_REFERENCE_FILE.read_text(encoding='utf-8', errors='ignore')
    return get_product_template_html()


def extract_product_template_placeholders(template_html: str):
    """Extract ordered unique placeholders like 【产品名字】 from template."""
    seen = set()
    ordered = []
    for token in re.findall(r'【[^】]+】', template_html or ''):
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def split_product_detail_from_editor(content_html: str):
    """Split visual editor content into two detail paragraphs."""
    source = (content_html or '').strip()
    if not source:
        return '', ''

    paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', source, re.S | re.I)
    if paragraphs:
        cleaned = []
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', '', p)
            text = html.unescape(text).strip()
            if text:
                cleaned.append(text)
        if cleaned:
            return cleaned[0], (cleaned[1] if len(cleaned) > 1 else '')

    plain = re.sub(r'(?i)<br\s*/?>', '\n', source)
    plain = re.sub(r'<[^>]+>', '', plain)
    plain = html.unescape(plain)
    parts = [x.strip() for x in re.split(r'\n{2,}|\n', plain) if x.strip()]
    if not parts:
        return '', ''
    return parts[0], (parts[1] if len(parts) > 1 else '')


def _strip_html_text(fragment: str) -> str:
    if not fragment:
        return ''
    text = re.sub(r'<[^>]+>', '', fragment, flags=re.S)
    return html.unescape(text).strip()


def extract_legacy_template_fields(page_html: str, defaults: dict):
    """Extract template-like fields from legacy product HTML structure."""
    extracted = {}
    content = page_html or ''

    def set_field(key, value):
        if key in defaults:
            val = str(value or '').strip()
            if val:
                extracted[key] = val

    def find_anchors_with_class(section_html: str, required_class: str):
        items = []
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', section_html or '', re.S | re.I):
            attrs = m.group(1) or ''
            body = m.group(2) or ''
            class_m = re.search(r'class="([^"]*)"', attrs, re.I)
            href_m = re.search(r'href="([^"]*)"', attrs, re.I)
            classes = class_m.group(1) if class_m else ''
            href = href_m.group(1) if href_m else ''
            if required_class in classes:
                items.append((href, body))
        return items

    # Product title / summary
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.S | re.I)
    if h1:
        title = _strip_html_text(h1.group(1))
        for k in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
            set_field(k, title)
    desc = re.search(r'<p[^>]*class="[^"]*vs-product-hero__desc[^"]*"[^>]*>(.*?)</p>', content, re.S | re.I)
    if desc:
        set_field('【产品描述】', _strip_html_text(desc.group(1)))

    # Main image / thumbnails
    main_img = re.search(r'<img[^>]*id="mainImage"[^>]*src="([^"]+)"', content, re.I)
    if not main_img:
        main_img = re.search(r'<div[^>]*class="[^"]*vs-gallery-main[^"]*"[^>]*>.*?<img[^>]*src="([^"]+)"', content, re.S | re.I)
    if main_img:
        set_field('【主图链接】', main_img.group(1))

    thumbs_block = re.search(r'<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>(.*?)</div>\s*</div>', content, re.S | re.I)
    if thumbs_block:
        thumbs = re.findall(r'<img[^>]*src="([^"]+)"', thumbs_block.group(1), re.I)
        for i, src in enumerate(thumbs, 1):
            set_field(f'【缩略图{i}链接】', src)

    # Features
    feature_ul = re.search(r'<ul[^>]*class="[^"]*vs-feature-list[^"]*"[^>]*>(.*?)</ul>', content, re.S | re.I)
    if feature_ul:
        features = re.findall(r'<li[^>]*>(.*?)</li>', feature_ul.group(1), re.S | re.I)
        for i, item in enumerate(features, 1):
            set_field(f'【特性{i}】', _strip_html_text(item))

    # Product detail paragraphs
    detail_block = re.search(
        r'产品详情\s*</h2>\s*<div[^>]*class="[^"]*vs-product-section__content[^"]*"[^>]*>(.*?)</div>',
        content, re.S | re.I
    )
    if detail_block:
        ps = re.findall(r'<p[^>]*>(.*?)</p>', detail_block.group(1), re.S | re.I)
        cleaned = [_strip_html_text(p) for p in ps if _strip_html_text(p)]
        if cleaned:
            set_field('【产品详情1】', cleaned[0])
        if len(cleaned) > 1:
            set_field('【产品详情2】', cleaned[1])

    # Advantages
    adv_grid = re.search(r'<div[^>]*class="[^"]*vs-advantages-grid[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</section>', content, re.S | re.I)
    if adv_grid:
        cards = re.findall(r'<div[^>]*class="[^"]*vs-advantage-card[^"]*"[^>]*>(.*?)</div>', adv_grid.group(1), re.S | re.I)
        for i, card in enumerate(cards, 1):
            h = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            if h:
                set_field(f'【优势{i}】', _strip_html_text(h.group(1)))
            if p:
                set_field(f'【优势{i}的描述】', _strip_html_text(p.group(1)))

    # Applications
    app_grid = re.search(r'<div[^>]*class="[^"]*vs-applications-grid[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</section>', content, re.S | re.I)
    if app_grid:
        cards = re.findall(r'<div[^>]*class="[^"]*vs-application-card[^"]*"[^>]*>(.*?)</div>\s*</div>', app_grid.group(1), re.S | re.I)
        for i, card in enumerate(cards, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', card, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', card, re.S | re.I)
            if img:
                set_field(f'【应用图{i}链接】', img.group(1))
            if h4:
                title = _strip_html_text(h4.group(1)).replace('•', ' ').strip()
                set_field(f'【应用{i}】', re.sub(r'\s+', ' ', title))
            if p:
                set_field(f'【应用{i}的描述】', _strip_html_text(p.group(1)))

    # Specs table
    specs_table = re.search(r'<table[^>]*class="[^"]*vs-specs-table[^"]*"[^>]*>(.*?)</table>', content, re.S | re.I)
    if specs_table:
        rows = re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>', specs_table.group(1), re.S | re.I)
        key_map = [
            (['检测原理', '传感器技术'], '【传感器技术】'),
            (['检测对象', '检测气体'], '【检测气体】'),
            (['检测范围'], '【检测范围】'),
            (['检测精度', '精度'], '【检测精度】'),
            (['响应速度', '响应时间'], '【响应时间】'),
            (['最低检测限'], '【最低检测限】'),
            (['模块功耗', '检测功耗', '功耗'], '【检测功耗】'),
            (['续航时间', '设计寿命'], '【续航时间】'),
            (['工作环境', '工作温度'], '【工作温度】'),
            (['产品尺寸', '尺寸'], '【产品尺寸】'),
            (['重量'], '【重量】')
        ]
        for raw_k, raw_v in rows:
            k = _strip_html_text(raw_k)
            v = _strip_html_text(raw_v)
            for aliases, target in key_map:
                if any(a in k for a in aliases):
                    set_field(target, v)
                    break

    # Related news
    news_section = re.search(r'<section[^>]*class="[^"]*vs-related-news[^"]*"[^>]*>(.*?)</section>', content, re.S | re.I)
    if news_section:
        items = find_anchors_with_class(news_section.group(1), 'vs-news-item')
        for i, (href, block) in enumerate(items, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', block, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', block, re.S | re.I)
            p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S | re.I)
            set_field(f'【新闻链接{i}】', href)
            if img:
                set_field(f'【新闻图片{i}链接】', img.group(1))
            if h4:
                set_field(f'【新闻标题{i}】', _strip_html_text(h4.group(1)))
            if p:
                set_field(f'【新闻描述{i}】', _strip_html_text(p.group(1)))

    # Related products
    related_section = re.search(r'<section[^>]*class="[^"]*vs-related-products[^"]*"[^>]*>(.*?)</section>', content, re.S | re.I)
    if related_section:
        items = find_anchors_with_class(related_section.group(1), 'vs-related-item')
        for i, (href, block) in enumerate(items, 1):
            img = re.search(r'<img[^>]*src="([^"]+)"', block, re.I)
            h4 = re.search(r'<h4[^>]*>(.*?)</h4>', block, re.S | re.I)
            set_field(f'【相关产品链接{i}】', href)
            if img:
                set_field(f'【相关产品图片{i}链接】', img.group(1))
            if h4:
                set_field(f'【相关产品标题{i}】', _strip_html_text(h4.group(1)))

    return extracted


def normalize_product_template_fields(raw_fields):
    """Keep only valid template placeholder key/value pairs."""
    normalized = {}
    if not isinstance(raw_fields, dict):
        return normalized
    for key, value in raw_fields.items():
        k = str(key or '').strip()
        if not k.startswith('【') or not k.endswith('】'):
            continue
        normalized[k] = str(value or '').strip()
    return normalized


def build_product_template_defaults(title: str, summary: str, image_url: str, detail1: str, detail2: str):
    """Build default values for all placeholders in product template HTML."""
    placeholders = extract_product_template_placeholders(get_product_template_html())
    image = (image_url or '/assets/images/logo.png').strip()
    defaults = {}
    for key in placeholders:
        if '链接' in key:
            if any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
                defaults[key] = image
            elif '新闻链接' in key or '相关产品链接' in key:
                defaults[key] = '#'
            else:
                defaults[key] = ''
        else:
            defaults[key] = ''

    for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
        defaults[key] = title
    defaults['【产品描述】'] = summary
    defaults['【产品详情1】'] = detail1
    defaults['【产品详情2】'] = detail2
    defaults['【主图链接】'] = image
    defaults['【缩略图1链接】'] = image
    return defaults


def sanitize_product_template_value(key: str, value: str) -> str:
    """Escape placeholder values safely for HTML/template substitution."""
    v = (value or '').strip()
    if not v:
        if '链接' in key:
            if any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
                return '/assets/images/logo.png'
            if '新闻链接' in key or '相关产品链接' in key:
                return '#'
        return ''
    if '链接' in key and any(tag in key for tag in ['图片', '主图', '缩略图', '详情图', '应用图']):
        if v.lower().startswith('assets/'):
            v = '/' + v
    if '链接' in key:
        return html.escape(v, quote=True)
    return html.escape(v, quote=True).replace('\n', '<br>')


def inject_product_meta_tags(page_html: str, title: str, short_name: str, image_url: str, summary: str, category: str) -> str:
    """Inject product-* meta tags for admin scanner compatibility."""
    safe_title = html.escape(title or '', quote=True)
    safe_short_name = html.escape(short_name or '', quote=True)
    safe_image = html.escape(image_url or '', quote=True)
    safe_summary = html.escape(summary or '', quote=True)
    safe_category = html.escape(category or 'module', quote=True)

    meta_block = f"""
    <meta name="product-name" content="{safe_title}" />
    <meta name="product-short-name" content="{safe_short_name}" />
    <meta name="product-image" content="{safe_image}" />
    <meta name="product-description" content="{safe_summary}" />
    <meta name="product-category" content="{safe_category}" />
"""
    if '</head>' in page_html:
        return page_html.replace('</head>', meta_block + '\n</head>', 1)
    return page_html + meta_block


def encode_product_admin_data(payload: dict) -> str:
    """Encode admin editor state into HTML comment for future edits."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
    return f'<!-- {PRODUCT_ADMIN_DATA_PREFIX}{encoded} -->'


def decode_product_admin_data(page_html: str):
    """Decode embedded admin editor payload from HTML comment."""
    m = re.search(r'<!--\s*' + re.escape(PRODUCT_ADMIN_DATA_PREFIX) + r'([A-Za-z0-9+/=_-]+)\s*-->', page_html or '')
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group(1)).decode('utf-8')
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def render_gassensing_product_html(
    title: str,
    short_name: str,
    category: str,
    image_url: str,
    summary: str,
    content_html: str,
    template_fields=None
):
    """Render product page based on resolved product template HTML."""
    safe_title = (title or '').strip()
    safe_short_name = (short_name or safe_title).strip()
    safe_category = (category or 'module').strip()
    safe_image = (image_url or '/assets/images/logo.png').strip()
    safe_summary = (summary or '').strip()
    safe_content = (content_html or '').strip()

    detail1, detail2 = split_product_detail_from_editor(safe_content)
    defaults = build_product_template_defaults(
        title=safe_title,
        summary=safe_summary,
        image_url=safe_image,
        detail1=detail1,
        detail2=detail2
    )
    incoming = normalize_product_template_fields(template_fields)
    placeholders = extract_product_template_placeholders(get_product_template_html())

    resolved = dict(defaults)
    for key in placeholders:
        if key in incoming and incoming[key]:
            resolved[key] = incoming[key]

    # Force key fields to match form inputs.
    for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
        resolved[key] = safe_title
    resolved['【产品描述】'] = safe_summary
    resolved['【主图链接】'] = safe_image
    if not resolved.get('【缩略图1链接】'):
        resolved['【缩略图1链接】'] = safe_image
    if not resolved.get('【产品详情1】'):
        resolved['【产品详情1】'] = detail1
    if not resolved.get('【产品详情2】'):
        resolved['【产品详情2】'] = detail2

    page_html = get_product_template_html()
    for key in placeholders:
        page_html = page_html.replace(key, sanitize_product_template_value(key, resolved.get(key, '')))

    page_html = inject_product_meta_tags(
        page_html=page_html,
        title=safe_title,
        short_name=safe_short_name,
        image_url=safe_image,
        summary=safe_summary,
        category=safe_category
    )

    admin_payload = {
        'version': 2,
        'title': safe_title,
        'short_name': safe_short_name,
        'category': safe_category,
        'image_url': safe_image,
        'summary': safe_summary,
        'content_html': safe_content,
        'template_fields': resolved
    }
    marker = encode_product_admin_data(admin_payload)
    if '</body>' in page_html:
        page_html = page_html.replace('</body>', marker + '\n</body>', 1)
    else:
        page_html += '\n' + marker

    return page_html, resolved


def parse_gassensing_product_detail(filepath: Path):
    """Parse product detail page fields for admin editing."""
    if not filepath.exists():
        return None

    content = filepath.read_text(encoding='utf-8', errors='ignore')
    admin_data = decode_product_admin_data(content)
    if isinstance(admin_data, dict):
        return {
            'id': filepath.stem,
            'title': (admin_data.get('title') or '').strip(),
            'short_name': (admin_data.get('short_name') or '').strip(),
            'category': (admin_data.get('category') or 'module').strip(),
            'image_url': (admin_data.get('image_url') or '').strip(),
            'summary': (admin_data.get('summary') or '').strip(),
            'content_html': (admin_data.get('content_html') or '').strip(),
            'template_fields': normalize_product_template_fields(admin_data.get('template_fields', {}))
        }

    # Backward compatible fallback for old pages without embedded admin data.
    base = extract_product_meta_from_html(filepath) or {}
    title = (base.get('name') or '').strip()
    short_name = (base.get('shortName') or '').strip()
    category = (base.get('category') or 'module').strip()
    image_url = (base.get('image') or '').strip()
    summary = (base.get('description') or '').strip()

    detail_match = re.search(
        r'<h3\s+class="section-header">\s*产品详情\s*</h3>\s*<div[^>]*>(.*?)</div>',
        content,
        re.S | re.I
    )
    if detail_match:
        content_html = detail_match.group(1).strip()
    else:
        article_match = re.search(r'<main\b[^>]*>(.*?)</main>', content, re.S | re.I)
        content_html = (article_match.group(1).strip() if article_match else '')

    detail1, detail2 = split_product_detail_from_editor(content_html)
    template_fields = build_product_template_defaults(
        title=title,
        summary=summary,
        image_url=image_url,
        detail1=detail1,
        detail2=detail2
    )
    legacy_extracted = extract_legacy_template_fields(content, template_fields)
    if legacy_extracted:
        template_fields.update(legacy_extracted)
    return {
        'id': filepath.stem,
        'title': title,
        'short_name': short_name,
        'category': category,
        'image_url': image_url,
        'summary': summary,
        'content_html': content_html,
        'template_fields': template_fields
    }


@app.route('/api/products/template/placeholders')
@login_required
def get_product_template_placeholders_api():
    """Get placeholder list from product template for admin visual form."""
    placeholders = extract_product_template_placeholders(get_product_template_html())
    return jsonify({'items': placeholders, 'count': len(placeholders)})


def call_openai_api_sync_with_custom_config(messages, config):
    """Call OpenAI-compatible API with explicit config."""
    api_key = (config or {}).get('api_key', '')
    api_base = (config or {}).get('api_base', 'https://api.openai.com/v1')
    model = (config or {}).get('model', 'gpt-4o-mini')

    if not api_key:
        return None, "产品页编程AI未配置 API Key"

    api_url = api_base.rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'messages': messages,
        'stream': False
    }
    connect_timeout = 20
    read_timeout = 300
    attempts = 2
    try:
        if REQUESTS_SUPPORT:
            last_error = None
            for i in range(attempts):
                try:
                    response = requests.post(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=(connect_timeout, read_timeout)
                    )
                except requests.exceptions.ReadTimeout:
                    last_error = f"上游响应超时（>{read_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"
                except requests.exceptions.ConnectTimeout:
                    last_error = f"连接超时（>{connect_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"

                if response.status_code != 200:
                    detail = ''
                    try:
                        detail = (response.text or '').strip()
                    except Exception:
                        detail = ''
                    if detail:
                        detail = detail[:500]
                    return None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                result = response.json()
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content'], None
                return None, "API返回格式错误"
            return None, f"API调用失败: {last_error or '未知错误'}"
        if HTTPX_SUPPORT:
            last_error = None
            timeout_obj = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=60, pool=60)
            for i in range(attempts):
                try:
                    response = httpx.post(api_url, json=payload, headers=headers, timeout=timeout_obj)
                except httpx.ReadTimeout:
                    last_error = f"上游响应超时（>{read_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"
                except httpx.ConnectTimeout:
                    last_error = f"连接超时（>{connect_timeout}s）"
                    if i < attempts - 1:
                        continue
                    return None, f"API调用失败: {last_error}"

                if response.status_code != 200:
                    detail = ''
                    try:
                        detail = (response.text or '').strip()
                    except Exception:
                        detail = ''
                    if detail:
                        detail = detail[:500]
                    return None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                result = response.json()
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content'], None
                return None, "API返回格式错误"
            return None, f"API调用失败: {last_error or '未知错误'}"
        return None, "缺少HTTP客户端库(requests或httpx)"
    except Exception as e:
        print(f"Product AI API error: {e}")
        return None, f"API调用失败: {str(e)}"


def _extract_stream_chunk_text(chunk_obj):
    """Extract text delta from OpenAI-compatible stream chunk."""
    if not isinstance(chunk_obj, dict):
        return ''
    choices = chunk_obj.get('choices') or []
    if not choices:
        return ''
    delta = choices[0].get('delta') or {}
    content = delta.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str):
                    parts.append(text)
        return ''.join(parts)
    return ''


def call_openai_api_stream_with_custom_config(messages, config):
    """Call OpenAI-compatible stream API with explicit config."""
    api_key = (config or {}).get('api_key', '')
    api_base = (config or {}).get('api_base', 'https://api.openai.com/v1')
    model = (config or {}).get('model', 'gpt-4o-mini')

    if not api_key:
        return None, "产品页编程AI未配置 API Key"

    api_url = api_base.rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'messages': messages,
        'stream': True
    }
    connect_timeout = 20
    read_timeout = 300

    if HTTPX_SUPPORT:
        def gen_httpx():
            try:
                timeout_obj = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=60, pool=60)
                with httpx.Client(timeout=timeout_obj) as client:
                    with client.stream('POST', api_url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            detail = (response.text or '').strip()
                            if detail:
                                detail = detail[:500]
                            yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                            return
                        for line in response.iter_lines():
                            if not line:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode('utf-8', errors='ignore')
                            if not line.startswith('data: '):
                                continue
                            data = line[6:].strip()
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            text = _extract_stream_chunk_text(chunk)
                            if text:
                                yield text, None
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_httpx()

    if REQUESTS_SUPPORT:
        def gen_requests():
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=(connect_timeout, read_timeout)
                )
                if response.status_code != 200:
                    detail = (response.text or '').strip()
                    if detail:
                        detail = detail[:500]
                    yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                    return
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode('utf-8', errors='ignore')
                    if not line.startswith('data: '):
                        continue
                    data = line[6:].strip()
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_stream_chunk_text(chunk)
                    if text:
                        yield text, None
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_requests()

    return None, "缺少HTTP客户端库(requests或httpx)"


def parse_json_object_from_ai_text(text: str):
    """Extract first valid JSON object from AI text."""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('AI返回为空')
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError('未找到 JSON 对象')
    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError('JSON 顶层必须是对象')
    return obj


def extract_html_from_ai_text(text: str, title: str = '产品页面'):
    """Extract HTML document from model output, with robust fallbacks."""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('AI返回为空')
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

    # Try JSON wrapper: {"html":"..."} / {"page_html":"..."} / {"content":"..."}
    try:
        obj = parse_json_object_from_ai_text(raw)
        if isinstance(obj, dict):
            for k in ('page_html', 'html', 'content'):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    raw = v.strip()
                    break
    except Exception:
        pass

    lower = raw.lower()
    idx = lower.find('<!doctype html')
    if idx < 0:
        idx = lower.find('<html')
    html_text = raw[idx:].strip() if idx >= 0 else raw
    if '<html' in html_text.lower():
        return html_text

    # If model returns body/main fragment, wrap to full HTML
    fragment = html_text.strip()
    if any(tag in fragment.lower() for tag in ('<body', '<main', '<section', '<div', '<h1', '<h2', '<p')):
        page = (
            "<!DOCTYPE html>\n"
            "<html lang=\"zh-CN\">\n"
            "<head>\n"
            "  <meta charset=\"UTF-8\">\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"  <title>{html.escape(title or '产品页面')}</title>\n"
            "</head>\n"
            "<body>\n"
            f"{fragment}\n"
            "</body>\n"
            "</html>"
        )
        return page

    preview = re.sub(r'\s+', ' ', raw)[:220]
    raise ValueError(f'AI未返回可识别的HTML（片段预览: {preview}）')


def build_product_content_html_from_template_fields(template_fields: dict):
    """Build editor content_html from template fields for admin edit backfill."""
    d1 = str((template_fields or {}).get('【产品详情1】', '') or '').strip()
    d2 = str((template_fields or {}).get('【产品详情2】', '') or '').strip()
    parts = []
    if d1:
        parts.append(f"<p>{html.escape(d1)}</p>")
    if d2:
        parts.append(f"<p>{html.escape(d2)}</p>")
    if not parts:
        parts.append("<p>请填写产品详情内容</p>")
    return ''.join(parts)


def _normalize_text_lines(value):
    """Normalize multiline / comma-separated text into clean non-empty lines."""
    if value is None:
        return []
    if isinstance(value, list):
        raw = '\n'.join([str(x or '') for x in value])
    else:
        raw = str(value)
    raw = raw.replace('\r', '\n')
    raw = raw.replace('，', ',').replace('；', ';')
    parts = re.split(r'[\n,;]+', raw)
    return [p.strip() for p in parts if p and p.strip()]


def _build_product_ai_html_messages(
    title,
    short_name,
    category,
    image_url,
    summary,
    context_text,
    detail_image_urls='',
    news_urls='',
    related_product_urls=''
):
    """Build system/user messages for product full-html generation."""
    ai_cfg = get_product_page_ai_config()
    reference_html = get_product_ai_reference_html()
    system_prompt = get_product_page_ai_system_prompt()
    detail_images = _normalize_text_lines(detail_image_urls)
    news_links = _normalize_text_lines(news_urls)
    related_links = _normalize_text_lines(related_product_urls)
    detail_images_block = '\n'.join([f"  - {u}" for u in detail_images]) if detail_images else '  - （无）'
    news_links_block = '\n'.join([f"  - {u}" for u in news_links]) if news_links else '  - （无）'
    related_links_block = '\n'.join([f"  - {u}" for u in related_links]) if related_links else '  - （无）'
    user_prompt = (
        "请基于“参考样例HTML”和“产品资料”直接生成完整产品页HTML文件。\n"
        "硬性要求：\n"
        "1) 输出必须是完整HTML文档（包含 <!DOCTYPE html> ... </html>）。\n"
        "2) 请直接开始写代码，代码写完后不要添加任何其他内容。\n"
        "3) 只输出HTML，不要解释、不要Markdown代码块。\n"
        "4) 必须参考模板结构与样式，保留可复用的布局和资源引用，不要删掉关键脚本/样式。\n"
        "5) 内容按资料进行替换与完善，不能编造资质证书、认证、客户案例。\n"
        "6) 必须确保页面中有可见图片：主图、详情图、新闻图、相关产品图至少要有可显示来源。\n"
        "7) 若某类图片URL未提供，可优先复用主图或详情图首图，最后兜底 /assets/images/logo.png。\n"
        "8) 相关新闻与相关产品区块必须保留，并尽量使用提供的 URL 生成链接。\n\n"
        "9) 相关新闻区块必须包含 `.vs-related-news .vs-news-grid` 结构。\n"
        "10) 相关产品区块必须包含 `.vs-related-products .vs-related-grid` 结构。\n"
        "11) 必须保留 `<script src=\"/assets/js/nav-loader.js\"></script>` 以支持动态数据填充。\n\n"
        f"产品资料：\n"
        f"- 产品标题: {title}\n"
        f"- 产品简称: {short_name}\n"
        f"- 产品分类: {category}\n"
        f"- 产品主图URL: {image_url or '/assets/images/logo.png'}\n"
        f"- 产品摘要: {summary or '（请你生成）'}\n"
        f"- 产品详情图片URL列表:\n{detail_images_block}\n"
        f"- 相关新闻URL列表:\n{news_links_block}\n"
        f"- 相关产品URL列表:\n{related_links_block}\n"
        f"- 详细补充资料:\n{context_text or '（无）'}\n\n"
        "参考样例HTML如下（请以此为参考生成最终完整HTML）:\n"
        f"{reference_html}"
    )
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]
    return messages, ai_cfg


def _ensure_html_tail(page_html: str) -> str:
    """Best-effort close missing body/html tail when output is truncated."""
    txt = (page_html or '').strip()
    if '<html' not in txt.lower():
        return txt
    low = txt.lower()
    if '</body>' not in low:
        txt += '\n</body>'
        low = txt.lower()
    if '</html>' not in low:
        txt += '\n</html>'
    return txt


def _is_html_complete(page_html: str) -> bool:
    return '</html>' in (page_html or '').lower()


def _continuation_prompt():
    return (
        "你上一次输出被截断。请仅从中断处继续输出剩余 HTML 代码，"
        "不要重复之前已输出内容，不要解释，直到输出到 </html> 结束。"
    )


def _insert_before_last_tag(text: str, tag: str, snippet: str) -> str:
    pattern = re.compile(rf'</{re.escape(tag)}\s*>', re.I)
    matches = list(pattern.finditer(text or ''))
    if matches:
        m = matches[-1]
        return (text or '')[:m.start()] + snippet + '\n' + (text or '')[m.start():]
    return (text or '') + '\n' + snippet


def _build_related_section_html(section_class: str, title: str, grid_class: str, loading_text: str) -> str:
    return (
        f'<section class="{section_class}">\n'
        '    <div class="vs-container">\n'
        f'        <h2>{title}</h2>\n'
        f'        <div class="{grid_class}">\n'
        f'            <p style="grid-column: 1/-1; text-align:center; color:#64748b;">{loading_text}</p>\n'
        '        </div>\n'
        '    </div>\n'
        '</section>'
    )


def ensure_product_dynamic_sections(page_html: str) -> str:
    """Post-process AI HTML to ensure related-news/products dynamic blocks are renderable."""
    text = str(page_html or '')
    if not text.strip():
        return text

    if not re.search(r'<script[^>]*src=["\']/assets/js/nav-loader\.js["\']', text, re.I):
        nav_script = '<script src="/assets/js/nav-loader.js"></script>'
        if re.search(r'</head\s*>', text, re.I):
            text = _insert_before_last_tag(text, 'head', nav_script)
        else:
            text = _insert_before_last_tag(text, 'body', nav_script)

    checks = [
        ('vs-related-news', '相关新闻', 'vs-news-grid', '正在加载相关新闻...'),
        ('vs-related-products', '相关产品', 'vs-related-grid', '正在加载相关产品...')
    ]

    for section_class, title, grid_class, loading_text in checks:
        section_pattern = re.compile(
            rf'<section[^>]*class=["\'][^"\']*\b{re.escape(section_class)}\b[^"\']*["\'][^>]*>.*?</section>',
            re.S | re.I
        )
        grid_pattern = re.compile(
            rf'class=["\'][^"\']*\b{re.escape(grid_class)}\b[^"\']*["\']',
            re.I
        )
        section_html = _build_related_section_html(section_class, title, grid_class, loading_text)
        m = section_pattern.search(text)
        if not m:
            if re.search(r'</main\s*>', text, re.I):
                text = _insert_before_last_tag(text, 'main', section_html)
            else:
                text = _insert_before_last_tag(text, 'body', section_html)
            continue
        if not grid_pattern.search(m.group(0)):
            text = text[:m.start()] + section_html + text[m.end():]

    return text


@app.route('/api/products/ai-generate-html', methods=['POST'])
@login_required
def ai_generate_product_html():
    """Generate full product HTML by AI with template.html as reference."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or 'sensor').strip()
    image_url = (data.get('image_url') or '').strip()
    detail_image_urls = (data.get('detail_image_urls') or '').strip()
    news_urls = (data.get('news_urls') or '').strip()
    related_product_urls = (data.get('related_product_urls') or '').strip()
    summary = (data.get('summary') or '').strip()
    context_text = (data.get('context_text') or '').strip()

    if not title or not short_name:
        return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

    messages, ai_cfg = _build_product_ai_html_messages(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url,
        summary=summary,
        context_text=context_text,
        detail_image_urls=detail_image_urls,
        news_urls=news_urls,
        related_product_urls=related_product_urls
    )
    if not ai_cfg.get('enabled', False):
        return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
    if not ai_cfg.get('api_key'):
        return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

    response_text = ''
    attempts_used = 0
    for _ in range(3):
        attempts_used += 1
        piece, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
        if error:
            return jsonify({'success': False, 'message': error}), 502
        piece = piece or ''
        response_text += piece
        if _is_html_complete(response_text):
            break
        messages.append({'role': 'assistant', 'content': piece})
        messages.append({'role': 'user', 'content': _continuation_prompt()})

    try:
        page_html = extract_html_from_ai_text(_ensure_html_tail(response_text), title=title)
        page_html = ensure_product_dynamic_sections(page_html)
    except Exception as e:
        return jsonify({'success': False, 'message': f'AI输出HTML解析失败: {str(e)}'}), 500

    return jsonify({'success': True, 'page_html': page_html, 'attempts_used': attempts_used})


@app.route('/api/products/ai-upload-images', methods=['POST'])
@login_required
def ai_upload_product_images():
    """Upload AI product images into pages/gassensing/<MODEL>/ folder."""
    slug = (request.form.get('slug') or '').strip().lower()
    short_name = (request.form.get('short_name') or '').strip()
    files = request.files.getlist('files')

    if not slug or not re.fullmatch(r'[a-z0-9_]+', slug):
        return jsonify({'success': False, 'message': '请提供合法链接标识（小写字母/数字/下划线）'}), 400
    if not files:
        return jsonify({'success': False, 'message': '请至少上传一张图片'}), 400

    slug_dash = slug.replace('_', '-')
    model_folder = re.sub(r'[^A-Za-z0-9._-]+', '', short_name.upper()) if short_name else ''
    if not model_folder:
        model_folder = slug_dash.upper()

    target_dir = Path(__file__).parent / 'pages' / 'gassensing' / model_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(target_dir.glob(f'{slug_dash}-product-*.*'))
    counter = len(existing) + 1
    urls = []

    for uploaded in files:
        original_name = uploaded.filename or ''
        mime = (uploaded.mimetype or uploaded.content_type or '').lower()
        sample = b''
        try:
            stream = uploaded.stream
            current_pos = stream.tell()
            sample = stream.read(1024)
            stream.seek(current_pos)
        except Exception:
            sample = b''

        ext = normalize_ai_product_image_extension(original_name, mime, sample)
        if not ext:
            display_ext = Path((original_name or '')).suffix.lower() or '未知'
            return jsonify({
                'success': False,
                'message': (
                    f'不支持的图片格式: {display_ext}。'
                    '支持 PNG/JPG/JPEG/WEBP/BMP/GIF/SVG/TIF/TIFF/HEIC/HEIF/AVIF'
                )
            }), 400

        mime_clean = (mime or '').split(';')[0].strip().lower()
        if mime_clean and mime_clean.startswith('image/') and mime_clean not in ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES:
            inferred_from_mime = infer_ai_product_image_extension_from_mime(mime_clean)
            if not inferred_from_mime:
                return jsonify({'success': False, 'message': f'文件类型不受支持: {mime_clean}'}), 400

        while True:
            filename = f'{slug_dash}-product-{counter:02d}{ext}'
            filepath = target_dir / filename
            if not filepath.exists():
                break
            counter += 1

        uploaded.save(str(filepath))
        urls.append(f'/pages/gassensing/{model_folder}/{filename}')
        counter += 1

    return jsonify({'success': True, 'folder': model_folder, 'urls': urls})


@app.route('/api/products/ai-generate-html-stream', methods=['POST'])
@login_required
def ai_generate_product_html_stream():
    """Generate full product HTML by AI with streaming + auto continuation."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or 'sensor').strip()
    image_url = (data.get('image_url') or '').strip()
    detail_image_urls = (data.get('detail_image_urls') or '').strip()
    news_urls = (data.get('news_urls') or '').strip()
    related_product_urls = (data.get('related_product_urls') or '').strip()
    summary = (data.get('summary') or '').strip()
    context_text = (data.get('context_text') or '').strip()

    if not title or not short_name:
        return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

    messages, ai_cfg = _build_product_ai_html_messages(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url,
        summary=summary,
        context_text=context_text,
        detail_image_urls=detail_image_urls,
        news_urls=news_urls,
        related_product_urls=related_product_urls
    )
    if not ai_cfg.get('enabled', False):
        return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
    if not ai_cfg.get('api_key'):
        return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

    def generate():
        accumulated = ''
        for round_idx in range(3):
            if round_idx > 0:
                yield f"data: {json.dumps({'type': 'retry', 'attempt': round_idx + 1, 'message': '检测到输出被截断，正在自动续写...' }, ensure_ascii=False)}\n\n"

            stream = call_openai_api_stream_with_custom_config(messages, ai_cfg)
            if isinstance(stream, tuple):
                _, err = stream
                yield f"data: {json.dumps({'type': 'error', 'error': err or 'API调用失败'}, ensure_ascii=False)}\n\n"
                return

            round_text = ''
            for chunk, err in stream:
                if err:
                    yield f"data: {json.dumps({'type': 'error', 'error': err}, ensure_ascii=False)}\n\n"
                    return
                if not chunk:
                    continue
                round_text += chunk
                accumulated += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

            if _is_html_complete(accumulated):
                break

            messages.append({'role': 'assistant', 'content': round_text or accumulated[-4000:]})
            messages.append({'role': 'user', 'content': _continuation_prompt()})

        accumulated = _ensure_html_tail(accumulated)
        try:
            page_html = extract_html_from_ai_text(accumulated, title=title)
            page_html = ensure_product_dynamic_sections(page_html)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'AI输出HTML解析失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done', 'page_html': page_html}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


def _build_product_ai_revise_messages(
    title,
    category,
    image_url,
    detail_image_urls,
    news_urls,
    related_product_urls,
    summary,
    context_text,
    instruction,
    current_html
):
    """Build system/user messages for product HTML revise workflow."""
    system_prompt = get_product_page_ai_system_prompt()
    detail_images = _normalize_text_lines(detail_image_urls)
    news_links = _normalize_text_lines(news_urls)
    related_links = _normalize_text_lines(related_product_urls)
    detail_images_block = '\n'.join([f"  - {u}" for u in detail_images]) if detail_images else '  - （无）'
    news_links_block = '\n'.join([f"  - {u}" for u in news_links]) if news_links else '  - （无）'
    related_links_block = '\n'.join([f"  - {u}" for u in related_links]) if related_links else '  - （无）'
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': (
            "请基于下方“当前HTML代码”和“修改意见”输出一份修改后的完整HTML。\n"
            "要求：\n"
            "1) 只输出完整HTML代码，不要解释，不要Markdown代码块。\n"
            "2) 尽量保留原有结构和样式，仅按修改意见调整。\n"
            "3) 输出必须从 <!DOCTYPE html> 或 <html> 开始，并在 </html> 结束。\n\n"
            "4) 相关新闻区块必须保留 `.vs-related-news .vs-news-grid` 结构。\n"
            "5) 相关产品区块必须保留 `.vs-related-products .vs-related-grid` 结构。\n"
            "6) 必须保留 `<script src=\"/assets/js/nav-loader.js\"></script>`。\n\n"
            "产品资料补充（用于保证图片和链接完整，可结合修改意见一起处理）：\n"
            f"- 产品标题: {title}\n"
            f"- 产品分类: {category}\n"
            f"- 产品主图URL: {image_url or '/assets/images/logo.png'}\n"
            f"- 产品摘要: {summary or '（未填写）'}\n"
            f"- 产品详情图片URL列表:\n{detail_images_block}\n"
            f"- 相关新闻URL列表:\n{news_links_block}\n"
            f"- 相关产品URL列表:\n{related_links_block}\n"
            f"- 详细补充资料:\n{context_text or '（无）'}\n\n"
            f"修改意见：\n{instruction}\n\n"
            f"当前HTML代码：\n{current_html}"
        )}
    ]


@app.route('/api/products/ai-revise-html-stream', methods=['POST'])
@login_required
def ai_revise_product_html_stream():
    """Revise already-generated HTML by user instruction (streaming)."""
    data = request.json or {}
    title = (data.get('title') or '').strip() or '产品页面'
    category = (data.get('category') or 'sensor').strip()
    image_url = (data.get('image_url') or '').strip()
    detail_image_urls = (data.get('detail_image_urls') or '').strip()
    news_urls = (data.get('news_urls') or '').strip()
    related_product_urls = (data.get('related_product_urls') or '').strip()
    summary = (data.get('summary') or '').strip()
    context_text = (data.get('context_text') or '').strip()
    instruction = (data.get('instruction') or '').strip()
    current_html = (data.get('current_html') or '').strip()

    if not instruction:
        return jsonify({'success': False, 'message': '请先填写修改意见'}), 400
    if '<html' not in current_html.lower():
        return jsonify({'success': False, 'message': '当前HTML为空或格式无效，请先生成HTML'}), 400

    ai_cfg = get_product_page_ai_config()
    if not ai_cfg.get('enabled', False):
        return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
    if not ai_cfg.get('api_key'):
        return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

    messages = _build_product_ai_revise_messages(
        title=title,
        category=category,
        image_url=image_url,
        detail_image_urls=detail_image_urls,
        news_urls=news_urls,
        related_product_urls=related_product_urls,
        summary=summary,
        context_text=context_text,
        instruction=instruction,
        current_html=current_html
    )

    def generate():
        accumulated = ''
        for round_idx in range(3):
            if round_idx > 0:
                yield f"data: {json.dumps({'type': 'retry', 'attempt': round_idx + 1, 'message': '检测到输出被截断，正在自动续写...' }, ensure_ascii=False)}\n\n"

            stream = call_openai_api_stream_with_custom_config(messages, ai_cfg)
            if isinstance(stream, tuple):
                _, err = stream
                yield f"data: {json.dumps({'type': 'error', 'error': err or 'API调用失败'}, ensure_ascii=False)}\n\n"
                return

            round_text = ''
            for chunk, err in stream:
                if err:
                    yield f"data: {json.dumps({'type': 'error', 'error': err}, ensure_ascii=False)}\n\n"
                    return
                if not chunk:
                    continue
                round_text += chunk
                accumulated += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

            if _is_html_complete(accumulated):
                break

            messages.append({'role': 'assistant', 'content': round_text or accumulated[-4000:]})
            messages.append({'role': 'user', 'content': _continuation_prompt()})

        accumulated = _ensure_html_tail(accumulated)
        try:
            page_html = extract_html_from_ai_text(accumulated, title=title)
            page_html = ensure_product_dynamic_sections(page_html)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'AI输出HTML解析失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done', 'page_html': page_html}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/api/products/ai-revise-html', methods=['POST'])
@login_required
def ai_revise_product_html():
    """Revise already-generated HTML by user instruction (non-stream fallback)."""
    data = request.json or {}
    title = (data.get('title') or '').strip() or '产品页面'
    category = (data.get('category') or 'sensor').strip()
    image_url = (data.get('image_url') or '').strip()
    detail_image_urls = (data.get('detail_image_urls') or '').strip()
    news_urls = (data.get('news_urls') or '').strip()
    related_product_urls = (data.get('related_product_urls') or '').strip()
    summary = (data.get('summary') or '').strip()
    context_text = (data.get('context_text') or '').strip()
    instruction = (data.get('instruction') or '').strip()
    current_html = (data.get('current_html') or '').strip()

    if not instruction:
        return jsonify({'success': False, 'message': '请先填写修改意见'}), 400
    if '<html' not in current_html.lower():
        return jsonify({'success': False, 'message': '当前HTML为空或格式无效，请先生成HTML'}), 400

    ai_cfg = get_product_page_ai_config()
    if not ai_cfg.get('enabled', False):
        return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
    if not ai_cfg.get('api_key'):
        return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

    messages = _build_product_ai_revise_messages(
        title=title,
        category=category,
        image_url=image_url,
        detail_image_urls=detail_image_urls,
        news_urls=news_urls,
        related_product_urls=related_product_urls,
        summary=summary,
        context_text=context_text,
        instruction=instruction,
        current_html=current_html
    )

    response_text = ''
    attempts_used = 0
    for _ in range(3):
        attempts_used += 1
        piece, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
        if error:
            return jsonify({'success': False, 'message': error}), 502
        piece = piece or ''
        response_text += piece
        if _is_html_complete(response_text):
            break
        messages.append({'role': 'assistant', 'content': piece or response_text[-4000:]})
        messages.append({'role': 'user', 'content': _continuation_prompt()})

    try:
        page_html = extract_html_from_ai_text(_ensure_html_tail(response_text), title=title)
        page_html = ensure_product_dynamic_sections(page_html)
    except Exception as e:
        return jsonify({'success': False, 'message': f'AI输出HTML解析失败: {str(e)}'}), 500

    return jsonify({'success': True, 'page_html': page_html, 'attempts_used': attempts_used})


@app.route('/api/products/ai-create-html', methods=['POST'])
@login_required
def ai_create_product_from_html():
    """Save AI-generated full HTML as a product page file."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    slug = (data.get('slug') or '').strip()
    page_html = (data.get('page_html') or '').strip()

    if not title or not category or not slug:
        return jsonify({'success': False, 'message': '请填写标题、分类和链接标识'}), 400
    if not re.fullmatch(r'[a-z0-9_]+', slug):
        return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400
    if '<html' not in page_html.lower():
        return jsonify({'success': False, 'message': 'HTML源码无效，请先生成完整HTML'}), 400
    allowed_categories = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}
    if category not in allowed_categories:
        return jsonify({'success': False, 'message': '产品分类不合法'}), 400

    if not short_name:
        short_name = slug.replace('_', '-').upper()
    if not summary:
        summary = title

    page_html = ensure_product_dynamic_sections(page_html)
    enriched_html = inject_product_meta_tags(
        page_html=page_html,
        title=title,
        short_name=short_name,
        image_url=image_url or '/assets/images/logo.png',
        summary=summary,
        category=category
    )

    admin_payload = {
        'version': 3,
        'title': title,
        'short_name': short_name,
        'category': category,
        'image_url': image_url or '/assets/images/logo.png',
        'summary': summary,
        'content_html': '',
        'template_fields': {},
        'source': 'ai-full-html'
    }
    marker = encode_product_admin_data(admin_payload)
    if '</body>' in enriched_html:
        enriched_html = enriched_html.replace('</body>', marker + '\n</body>', 1)
    else:
        enriched_html += '\n' + marker

    products_dir = Path(__file__).parent / 'pages' / 'gassensing'
    products_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{slug}.html'
    filepath = products_dir / filename
    if filepath.exists():
        return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409
    filepath.write_text(enriched_html, encoding='utf-8')
    return jsonify({'success': True, 'filename': filename, 'link': f'/pages/gassensing/{filename}'})


@app.route('/api/products/ai-generate-fields', methods=['POST'])
@login_required
def ai_generate_product_template_fields():
    """Generate template fields by product-page coding AI."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or 'sensor').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    context_text = (data.get('context_text') or '').strip()

    if not title or not short_name:
        return jsonify({'success': False, 'message': '请至少填写产品标题和产品简称'}), 400

    ai_cfg = get_product_page_ai_config()
    if not ai_cfg.get('enabled', False):
        return jsonify({'success': False, 'message': '产品页编程 AI 未启用，请先在 AI 客服设置中开启'}), 400
    if not ai_cfg.get('api_key'):
        return jsonify({'success': False, 'message': '产品页编程 AI 未配置 API Key'}), 400

    placeholders = extract_product_template_placeholders(get_product_template_html())
    defaults = build_product_template_defaults(
        title=title,
        summary=summary,
        image_url=image_url or '/assets/images/logo.png',
        detail1='',
        detail2=''
    )
    system_prompt = get_product_page_ai_system_prompt()
    user_prompt = (
        "请根据以下资料，生成模板字段 JSON。\n"
        f"产品标题: {title}\n"
        f"产品简称: {short_name}\n"
        f"产品分类: {category}\n"
        f"封面图: {image_url}\n"
        f"产品摘要: {summary}\n\n"
        f"补充资料:\n{context_text or '（无）'}\n\n"
        f"可用占位符列表（只能使用这些 key）:\n{json.dumps(placeholders, ensure_ascii=False)}\n\n"
        f"默认字段（可参考）:\n{json.dumps(defaults, ensure_ascii=False)}\n"
    )
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]

    response_text, error = call_openai_api_sync_with_custom_config(messages, ai_cfg)
    if error:
        return jsonify({'success': False, 'message': error}), 502

    try:
        parsed = parse_json_object_from_ai_text(response_text or '')
    except Exception as e:
        return jsonify({'success': False, 'message': f'AI输出解析失败: {str(e)}'}), 500

    ai_title = str(parsed.get('title') or title).strip() or title
    ai_short = str(parsed.get('short_name') or short_name).strip() or short_name
    ai_summary = str(parsed.get('summary') or summary).strip() or summary
    ai_fields_raw = parsed.get('template_fields', parsed if isinstance(parsed, dict) else {})
    ai_fields = normalize_product_template_fields(ai_fields_raw if isinstance(ai_fields_raw, dict) else {})

    merged = dict(defaults)
    for key in placeholders:
        if key in ai_fields and str(ai_fields[key]).strip():
            merged[key] = str(ai_fields[key]).strip()

    for key in ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】']:
        merged[key] = ai_title
    if ai_summary:
        merged['【产品描述】'] = ai_summary
    if image_url:
        merged['【主图链接】'] = image_url
        if not merged.get('【缩略图1链接】'):
            merged['【缩略图1链接】'] = image_url

    return jsonify({
        'success': True,
        'title': ai_title,
        'short_name': ai_short,
        'summary': ai_summary,
        'template_fields': merged
    })


@app.route('/api/products/ai-create', methods=['POST'])
@login_required
def ai_create_gassensing_product():
    """Create product HTML from AI-generated template fields."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    slug = (data.get('slug') or '').strip()
    template_fields = normalize_product_template_fields(data.get('template_fields', {}))

    if not title or not short_name or not category or not summary or not slug:
        return jsonify({'success': False, 'message': '请填写标题、简称、分类、链接标识和摘要'}), 400
    if not re.fullmatch(r'[a-z0-9_]+', slug):
        return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400
    allowed_categories = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}
    if category not in allowed_categories:
        return jsonify({'success': False, 'message': '产品分类不合法'}), 400

    content_html = build_product_content_html_from_template_fields(template_fields)
    html_text, _ = render_gassensing_product_html(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url or '/assets/images/logo.png',
        summary=summary,
        content_html=content_html,
        template_fields=template_fields
    )

    products_dir = Path(__file__).parent / 'pages' / 'gassensing'
    products_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{slug}.html'
    filepath = products_dir / filename
    if filepath.exists():
        return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409

    filepath.write_text(html_text, encoding='utf-8')
    return jsonify({'success': True, 'filename': filename, 'link': f'/pages/gassensing/{filename}'})


def extract_product_meta_from_html(filepath):
    """从产品HTML文件中提取meta标签信息"""
    from html.parser import HTMLParser
    
    class ProductMetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.meta = {}
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
            
            if tag == 'meta':
                name = attrs_dict.get('name', '')
                content = attrs_dict.get('content', '')
                if name.startswith('product-'):
                    key = name.replace('product-', '')
                    self.meta[key] = content
            elif tag == 'title':
                self.in_title = True
            elif tag == 'h1' and not self.found_h1:
                self.in_h1 = True
            elif tag == 'p' and self.found_h1 and not self.found_p:
                self.in_p = True
            elif tag == 'img' and not self.first_img and 'src' in attrs_dict:
                src = attrs_dict['src']
                # 排除通用图标和小图
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
        
        parser = ProductMetaParser()
        parser.feed(content)
        
        # 优先使用 meta 标签，否则从页面内容推断
        product_id = filepath.stem
        
        # 名称：meta > h1 > title
        name = parser.meta.get('name', '') or parser.first_h1 or parser.title.replace(' - 元芯传感', '').replace(' - 气体传感产品', '').strip()
        
        # 如果名称为空，跳过这个文件
        if not name:
            return None
        
        # 简称：meta > 名称截断
        short_name = parser.meta.get('short-name', '')
        if not short_name:
            # 自动生成简称（截取前20个字符）
            short_name = name[:20] + ('...' if len(name) > 20 else '')
        
        # 图片：meta > 主图(mainImage) > 缩略图首图(vs-gallery-thumbs) > 第一张图片
        main_img = re.search(r'<img[^>]*id="mainImage"[^>]*src="([^"]+)"', content, re.I)
        gallery_thumb = re.search(
            r'<div[^>]*class="[^"]*vs-gallery-thumbs[^"]*"[^>]*>.*?<img[^>]*src="([^"]+)"',
            content, re.S | re.I
        )
        image = (
            parser.meta.get('image', '')
            or (main_img.group(1) if main_img else '')
            or (gallery_thumb.group(1) if gallery_thumb else '')
            or parser.first_img
        )
        
        # 描述：meta > 第一段
        description = parser.meta.get('description', '') or parser.first_p[:200] if parser.first_p else ''
        
        # 类别：meta > 默认映射 > 'module'
        category = parser.meta.get('category', '') or DEFAULT_PRODUCT_CATEGORIES.get(product_id, 'module')
        
        return {
            'id': product_id,
            'name': name,
            'shortName': short_name,
            'image': image,
            'description': description,
            'category': category
        }
    except Exception as e:
        print(f"Error parsing product file {filepath}: {e}")
        return None


@app.route('/api/products/create', methods=['POST'])
@login_required
def create_gassensing_product():
    """Create a gassensing product detail page from admin visual form."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    slug = (data.get('slug') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))
    template_fields = normalize_product_template_fields(data.get('template_fields', {}))

    if not title or not short_name or not category or not summary or not slug or not content:
        return jsonify({'success': False, 'message': '请填写标题、简称、分类、链接标识、摘要和正文'}), 400

    if not re.fullmatch(r'[a-z0-9_]+', slug):
        return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400

    allowed_categories = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}
    if category not in allowed_categories:
        return jsonify({'success': False, 'message': '产品分类不合法'}), 400

    content_html = content if content_is_html else render_markdown(content)
    html_text, _ = render_gassensing_product_html(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url or '/assets/images/logo.png',
        summary=summary,
        content_html=content_html,
        template_fields=template_fields
    )

    products_dir = Path(__file__).parent / 'pages' / 'gassensing'
    products_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{slug}.html'
    filepath = products_dir / filename
    if filepath.exists():
        return jsonify({'success': False, 'message': f'文件已存在：{filename}，请更换链接标识'}), 409

    filepath.write_text(html_text, encoding='utf-8')
    return jsonify({
        'success': True,
        'filename': filename,
        'link': f'/pages/gassensing/{filename}'
    })


@app.route('/api/products/detail')
@login_required
def get_product_detail():
    """Get one gassensing product detail for admin visual editing."""
    product_id = (request.args.get('id') or '').strip()
    if not product_id:
        return jsonify({'success': False, 'message': '缺少产品ID'}), 400
    if product_id.startswith('../'):
        return jsonify({'success': False, 'message': '该产品不在气体传感目录，暂不支持可视化编辑'}), 400
    if not re.fullmatch(r'[a-z0-9_]+', product_id):
        return jsonify({'success': False, 'message': '产品ID不合法'}), 400

    filepath = Path(__file__).parent / 'pages' / 'gassensing' / f'{product_id}.html'
    detail = parse_gassensing_product_detail(filepath)
    if not detail:
        return jsonify({'success': False, 'message': '产品文件不存在'}), 404
    return jsonify({'success': True, 'detail': detail})


@app.route('/api/products/update', methods=['POST'])
@login_required
def update_gassensing_product():
    """Update an existing gassensing product detail page."""
    data = request.json or {}
    original_slug = (data.get('original_slug') or '').strip()
    slug = (data.get('slug') or '').strip()
    title = (data.get('title') or '').strip()
    short_name = (data.get('short_name') or '').strip()
    category = (data.get('category') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))
    template_fields = normalize_product_template_fields(data.get('template_fields', {}))

    if not original_slug or not slug:
        return jsonify({'success': False, 'message': '缺少原始链接标识或新链接标识'}), 400
    if not title or not short_name or not category or not summary or not content:
        return jsonify({'success': False, 'message': '请填写标题、简称、分类、摘要和正文'}), 400
    if not re.fullmatch(r'[a-z0-9_]+', original_slug) or not re.fullmatch(r'[a-z0-9_]+', slug):
        return jsonify({'success': False, 'message': '链接标识仅支持小写字母、数字、下划线'}), 400

    allowed_categories = {'sensor', 'module', 'detector', 'alarm', 'system', 'iot', 'service', 'probe'}
    if category not in allowed_categories:
        return jsonify({'success': False, 'message': '产品分类不合法'}), 400

    products_dir = Path(__file__).parent / 'pages' / 'gassensing'
    old_path = products_dir / f'{original_slug}.html'
    if not old_path.exists():
        return jsonify({'success': False, 'message': '原产品文件不存在'}), 404
    new_path = products_dir / f'{slug}.html'
    if slug != original_slug and new_path.exists():
        return jsonify({'success': False, 'message': f'目标文件已存在：{slug}.html'}), 409

    content_html = content if content_is_html else render_markdown(content)
    html_text, _ = render_gassensing_product_html(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url or '/assets/images/logo.png',
        summary=summary,
        content_html=content_html,
        template_fields=template_fields
    )

    if slug != original_slug:
        try:
            old_path.unlink()
        except Exception:
            pass
    new_path.write_text(html_text, encoding='utf-8')

    # Keep product settings in sync when slug changes.
    if slug != original_slug:
        settings = get_product_settings()
        if original_slug in settings:
            settings[slug] = settings.get(original_slug, {})
            settings.pop(original_slug, None)
            save_product_settings(settings)

    return jsonify({
        'success': True,
        'filename': f'{slug}.html',
        'link': f'/pages/gassensing/{slug}.html'
    })


@app.route('/api/products/preview-page', methods=['POST'])
@login_required
def preview_product_page():
    """Render full gassensing product page HTML for admin live preview."""
    data = request.json or {}
    title = (data.get('title') or '').strip() or '产品标题'
    short_name = (data.get('short_name') or '').strip() or title
    category = (data.get('category') or '').strip() or 'sensor'
    image_url = (data.get('image_url') or '').strip() or '/assets/images/logo.png'
    summary = (data.get('summary') or '').strip() or '产品摘要'
    content = (data.get('content') or '').strip() or '<p>请填写产品详情内容</p>'
    content_is_html = bool(data.get('content_is_html', False))
    template_fields = normalize_product_template_fields(data.get('template_fields', {}))
    content_html = content if content_is_html else render_markdown(content)

    page_html, _ = render_gassensing_product_html(
        title=title,
        short_name=short_name,
        category=category,
        image_url=image_url,
        summary=summary,
        content_html=content_html,
        template_fields=template_fields
    )

    resize_bridge = """
<script>
(function () {
  function sendHeight() {
    var h = Math.max(
      document.body ? document.body.scrollHeight : 0,
      document.documentElement ? document.documentElement.scrollHeight : 0
    );
    try { parent.postMessage({ type: 'product-preview-height', height: h }, '*'); } catch (e) {}
  }
  window.addEventListener('load', sendHeight);
  window.addEventListener('resize', sendHeight);
  setTimeout(sendHeight, 100);
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1200);
})();
</script>
"""
    if '</body>' in page_html:
        page_html = page_html.replace('</body>', resize_bridge + '\n</body>')
    else:
        page_html += resize_bridge

    return jsonify({'success': True, 'page_html': page_html})


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
        image = parser.first_img

        return {
            'id': item_id,
            'title': title,
            'image': image,
            'desc': desc
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


# ============ Product Menu Settings API ============

PRODUCT_SETTINGS_FILE = DATA_DIR / 'product_settings.json'
PRODUCT_INDUSTRY_FILTERS_FILE = DATA_DIR / 'product_industry_filters.json'

DEFAULT_INDUSTRY_FILTERS = [
    {'key': 'hydrogen', 'name': '氢能源产品'},
    {'key': 'power', 'name': '智慧电力产品'},
    {'key': 'leak', 'name': '工业检漏产品'},
    {'key': 'research', 'name': '科研服务产品'},
    {'key': 'custom', 'name': '定制类产品'},
]


def normalize_filter_key(raw_key, fallback_index=0):
    """Normalize filter key to lowercase ascii slug."""
    key = (raw_key or '').strip().lower()
    key = re.sub(r'[^a-z0-9_-]+', '-', key)
    key = re.sub(r'-{2,}', '-', key).strip('-')
    if not key:
        key = f'industry-{fallback_index + 1}'
    return key


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

    return {'categories': cleaned}


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
            return json.loads(PRODUCT_SETTINGS_FILE.read_text(encoding='utf-8'))
        except:
            pass
    return {}

def save_product_settings(settings):
    """Save product settings."""
    PRODUCT_SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')


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
        link = str(item or '').strip()
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


@app.route('/api/products/settings', methods=['POST'])
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
        settings[product_id]['displayName'] = data['displayName']
    
    if 'isNew' in data:
        settings[product_id]['isNew'] = bool(data['isNew'])
    
    if 'hidden' in data:
        settings[product_id]['hidden'] = bool(data['hidden'])
    
    if 'sortOrder' in data:
        settings[product_id]['sortOrder'] = int(data['sortOrder'])

    if 'cardTitle' in data:
        settings[product_id]['cardTitle'] = str(data['cardTitle'] or '').strip()

    if 'cardImage' in data:
        settings[product_id]['cardImage'] = str(data['cardImage'] or '').strip()

    if 'cardSummary' in data:
        settings[product_id]['cardSummary'] = str(data['cardSummary'] or '').strip()

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


@app.route('/api/products/settings/sort', methods=['POST'])
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


@app.route('/api/products/code/download')
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
@login_required
def upload_product_code():
    """Upload and overwrite product html source by product id."""
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

    # Sort by custom sortOrder first, then by name
    products.sort(key=lambda p: (p.get('sortOrder', 999), p.get('name', '')))
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
        'title': title,
        'image': image,
        'summary': summary,
        'link': link
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
        'title': title or filepath.stem,
        'image': image,
        'desc': desc
    }


def get_all_case_items():
    cases_dir = Path(__file__).parent / 'pages' / 'gassensing' / 'cases'
    items = []
    if cases_dir.exists():
        for filepath in sorted(cases_dir.glob('case-*.html')):
            item = extract_case_meta_from_html(filepath)
            if item:
                item['link'] = f"pages/gassensing/cases/{filepath.name}"
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


def get_default_nav_industry_categories():
    """Default industry category links for gas nav mega menu."""
    return {
        'items': [
            {'name': '氢能源产业链', 'url': '/pages/solutions/industry-hydrogen.html'},
            {'name': '智慧电力安全', 'url': '/pages/solutions/industry-power-safety.html'},
            {'name': '工业检漏监测', 'url': '/pages/solutions/industry-leak-detection.html'},
            {'name': '绿色能源存储', 'url': '/pages/solutions/industry-energy-storage.html'},
            {'name': '大气环境监测', 'url': '/pages/solutions/industry-environment.html'}
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
                return {'items': items}
        except Exception:
            pass
    return get_default_nav_industry_categories()


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
                return {'items': items}
        except Exception:
            pass
    return get_default_measurement_targets()


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
            {'name': 'LD-H2-Gen5 第五代氢气传感器', 'url': '../gassensing/ld_h2_detector.html'},
            {'name': '车载高集成氢气安全监测模组', 'url': '../gassensing/mchp_vehicle_h2.html'}
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


@app.route('/api/measurement-targets', methods=['POST'])
def update_measurement_targets_api():
    """Update mega menu measurement targets."""
    data = request.json or {}
    items = normalize_measurement_target_items(data.get('items', []))
    if not items:
        return jsonify({'success': False, 'message': '请至少提供 1 条有效测量对象（名称 + 相对路径或 http(s) 链接）'}), 400

    payload = {'items': items}
    save_measurement_targets(payload)
    return jsonify({'success': True, 'items': items})


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
    return jsonify({'success': True, 'items': items})


# ============ Hero Carousel API ============

@app.route('/api/hero', methods=['GET'])
def get_hero():
    """Get hero carousel configuration."""
    payload = build_hero_api_payload()
    # Admin UI must always see fresh data after edits/deletes.
    if session.get('admin_logged_in'):
        response = jsonify(payload)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return cached_json_response(payload)


@app.route('/api/hero', methods=['POST'])
@login_required
def update_hero():
    """Update hero carousel configuration."""
    data = request.json or {}
    config = save_hero_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/hero/upload', methods=['POST'])
@login_required
def upload_hero_media():
    """Upload hero carousel media (image/video)."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    original_name = file.filename
    filename = secure_filename(original_name)
    ext = Path(filename).suffix.lower()
    mime = (file.mimetype or '').lower()

    if ext not in ALLOWED_HERO_EXTENSIONS:
        inferred_ext = infer_extension_from_mime(mime)
        if inferred_ext:
            ext = inferred_ext
        else:
            return jsonify({'success': False, 'message': '只支持 PNG/JPG/JPEG/MP4 文件'}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = HERO_UPLOADS_DIR / saved_name
    file.save(str(save_path))

    item_type = 'video' if ext == '.mp4' else 'image'
    if item_type == 'image':
        generate_hero_variants_for_source(saved_name)

    item = {
        'id': uuid.uuid4().hex,
        'type': item_type,
        'url': f"/media/hero/{saved_name}",
        'source': 'upload'
    }

    config = get_hero_config()
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []
    items.append(item)
    config['items'] = items
    save_hero_config(config)

    return jsonify({'success': True, 'item': item})


@app.route('/api/hero/items/<item_id>', methods=['DELETE'])
@login_required
def delete_hero_item(item_id):
    """Delete hero carousel item and uploaded file if applicable."""
    config = get_hero_config()
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []

    remaining = []
    deleted_item = None
    for item in items:
        if isinstance(item, dict) and item.get('id') == item_id:
            deleted_item = item
        else:
            remaining.append(item)

    if not deleted_item:
        # DELETE should be idempotent to avoid false failures on repeated clicks.
        return jsonify({'success': True, 'alreadyDeleted': True, 'message': '项目已不存在'})

    if deleted_item.get('source') == 'upload':
        url = deleted_item.get('url', '')
        if url.startswith('/media/hero/'):
            filename = url.replace('/media/hero/', '')
            file_path = HERO_UPLOADS_DIR / filename
            remove_hero_variants_for_source(filename)
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

    config['items'] = remaining
    save_hero_config(config)
    return jsonify({'success': True})


@app.route('/media/hero/<path:filename>')
def serve_hero_media(filename):
    """Serve uploaded hero media files."""
    response = send_from_directory(HERO_UPLOADS_DIR, filename, max_age=31536000)
    response.headers['Cache-Control'] = MEDIA_IMMUTABLE_CACHE_CONTROL
    return response


@app.route('/media/hero-derived/<path:filename>')
def serve_hero_derived_media(filename):
    """Serve derived responsive hero images."""
    response = send_from_directory(HERO_DERIVED_DIR, filename, max_age=31536000)
    response.headers['Cache-Control'] = MEDIA_IMMUTABLE_CACHE_CONTROL
    return response


@app.route('/media/h2-home/<path:filename>')
def serve_h2_home_media(filename):
    """Serve uploaded H2 home video files."""
    response = send_from_directory(H2_HOME_VIDEO_UPLOADS_DIR, filename, max_age=31536000)
    response.headers['Cache-Control'] = MEDIA_IMMUTABLE_CACHE_CONTROL
    return response


# ============ Partners API ============

@app.route('/api/partners', methods=['GET'])
def get_partners():
    """Get partners configuration."""
    return jsonify(get_partners_config())


@app.route('/api/partners', methods=['POST'])
@login_required
def update_partners():
    """Update partners configuration."""
    data = request.json or {}
    config = save_partners_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/partners/upload', methods=['POST'])
@login_required
def upload_partner_logo():
    """Upload partner logo image."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    original_name = file.filename
    filename = secure_filename(original_name)
    ext = Path(filename).suffix.lower()
    mime = (file.mimetype or '').lower()

    if ext not in ALLOWED_PARTNER_EXTENSIONS:
        inferred_ext = infer_partner_extension_from_mime(mime)
        if inferred_ext:
            ext = inferred_ext
        else:
            return jsonify({'success': False, 'message': '只支持 PNG/JPG/JPEG/SVG/WEBP 文件'}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = PARTNERS_UPLOADS_DIR / saved_name
    file.save(str(save_path))

    item = {
        'id': uuid.uuid4().hex,
        'url': f"/media/partners/{saved_name}",
        'source': 'upload'
    }

    config = get_partners_config()
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []
    items.append(item)
    config['items'] = items
    save_partners_config(config)

    return jsonify({'success': True, 'item': item})


@app.route('/api/partners/items/<item_id>', methods=['DELETE'])
@login_required
def delete_partner_item(item_id):
    """Delete partner logo item and uploaded file if applicable."""
    config = get_partners_config()
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []

    remaining = []
    deleted_item = None
    for item in items:
        if isinstance(item, dict) and item.get('id') == item_id:
            deleted_item = item
        else:
            remaining.append(item)

    if not deleted_item:
        return jsonify({'success': False, 'message': '未找到项目'}), 404

    if deleted_item.get('source') == 'upload':
        url = deleted_item.get('url', '')
        if url.startswith('/media/partners/'):
            filename = url.replace('/media/partners/', '')
            file_path = PARTNERS_UPLOADS_DIR / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

    config['items'] = remaining
    save_partners_config(config)
    return jsonify({'success': True})


@app.route('/media/partners/<path:filename>')
def serve_partners_media(filename):
    """Serve uploaded partner logo files."""
    return send_from_directory(PARTNERS_UPLOADS_DIR, filename)

@app.route('/api/home/section-visibility', methods=['GET'])
def get_home_section_visibility():
    """Get homepage section visibility for frontend and admin."""
    return jsonify(get_home_section_visibility_config())

@app.route('/api/home/section-visibility', methods=['POST'])
@login_required
def update_home_section_visibility():
    """Update homepage section visibility."""
    data = request.json or {}
    config = save_home_section_visibility_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/products/card-image/upload', methods=['POST'])
def upload_product_card_image():
    """Upload image file for product card and return accessible URL."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未找到上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    content_type = (file.content_type or '').lower()

    if ext not in ALLOWED_PRODUCT_CARD_EXTENSIONS:
        inferred = infer_product_card_extension_from_mime(content_type)
        if inferred:
            ext = inferred
        else:
            return jsonify({'success': False, 'message': '仅支持 PNG/JPG/JPEG/WEBP 图片'}), 400

    if content_type and content_type not in ALLOWED_PRODUCT_CARD_MIME_TYPES:
        return jsonify({'success': False, 'message': '文件类型不支持'}), 400

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

@app.route('/api/news/image/import', methods=['POST'])
@login_required
def import_news_image_from_url():
    """Download an image URL to local media and return local URL."""
    data = request.json or {}
    source_url = (data.get('url') or '').strip()
    if not source_url:
        return jsonify({'success': False, 'message': '缺少图片链接'}), 400
    if not (source_url.startswith('http://') or source_url.startswith('https://')):
        return jsonify({'success': False, 'message': '仅支持 http/https 图片链接'}), 400

    parsed = urlparse(source_url)
    ext = Path(parsed.path).suffix.lower()
    content_type = ''
    content = b''

    try:
        if REQUESTS_SUPPORT:
            resp = requests.get(source_url, timeout=20)
            resp.raise_for_status()
            content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            content = resp.content or b''
        elif HTTPX_SUPPORT:
            resp = httpx.get(source_url, timeout=20.0, follow_redirects=True)
            resp.raise_for_status()
            content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            content = resp.content or b''
        else:
            return jsonify({'success': False, 'message': '服务端缺少下载客户端依赖'}), 500
    except Exception:
        return jsonify({'success': False, 'message': '图片下载失败，请检查链接是否可访问'}), 400

    if len(content) == 0:
        return jsonify({'success': False, 'message': '图片内容为空'}), 400
    if len(content) > 15 * 1024 * 1024:
        return jsonify({'success': False, 'message': '图片过大（最大15MB）'}), 400

    if ext not in ALLOWED_NEWS_IMAGE_EXTENSIONS:
        if content_type in ALLOWED_NEWS_IMAGE_MIME_TYPES:
            ext = infer_news_image_extension_from_mime(content_type)
        else:
            guessed = mimetypes.guess_extension(content_type) if content_type else ''
            ext = (guessed or '').lower()
            if ext == '.jpe':
                ext = '.jpg'
            if ext not in ALLOWED_NEWS_IMAGE_EXTENSIONS:
                return jsonify({'success': False, 'message': '链接内容不是受支持的图片格式'}), 400

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = NEWS_UPLOADS_DIR / filename
    file_path.write_bytes(content)
    return jsonify({'success': True, 'url': f'/media/news/{filename}'})

@app.route('/api/news/image/upload', methods=['POST'])
@login_required
def upload_news_image_file():
    """Upload a local image file for news rich text editor."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    original_name = file.filename
    filename = secure_filename(original_name)
    ext = Path(filename).suffix.lower()
    mime = (file.mimetype or '').lower()

    if ext not in ALLOWED_NEWS_IMAGE_EXTENSIONS:
        inferred = infer_news_image_extension_from_mime(mime)
        if inferred:
            ext = inferred
        else:
            return jsonify({'success': False, 'message': '仅支持 PNG/JPG/JPEG/WEBP/GIF/SVG'}), 400

    if mime and mime not in ALLOWED_NEWS_IMAGE_MIME_TYPES:
        inferred = infer_news_image_extension_from_mime(mime)
        if not inferred:
            return jsonify({'success': False, 'message': '文件类型不受支持'}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = NEWS_UPLOADS_DIR / saved_name
    file.save(str(save_path))

    if save_path.stat().st_size > 15 * 1024 * 1024:
        try:
            save_path.unlink()
        except Exception:
            pass
        return jsonify({'success': False, 'message': '图片过大（最大15MB）'}), 400

    return jsonify({'success': True, 'url': f'/media/news/{saved_name}'})

@app.route('/media/news/<path:filename>')
def serve_news_media(filename):
    """Serve imported news images."""
    return send_from_directory(NEWS_UPLOADS_DIR, filename)


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


@app.route('/api/products/industry-filters', methods=['POST'])
def save_industry_filters_api():
    """Update all-products industry filters."""
    data = request.json or {}
    saved = save_industry_filters(data)
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
            resume_url = (msg.get('resume_url') or '').strip()
            if resume_url.startswith('/media/resumes/'):
                resume_name = resume_url.split('/media/resumes/', 1)[1]
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
        'resume_url': f'/media/resumes/{saved_name}',
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


@app.route('/media/resumes/<path:filename>')
def serve_resume_media(filename):
    """Serve uploaded resumes."""
    return send_from_directory(RESUME_UPLOADS_DIR, filename)


register_backup_routes(
    app,
    login_required=login_required,
    project_root=Path(__file__).parent,
    backup_meta_files=BACKUP_META_FILES,
    backup_excluded_dir_names=BACKUP_EXCLUDED_DIR_NAMES,
    backup_excluded_file_names=BACKUP_EXCLUDED_FILE_NAMES,
    backup_excluded_suffixes=BACKUP_EXCLUDED_SUFFIXES,
)


# ============ Chatbot API ============

# Knowledge base cache
_knowledge_cache = {
    'content': '',
    'last_updated': 0,
    'files': []
}
_knowledge_lock = threading.Lock()

CHATBOT_SYSTEM_PROMPT = '''你是元芯传感的智能客服助手。你的职责是回答用户关于公司产品、技术和服务的问题。

公司信息：
- 公司名称：湖南元芯传感科技有限责任公司
- 主要业务：先进生物与化学传感技术解决方案
- 核心技术：碳基电子传感技术
- 主要产品：氢气传感器、生物传感器、气体检测模组

请用专业、友好的语气回答问题。如果遇到不确定的问题，请引导用户联系我们的销售团队。'''

PRODUCT_AI_SYSTEM_PROMPT = '''你是“元芯传感产品页编程助手”，负责根据后台给定的产品资料生成可发布的页面内容。

你在“产品页编程 AI”场景下的硬性规则：
1) 你的输出目标是完整 HTML 页面代码。
2) 请直接开始写代码，代码写完后不要添加任何其他内容。
3) 禁止输出解释、注释说明、Markdown代码块（```）。
4) 输出尽量完整，包含 <!DOCTYPE html>、<html>、<head>、<body>。
5) 必须参考提供的模板结构与样式，不要无故删除关键布局和资源引用。
6) 文案专业、克制、可发布；禁止编造认证/资质/客户背书。
7) 图片或链接未知时可使用占位路径 /assets/images/logo.png 或保守留空。'''


def get_chatbot_system_prompt():
    return CHATBOT_SYSTEM_PROMPT


def get_product_page_ai_system_prompt():
    return PRODUCT_AI_SYSTEM_PROMPT


def get_chatbot_config():
    """Get chatbot configuration from config."""
    config = get_config()
    return {
        'api_key': config.get('chatbot_api_key', ''),
        'api_base': config.get('chatbot_api_base', 'https://api.openai.com/v1'),
        'model': config.get('chatbot_model', 'gpt-3.5-turbo'),
        'enabled': config.get('chatbot_enabled', True)
    }


def get_product_page_ai_config():
    """Get product-page coding AI configuration from config."""
    config = get_config()
    return {
        'enabled': config.get('product_ai_enabled', False),
        'api_key': config.get('product_ai_api_key', ''),
        'api_base': config.get('product_ai_api_base', 'https://api.openai.com/v1'),
        'model': config.get('product_ai_model', 'gpt-4o-mini')
    }


def load_knowledge_base():
    """Load and cache knowledge base content from PDF files."""
    global _knowledge_cache
    
    with _knowledge_lock:
        # Check if we need to reload
        pdf_files = list(KNOWLEDGE_DIR.glob('*.pdf'))
        current_files = sorted([f.name for f in pdf_files])
        current_mtime = max([f.stat().st_mtime for f in pdf_files]) if pdf_files else 0
        
        if (_knowledge_cache['files'] == current_files and 
            _knowledge_cache['last_updated'] >= current_mtime and
            _knowledge_cache['content']):
            return _knowledge_cache['content']
        
        if not PDF_SUPPORT:
            return ""
        
        knowledge_text = []
        
        for pdf_path in pdf_files:
            try:
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    pdf_text = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            pdf_text.append(text)
                    
                    if pdf_text:
                        knowledge_text.append(f"\n--- 来自文档: {pdf_path.name} ---\n")
                        knowledge_text.append('\n'.join(pdf_text))
                        
            except Exception as e:
                print(f"Error reading PDF {pdf_path}: {e}")
                continue
        
        _knowledge_cache['content'] = '\n'.join(knowledge_text)
        _knowledge_cache['last_updated'] = current_mtime
        _knowledge_cache['files'] = current_files
        
        return _knowledge_cache['content']


def call_openai_api(messages, stream=False):
    """Call OpenAI-compatible API."""
    if stream:
        return call_openai_api_stream(messages)
    return call_openai_api_sync(messages)


def call_openai_api_sync(messages):
    """Call OpenAI-compatible API (non-stream)."""
    config = get_chatbot_config()

    if not config['api_key']:
        return None, "AI客服未配置，请联系管理员"

    api_url = config['api_base'].rstrip('/') + '/chat/completions'

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json'
    }

    payload = {
        'model': config['model'],
        'messages': messages,
        'stream': False
    }

    try:
        if REQUESTS_SUPPORT:
            response = requests.post(api_url, json=payload, headers=headers, timeout=60)
            if response.status_code != 200:
                return None, f"API错误: {response.status_code}"

            result = response.json()
            if 'choices' in result and result['choices']:
                return result['choices'][0]['message']['content'], None
            return None, "API返回格式错误"
        elif HTTPX_SUPPORT:
            response = httpx.post(api_url, json=payload, headers=headers, timeout=60.0)
            if response.status_code != 200:
                return None, f"API错误: {response.status_code}"
            result = response.json()
            if 'choices' in result and result['choices']:
                return result['choices'][0]['message']['content'], None
            return None, "API返回格式错误"
        else:
            return None, "缺少HTTP客户端库(requests或httpx)"
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None, f"API调用失败: {str(e)}"


def call_openai_api_stream(messages):
    """Call OpenAI-compatible API (stream)."""
    config = get_chatbot_config()

    if not config['api_key']:
        return None, "AI客服未配置，请联系管理员"

    api_url = config['api_base'].rstrip('/') + '/chat/completions'

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json'
    }

    payload = {
        'model': config['model'],
        'messages': messages,
        'stream': True
    }

    if HTTPX_SUPPORT:
        def gen_httpx():
            try:
                with httpx.Client(timeout=60.0) as client:
                    with client.stream('POST', api_url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            yield None, f"API错误: {response.status_code}"
                            return
                        for line in response.iter_lines():
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if 'choices' in chunk and chunk['choices']:
                                        delta = chunk['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            yield content, None
                                except json.JSONDecodeError:
                                    continue
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_httpx()

    if REQUESTS_SUPPORT:
        def gen_requests():
            try:
                response = requests.post(api_url, json=payload, headers=headers, stream=True, timeout=60)
                if response.status_code != 200:
                    yield None, f"API错误: {response.status_code}"
                    return
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and chunk['choices']:
                                    delta = chunk['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        yield content, None
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                yield None, f"API调用失败: {str(e)}"
        return gen_requests()

    return None, "缺少HTTP客户端库(requests或httpx)"


@app.route('/api/chatbot/chat', methods=['POST'])
def chatbot_chat():
    """Handle chatbot conversation."""
    config = get_chatbot_config()
    
    if not config['enabled']:
        return jsonify({
            'success': False,
            'message': '智能客服暂时不可用'
        }), 503
    
    data = request.json or {}
    user_message = data.get('message', '').strip()
    history = data.get('history', [])
    
    if not user_message:
        return jsonify({
            'success': False,
            'message': '请输入您的问题'
        }), 400
    
    # Load knowledge base
    knowledge = load_knowledge_base()
    
    # Build system prompt with knowledge base
    system_prompt = get_chatbot_system_prompt()
    if knowledge:
        system_prompt += f"\n\n以下是公司知识库的相关内容，请参考这些信息回答用户问题：\n{knowledge[:8000]}"  # Limit knowledge base size
    
    # Build messages
    messages = [{'role': 'system', 'content': system_prompt}]
    
    # Add conversation history (limited)
    for msg in history[-8:]:  # Last 8 messages for context
        role = msg.get('role', 'user')
        if role == 'assistant':
            role = 'assistant'
        messages.append({
            'role': role,
            'content': msg.get('content', '')
        })
    
    # Add current message
    messages.append({'role': 'user', 'content': user_message})
    
    # Try streaming first
    use_stream = HTTPX_SUPPORT or (REQUESTS_SUPPORT and config.get('use_stream', True))
    
    if use_stream:
        def generate():
            try:
                stream = call_openai_api(messages, stream=True)
                if isinstance(stream, tuple):
                    _, error = stream
                    yield f"data: {json.dumps({'error': error or 'API调用失败'})}\n\n"
                    return
                for chunk, err in stream:
                    if err:
                        yield f"data: {json.dumps({'error': err})}\n\n"
                        return
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    else:
        # Non-streaming fallback
        response, error = call_openai_api(messages, stream=False)
        
        if error:
            return jsonify({
                'success': False,
                'message': error
            }), 500
        
        return jsonify({
            'success': True,
            'response': response
        })


# ============ Knowledge Base Management API ============

@app.route('/api/chatbot/knowledge', methods=['GET'])
@login_required
def list_knowledge_files():
    """List all knowledge base PDF files."""
    files = []
    for pdf_path in sorted(KNOWLEDGE_DIR.glob('*.pdf')):
        stat = pdf_path.stat()
        files.append({
            'name': pdf_path.name,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    return jsonify({'files': files, 'pdf_support': PDF_SUPPORT})


@app.route('/api/chatbot/knowledge/upload', methods=['POST'])
@login_required
def upload_knowledge_file():
    """Upload a PDF file to knowledge base."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400
    
    file = request.files['file']
    
    if not file.filename:
        return jsonify({'success': False, 'message': '文件名为空'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'message': '只支持PDF文件'}), 400
    
    # Sanitize filename
    filename = re.sub(r'[^\w\u4e00-\u9fff\-_.]', '_', file.filename)
    filepath = KNOWLEDGE_DIR / filename
    
    try:
        file.save(str(filepath))
        
        # Clear knowledge cache to force reload
        with _knowledge_lock:
            _knowledge_cache['content'] = ''
            _knowledge_cache['last_updated'] = 0
        
        return jsonify({
            'success': True,
            'message': f'文件 {filename} 上传成功',
            'filename': filename
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500


@app.route('/api/chatbot/knowledge/<filename>', methods=['DELETE'])
@login_required
def delete_knowledge_file(filename):
    """Delete a knowledge base file."""
    filepath = KNOWLEDGE_DIR / filename
    
    if not filepath.exists():
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    
    try:
        filepath.unlink()
        
        # Clear knowledge cache
        with _knowledge_lock:
            _knowledge_cache['content'] = ''
            _knowledge_cache['last_updated'] = 0
        
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500


# ============ Chatbot Config API ============

@app.route('/api/chatbot/config', methods=['GET'])
@login_required
def get_chatbot_config_api():
    """Get chatbot configuration (excluding API key for security)."""
    config = get_chatbot_config()
    # Mask API key for display
    if config['api_key']:
        config['api_key'] = config['api_key'][:8] + '...' + config['api_key'][-4:] if len(config['api_key']) > 12 else '***'
    return jsonify(config)


@app.route('/api/chatbot/config', methods=['POST'])
@login_required
def update_chatbot_config():
    """Update chatbot configuration."""
    data = request.json or {}
    
    updates = {}
    
    if 'api_key' in data and data['api_key'] and not data['api_key'].startswith('***'):
        updates['chatbot_api_key'] = data['api_key']
    
    if 'api_base' in data:
        updates['chatbot_api_base'] = data['api_base']
    
    if 'model' in data:
        updates['chatbot_model'] = data['model']
    
    if 'enabled' in data:
        updates['chatbot_enabled'] = bool(data['enabled'])
    
    if updates:
        update_config(updates)
    
    return jsonify({'success': True, 'message': '配置已更新'})


@app.route('/api/product-ai/config', methods=['GET'])
@login_required
def get_product_ai_config_api():
    """Get product-page coding AI configuration (excluding API key for security)."""
    config = get_product_page_ai_config()
    if config['api_key']:
        config['api_key'] = config['api_key'][:8] + '...' + config['api_key'][-4:] if len(config['api_key']) > 12 else '***'
    return jsonify(config)


@app.route('/api/product-ai/config', methods=['POST'])
@login_required
def update_product_ai_config():
    """Update product-page coding AI configuration."""
    data = request.json or {}
    updates = {}

    if 'api_key' in data and data['api_key'] and not str(data['api_key']).startswith('***'):
        updates['product_ai_api_key'] = str(data['api_key']).strip()
    if 'api_base' in data:
        updates['product_ai_api_base'] = str(data['api_base']).strip()
    if 'model' in data:
        updates['product_ai_model'] = str(data['model']).strip()
    if 'enabled' in data:
        updates['product_ai_enabled'] = bool(data['enabled'])

    if updates:
        update_config(updates)

    return jsonify({'success': True, 'message': '产品页编程AI配置已更新'})


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
    result = {
        'url': url,
        'head_status': None,
        'get_status': None,
        'reachable': False,
        'error': ''
    }

    try:
        if REQUESTS_SUPPORT:
            try:
                head_res = requests.head(url, allow_redirects=True, timeout=(4, 8))
                result['head_status'] = int(head_res.status_code)
                if 200 <= head_res.status_code < 400:
                    result['reachable'] = True
            except Exception:
                pass

            try:
                get_res = requests.get(url, headers={'Range': 'bytes=0-2047'}, stream=True, timeout=(4, 10))
                result['get_status'] = int(get_res.status_code)
                if get_res.status_code in (200, 206):
                    result['reachable'] = True
            except Exception as e:
                if not result.get('error'):
                    result['error'] = str(e)
        elif HTTPX_SUPPORT:
            try:
                head_res = httpx.head(url, follow_redirects=True, timeout=8.0)
                result['head_status'] = int(head_res.status_code)
                if 200 <= head_res.status_code < 400:
                    result['reachable'] = True
            except Exception:
                pass

            try:
                get_res = httpx.get(url, headers={'Range': 'bytes=0-2047'}, follow_redirects=True, timeout=10.0)
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

    if cdn_enabled:
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


# ============ Site Search API ============

# Search index cache
_search_index = {
    'pages': [],
    'last_updated': 0
}
_search_lock = threading.Lock()

def extract_text_from_html(html_content):
    """Extract readable text from HTML content."""
    from html.parser import HTMLParser
    
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text_parts = []
            self.skip_tags = {'script', 'style', 'nav', 'header', 'footer', 'noscript'}
            self.current_tag = None
            self.skip_depth = 0
            
        def handle_starttag(self, tag, attrs):
            self.current_tag = tag
            if tag in self.skip_tags:
                self.skip_depth += 1
                
        def handle_endtag(self, tag):
            if tag in self.skip_tags and self.skip_depth > 0:
                self.skip_depth -= 1
                
        def handle_data(self, data):
            if self.skip_depth == 0:
                text = data.strip()
                if text and len(text) > 1:
                    self.text_parts.append(text)
                    
        def get_text(self):
            return ' '.join(self.text_parts)
    
    try:
        parser = TextExtractor()
        parser.feed(html_content)
        return parser.get_text()
    except:
        return ""

def extract_title_from_html(html_content):
    """Extract title from HTML content."""
    import re
    # Try to find <title> tag
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()
    # Try to find <h1> tag
    h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content, re.IGNORECASE)
    if h1_match:
        return h1_match.group(1).strip()
    return ""

def build_search_index():
    """Build search index from all HTML pages."""
    global _search_index
    
    with _search_lock:
        pages_dir = Path(__file__).parent / 'pages'
        index_file = Path(__file__).parent / 'index.html'
        
        pages = []
        
        # Index main page
        if index_file.exists():
            try:
                content = index_file.read_text(encoding='utf-8')
                title = extract_title_from_html(content)
                text = extract_text_from_html(content)
                pages.append({
                    'url': '/',
                    'title': title or '首页',
                    'content': text[:2000],  # Limit content size
                    'path': 'index.html'
                })
            except:
                pass
        
        # Index all pages in pages directory
        for html_file in pages_dir.rglob('*.html'):
            # Skip admin pages
            if 'admin' in str(html_file).lower():
                continue
                
            try:
                content = html_file.read_text(encoding='utf-8')
                title = extract_title_from_html(content)
                text = extract_text_from_html(content)
                
                # Get relative URL
                rel_path = html_file.relative_to(Path(__file__).parent)
                url = '/' + str(rel_path).replace('\\', '/')
                
                pages.append({
                    'url': url,
                    'title': title or html_file.stem,
                    'content': text[:2000],
                    'path': str(rel_path)
                })
            except Exception as e:
                print(f"Error indexing {html_file}: {e}")
                continue
        
        _search_index['pages'] = pages
        _search_index['last_updated'] = time.time()
        
        return pages

def search_pages(query, limit=20):
    """Search indexed pages for query."""
    global _search_index
    
    # Rebuild index if empty or stale (older than 5 minutes)
    if not _search_index['pages'] or time.time() - _search_index['last_updated'] > 300:
        build_search_index()
    
    if not query:
        return []
    
    query_lower = query.lower()
    results = []
    
    for page in _search_index['pages']:
        score = 0
        snippet = ""
        
        title = page.get('title', '')
        content = page.get('content', '')
        
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Title match (higher score)
        if query_lower in title_lower:
            score += 100
            snippet = title
        
        # Content match
        if query_lower in content_lower:
            score += 50
            # Extract snippet around the match
            idx = content_lower.find(query_lower)
            start = max(0, idx - 50)
            end = min(len(content), idx + len(query) + 100)
            snippet = content[start:end]
            if start > 0:
                snippet = '...' + snippet
            if end < len(content):
                snippet = snippet + '...'
        
        # Partial word match in title
        for word in query_lower.split():
            if len(word) >= 2:
                if word in title_lower:
                    score += 30
                if word in content_lower:
                    score += 10
        
        if score > 0:
            results.append({
                'url': page['url'],
                'title': title,
                'snippet': snippet or content[:150] + '...' if content else '',
                'score': score
            })
    
    # Sort by score and limit results
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]


@app.route('/api/search')
def api_search():
    """Search API endpoint."""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    
    if not query:
        return jsonify({'results': [], 'query': ''})
    
    results = search_pages(query, limit)
    return jsonify({
        'results': results,
        'query': query,
        'total': len(results)
    })


@app.route('/api/search/rebuild')
@login_required
def api_search_rebuild():
    """Force rebuild search index (admin only)."""
    pages = build_search_index()
    return jsonify({
        'success': True,
        'message': f'索引重建完成，共索引 {len(pages)} 个页面'
    })


# ============ Static Files ============

@app.route('/favicon.ico')
@app.route('/apple-touch-icon.png')
@app.route('/favicon.png')
def site_favicon():
    """Serve a unified site favicon (company logo) for all pages."""
    favicon_file = CDN_ASSETS_DIR / SITE_FAVICON_RELATIVE_PATH
    if favicon_file.exists() and favicon_file.is_file():
        response = send_file(str(favicon_file), mimetype='image/png')
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response
    return Response(status=204)


@app.route('/')
def index():
    """Serve main page."""
    return send_from_directory('.', 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files."""
    # Try exact path first
    if os.path.isfile(path):
        return send_from_directory('.', path)
    # Try with .html extension
    if os.path.isfile(path + '.html'):
        return send_from_directory('.', path + '.html')
    # Try as directory with index.html
    if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'index.html')):
        return send_from_directory(path, 'index.html')
    return send_from_directory('.', path)


if __name__ == '__main__':
    print("=" * 50)
    print("YX Website Server")
    print("=" * 50)
    print(f"Local:   http://localhost:8000")
    print(f"Admin:   http://localhost:8000/admin")
    print(f"Data:    {MESSAGES_DIR.absolute()}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8000, debug=True)
