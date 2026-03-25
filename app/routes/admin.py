"""Admin/auth route module."""

import hmac
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import jsonify, make_response, request, send_from_directory, session

LOGIN_FAIL_WINDOW_SECONDS = 12 * 3600
LOGIN_FAIL_LIMIT = 3
LOGIN_BLOCK_SECONDS = 12 * 3600
LOGIN_ATTEMPTS_LOCK = threading.Lock()


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


def _get_login_attempts_file(project_root: Path) -> Path:
    data_dir = (project_root / 'data').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'admin_login_attempts.json'


def _load_login_attempts(file_path: Path):
    default_state = {'ips': {}}
    if not file_path.exists():
        return default_state
    try:
        data = json.loads(file_path.read_text(encoding='utf-8'))
        if isinstance(data, dict) and isinstance(data.get('ips'), dict):
            return data
    except Exception:
        pass
    return default_state


def _save_login_attempts(file_path: Path, state):
    safe_state = state if isinstance(state, dict) else {'ips': {}}
    if not isinstance(safe_state.get('ips'), dict):
        safe_state['ips'] = {}
    tmp = file_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file_path)


def _get_request_ip(req):
    trust_proxy_headers = (os.environ.get('TRUST_PROXY_HEADERS') or '').strip() == '1'
    if trust_proxy_headers:
        xff = (req.headers.get('X-Forwarded-For') or '').strip()
        if xff:
            first = xff.split(',')[0].strip()
            if first:
                return first
        x_real_ip = (req.headers.get('X-Real-IP') or '').strip()
        if x_real_ip:
            return x_real_ip
    return (req.remote_addr or 'unknown').strip() or 'unknown'


