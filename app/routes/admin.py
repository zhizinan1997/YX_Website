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


def _parse_datetime_safe(raw_value: str):
    """Parse datetime with several common formats."""
    value = (raw_value or '').strip()
    if not value:
        return None
    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _to_display_time(dt_value):
    """Format datetime object to standard string."""
    if not isinstance(dt_value, datetime):
        return ''
    return dt_value.strftime('%Y-%m-%d %H:%M:%S')


def _get_changelog_dir(project_root: Path) -> Path:
    """Get changelog directory from env or default folder."""
    explicit = (os.environ.get('APP_CHANGELOG_DIR') or '').strip()
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        return p
    return (project_root / 'update_logs').resolve()


def _find_local_update_logs(project_root: Path):
    """Locate all local changelog markdown files in update log directory."""
    explicit_file = (os.environ.get('APP_CHANGELOG_FILE') or '').strip()
    if explicit_file:
        p = Path(explicit_file).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if p.exists() and p.is_file():
            return [p]
        return []

    changelog_dir = _get_changelog_dir(project_root)
    if not changelog_dir.exists() or not changelog_dir.is_dir():
        return []

    files = [p for p in changelog_dir.glob('*.md') if p.is_file()]
    return sorted(files, key=lambda p: p.name, reverse=True)


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


def _normalize_version_text(raw: str):
    value = (raw or '').strip()
    if not value:
        return ''
    if value.lower().startswith('v'):
        return value
    return f'v{value}'


def _extract_release_from_markdown(log_file: Path, item_limit: int):
    """Build one structured release item from one markdown file."""
    try:
        text = log_file.read_text(encoding='utf-8')
    except Exception:
        return None

    version = _normalize_version_text(_extract_markdown_field(
        text,
        (
            r'版本(?:号)?\s*[:：]\s*(.+)$',
            r'VERSION\s*[:：]\s*(.+)$',
        ),
    ))
    if not version:
        m_version = re.search(r'v(\d+(?:\.\d+)*)', log_file.name, flags=re.IGNORECASE)
        if m_version:
            version = f"v{m_version.group(1)}"

    build_time_raw = _extract_markdown_field(
        text,
        (
            r'构建时间\s*[:：]\s*(.+)$',
            r'更新时间\s*[:：]\s*(.+)$',
            r'BUILD(?:_TIME)?\s*[:：]\s*(.+)$',
            r'DATE\s*[:：]\s*(.+)$',
        ),
    )
    build_dt = _parse_datetime_safe(build_time_raw)
    if not build_dt:
        m_date = re.search(r'(\d{4}-\d{2}-\d{2})', log_file.name)
        if m_date:
            build_dt = _parse_datetime_safe(m_date.group(1))
    if not build_dt:
        try:
            build_dt = datetime.fromtimestamp(log_file.stat().st_mtime)
        except OSError:
            build_dt = datetime.now()

    if not version:
        version = f"v{build_dt.strftime('%Y.%m.%d')}"

    updates = _extract_updates_from_markdown(text, item_limit)
    if not updates:
        updates = [f'已读取本地更新日志：{log_file.name}']

    return {
        'version': version,
        'build_time': _to_display_time(build_dt),
        'updates': updates[:item_limit],
        '_sort_key': build_dt.timestamp(),
    }


def _build_local_changelog_history(project_root: Path, release_limit: int, item_limit: int):
    """Build structured release history from local markdown files."""
    files = _find_local_update_logs(project_root)
    if not files:
        return []

    history = []
    for log_file in files:
        release = _extract_release_from_markdown(log_file, item_limit)
        if release:
            history.append(release)

    if not history:
        return []

    history.sort(key=lambda item: item.get('_sort_key', 0), reverse=True)
    normalized = []
    for item in history[:release_limit]:
        normalized.append({
            'version': item.get('version', 'v1.0.0'),
            'build_time': item.get('build_time', ''),
            'updates': item.get('updates', []),
        })
    return normalized


def build_admin_changelog_payload(project_root=None):
    """Build admin changelog payload from local markdown history, env vars or git metadata."""
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]

    release_limit_raw = (os.environ.get('APP_CHANGELOG_LIMIT') or '20').strip()
    item_limit_raw = (os.environ.get('APP_CHANGELOG_ITEM_LIMIT') or '12').strip()
    try:
        release_limit = max(1, min(int(release_limit_raw), 50))
    except ValueError:
        release_limit = 20
    try:
        item_limit = max(1, min(int(item_limit_raw), 50))
    except ValueError:
        item_limit = 12

    history = _build_local_changelog_history(root, release_limit, item_limit)
    if history:
        latest = history[0]
        return {
            'version': latest.get('version', 'v1.0.0'),
            'build_time': latest.get('build_time', ''),
            'updates': latest.get('updates', []),
            'history': history,
        }

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

    updates_text = _run_git_command(['log', f'-n{item_limit}', '--pretty=%s'], root)
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
        'updates': updates[:item_limit],
        'history': [{
            'version': version,
            'build_time': build_time,
            'updates': updates[:item_limit],
        }],
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

    @app.route('/api/changelog/latest')
    def public_changelog_latest():
        """Public endpoint for homepage test-version popup."""
        payload = build_admin_changelog_payload(project_root=project_root)
        history_raw = payload.get('history') if isinstance(payload, dict) else []
        history = []
        if isinstance(history_raw, list):
            for item in history_raw:
                if not isinstance(item, dict):
                    continue
                updates_raw = item.get('updates', [])
                updates = [str(x).strip() for x in updates_raw if str(x or '').strip()]
                history.append({
                    'version': str(item.get('version', '')).strip() or 'v1.0.0',
                    'build_time': str(item.get('build_time', '')).strip(),
                    'updates': updates,
                })

        if not history:
            updates_raw = payload.get('updates') if isinstance(payload, dict) else []
            updates = [str(item).strip() for item in updates_raw if str(item or '').strip()]
            history = [{
                'version': str(payload.get('version', 'v1.0.0')),
                'build_time': str(payload.get('build_time', '')),
                'updates': updates,
            }]

        latest = history[0] if history else {'version': 'v1.0.0', 'build_time': '', 'updates': []}
        latest_updates = latest.get('updates') if isinstance(latest.get('updates'), list) else []
        latest_update = latest_updates[0] if latest_updates else '暂无更新内容'
        return jsonify({
            'version': str(latest.get('version', 'v1.0.0')),
            'build_time': str(latest.get('build_time', '')),
            'latest_update': latest_update,
            'history': history,
        })
