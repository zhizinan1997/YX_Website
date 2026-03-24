"""Admin/auth route module."""

import os
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


def build_admin_changelog_payload(project_root=None):
    """Build admin changelog payload from env vars or git metadata."""
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]

    limit_raw = (os.environ.get('APP_CHANGELOG_LIMIT') or '6').strip()
    try:
        limit = max(1, min(int(limit_raw), 20))
    except ValueError:
        limit = 6

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
