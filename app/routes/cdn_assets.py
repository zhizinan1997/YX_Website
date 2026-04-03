"""
CDN Assets Management Module
Provides file management API for cdn_assets folder.
Supports recursive directory browsing.
"""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory, session

cdn_assets_bp = Blueprint('cdn_assets', __name__)

# Module-level variables (will be set by register_cdn_assets_routes)
_cdn_assets_dir = None
_config_file = None


def _get_config_file() -> Path:
    """Get the config file path."""
    if _config_file and _config_file.exists():
        return _config_file
    # Fallback: try common locations
    for candidate in [Path('data/config.json'), Path('data/site_config.json')]:
        if candidate.exists():
            return candidate
    return Path('data/config.json')


def _get_cdn_assets_dir() -> Path:
    """Get the cdn_assets directory path."""
    if _cdn_assets_dir:
        return Path(_cdn_assets_dir)
    return Path('cdn_assets')


def get_cdn_settings():
    """Get CDN settings from config file."""
    config_file = _get_config_file()
    if not config_file.exists():
        return {'cdn_enabled': False, 'cdn_domain': ''}

    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
        return {
            'cdn_enabled': bool(config.get('cdn_enabled', False)),
            'cdn_domain': str(config.get('cdn_domain') or '').strip().rstrip('/')
        }
    except Exception:
        return {'cdn_enabled': False, 'cdn_domain': ''}


def _check_auth():
    """Check admin authentication. Returns error response or None."""
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登录'}), 401
    return None


def _safe_subpath(base: Path, subpath: str) -> Path | None:
    """Resolve subpath under base directory safely, preventing traversal."""
    if not subpath:
        return base
    # Reject obvious traversal attempts
    if '..' in subpath.split('/'):
        return None
    resolved = (base / subpath).resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return None
    return resolved


def _build_file_url(relative_to_cdn: str) -> str:
    """Build the full URL for a cdn_assets file."""
    cdn_path = f'/cdn_assets/{relative_to_cdn}'
    settings = get_cdn_settings()
    if settings.get('cdn_enabled') and settings.get('cdn_domain'):
        return f"{settings['cdn_domain']}{cdn_path}"
    return cdn_path


@cdn_assets_bp.route('/api/cdn/assets/list', methods=['GET'])
def list_cdn_assets():
    """List files in cdn_assets folder, supporting subdirectory browsing."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    cdn_dir = _get_cdn_assets_dir()
    subpath = request.args.get('path', '').strip().strip('/')

    target_dir = _safe_subpath(cdn_dir, subpath)
    if target_dir is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    if not target_dir.is_dir():
        return jsonify({'success': False, 'message': '路径不是目录'}), 400

    try:
        files = []
        for item in sorted(target_dir.iterdir(),
                           key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith('.'):
                continue

            stat = item.stat()
            # Path relative to cdn_assets root
            rel = item.relative_to(cdn_dir.resolve())
            relative_path = f'/cdn_assets/{rel.as_posix()}'

            if item.is_dir():
                # Count children (non-hidden)
                child_count = sum(
                    1 for c in item.iterdir() if not c.name.startswith('.'))
                files.append({
                    'name': item.name,
                    'type': 'folder',
                    'size': 0,
                    'children': child_count,
                    'modified': datetime.fromtimestamp(
                        stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'url': relative_path
                })
            else:
                files.append({
                    'name': item.name,
                    'type': 'file',
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(
                        stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'url': relative_path
                })

        # Build breadcrumb parts
        breadcrumb = []
        if subpath:
            parts = subpath.split('/')
            for i, part in enumerate(parts):
                breadcrumb.append({
                    'name': part,
                    'path': '/'.join(parts[:i + 1])
                })

        return jsonify({
            'success': True,
            'files': files,
            'current_path': subpath,
            'breadcrumb': breadcrumb,
            'cdn_settings': get_cdn_settings()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取文件列表失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/upload', methods=['POST'])
def upload_cdn_asset():
    """Upload a file to cdn_assets folder (supports subdirectory)."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名不能为空'}), 400

    cdn_dir = _get_cdn_assets_dir()
    subpath = request.form.get('path', '').strip().strip('/')

    target_dir = _safe_subpath(cdn_dir, subpath)
    if target_dir is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        filename = file.filename
        filepath = target_dir / filename

        # Avoid overwrite: auto-rename
        counter = 1
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        while filepath.exists():
            filename = f"{stem}_{counter}{suffix}"
            filepath = target_dir / filename
            counter += 1

        file.save(str(filepath))

        rel = filepath.relative_to(cdn_dir.resolve())
        relative_path = f'/cdn_assets/{rel.as_posix()}'
        full_url = _build_file_url(rel.as_posix())

        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'file': {
                'name': filename,
                'size': filepath.stat().st_size,
                'url': relative_path,
                'full_url': full_url
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'上传失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/mkdir', methods=['POST'])
def mkdir_cdn_asset():
    """Create a new subdirectory inside cdn_assets."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    parent = data.get('path', '').strip().strip('/')
    folder_name = data.get('name', '').strip()

    if not folder_name:
        return jsonify({'success': False, 'message': '文件夹名不能为空'}), 400
    if '/' in folder_name or '..' in folder_name:
        return jsonify({'success': False, 'message': '非法文件夹名'}), 400

    cdn_dir = _get_cdn_assets_dir()
    parent_dir = _safe_subpath(cdn_dir, parent)
    if parent_dir is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    new_dir = parent_dir / folder_name
    if new_dir.exists():
        return jsonify({'success': False, 'message': '文件夹已存在'}), 400

    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        return jsonify({'success': True, 'message': '文件夹创建成功'})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'创建失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/delete', methods=['POST'])
def delete_cdn_asset():
    """Delete a file or folder from cdn_assets."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    filepath_str = data.get('path', '').strip().strip('/')

    if not filepath_str:
        return jsonify({'success': False, 'message': '路径不能为空'}), 400

    cdn_dir = _get_cdn_assets_dir()
    filepath = _safe_subpath(cdn_dir, filepath_str)
    if filepath is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    # Don't allow deleting the root
    if filepath.resolve() == cdn_dir.resolve():
        return jsonify({'success': False, 'message': '不能删除根目录'}), 400

    try:
        if not filepath.exists():
            return jsonify({'success': False, 'message': '文件不存在'}), 404

        if filepath.is_dir():
            shutil.rmtree(str(filepath))
        else:
            filepath.unlink()

        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/rename', methods=['POST'])
