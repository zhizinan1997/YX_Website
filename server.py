"""
Flask server for YX Website with feedback form backend and admin panel.
Supports both local development and Docker deployment.
Includes AI Chatbot with knowledge base support.
"""
import os
import json
import time
import hashlib
import threading
import re
import uuid
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string, Response, stream_with_context
from werkzeug.utils import secure_filename

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

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'metachip-secret-key-2024')

# Configuration
DATA_DIR = Path(__file__).parent / 'data'
MESSAGES_DIR = DATA_DIR / 'messages'
KNOWLEDGE_DIR = DATA_DIR / 'knowledge'
RATE_LIMIT_FILE = DATA_DIR / 'rate_limits.json'
CONFIG_FILE = DATA_DIR / 'config.json'
HERO_DIR = DATA_DIR / 'hero'
HERO_UPLOADS_DIR = HERO_DIR / 'uploads'
HERO_CONFIG_FILE = HERO_DIR / 'hero.json'
PARTNERS_DIR = DATA_DIR / 'partners'
PARTNERS_UPLOADS_DIR = PARTNERS_DIR / 'uploads'
PARTNERS_CONFIG_FILE = PARTNERS_DIR / 'partners.json'
NEWS_FEATURED_FILE = DATA_DIR / 'news_featured.json'
NEWS_VISIBILITY_FILE = DATA_DIR / 'news_visibility.json'
PRODUCT_FEATURED_FILE = DATA_DIR / 'product_featured.json'
SOLUTIONS_FEATURED_FILE = DATA_DIR / 'solutions_featured.json'
JOBS_FILE = DATA_DIR / 'jobs.json'
H2_HOME_FILE = DATA_DIR / 'h2_home.json'

