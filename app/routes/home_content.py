"""
首页内容管理路由模块。

本模块提供首页内容的管理功能，包括：
1. Hero轮播区管理
2. 合作伙伴展示
3. 首页区块显示控制
4. 派生图片生成

主要功能：
1. Hero轮播管理
   - 轮播项配置（图片/视频）
   - 轮播间隔设置
   - 多媒体URL管理
   - 派生图片生成（不同尺寸和格式）

2. 合作伙伴管理
   - Logo上传
   - URL链接配置
   - 显示顺序管理

3. 首页区块控制
   - 各区块显示/隐藏
   - 持久化配置

4. 派生图片处理
   - 自动生成多尺寸图片
   - 支持AVIF、WebP格式
   - 清单文件管理

作者：元芯传感技术团队
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from flask import jsonify, request, send_from_directory, session

from app.atomic_io import atomic_write_text


def get_hero_config(hero_config_file, sanitize_public_media_url):
    """从文件或默认值加载 Hero 轮播配置。"""
    hero_config_path = Path(hero_config_file)
    default_config = {
        'interval_seconds': 5,
        'cta_buttons_visible': True,
        'items': [],
    }

    if hero_config_path.exists():
        try:
            config = json.loads(hero_config_path.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            items = merged.get('items', [])
            if not isinstance(items, list):
                items = []
            merged['cta_buttons_visible'] = bool(merged.get('cta_buttons_visible', True))
            merged['items'] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get('type') or 'image').lower()
                if item_type not in {'image', 'video'}:
                    continue
                url = sanitize_public_media_url(item.get('url', ''), enforce_remote_public=False)
                if not url:
                    continue
                link_enabled = bool(item.get('link_enabled', False))
                link_url = str(item.get('link_url') or '').strip()
                normalized_item = {
                    'id': str(item.get('id') or uuid.uuid4().hex),
                    'type': item_type,
                    'url': url,
                    'source': 'upload' if str(item.get('source') or '').lower() == 'upload' else 'url',
                    'link_enabled': link_enabled,
                    'link_url': link_url if link_enabled else '',
                }
                if item_type == 'image':
                    mobile_url = sanitize_public_media_url(
                        item.get('mobile_url', ''),
                        enforce_remote_public=False,
                    )
                    if mobile_url:
                        normalized_item['mobile_url'] = mobile_url
                merged['items'].append(normalized_item)
            return merged
        except Exception:
            pass

    atomic_write_text(hero_config_path, json.dumps(default_config, indent=2, ensure_ascii=False))
    return default_config


def save_hero_config(new_config, *, hero_config_file, sanitize_public_media_url):
    """校验并保存 Hero 轮播配置。"""
    config = get_hero_config(hero_config_file, sanitize_public_media_url)
    interval_seconds = new_config.get('interval_seconds', config.get('interval_seconds', 5))
    try:
        interval_seconds = int(interval_seconds)
    except Exception:
        interval_seconds = 5
    interval_seconds = min(max(interval_seconds, 1), 60)
    cta_buttons_visible = bool(new_config.get('cta_buttons_visible', config.get('cta_buttons_visible', True)))

    items = new_config.get('items', config.get('items', []))
    normalized_items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get('id') or uuid.uuid4().hex)
            item_type = str(item.get('type') or 'image').lower()
            if item_type not in {'image', 'video'}:
                continue
            url = sanitize_public_media_url(item.get('url', ''), enforce_remote_public=True)
            if not url:
                continue
            link_enabled = bool(item.get('link_enabled', False))
            link_url = str(item.get('link_url') or '').strip()
            if link_enabled and link_url:
                if not link_url.startswith('https://') and not link_url.startswith('http://'):
                    link_url = ''
                    link_enabled = False
            else:
                link_url = ''
                link_enabled = False
            normalized_item = {
                'id': item_id,
                'type': item_type,
                'url': url,
                'source': str(item.get('source') or 'url').lower(),
                'link_enabled': link_enabled,
                'link_url': link_url,
            }
            if item_type == 'image':
                mobile_url = sanitize_public_media_url(
                    item.get('mobile_url', ''),
                    enforce_remote_public=True,
                )
                if mobile_url:
                    normalized_item['mobile_url'] = mobile_url
            normalized_items.append(normalized_item)

    saved = {
        'interval_seconds': interval_seconds,
        'cta_buttons_visible': cta_buttons_visible,
        'items': normalized_items,
    }
    atomic_write_text(Path(hero_config_file), json.dumps(saved, indent=2, ensure_ascii=False))
    return saved


def load_hero_derived_manifest(hero_derived_manifest_file):
    """从磁盘加载 Hero 派生图片清单。"""
    manifest_path = Path(hero_derived_manifest_file)
    default_manifest = {'version': 1, 'items': {}}
    if not manifest_path.exists():
        return default_manifest
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return default_manifest
    if not isinstance(payload, dict):
        return default_manifest
    items = payload.get('items')
    if not isinstance(items, dict):
        items = {}
    return {'version': 1, 'items': items}


def save_hero_derived_manifest(manifest, *, hero_derived_manifest_file):
    """将 Hero 派生图片清单持久化到磁盘。"""
    payload = manifest if isinstance(manifest, dict) else {'version': 1, 'items': {}}
    atomic_write_text(
        Path(hero_derived_manifest_file),
        json.dumps(payload, indent=2, ensure_ascii=False),
    )


def hero_source_filename_from_url(url: str) -> str:
    raw = (url or '').strip()
    if not raw.startswith('/media/hero/'):
        return ''
    return raw.replace('/media/hero/', '', 1).strip()


def _iter_hero_variant_filenames(entry):
    variants = (entry or {}).get('variants', {})
    if not isinstance(variants, dict):
        return []
    names = []
    for group in variants.values():
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            filename = str(item.get('filename') or '').strip()
            if filename:
                names.append(filename)
    return names


def remove_hero_variants_for_source(source_filename: str, *, hero_derived_dir, hero_derived_manifest_file):
    """删除某张 Hero 原图对应的派生图片并更新清单。"""
    source_name = (source_filename or '').strip()
    if not source_name:
        return
    derived_dir = Path(hero_derived_dir)
    manifest = load_hero_derived_manifest(hero_derived_manifest_file)
    items = manifest.get('items', {})
    if not isinstance(items, dict):
        items = {}
    entry = items.pop(source_name, None)
    if entry:
        for variant_name in _iter_hero_variant_filenames(entry):
            variant_path = derived_dir / variant_name
            if variant_path.exists():
                try:
                    variant_path.unlink()
                except Exception:
                    pass
    manifest['items'] = items
    save_hero_derived_manifest(manifest, hero_derived_manifest_file=hero_derived_manifest_file)


def _hero_can_encode_avif(*, pil_support, pil_features):
    if not pil_support or pil_features is None:
        return False
    try:
        return bool(pil_features.check('avif'))
    except Exception:
        return False


def generate_hero_variants_for_source(
    source_filename: str,
    *,
    pil_support,
    image_module,
    image_ops_module,
    pil_features,
    hero_uploads_dir,
    hero_derived_dir,
    hero_derived_manifest_file,
    hero_source_image_extensions,
    hero_derived_widths,
    hero_derived_formats,
):
    """为单张 Hero 原图生成 AVIF/WebP 响应式派生图。"""
    source_name = (source_filename or '').strip()
    if not source_name or not pil_support:
        return None

    uploads_dir = Path(hero_uploads_dir)
    derived_dir = Path(hero_derived_dir)
    source_path = uploads_dir / source_name
    if not source_path.exists() or source_path.suffix.lower() not in hero_source_image_extensions:
        return None

    try:
        with image_module.open(source_path) as raw_img:
            img = image_ops_module.exif_transpose(raw_img)
            src_width, src_height = img.size
            if src_width <= 0 or src_height <= 0:
                return None
            if img.mode in ('RGBA', 'LA') or ('transparency' in img.info):
                base_img = img.convert('RGBA')
            else:
                base_img = img.convert('RGB')
    except Exception:
        return None

    resample = image_module.Resampling.LANCZOS if hasattr(image_module, 'Resampling') else image_module.LANCZOS
    variant_widths = sorted({w for w in hero_derived_widths if isinstance(w, int) and w > 0})
    if src_width not in variant_widths:
        variant_widths.append(src_width)
    variant_widths = sorted({min(src_width, w) for w in variant_widths if w > 0})

    allow_avif = _hero_can_encode_avif(pil_support=pil_support, pil_features=pil_features)
    format_map = []
    for fmt in hero_derived_formats:
        if fmt == 'avif' and not allow_avif:
            continue
        if fmt == 'webp':
            format_map.append(('webp', 'WEBP', {'quality': 80, 'method': 6}))
        elif fmt == 'avif':
            format_map.append(('avif', 'AVIF', {'quality': 50, 'speed': 6}))

    if not format_map:
        return None

    base_name = Path(source_name).stem
    variants = {}
    created_files = set()
    for fmt_name, pil_format, save_options in format_map:
        rows = []
        for width in variant_widths:
            width = int(width)
            if width <= 0:
                continue
            if width == src_width:
                resized = base_img.copy()
                height = src_height
            else:
                height = max(1, int(round(src_height * width / src_width)))
                resized = base_img.resize((width, height), resample)
            out_filename = f'{base_name}-w{width}.{fmt_name}'
            out_path = derived_dir / out_filename
            try:
                resized.save(out_path, pil_format, **save_options)
            except Exception:
                continue
            rows.append({'width': width, 'filename': out_filename})
            created_files.add(out_filename)
        if rows:
            rows.sort(key=lambda item: int(item.get('width', 0)))
            variants[fmt_name] = rows

    if not variants:
        return None

    manifest = load_hero_derived_manifest(hero_derived_manifest_file)
    items = manifest.get('items', {})
    if not isinstance(items, dict):
        items = {}
    old_entry = items.get(source_name, {})
    stale_files = set(_iter_hero_variant_filenames(old_entry)) - created_files
    for stale in stale_files:
        stale_path = derived_dir / stale
        if stale_path.exists():
            try:
                stale_path.unlink()
            except Exception:
                pass

    new_entry = {
        'width': int(src_width),
        'height': int(src_height),
        'variants': variants,
        'updated_at': int(time.time()),
    }
    items[source_name] = new_entry
    manifest['items'] = items
    save_hero_derived_manifest(manifest, hero_derived_manifest_file=hero_derived_manifest_file)
    return new_entry


def build_hero_api_payload(
    *,
    hero_config_file,
    sanitize_public_media_url,
    hero_derived_manifest_file,
    pil_support,
    image_module,
    image_ops_module,
    pil_features,
    hero_uploads_dir,
    hero_derived_dir,
    hero_source_image_extensions,
    hero_derived_widths,
    hero_derived_formats,
):
    """在可用时为 Hero 接口构建带响应式图片源的返回载荷。"""
    config = get_hero_config(hero_config_file, sanitize_public_media_url)
    items = config.get('items', [])
    if not isinstance(items, list):
        items = []

    manifest_items = load_hero_derived_manifest(hero_derived_manifest_file).get('items', {})
    if not isinstance(manifest_items, dict):
        manifest_items = {}

    def image_payload_for_url(raw_url):
        fallback_url = str(raw_url or '').strip()
        result = {'fallback': fallback_url}
        source_name = hero_source_filename_from_url(fallback_url)
        if not source_name:
            return result

        entry = manifest_items.get(source_name)
        if not isinstance(entry, dict) and pil_support:
            entry = generate_hero_variants_for_source(
                source_name,
                pil_support=pil_support,
                image_module=image_module,
                image_ops_module=image_ops_module,
                pil_features=pil_features,
                hero_uploads_dir=hero_uploads_dir,
                hero_derived_dir=hero_derived_dir,
                hero_derived_manifest_file=hero_derived_manifest_file,
                hero_source_image_extensions=hero_source_image_extensions,
                hero_derived_widths=hero_derived_widths,
                hero_derived_formats=hero_derived_formats,
            )
            if isinstance(entry, dict):
                manifest_items[source_name] = entry
        if not isinstance(entry, dict):
            return result

        width = int(entry.get('width') or 0)
        height = int(entry.get('height') or 0)
        if width > 0:
            result['width'] = width
        if height > 0:
            result['height'] = height

        variants = entry.get('variants', {})
        if not isinstance(variants, dict):
            return result

        sources = []
        for fmt in hero_derived_formats:
            rows = variants.get(fmt, [])
            if not isinstance(rows, list) or not rows:
                continue
            srcset_parts = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                variant_name = str(row.get('filename') or '').strip()
                variant_width = int(row.get('width') or 0)
                if not variant_name or variant_width <= 0:
                    continue
                srcset_parts.append(f'/media/hero-derived/{variant_name} {variant_width}w')
            if srcset_parts:
                sources.append({
                    'type': f'image/{fmt}',
                    'srcset': ', '.join(srcset_parts),
                    'sizes': '100vw',
                })
        if sources:
            result['sources'] = sources
        return result

    payload_items = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        if str(item.get('type') or '').lower() != 'image':
            payload_items.append(item)
            continue

        desktop_payload = image_payload_for_url(item.get('url'))
        item.update(desktop_payload)
        mobile_url = str(item.get('mobile_url') or '').strip()
        if mobile_url:
            mobile_payload = image_payload_for_url(mobile_url)
            item['mobile_fallback'] = mobile_payload.get('fallback', mobile_url)
            if mobile_payload.get('sources'):
                item['mobile_sources'] = mobile_payload['sources']
            if mobile_payload.get('width'):
                item['mobile_width'] = mobile_payload['width']
            if mobile_payload.get('height'):
                item['mobile_height'] = mobile_payload['height']
        payload_items.append(item)

    return {
        'interval_seconds': config.get('interval_seconds', 5),
        'cta_buttons_visible': bool(config.get('cta_buttons_visible', True)),
        'items': payload_items,
    }


def sanitize_public_partner_items(items, sanitize_public_media_url):
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = sanitize_public_media_url(item.get('url', ''), enforce_remote_public=False)
        if not url:
            continue
        cleaned.append({
            'id': str(item.get('id') or uuid.uuid4().hex),
            'url': url,
            'source': 'upload' if str(item.get('source') or '').lower() == 'upload' else 'url',
        })
    return cleaned


def get_partners_config(partners_config_file, sanitize_public_media_url):
    """从文件或默认值加载合作伙伴配置。"""
    partners_config_path = Path(partners_config_file)
    default_config = {'items': []}

    if partners_config_path.exists():
        try:
            config = json.loads(partners_config_path.read_text(encoding='utf-8'))
            merged = {**default_config, **config}
            items = merged.get('items', [])
            if not isinstance(items, list):
                items = []
            merged['items'] = sanitize_public_partner_items(items, sanitize_public_media_url)
            return merged
        except Exception:
            pass

    atomic_write_text(partners_config_path, json.dumps(default_config, indent=2, ensure_ascii=False))
    return default_config


def save_partners_config(new_config, *, partners_config_file, sanitize_public_media_url):
    """校验并保存合作伙伴配置。"""
    config = get_partners_config(partners_config_file, sanitize_public_media_url)
    items = new_config.get('items', config.get('items', []))
    normalized_items = sanitize_public_partner_items(items if isinstance(items, list) else [], sanitize_public_media_url)
    saved = {'items': normalized_items}
    atomic_write_text(Path(partners_config_file), json.dumps(saved, indent=2, ensure_ascii=False))
    return saved


def get_home_section_visibility_config(home_section_visibility_file):
    """加载首页区块显示控制配置。"""
    visibility_path = Path(home_section_visibility_file)
    default_config = {
        'partners': True,
        'products': True,
        'news': True,
        'solutions': True,
    }
    if visibility_path.exists():
        try:
            config = json.loads(visibility_path.read_text(encoding='utf-8'))
            if isinstance(config, dict):
                return {
                    'partners': bool(config.get('partners', True)),
                    'products': bool(config.get('products', True)),
                    'news': bool(config.get('news', True)),
                    'solutions': bool(config.get('solutions', True)),
                }
        except Exception:
            pass
    atomic_write_text(visibility_path, json.dumps(default_config, indent=2, ensure_ascii=False))
    return default_config


def save_home_section_visibility_config(new_config, *, home_section_visibility_file):
    """保存首页区块显示控制配置。"""
    existing = get_home_section_visibility_config(home_section_visibility_file)
    saved = {
        'partners': bool(new_config.get('partners', existing.get('partners', True))),
        'products': bool(new_config.get('products', existing.get('products', True))),
        'news': bool(new_config.get('news', existing.get('news', True))),
        'solutions': bool(new_config.get('solutions', existing.get('solutions', True))),
    }
    atomic_write_text(Path(home_section_visibility_file), json.dumps(saved, indent=2, ensure_ascii=False))
    return saved



# 路由注册入口。
def register_home_content_routes(
    app,
    *,
    login_required,
    cached_json_response,
    sanitize_public_media_url,
    validate_uploaded_video_extension,
    validate_uploaded_image_extension,
    allowed_partner_extensions,
    hero_config_file,
    hero_uploads_dir,
    hero_derived_dir,
    hero_derived_manifest_file,
    hero_source_image_extensions,
    hero_derived_widths,
    hero_derived_formats,
    h2_home_video_uploads_dir,
    partners_config_file,
    partners_uploads_dir,
    home_section_visibility_file,
    allowed_hero_extensions,
    media_immutable_cache_control,
    pil_support,
    image_module,
    image_ops_module,
    pil_features,
):
    """注册首页 Hero、合作伙伴与区块显示控制相关路由。"""

    def remove_uploaded_hero_image(media_url):
        url = str(media_url or '').strip()
        if not url.startswith('/media/hero/'):
            return
        filename = url.replace('/media/hero/', '', 1)
        remove_hero_variants_for_source(
            filename,
            hero_derived_dir=hero_derived_dir,
            hero_derived_manifest_file=hero_derived_manifest_file,
        )
        file_path = Path(hero_uploads_dir) / filename
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

    @app.route('/api/hero', methods=['GET'])
    def get_hero():
        payload = build_hero_api_payload(
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
            hero_derived_manifest_file=hero_derived_manifest_file,
            pil_support=pil_support,
            image_module=image_module,
            image_ops_module=image_ops_module,
            pil_features=pil_features,
            hero_uploads_dir=hero_uploads_dir,
            hero_derived_dir=hero_derived_dir,
            hero_source_image_extensions=hero_source_image_extensions,
            hero_derived_widths=hero_derived_widths,
            hero_derived_formats=hero_derived_formats,
        )
        if session.get('admin_logged_in'):
            response = jsonify(payload)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return cached_json_response(payload)

    @app.route('/api/hero', methods=['POST'])
    @login_required
    def update_hero():
        data = request.get_json(silent=True) or {}
        config = save_hero_config(
            data,
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        return jsonify({'success': True, 'config': config})

    @app.route('/api/hero/upload', methods=['POST'])
    @login_required
    def upload_hero_media():
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = validate_uploaded_video_extension(file, allowed_extensions={'.mp4'})
        if not ext:
            ext = validate_uploaded_image_extension(file, allowed_extensions={'.webp', '.png', '.jpg', '.jpeg'})
        if not ext or ext not in allowed_hero_extensions:
            return jsonify({'success': False, 'message': '只支持 WebP/PNG/JPG/JPEG/MP4 文件'}), 400

        saved_name = f'{uuid.uuid4().hex}{ext}'
        save_path = Path(hero_uploads_dir) / saved_name
        file.save(str(save_path))

        item_type = 'video' if ext == '.mp4' else 'image'
        if item_type == 'image':
            generate_hero_variants_for_source(
                saved_name,
                pil_support=pil_support,
                image_module=image_module,
                image_ops_module=image_ops_module,
                pil_features=pil_features,
                hero_uploads_dir=hero_uploads_dir,
                hero_derived_dir=hero_derived_dir,
                hero_derived_manifest_file=hero_derived_manifest_file,
                hero_source_image_extensions=hero_source_image_extensions,
                hero_derived_widths=hero_derived_widths,
                hero_derived_formats=hero_derived_formats,
            )

        item = {
            'id': uuid.uuid4().hex,
            'type': item_type,
            'url': f'/media/hero/{saved_name}',
            'source': 'upload',
        }

        config = get_hero_config(hero_config_file, sanitize_public_media_url)
        items = config.get('items', [])
        if not isinstance(items, list):
            items = []
        items.append(item)
        config['items'] = items
        save_hero_config(
            config,
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )

        return jsonify({'success': True, 'item': item})

    @app.route('/api/hero/items/<item_id>/mobile-image', methods=['POST'])
    @login_required
    def upload_hero_mobile_image(item_id):
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = validate_uploaded_image_extension(
            file,
            allowed_extensions={'.webp', '.png', '.jpg', '.jpeg'},
        )
        if not ext or ext not in allowed_hero_extensions:
            return jsonify({'success': False, 'message': '手机端图片只支持 WebP/PNG/JPG/JPEG 文件'}), 400

        config = get_hero_config(hero_config_file, sanitize_public_media_url)
        items = config.get('items', [])
        target_item = next(
            (item for item in items if isinstance(item, dict) and item.get('id') == item_id),
            None,
        )
        if not target_item:
            return jsonify({'success': False, 'message': '轮播项不存在'}), 404
        if str(target_item.get('type') or '').lower() != 'image':
            return jsonify({'success': False, 'message': '只有图片轮播项可以上传手机端图片'}), 400

        saved_name = f'{uuid.uuid4().hex}{ext}'
        save_path = Path(hero_uploads_dir) / saved_name
        file.save(str(save_path))
        generate_hero_variants_for_source(
            saved_name,
            pil_support=pil_support,
            image_module=image_module,
            image_ops_module=image_ops_module,
            pil_features=pil_features,
            hero_uploads_dir=hero_uploads_dir,
            hero_derived_dir=hero_derived_dir,
            hero_derived_manifest_file=hero_derived_manifest_file,
            hero_source_image_extensions=hero_source_image_extensions,
            hero_derived_widths=hero_derived_widths,
            hero_derived_formats=hero_derived_formats,
        )

        old_mobile_url = target_item.get('mobile_url', '')
        target_item['mobile_url'] = f'/media/hero/{saved_name}'
        config['items'] = items
        saved_config = save_hero_config(
            config,
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        if old_mobile_url and old_mobile_url != target_item['mobile_url']:
            remove_uploaded_hero_image(old_mobile_url)
        saved_item = next(
            (item for item in saved_config.get('items', []) if item.get('id') == item_id),
            target_item,
        )
        return jsonify({'success': True, 'item': saved_item})

    @app.route('/api/hero/items/<item_id>/mobile-image', methods=['DELETE'])
    @login_required
    def delete_hero_mobile_image(item_id):
        config = get_hero_config(hero_config_file, sanitize_public_media_url)
        items = config.get('items', [])
        target_item = next(
            (item for item in items if isinstance(item, dict) and item.get('id') == item_id),
            None,
        )
        if not target_item:
            return jsonify({'success': False, 'message': '轮播项不存在'}), 404
        if str(target_item.get('type') or '').lower() != 'image':
            return jsonify({'success': False, 'message': '该轮播项不是图片'}), 400

        old_mobile_url = target_item.pop('mobile_url', '')
        config['items'] = items
        save_hero_config(
            config,
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        if old_mobile_url:
            remove_uploaded_hero_image(old_mobile_url)
        return jsonify({'success': True, 'alreadyDeleted': not bool(old_mobile_url)})

    @app.route('/api/hero/items/<item_id>', methods=['DELETE'])
    @login_required
    def delete_hero_item(item_id):
        config = get_hero_config(hero_config_file, sanitize_public_media_url)
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
            return jsonify({'success': True, 'alreadyDeleted': True, 'message': '项目已不存在'})

        if deleted_item.get('source') == 'upload':
            remove_uploaded_hero_image(deleted_item.get('url', ''))
        remove_uploaded_hero_image(deleted_item.get('mobile_url', ''))

        config['items'] = remaining
        save_hero_config(
            config,
            hero_config_file=hero_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        return jsonify({'success': True})

    @app.route('/media/hero/<path:filename>')
    def serve_hero_media(filename):
        response = send_from_directory(hero_uploads_dir, filename, max_age=31536000)
        response.headers['Cache-Control'] = media_immutable_cache_control
        return response

    @app.route('/media/hero-derived/<path:filename>')
    def serve_hero_derived_media(filename):
        response = send_from_directory(hero_derived_dir, filename, max_age=31536000)
        response.headers['Cache-Control'] = media_immutable_cache_control
        return response

    @app.route('/media/h2-home/<path:filename>')
    def serve_h2_home_media(filename):
        response = send_from_directory(h2_home_video_uploads_dir, filename, max_age=31536000)
        response.headers['Cache-Control'] = media_immutable_cache_control
        return response

    @app.route('/api/partners', methods=['GET'])
    def get_partners():
        return jsonify(get_partners_config(partners_config_file, sanitize_public_media_url))

    @app.route('/api/partners', methods=['POST'])
    @login_required
    def update_partners():
        data = request.get_json(silent=True) or {}
        config = save_partners_config(
            data,
            partners_config_file=partners_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        return jsonify({'success': True, 'config': config})

    @app.route('/api/partners/upload', methods=['POST'])
    @login_required
    def upload_partner_logo():
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有上传文件'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = validate_uploaded_image_extension(file, allowed_extensions=allowed_partner_extensions)
        if not ext:
            return jsonify({'success': False, 'message': '只支持 PNG/JPG/JPEG/WEBP 文件'}), 400

        saved_name = f'{uuid.uuid4().hex}{ext}'
        save_path = Path(partners_uploads_dir) / saved_name
        file.save(str(save_path))

        item = {
            'id': uuid.uuid4().hex,
            'url': f'/media/partners/{saved_name}',
            'source': 'upload',
        }

        config = get_partners_config(partners_config_file, sanitize_public_media_url)
        items = config.get('items', [])
        if not isinstance(items, list):
            items = []
        items.append(item)
        config['items'] = items
        save_partners_config(
            config,
            partners_config_file=partners_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )

        return jsonify({'success': True, 'item': item})

    @app.route('/api/partners/items/<item_id>', methods=['DELETE'])
    @login_required
    def delete_partner_item(item_id):
        config = get_partners_config(partners_config_file, sanitize_public_media_url)
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
                filename = url.replace('/media/partners/', '', 1)
                file_path = Path(partners_uploads_dir) / filename
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception:
                        pass

        config['items'] = remaining
        save_partners_config(
            config,
            partners_config_file=partners_config_file,
            sanitize_public_media_url=sanitize_public_media_url,
        )
        return jsonify({'success': True})

    @app.route('/media/partners/<path:filename>')
    def serve_partners_media(filename):
        return send_from_directory(partners_uploads_dir, filename)

    @app.route('/api/home/section-visibility', methods=['GET'])
    def get_home_section_visibility():
        return jsonify(get_home_section_visibility_config(home_section_visibility_file))

    @app.route('/api/home/section-visibility', methods=['POST'])
    @login_required
    def update_home_section_visibility():
        data = request.get_json(silent=True) or {}
        config = save_home_section_visibility_config(
            data,
            home_section_visibility_file=home_section_visibility_file,
        )
        return jsonify({'success': True, 'config': config})
