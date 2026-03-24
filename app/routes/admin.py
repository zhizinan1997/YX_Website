"""Admin/auth route module."""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from flask import jsonify, make_response, request, send_from_directory, session


def _run_git_command(args, cwd: Path) -> str:
    """Run git command safely and return trimmed stdout."""
    try:
        proc = subprocess.run(
            ['git', *args],
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except Exception:
        return ''

    if proc.returncode != 0:
        return ''
    return (proc.stdout or '').strip()


def _find_local_update_log(project_root: Path):
    """Locate changelog markdown file from env or UPDATE_LOG_*.md convention."""
    explicit = (os.environ.get('APP_CHANGELOG_FILE') or '').strip()
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if p.exists() and p.is_file():
            return p

    candidates = []
    for p in project_root.glob('UPDATE_LOG_*.md'):
        if p.is_file():
            m = re.search(r'UPDATE_LOG_(\d{4}-\d{2}-\d{2})', p.name)
            date_key = m.group(1) if m else ''
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0
            candidates.append((date_key, mtime, p.name, p))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][3]


def _extract_updates_from_markdown(text: str, limit: int):
    """Extract markdown list items as logical entries (merge nested sub-items)."""
    items = []
    current = ''
    in_code_block = False

    for raw in text.splitlines():
        line = (raw or '').rstrip()
        stripped = line.strip()

        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            continue

        bullet_match = re.match(r'^(\s*)[-*]\s+(.+)$', line)
        if bullet_match:
            indent = len((bullet_match.group(1) or '').expandtabs(4))
            value = re.sub(r'\s+', ' ', (bullet_match.group(2) or '').strip())
            if not value:
                continue

            # Top-level bullet starts a new entry.
            if indent <= 1 or not current:
                if current:
                    items.append(current.strip())
                    if len(items) >= limit:
                        return items[:limit]
                current = value
            else:
                # Nested bullet belongs to previous top-level entry.
                current = f"{current}\n• {value}".strip()
            continue

        numbered_match = re.match(r'^(\s*)\d+[.)]\s+(.+)$', line)
        if numbered_match:
            indent = len((numbered_match.group(1) or '').expandtabs(4))
            value = re.sub(r'\s+', ' ', (numbered_match.group(2) or '').strip())
            if not value:
                continue

            if indent > 1 and current:
                current = f"{current}\n• {value}".strip()
            else:
                if current:
                    items.append(current.strip())
                    if len(items) >= limit:
                        return items[:limit]
                current = value
            continue

        # Continuation line: append to current item instead of creating a new one.
        if current and not stripped.startswith('#'):
            continuation = re.sub(r'\s+', ' ', stripped)
            if continuation:
                current = f"{current} {continuation}".strip()

    if current and len(items) < limit:
        items.append(current.strip())
    return items[:limit]


def _extract_markdown_field(text: str, patterns):
    """Extract one-line field value with regex patterns."""
    for raw in text.splitlines():
        line = (raw or '').strip()
        if not line:
            continue
        for pattern in patterns:
            m = re.search(pattern, line, flags=re.IGNORECASE)
            if m:
                value = (m.group(1) or '').strip().strip('`')
                if value:
                    return value
    return ''


def _build_payload_from_local_markdown(project_root: Path, limit: int):
    """Build changelog payload from local markdown log if available."""
    log_file = _find_local_update_log(project_root)
    if not log_file:
        return None

    try:
        text = log_file.read_text(encoding='utf-8')
    except Exception:
        return None

    version = (os.environ.get('APP_VERSION') or '').strip()
    build_time = (os.environ.get('APP_BUILD_TIME') or '').strip()

    if not version:
        version = _extract_markdown_field(
            text,
            (
                r'版本(?:号)?\s*[:：]\s*(.+)$',
                r'VERSION\s*[:：]\s*(.+)$',
            ),
        )
    if not version:
        m = re.search(r'UPDATE_LOG_(\d{4}-\d{2}-\d{2})', log_file.name)
        if m:
            version = f"v{m.group(1).replace('-', '.')}"

    if not build_time:
        build_time = _extract_markdown_field(
            text,
            (
                r'构建时间\s*[:：]\s*(.+)$',
                r'更新时间\s*[:：]\s*(.+)$',
                r'BUILD(?:_TIME)?\s*[:：]\s*(.+)$',
            ),
        )
    if not build_time:
        try:
            build_time = datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except OSError:
            build_time = ''

    updates = _extract_updates_from_markdown(text, limit)
    if not updates:
        updates = [f'已读取本地更新日志：{log_file.name}']

    return {
        'version': version or 'v1.0.0',
        'build_time': build_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'updates': updates[:limit],
    }