def rename_cdn_asset():
    """Rename a file or folder in cdn_assets."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    old_path_str = data.get('old_path', '').strip().strip('/')
    new_name = data.get('new_name', '').strip()

    # Backward compat: accept 'old_name' / 'new_name' at top level
    if not old_path_str:
        old_name = data.get('old_name', '').strip()
        if old_name:
            old_path_str = old_name

    if not old_path_str or not new_name:
        return jsonify({'success': False, 'message': '路径或新名称不能为空'}), 400

    if '/' in new_name or '..' in new_name:
        return jsonify({'success': False, 'message': '非法文件名'}), 400

    cdn_dir = _get_cdn_assets_dir()
    old_path = _safe_subpath(cdn_dir, old_path_str)
    if old_path is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    new_path = old_path.parent / new_name

    try:
        if not old_path.exists():
            return jsonify({'success': False, 'message': '文件不存在'}), 404

        if new_path.exists():
            return jsonify({
                'success': False,
                'message': '目标名已存在'
            }), 400

        old_path.rename(new_path)

        rel = new_path.relative_to(cdn_dir.resolve())
        relative_path = f'/cdn_assets/{rel.as_posix()}'
        full_url = _build_file_url(rel.as_posix())

        return jsonify({
            'success': True,
            'message': '重命名成功',
            'file': {
                'name': new_name,
                'url': relative_path,
                'full_url': full_url
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'重命名失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/download/<path:filepath>', methods=['GET'])
def download_cdn_asset(filepath):
    """Download a file from cdn_assets."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    cdn_dir = _get_cdn_assets_dir()
    full_path = _safe_subpath(cdn_dir, filepath)
    if full_path is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    if not full_path.exists() or not full_path.is_file():
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    try:
        return send_from_directory(
            str(full_path.parent),
            full_path.name,
            as_attachment=True,
            download_name=full_path.name
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'下载失败: {str(e)}'
        }), 500


@cdn_assets_bp.route('/api/cdn/assets/url', methods=['GET'])
def get_asset_url():
    """Get the full URL for an asset."""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    filepath_str = request.args.get('path', '').strip().strip('/')
    # Backward compat
    if not filepath_str:
        filepath_str = request.args.get('filename', '').strip().strip('/')

    if not filepath_str:
        return jsonify({'success': False, 'message': '路径不能为空'}), 400

    cdn_dir = _get_cdn_assets_dir()
    filepath = _safe_subpath(cdn_dir, filepath_str)
    if filepath is None:
        return jsonify({'success': False, 'message': '非法路径'}), 400

    if not filepath.exists():
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    relative_path = f'/cdn_assets/{filepath_str}'
    full_url = _build_file_url(filepath_str)
    cdn_settings = get_cdn_settings()

    return jsonify({
        'success': True,
        'filename': filepath.name,
        'relative_url': relative_path,
        'full_url': full_url,
        'cdn_enabled': cdn_settings.get('cdn_enabled', False),
        'cdn_domain': cdn_settings.get('cdn_domain', '')
    })


def register_cdn_assets_routes(app, cdn_assets_dir=None,
                                site_config_file=None):
    """Register CDN assets routes to the Flask app."""
    global _cdn_assets_dir, _config_file
    _cdn_assets_dir = cdn_assets_dir
    # Accept either site_config_file or find config.json in data/
    if site_config_file:
        cfg = Path(site_config_file)
        if cfg.exists():
            _config_file = cfg
        else:
            # Try config.json in the same directory
            alt = cfg.parent / 'config.json'
            _config_file = alt if alt.exists() else cfg
    app.register_blueprint(cdn_assets_bp)
