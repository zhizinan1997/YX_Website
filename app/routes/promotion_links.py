"""
推广链接管理路由。

该模块负责后台创建、维护带 UTM 参数的官网推广链接，并提供
按推广标记聚合的统计查询。二维码由后台前端即时生成，后端只保存
链接配置本身。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from flask import jsonify, request, session

PROMOTION_LINKS_FILE = Path(__file__).resolve().parents[2] / 'data' / 'promotion_links.json'
PROMOTION_LINKS_LOCK = threading.RLock()

PROMOTION_MARK_RULE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{1,62}[A-Za-z0-9]$')
UTM_SAFE_TEXT_RULE = re.compile(r'[^A-Za-z0-9._:-]+')
TRACKING_QUERY_KEYS = {
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_content',
    'utm_term',
    'utm_id',
}


def _clean_text(value, max_length=120):
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text[:max_length]


def normalize_promotion_mark(value: str) -> str:
    text = _clean_text(value, max_length=64)
    text = UTM_SAFE_TEXT_RULE.sub('-', text).strip('.:-_')
    return text[:64]


def _clean_utm(value, max_length=80):
    text = _clean_text(value, max_length=max_length)
    if not text:
        return ''
    return UTM_SAFE_TEXT_RULE.sub('-', text).strip('.:-_')[:max_length]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _read_json_file(path: Path, default):
    try:
        if not path.exists():
            return default
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default
    return data if isinstance(data, dict) else default


def _write_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f'.tmp-{uuid.uuid4().hex}')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def load_promotion_links(file_path: Path | None = None) -> list[dict]:
    path = Path(file_path or PROMOTION_LINKS_FILE)
    with PROMOTION_LINKS_LOCK:
        payload = _read_json_file(path, {'version': 1, 'items': []})
    items = payload.get('items') if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _save_promotion_links(items: list[dict], file_path: Path | None = None):
    path = Path(file_path or PROMOTION_LINKS_FILE)
    payload = {'version': 1, 'items': [item for item in items if isinstance(item, dict)]}
    with PROMOTION_LINKS_LOCK:
        _write_json_file(path, payload)


def _promotion_lookup(items: list[dict]) -> dict[str, dict]:
    lookup = {}
    for item in items:
        mark = normalize_promotion_mark(item.get('promotion_mark'))
        if mark and not item.get('archived_at') and mark not in lookup:
            lookup[mark] = item
    return lookup


def _base_url(get_public_base_url) -> str:
    base = ''
    if callable(get_public_base_url):
        base = str(get_public_base_url() or '').strip().rstrip('/')
    if not base:
        base = str(request.host_url or '').strip().rstrip('/')
    if not base:
        base = 'http://localhost:8000'
    return base


def _normalize_target_path(raw_value: str, *, base_url: str) -> str:
    value = _clean_text(raw_value, max_length=260)
    if not value:
        value = '/'
    parsed_base = urlparse(base_url)
    try:
        parsed = urlparse(value)
    except Exception as exc:
        raise ValueError('目标页面格式无效') from exc
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('目标页面只支持本站 http/https 链接')
        if parsed.netloc.lower() != parsed_base.netloc.lower():
            raise ValueError('目标页面必须是本站链接')
        path = parsed.path or '/'
        query = parsed.query or ''
    else:
        path = value.split('#', 1)[0]
        if '?' in path:
            path, query = path.split('?', 1)
        else:
            query = ''
    if not path.startswith('/'):
        path = '/' + path.lstrip('./')
    path = re.sub(r'/+', '/', path)[:220] or '/'
    pairs = [
        (key, val)
        for key, val in parse_qsl(query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS
    ]
    clean_query = urlencode(pairs, doseq=True)
    return f'{path}?{clean_query}' if clean_query else path


def build_promotion_url(item: dict, *, base_url: str) -> str:
    target = str(item.get('target_path') or '/')
    parsed = urlparse(target)
    pairs = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS
    ]
    fields = {
        'utm_source': item.get('utm_source'),
        'utm_medium': item.get('utm_medium'),
        'utm_campaign': item.get('utm_campaign'),
        'utm_content': item.get('utm_content'),
        'utm_term': item.get('utm_term'),
        'utm_id': item.get('promotion_mark'),
    }
    for key, value in fields.items():
        cleaned = _clean_utm(value, max_length=96)
        if cleaned:
            pairs.append((key, cleaned))
    query = urlencode(pairs, doseq=True)
    path = parsed.path or '/'
    return f'{base_url.rstrip("/")}{urlunparse(("", "", path, "", query, ""))}'


def _public_item(item: dict, *, base_url: str) -> dict:
    row = {
        'id': str(item.get('id') or ''),
        'name': _clean_text(item.get('name'), max_length=120),
        'promotion_mark': normalize_promotion_mark(item.get('promotion_mark')),
        'target_path': str(item.get('target_path') or '/'),
        'utm_source': _clean_utm(item.get('utm_source'), max_length=80),
        'utm_medium': _clean_utm(item.get('utm_medium'), max_length=80),
        'utm_campaign': _clean_utm(item.get('utm_campaign'), max_length=80),
        'utm_content': _clean_utm(item.get('utm_content'), max_length=80),
        'utm_term': _clean_utm(item.get('utm_term'), max_length=80),
        'enabled': bool(item.get('enabled', True)),
        'created_at': str(item.get('created_at') or ''),
        'updated_at': str(item.get('updated_at') or ''),
        'archived_at': str(item.get('archived_at') or ''),
    }
    row['url'] = build_promotion_url(row, base_url=base_url)
    return row


def _item_from_payload(payload: dict, *, base_url: str, existing: dict | None = None) -> dict:
    data = payload if isinstance(payload, dict) else {}
    now = _now_iso()
    if existing:
        mark = normalize_promotion_mark(existing.get('promotion_mark'))
    else:
        mark = normalize_promotion_mark(data.get('promotion_mark'))
        if not mark or not PROMOTION_MARK_RULE.match(mark):
            raise ValueError('推广标记需为 3-64 位，仅支持字母、数字、点、下划线、冒号和短横线，且首尾需为字母或数字。')

    name = _clean_text(data.get('name'), max_length=120)
    if not name:
        raise ValueError('请填写链接名称')
    target_path = _normalize_target_path(data.get('target_path') or '/', base_url=base_url)
    item = dict(existing or {})
    item.update({
        'name': name,
        'promotion_mark': mark,
        'target_path': target_path,
        'utm_source': _clean_utm(data.get('utm_source'), max_length=80),
        'utm_medium': _clean_utm(data.get('utm_medium'), max_length=80),
        'utm_campaign': _clean_utm(data.get('utm_campaign'), max_length=80),
        'utm_content': _clean_utm(data.get('utm_content'), max_length=80),
        'utm_term': _clean_utm(data.get('utm_term'), max_length=80),
        'enabled': bool(data.get('enabled', True)),
        'updated_at': now,
    })
    if not existing:
        item['id'] = uuid.uuid4().hex
        item['created_at'] = now
        item['archived_at'] = ''
    return item


def _find_item(items: list[dict], item_id: str):
    safe_id = str(item_id or '').strip()
    for index, item in enumerate(items):
        if str(item.get('id') or '') == safe_id:
            return item, index
    return None, -1


def _require_promotion_links_admin_api():
    if bool(session.get('admin_is_super_admin', False)):
        return None
    raw = session.get('admin_permissions', [])
    permissions = {str(item or '').strip() for item in raw} if isinstance(raw, (list, tuple, set)) else set()
    if 'promotion-links' in permissions:
        return None
    return jsonify({'success': False, 'message': '当前账号无权限访问推广链接'}), 403


def _require_unique_mark(items: list[dict], mark: str, current_id: str = ''):
    for item in items:
        if str(item.get('id') or '') == current_id:
            continue
        if normalize_promotion_mark(item.get('promotion_mark')) == mark:
            raise ValueError('推广标记已存在，请换一个唯一标记')


def register_promotion_link_routes(
    app,
    *,
    login_required,
    data_dir,
    get_public_base_url,
):
    """注册推广链接管理接口。"""
    global PROMOTION_LINKS_FILE
    PROMOTION_LINKS_FILE = Path(data_dir) / 'promotion_links.json'

    @app.route('/api/admin/promotion-links', methods=['GET'])
    @login_required
    def list_promotion_links_admin():
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        base = _base_url(get_public_base_url)
        include_archived = str(request.args.get('include_archived') or '').lower() in {'1', 'true', 'yes'}
        items = load_promotion_links(PROMOTION_LINKS_FILE)
        if not include_archived:
            items = [item for item in items if not item.get('archived_at')]
        rows = [_public_item(item, base_url=base) for item in items]
        rows.sort(key=lambda item: item.get('created_at') or '', reverse=True)
        return jsonify({'success': True, 'items': rows, 'base_url': base})

    @app.route('/api/admin/promotion-links', methods=['POST'])
    @login_required
    def create_promotion_link_admin():
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        base = _base_url(get_public_base_url)
        payload = request.get_json(silent=True) or {}
        try:
            with PROMOTION_LINKS_LOCK:
                items = load_promotion_links(PROMOTION_LINKS_FILE)
                item = _item_from_payload(payload, base_url=base)
                _require_unique_mark(items, item['promotion_mark'])
                items.append(item)
                _save_promotion_links(items, PROMOTION_LINKS_FILE)
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        return jsonify({'success': True, 'item': _public_item(item, base_url=base)})

    @app.route('/api/admin/promotion-links/<item_id>', methods=['PUT'])
    @login_required
    def update_promotion_link_admin(item_id):
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        base = _base_url(get_public_base_url)
        payload = request.get_json(silent=True) or {}
        try:
            with PROMOTION_LINKS_LOCK:
                items = load_promotion_links(PROMOTION_LINKS_FILE)
                existing, index = _find_item(items, item_id)
                if existing is None or existing.get('archived_at'):
                    return jsonify({'success': False, 'message': '推广链接不存在'}), 404
                requested_mark = normalize_promotion_mark(payload.get('promotion_mark'))
                if requested_mark and requested_mark != normalize_promotion_mark(existing.get('promotion_mark')):
                    return jsonify({'success': False, 'message': '推广标记创建后不能修改'}), 400
                item = _item_from_payload(payload, base_url=base, existing=existing)
                _require_unique_mark(items, item['promotion_mark'], current_id=str(item.get('id') or ''))
                items[index] = item
                _save_promotion_links(items, PROMOTION_LINKS_FILE)
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        return jsonify({'success': True, 'item': _public_item(item, base_url=base)})

    @app.route('/api/admin/promotion-links/<item_id>', methods=['DELETE'])
    @login_required
    def archive_promotion_link_admin(item_id):
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        base = _base_url(get_public_base_url)
        with PROMOTION_LINKS_LOCK:
            items = load_promotion_links(PROMOTION_LINKS_FILE)
            item, index = _find_item(items, item_id)
            if item is None or item.get('archived_at'):
                return jsonify({'success': False, 'message': '推广链接不存在'}), 404
            updated = dict(item)
            updated['enabled'] = False
            updated['archived_at'] = _now_iso()
            updated['updated_at'] = updated['archived_at']
            items[index] = updated
            _save_promotion_links(items, PROMOTION_LINKS_FILE)
        return jsonify({'success': True, 'item': _public_item(updated, base_url=base)})

    @app.route('/api/admin/promotion-links/stats', methods=['GET'])
    @login_required
    def promotion_link_stats_admin():
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        try:
            from app.routes.site_analytics import build_promotion_link_stats

            report = build_promotion_link_stats(
                start_date=request.args.get('start_date') or '',
                end_date=request.args.get('end_date') or '',
            )
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        except Exception:
            return jsonify({'success': False, 'message': '统计数据生成失败'}), 500
        return jsonify({'success': True, **report})

    @app.route('/api/admin/promotion-links/<item_id>/detail-stats', methods=['GET'])
    @login_required
    def promotion_link_detail_stats_admin(item_id):
        denied = _require_promotion_links_admin_api()
        if denied:
            return denied
        items = load_promotion_links(PROMOTION_LINKS_FILE)
        item, _index = _find_item(items, item_id)
        if item is None:
            return jsonify({'success': False, 'message': '推广链接不存在'}), 404
        try:
            from app.routes.site_analytics import build_promotion_link_detail_stats

            report = build_promotion_link_detail_stats(
                normalize_promotion_mark(item.get('promotion_mark')),
                start_date=request.args.get('start_date') or '',
                end_date=request.args.get('end_date') or '',
            )
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        except Exception:
            return jsonify({'success': False, 'message': '推广链接访问数据生成失败'}), 500
        return jsonify({'success': True, **report})


__all__ = [
    'PROMOTION_MARK_RULE',
    'build_promotion_url',
    'load_promotion_links',
    'normalize_promotion_mark',
    'register_promotion_link_routes',
]
