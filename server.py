"""
Flask server for YX Website with feedback form backend and admin panel.
Supports both local development and Docker deployment.
"""
import os
import json
import time
import hashlib
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'metachip-secret-key-2024')

# Configuration
DATA_DIR = Path(__file__).parent / 'data'
MESSAGES_DIR = DATA_DIR / 'messages'
RATE_LIMIT_FILE = DATA_DIR / 'rate_limits.json'
CONFIG_FILE = DATA_DIR / 'config.json'

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