def _prune_login_attempts(state, now_ts: int):
    ips = state.get('ips') if isinstance(state, dict) else {}
    if not isinstance(ips, dict):
        state['ips'] = {}
        return
    to_delete = []
    for ip, item in ips.items():
        if not isinstance(item, dict):
            to_delete.append(ip)
            continue
        failures = item.get('failures', [])
        failures = [int(ts) for ts in failures if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
        blocked_until = int(item.get('blocked_until', 0) or 0)
        if blocked_until <= now_ts:
            blocked_until = 0
        if not failures and blocked_until <= 0:
            to_delete.append(ip)
        else:
            item['failures'] = failures
            item['blocked_until'] = blocked_until
            ips[ip] = item
    for ip in to_delete:
        ips.pop(ip, None)


def _register_login_failure(state, ip_addr: str, now_ts: int):
    ips = state.setdefault('ips', {})
    item = ips.get(ip_addr, {}) if isinstance(ips.get(ip_addr), dict) else {}
    failures = [int(ts) for ts in item.get('failures', []) if isinstance(ts, (int, float)) and now_ts - int(ts) <= LOGIN_FAIL_WINDOW_SECONDS]
    failures.append(now_ts)
    blocked_until = int(item.get('blocked_until', 0) or 0)

    is_blocked_now = False
    if len(failures) >= LOGIN_FAIL_LIMIT:
        blocked_until = now_ts + LOGIN_BLOCK_SECONDS
        failures = []
        is_blocked_now = True

    item['failures'] = failures
    item['blocked_until'] = blocked_until
    ips[ip_addr] = item
    remaining = max(0, LOGIN_FAIL_LIMIT - len(failures))
    return is_blocked_now, blocked_until, remaining


def _reset_login_attempts_for_ip(state, ip_addr: str):
    ips = state.get('ips') if isinstance(state, dict) else {}
    if isinstance(ips, dict):
        ips.pop(ip_addr, None)


def _format_blocked_until(ts_value: int) -> str:
    ts = int(ts_value or 0)
    if ts <= 0:
        return ''
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


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
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'same-origin'
        return resp

    @app.route('/admin/login', methods=['POST'])
    def admin_login():
        """Handle admin login."""
        data = request.form if request.form else request.get_json(silent=True) or {}
        username = str(data.get('username', '') or '').strip()
        password = str(data.get('password', '') or '')
        ip_addr = _get_request_ip(request)
        now_ts = int(time.time())
        root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        attempts_file = _get_login_attempts_file(root)
        config = get_config()
        admin_username = str(config.get('admin_username', '') or '')
        admin_password = str(config.get('admin_password', '') or '')
        credentials_ok = (
            hmac.compare_digest(username, admin_username)
            and hmac.compare_digest(password, admin_password)
        )
        if not username and not password:
            fail_reason = '用户名和密码不能为空'
        elif not username:
            fail_reason = '用户名不能为空'
        elif not password:
            fail_reason = '密码不能为空'
        else:
            fail_reason = '用户名或密码错误'

        failed_payload = None
        failed_status = 401
        failed_detail = ''

        with LOGIN_ATTEMPTS_LOCK:
            attempts_state = _load_login_attempts(attempts_file)
            _prune_login_attempts(attempts_state, now_ts)
            ip_item = attempts_state.get('ips', {}).get(ip_addr, {})
            blocked_until = int(ip_item.get('blocked_until', 0) or 0) if isinstance(ip_item, dict) else 0

            if blocked_until > now_ts:
                _save_login_attempts(attempts_file, attempts_state)
                blocked_at = _format_blocked_until(blocked_until)
                failed_payload = {
                    'success': False,
                    'message': f'当前 IP 已被封禁，解封时间：{blocked_at}，请稍后再试。'
                }
                failed_status = 429
                failed_detail = f'IP 被封禁，解封时间：{blocked_at or blocked_until}'
            elif credentials_ok:
                _reset_login_attempts_for_ip(attempts_state, ip_addr)
                _save_login_attempts(attempts_file, attempts_state)
            else:
                is_blocked_now, blocked_until, remaining = _register_login_failure(attempts_state, ip_addr, now_ts)
                _save_login_attempts(attempts_file, attempts_state)
                if is_blocked_now:
                    blocked_at = _format_blocked_until(blocked_until)
                    failed_payload = {
                        'success': False,
                        'message': f'{fail_reason}。同一 IP 在 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，已封禁至 {blocked_at}。'
                    }
                    failed_status = 429
                    failed_detail = f'{fail_reason}；同一 IP 12 小时内失败达到 {LOGIN_FAIL_LIMIT} 次，封禁至 {blocked_at or blocked_until}'
                else:
                    failed_payload = {
                        'success': False,
                        'message': f'{fail_reason}。当前 IP 还可再尝试 {remaining} 次（超过将封禁 12 小时）。'
                    }
                    failed_status = 400 if fail_reason != '用户名或密码错误' else 401
                    failed_detail = f'{fail_reason}；当前 IP 在 12 小时窗口内剩余尝试次数：{remaining}'

        if failed_payload is not None:
            append_admin_login_log(
                operation='后台登录',
                success=False,
                username=username,
                detail=failed_detail
            )
            return jsonify(failed_payload), failed_status

        # Successful login: clear old session to reduce fixation risk.
        session.clear()
        session['admin_logged_in'] = True
        session['admin_username'] = admin_username
        append_admin_login_log(
            operation='后台登录',
            success=True,
            username=admin_username,
            detail='用户名和密码验证通过'
        )
        return jsonify({'success': True})

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
        # Backward-compatible mode: ?limit=300
        limit_raw = request.args.get('limit')
        page_raw = request.args.get('page')
        page_size_raw = request.args.get('page_size')
        if limit_raw and page_raw is None and page_size_raw is None:
            try:
                limit = int(limit_raw)
            except (TypeError, ValueError):
                limit = 200
            limit = max(1, min(limit, 1000))

            with admin_login_log_lock:
                items = load_admin_login_logs()

            output = list(reversed(items))[:limit]
            return jsonify({'items': output, 'count': len(output)})

        try:
            page = int(page_raw or '1')
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(page_size_raw or '20')
        except (TypeError, ValueError):
            page_size = 20

        page = max(1, page)
        page_size = max(5, min(page_size, 200))

        with admin_login_log_lock:
            items = list(reversed(load_admin_login_logs()))

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        start = (page - 1) * page_size
        end = start + page_size
        output = items[start:end]

        return jsonify({
            'items': output,
            'count': len(output),
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        })

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
