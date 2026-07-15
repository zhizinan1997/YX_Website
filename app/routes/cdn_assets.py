"""
CDN素材管理路由模块。

本模块提供cdn_assets目录的完整文件管理功能，支持后台管理员
对静态资源的上传、浏览、重命名、删除等操作。

主要功能：
1. 文件列表浏览（/api/cdn/assets/list）
   - 递归列出目录内容
   - 支持子目录浏览
   - 显示文件大小、修改时间
   - 生成面包屑导航
   - 区分文件和文件夹

2. 文件上传（/api/cdn/assets/upload）
   - 支持多格式文件上传
   - 自动创建目标目录
   - 避免文件名冲突（自动重命名）
   - 返回文件URL和完整地址

3. 目录创建（/api/cdn/assets/mkdir）
   - 在指定路径创建子目录
   - 验证目录名合法性
   - 防止路径穿越攻击

4. 文件/目录删除（/api/cdn/assets/delete）
   - 删除指定文件或空目录
   - 递归删除目录树
   - 保护根目录不被删除

5. 重命名功能（/api/cdn/assets/rename）
   - 重命名文件或目录
   - 验证目标名称合法性
   - 检查目标名是否已存在
   - 兼容新旧参数格式

6. 文件下载（/api/cdn/assets/download）
   - 后台下载指定文件
   - 支持文件流传输

7. URL获取（/api/cdn/assets/url）
   - 获取文件的相对URL
   - 获取文件的完整CDN地址
   - 显示CDN配置状态

安全特性：
- 路径穿越防护（使用safe_subpath函数）
- 隐藏文件过滤（.开头文件不显示）
- 根目录保护（不允许删除）
- 登录状态校验
- 文件名合法性验证

CDN配置支持：
- 本地模式：使用/cdn_assets/路径
- CDN模式：使用配置的CDN域名
- 配置状态查询

文件组织：
cdn_assets/
├── images/
│   ├── common/
│   ├── products/
│   ├── news/
│   ├── gassensing/
│   ├── biosensing/
│   └── measurement/
├── research/
│   ├── development/
│   └── cooperation/
└── external-cache/

作者：元芯传感技术团队
"""
import os
import json
import shutil
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory, session

BEIJING_TZ = timezone(timedelta(hours=8))

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)

cdn_assets_bp = Blueprint('cdn_assets', __name__)

# 模块级配置变量，由素材路由注册入口统一注入。
_cdn_assets_dir = None
_config_file = None


def _get_config_file() -> Path:
    """获取配置文件路径。"""
    if _config_file and _config_file.exists():
        return _config_file
    # 兜底逻辑：尝试几个常见目录位置。
    for candidate in [Path('data/config.json'), Path('data/site_config.json')]:
        if candidate.exists():
            return candidate
    return Path('data/config.json')


def _get_cdn_assets_dir() -> Path:
    """获取素材目录路径。"""
    if _cdn_assets_dir:
        return Path(_cdn_assets_dir)
    return Path('cdn_assets')


def get_cdn_settings():
    """从配置文件读取 CDN 设置。"""
    config_file = _get_config_file()
    if not config_file.exists():
        return {'cdn_enabled': False, 'cdn_domain': ''}

    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
        legacy_enabled = bool(config.get('cdn_enabled', False))
        return {
            'cdn_enabled': False,
            'cdn_domain': str(config.get('cdn_domain') or '').strip().rstrip('/'),
            'legacy_cdn_enabled': legacy_enabled,
            'cdn_redirect_deprecated': True,
        }
    except Exception:
        return {'cdn_enabled': False, 'cdn_domain': ''}


def _check_auth():
    """检查后台登录状态，返回错误响应或 None。"""
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登录'}), 401
    return None


def _safe_subpath(base: Path, subpath: str) -> Path | None:
    """在基础目录下安全解析子路径，防止路径穿越。"""
    if not subpath:
        return base
    # 拒绝明显的路径穿越尝试。
    if '..' in subpath.split('/'):
        return None
    resolved = (base / subpath).resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return None
    return resolved


def _build_file_url(relative_to_cdn: str) -> str:
    """构建素材文件的完整访问地址。"""
    cdn_path = f'/cdn_assets/{relative_to_cdn}'
    return cdn_path


def _semantic_upload_name(original_name: str) -> str:
    path = Path(str(original_name or 'asset'))
    stem = path.stem.lower().strip()
    stem = re.sub(r'[^a-z0-9]+', '-', stem).strip('-')[:80] or 'asset'
    suffix = re.sub(r'[^a-z0-9.]', '', path.suffix.lower())[:12]
    return f'{stem}-{uuid.uuid4().hex[:10]}{suffix}'


@cdn_assets_bp.route('/api/cdn/assets/list', methods=['GET'])
def list_cdn_assets():
    """列出 cdn_assets 目录内容，并支持子目录浏览。"""
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
            # 相对于 `cdn_assets` 根目录的路径。
            rel = item.relative_to(cdn_dir.resolve())
            relative_path = f'/cdn_assets/{rel.as_posix()}'

            if item.is_dir():
                # 统计子项数量，忽略隐藏项。
                child_count = sum(
                    1 for c in item.iterdir() if not c.name.startswith('.'))
                files.append({
                    'name': item.name,
                    'type': 'folder',
                    'size': 0,
                    'children': child_count,
                    'modified': datetime.fromtimestamp(
                        stat.st_mtime, tz=BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                    'url': relative_path
                })
            else:
                files.append({
                    'name': item.name,
                    'type': 'file',
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(
                        stat.st_mtime, tz=BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                    'url': relative_path
                })

        # 构建面包屑路径。
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
    """上传文件到 cdn_assets 目录，支持子目录。"""
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
        filename = _semantic_upload_name(file.filename)
        filepath = target_dir / filename

        # 避免覆盖已有文件：自动重命名。
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
        if filepath.suffix.lower() in {'.avif', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp'}:
            try:
                from app.routes.image_seo import register_uploaded_image
                register_uploaded_image(relative_path, filepath)
            except Exception:
                pass

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
    """在素材目录下创建子目录。"""
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
    """删除 cdn_assets 中的文件或目录。"""
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

    # 不允许删除根目录。
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
    """重命名 cdn_assets 中的文件或目录。"""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    old_path_str = data.get('old_path', '').strip().strip('/')
    new_name = data.get('new_name', '').strip()

    # 兼容旧参数格式：顶层直接接收 `old_name` / `new_name`。
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
    """下载素材目录中的文件。"""
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
    """获取素材的完整访问 URL。"""
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    filepath_str = request.args.get('path', '').strip().strip('/')
    # 兼容旧调用格式。
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



# 路由注册入口。
def register_cdn_assets_routes(app, cdn_assets_dir=None,
                                site_config_file=None):
    """向 Flask 应用注册 CDN 素材管理路由。"""
    global _cdn_assets_dir, _config_file
    _cdn_assets_dir = cdn_assets_dir
    # 既支持显式传入站点配置文件，也支持在数据目录中自动查找配置文件。
    if site_config_file:
        cfg = Path(site_config_file)
        if cfg.exists():
            _config_file = cfg
        else:
            # 尝试同目录下的备用配置文件。
            alt = cfg.parent / 'config.json'
            _config_file = alt if alt.exists() else cfg
    app.register_blueprint(cdn_assets_bp)
