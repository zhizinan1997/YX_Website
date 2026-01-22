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
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string, Response, stream_with_context

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

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'metachip-secret-key-2024')

# Configuration
DATA_DIR = Path(__file__).parent / 'data'
MESSAGES_DIR = DATA_DIR / 'messages'
KNOWLEDGE_DIR = DATA_DIR / 'knowledge'
RATE_LIMIT_FILE = DATA_DIR / 'rate_limits.json'
CONFIG_FILE = DATA_DIR / 'config.json'

# Ensure directories exist
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_MAX = 5  # Max submissions per IP per hour
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# Ensure directories exist
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

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
        'stream': stream
    }
    
    try:
        if HTTPX_SUPPORT and stream:
            # Use httpx for streaming
            with httpx.Client(timeout=60.0) as client:
                with client.stream('POST', api_url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        return None, f"API错误: {response.status_code}"
                    
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
                                        yield content
                            except json.JSONDecodeError:
                                continue
        elif REQUESTS_SUPPORT:
            if stream:
                response = requests.post(api_url, json=payload, headers=headers, stream=True, timeout=60)
                if response.status_code != 200:
                    return None, f"API错误: {response.status_code}"
                
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
                                        yield content
                            except json.JSONDecodeError:
                                continue
            else:
                response = requests.post(api_url, json=payload, headers=headers, timeout=60)
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
                for chunk in call_openai_api(messages, stream=True):
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