def build_admin_changelog_payload(project_root=None):
    """Build admin changelog payload from local markdown, env vars or git metadata."""
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]

    limit_raw = (os.environ.get('APP_CHANGELOG_LIMIT') or '12').strip()
    try:
        limit = max(1, min(int(limit_raw), 20))
    except ValueError:
        limit = 12

    local_payload = _build_payload_from_local_markdown(root, limit)
    if local_payload:
        return local_payload

    version = (os.environ.get('APP_VERSION') or '').strip()
    build_time = (os.environ.get('APP_BUILD_TIME') or '').strip()

    if not version:
        rev = _run_git_command(['rev-parse', '--short', 'HEAD'], root)
        if rev:
            version = f'v{rev}'

    if not build_time:
        build_time = _run_git_command(
            ['show', '-s', '--format=%cd', '--date=format:%Y-%m-%d %H:%M:%S', 'HEAD'],
            root,
        )

    updates_text = _run_git_command(['log', f'-n{limit}', '--pretty=%s'], root)
    updates = [line.strip() for line in updates_text.splitlines() if line.strip()] if updates_text else []

    if not version:
        version = 'v1.0.0'
    if not build_time:
        build_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not updates:
        updates = ['新增后台「更新日志」菜单，可查看版本号、构建时间与更新内容。']

    return {
        'version': version,
        'build_time': build_time,
        'updates': updates[:limit],
    }


def register_admin_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
    append_admin_login_log,
    load_admin_login_logs,
    admin_login_log_lock,
    project_root=None,
):
    """Register admin routes on the given Flask app."""

    @app.route('/admin', strict_slashes=False)
    def admin_page():
        """Admin login/dashboard page."""
        resp = make_response(send_from_directory('admin', 'index.html'))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    @app.route('/admin/login', methods=['POST'])
    def admin_login():
        """Handle admin login."""
        data = request.form if request.form else request.json or {}
        username = data.get('username', '')
        password = data.get('password', '')

        config = get_config()

        if username == config['admin_username'] and password == config['admin_password']:
            session['admin_logged_in'] = True
            session['admin_username'] = config['admin_username']
            append_admin_login_log(
                operation='后台登录',
                success=True,
                username=config['admin_username'],
                detail='用户名和密码验证通过'
            )
            return jsonify({'success': True})
        append_admin_login_log(
            operation='后台登录',
            success=False,
            username=username,
            detail='用户名或密码错误'
        )
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
        current_admin = session.get('admin_username') or config.get('admin_username', '')

        if old_password != config['admin_password']:
            append_admin_login_log(
                operation='修改账号密码',
                success=False,
                username=current_admin,
                detail='原密码校验失败'
            )
            return jsonify({'success': False, 'message': '原密码错误'}), 400

        if not new_username or not new_password:
            append_admin_login_log(
                operation='修改账号密码',
                success=False,
                username=current_admin,
                detail='新用户名或新密码为空'
            )
            return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

        update_config({
            'admin_username': new_username,
            'admin_password': new_password
        })
        session['admin_username'] = new_username
        append_admin_login_log(
            operation='修改账号密码',
            success=True,
            username=new_username,
            detail='账号信息更新成功'
        )

        return jsonify({'success': True, 'message': '修改成功'})

    @app.route('/admin/logout', methods=['POST'])
    def admin_logout():
        """Handle admin logout."""
        username = session.get('admin_username') or ''
        if session.get('admin_logged_in'):
            append_admin_login_log(
                operation='退出登录',
                success=True,
                username=username,
                detail='管理员主动退出'
            )
        session.pop('admin_logged_in', None)
        session.pop('admin_username', None)
        return jsonify({'success': True})

    @app.route('/admin/check')
    def admin_check():
        """Check if admin is logged in."""
        return jsonify({'logged_in': session.get('admin_logged_in', False)})

    @app.route('/api/admin/login-logs')
    @login_required
    def admin_login_logs():
        """Get immutable admin login-operation logs."""
        limit_raw = request.args.get('limit', '200')
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 200
        limit = max(1, min(limit, 1000))

        with admin_login_log_lock:
            items = load_admin_login_logs()

        output = list(reversed(items))[:limit]
        return jsonify({'items': output, 'count': len(output)})

    @app.route('/api/admin/changelog')
    @login_required
    def admin_changelog():
        """Get current version/build info and recent update entries."""
        return jsonify(build_admin_changelog_payload(project_root=project_root))