# Ensure directories exist
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
HERO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PARTNERS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_MAX = 5  # Max submissions per IP per hour
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# Ensure directories exist
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_HERO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.mp4'}
ALLOWED_HERO_MIME_TYPES = {'image/png', 'image/jpeg', 'video/mp4'}
ALLOWED_PARTNER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}
ALLOWED_PARTNER_MIME_TYPES = {'image/png', 'image/jpeg', 'image/svg+xml', 'image/webp'}

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
    default_config = {
        'admin_username': os.environ.get('ADMIN_USERNAME', 'admin'),
        'admin_password': os.environ.get('ADMIN_PASSWORD', 'admin123')
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

def get_client_ip():
    """Get client IP address, considering proxy headers."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


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
        return f(*args, **kwargs)
    return decorated_function



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
                            'image': ''
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
    
    <!-- Vaisala Style V2.0 -->
    <link rel="stylesheet" href="../../assets/css/vaisala-style.css">
    
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
        if re.match(r'^\\d+\\.\\s+', line):
            if in_ul:
                html_lines.append('</ul>')
                in_ul = False
            if not in_ol:
                html_lines.append('<ol>')
                in_ol = True
            item = re.sub(r'^\\d+\\.\\s+', '', line)
            html_lines.append(f'<li>{item}</li>')
            continue

        close_lists()

        # Inline formatting
        line = re.sub(r'\\*\\*(.+?)\\*\\*', r'<strong>\\1</strong>', line)
        line = re.sub(r'\\*(.+?)\\*', r'<em>\\1</em>', line)
        line = re.sub(r'!\\[(.*?)\\]\\((.*?)\\)', r'<img src="\\2" alt="\\1">', line)
        line = re.sub(r'\\[(.*?)\\]\\((.*?)\\)', r'<a href="\\2">\\1</a>', line)

        html_lines.append(f'<p>{line}</p>')

    close_lists()
    return '\n'.join(html_lines)

def parse_news_article_html(filepath: Path):
    """Parse a news article HTML to extract fields."""
    if not filepath.exists():
        return None
    content = filepath.read_text(encoding='utf-8')
    title_match = re.search(r'<h1 class="article-hero__title">(.*?)</h1>', content, re.S)
    date_match = re.search(r'<div class="article-hero__meta">(.*?)</div>', content, re.S)
    body_match = re.search(r'<div class="article-content">(.*?)</div>', content, re.S)
    title = title_match.group(1).strip() if title_match else ''
    date = date_match.group(1).strip() if date_match else ''
    body_html = body_match.group(1).strip() if body_match else ''
    image_match = re.search(r'<img\\s+[^>]*src=\"([^\"]+)\"', body_html)
    image_url = image_match.group(1) if image_match else ''
    if image_url:
        body_html = re.sub(r'<img\\s+[^>]*>\\s*', '', body_html, count=1)
    return {
        'title': title,
        'date': date,
        'image_url': image_url,
        'content_html': body_html
    }

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


def load_jobs_data():
    if JOBS_FILE.exists():
        try:
            data = json.loads(JOBS_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('jobs', []), list):
                return data
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
    """Load hydrogen homepage video list."""
    default_config = {'items': []}
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
    saved = {'items': cleaned}
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


@app.route('/api/solutions/all')
@login_required
def get_all_solutions():
    """Get all solutions for admin selection."""
    return jsonify({'items': get_all_solution_items()})


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
    title = (data.get('title') or '').strip()
    department = (data.get('department') or '').strip()
    location = (data.get('location') or '').strip()
    date = (data.get('date') or '').strip()
    content_html = (data.get('content_html') or '').strip()
    visible = bool(data.get('visible', True))
    job_id = (data.get('id') or '').strip()

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
    return jsonify(get_h2_home_config())


@app.route('/api/h2-home', methods=['POST'])
@login_required
def update_h2_home():
    data = request.json or {}
    config = save_h2_home_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/news/create', methods=['POST'])
@login_required
def create_news():
    """Create a news article and add to news list."""
    data = request.json or {}
    title = (data.get('title') or '').strip()
    date = (data.get('date') or '').strip()
    category = (data.get('category') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))

    if not title or not date or not category or not image_url or not summary or not content:
        return jsonify({'success': False, 'message': '请填写完整信息'}), 400

    if category not in {'enterprise', 'industry', 'science'}:
        return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

    # Build content HTML (Markdown supported)
    if content_is_html:
        content_html = content
    else:
        content_html = render_markdown(content)

    # Create news file
    news_dir = Path(__file__).parent / 'pages' / 'news'
    news_dir.mkdir(parents=True, exist_ok=True)
    news_id = get_next_news_id()
    filename = f'news_show.aspx_id_{news_id}.html'
    filepath = news_dir / filename
    html = build_news_article_html(title, date, image_url, content_html)
    filepath.write_text(html, encoding='utf-8')

    # Insert card into news list
    card_html = f"""
                    <a href="../../pages/news/{filename}" class="vs-card" data-category="{category}" data-hidden="false">
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
        pattern = re.compile(rf'(<a\\s+[^>]*href=\"\\.{2}/\\.{2}/pages/news/{re.escape(Path(link).name)}\"[^>]*)(>)', re.IGNORECASE)
        def repl(match):
            tag_start = match.group(1)
            if 'data-hidden' in tag_start:
                tag_start = re.sub(r'data-hidden=\"(true|false)\"', f'data-hidden=\"{str(hidden).lower()}\"', tag_start)
            else:
                tag_start += f' data-hidden=\"{str(hidden).lower()}\"'
            return tag_start + match.group(2)
        content = pattern.sub(repl, content, count=1)
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
        pattern = re.compile(rf'<a\\s+[^>]*href=\"\\.{2}/\\.{2}/pages/news/{re.escape(filename)}\"[^>]*>.*?</a>', re.DOTALL | re.IGNORECASE)
        content, _ = pattern.subn('', content, count=1)
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
    image_url = (data.get('image_url') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    content_is_html = bool(data.get('content_is_html', False))

    if not link:
        return jsonify({'success': False, 'message': '缺少资讯链接'}), 400
    if not title or not date or not category or not image_url or not summary or not content:
        return jsonify({'success': False, 'message': '请填写完整信息'}), 400
    if category not in {'enterprise', 'industry', 'science'}:
        return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

    if content_is_html:
        content_html = content
    else:
        content_html = render_markdown(content)

    filename = Path(link).name
    news_dir = Path(__file__).parent / 'pages' / 'news'
    filepath = news_dir / filename
    if not filepath.exists():
        return jsonify({'success': False, 'message': '资讯文件不存在'}), 404

    html = build_news_article_html(title, date, image_url, content_html)
    filepath.write_text(html, encoding='utf-8')

    # Update card in news.html
    news_index = news_dir / 'news.html'
    if news_index.exists():
        content_text = news_index.read_text(encoding='utf-8')
        card_html = f"""
                    <a href="../../pages/news/{filename}" class="vs-card" data-category="{category}" data-hidden="false">
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
        pattern = re.compile(rf'<a\\s+[^>]*href=\"\\.{2}/\\.{2}/pages/news/{re.escape(filename)}\"[^>]*>.*?</a>', re.DOTALL | re.IGNORECASE)
        content_text, count = pattern.subn(card_html, content_text, count=1)
        if count:
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


@app.route('/api/news/ai-polish', methods=['POST'])
@login_required
def ai_polish_news():
    """Use AI to polish news content to Markdown."""
    config = get_chatbot_config()
    if not config.get('enabled', True):
        return jsonify({'success': False, 'message': 'AI客服暂时不可用'}), 503
    if not config.get('api_key'):
        return jsonify({'success': False, 'message': 'AI客服未配置'}), 400

    data = request.json or {}
    title = (data.get('title') or '').strip()
    summary = (data.get('summary') or '').strip()
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'message': '请输入正文内容'}), 400

    system_prompt = (
        "你是一名企业资讯编辑，请根据给定内容进行润色排版。"
        "输出为 Markdown，保持事实不变，不新增虚构信息。"
        "结构清晰，适当使用小标题、列表与重点强调。"
    )
    user_prompt = f"标题：{title}\n摘要：{summary}\n正文：\n{content}\n\n请输出润色后的 Markdown 正文。"
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]

    response, error = call_openai_api(messages, stream=False)
    if error:
        return jsonify({'success': False, 'message': error}), 500
    return jsonify({'success': True, 'content': response})


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
        
        # 图片：meta > 第一张图片
        image = parser.meta.get('image', '') or parser.first_img
        
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
                product['isBiosensing'] = True
                products.append(product)
    
    # 按类别排序
    category_order = {'iot': 0, 'module': 1, 'sensor': 2, 'detector': 3, 'alarm': 4, 'system': 5, 'probe': 6, 'service': 7}
    products.sort(key=lambda p: (category_order.get(p.get('category', 'module'), 99), p.get('name', '')))
    
    return jsonify({'products': products, 'count': len(products)})


# ============ Product Menu Settings API ============

PRODUCT_SETTINGS_FILE = DATA_DIR / 'product_settings.json'

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
    
    if 'categories' in data:
        # 支持多分类数组
        settings[product_id]['categories'] = list(data['categories']) if isinstance(data['categories'], list) else [data['categories']]
    
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
                products.append(product)

    # Scan customization directory
    if customization_dir.exists():
        for filepath in sorted(customization_dir.glob('*.html')):
            if filepath.name == 'index.html':
                continue
            product = extract_product_meta_from_html(filepath)
            if product:
                product['id'] = '../customization/' + product['id']
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
            product['categories'] = [product.get('category', 'module')]

    # Sort by custom sortOrder first, then by name
    products.sort(key=lambda p: (p.get('sortOrder', 999), p.get('name', '')))
    return products


# ============ Mega Menu Recommendations API ============

RECOMMENDATIONS_FILE = DATA_DIR / 'recommendations.json'

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
        recommendations['latestReleases'] = data['latestReleases']
    
    if 'applicationAreas' in data:
        recommendations['applicationAreas'] = data['applicationAreas']
    
    save_recommendations(recommendations)
    return jsonify({'success': True, 'recommendations': recommendations})


# ============ Hero Carousel API ============

@app.route('/api/hero', methods=['GET'])
def get_hero():
    """Get hero carousel configuration."""
    return jsonify(get_hero_config())


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
        return jsonify({'success': False, 'message': '未找到项目'}), 404

    if deleted_item.get('source') == 'upload':
        url = deleted_item.get('url', '')
        if url.startswith('/media/hero/'):
            filename = url.replace('/media/hero/', '')
            file_path = HERO_UPLOADS_DIR / filename
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
    return send_from_directory(HERO_UPLOADS_DIR, filename)


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
    for filepath in sorted(MESSAGES_DIR.glob('*.json'), reverse=True):
        try:
            msg = json.loads(filepath.read_text(encoding='utf-8'))
            messages.append(msg)
        except:
            continue
    return jsonify(messages)


@app.route('/api/messages/<message_id>', methods=['DELETE'])
@login_required
def delete_message(message_id):
    """Delete a message."""
    filepath = MESSAGES_DIR / f"{message_id}.json"
    if filepath.exists():
        filepath.unlink()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '留言不存在'}), 404


# ============ Chatbot API ============

# Knowledge base cache
_knowledge_cache = {
    'content': '',
    'last_updated': 0,
    'files': []
}
_knowledge_lock = threading.Lock()

def get_chatbot_config():
    """Get chatbot configuration from config."""
    config = get_config()
    return {
        'api_key': config.get('chatbot_api_key', ''),
        'api_base': config.get('chatbot_api_base', 'https://api.openai.com/v1'),
        'model': config.get('chatbot_model', 'gpt-3.5-turbo'),
        'system_prompt': config.get('chatbot_system_prompt', '''你是元芯传感的智能客服助手。你的职责是回答用户关于公司产品、技术和服务的问题。

公司信息：
- 公司名称：湖南元芯传感科技有限责任公司
- 主要业务：先进生物与化学传感技术解决方案
- 核心技术：碳基电子传感技术
- 主要产品：氢气传感器、生物传感器、气体检测模组

请用专业、友好的语气回答问题。如果遇到不确定的问题，请引导用户联系我们的销售团队。'''),
        'max_tokens': int(config.get('chatbot_max_tokens', 1000)),
        'temperature': float(config.get('chatbot_temperature', 0.7)),
        'enabled': config.get('chatbot_enabled', True)
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
        'max_tokens': config['max_tokens'],
        'temperature': config['temperature'],
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
        'max_tokens': config['max_tokens'],
        'temperature': config['temperature'],
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
    system_prompt = config['system_prompt']
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
    
    if 'system_prompt' in data:
        updates['chatbot_system_prompt'] = data['system_prompt']
    
    if 'max_tokens' in data:
        updates['chatbot_max_tokens'] = int(data['max_tokens'])
    
    if 'temperature' in data:
        updates['chatbot_temperature'] = float(data['temperature'])
    
    if 'enabled' in data:
        updates['chatbot_enabled'] = bool(data['enabled'])
    
    if updates:
        update_config(updates)
    
    return jsonify({'success': True, 'message': '配置已更新'})


# ============ Admin Routes ============

@app.route('/admin')
def admin_page():
    """Admin login/dashboard page."""
    return send_from_directory('admin', 'index.html')


@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Handle admin login."""
    data = request.form if request.form else request.json or {}
    username = data.get('username', '')
    password = data.get('password', '')
    
    config = get_config()
    
    if username == config['admin_username'] and password == config['admin_password']:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401


@app.route('/admin/change-password', methods=['POST'])
@login_required
def change_password():
    """Change admin username and password."""
    data = request.form if request.form else request.json or {}
    old_password = data.get('oldPassword', '')
    new_username = data.get('newUsername', '').strip()
    new_password = data.get('newPassword', '').strip()
    
    config = get_config()
    
    if old_password != config['admin_password']:
        return jsonify({'success': False, 'message': '原密码错误'}), 400
        
    if not new_username or not new_password:
         return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
         
    update_config({
        'admin_username': new_username,
        'admin_password': new_password
    })
    
    return jsonify({'success': True, 'message': '修改成功'})


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Handle admin logout."""
    session.pop('admin_logged_in', None)
    return jsonify({'success': True})


@app.route('/admin/check')
def admin_check():
    """Check if admin is logged in."""
    return jsonify({'logged_in': session.get('admin_logged_in', False)})


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
