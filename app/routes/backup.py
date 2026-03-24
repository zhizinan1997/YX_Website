"""Backup/restore route module."""

import json
import os
import posixpath
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import after_this_request, jsonify, request, send_file


def register_backup_routes(
    app,
    *,
    login_required,
    project_root,
    backup_meta_files,
    backup_excluded_dir_names,
    backup_excluded_file_names,
    backup_excluded_suffixes,
):
    """Register full-site backup/restore routes."""
    root = Path(project_root)

    def normalize_backup_rel_path(raw_path: str) -> str:
        """Normalize backup relative path and guard against traversal."""
        if not raw_path:
            return ''
        normalized = posixpath.normpath(str(raw_path).replace('\\', '/')).lstrip('./')
        if not normalized or normalized.startswith('../') or normalized.startswith('/'):
            return ''
        return normalized

    def should_include_site_backup_path(rel_path: str) -> bool:
        """Decide whether a relative path should be included in full-site backup."""
        normalized = normalize_backup_rel_path(rel_path)
        if not normalized:
            return False
        if normalized in backup_meta_files:
            return False

        parts = [p for p in normalized.split('/') if p and p != '.']
        if not parts:
            return False

        # Exclude cache/dev directories from any depth.
        for part in parts[:-1]:
            if part in backup_excluded_dir_names:
                return False

        filename = parts[-1]
        if filename in backup_excluded_file_names:
            return False

        filename_lower = filename.lower()
        if any(filename_lower.endswith(suffix) for suffix in backup_excluded_suffixes):
            return False

        return True

    def iter_site_backup_files():
        """Yield (abs_file_path, rel_posix_path) for backup-eligible files."""
        for current_root, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in backup_excluded_dir_names]

            current_dir = Path(current_root)
            for filename in filenames:
                abs_path = current_dir / filename
                if not abs_path.is_file() or abs_path.is_symlink():
                    continue
                rel_posix = abs_path.relative_to(root).as_posix()
                if should_include_site_backup_path(rel_posix):
                    yield abs_path, rel_posix

    @app.route('/api/backup/download', methods=['GET'])
    @login_required
    def download_backup():
        """Download full-site backup (excluding cache/dev directories)."""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'yx_backup_{ts}.zip'

        fd, temp_zip = tempfile.mkstemp(prefix='yx_backup_', suffix='.zip')
        os.close(fd)

        try:
            included_files = list(iter_site_backup_files())

            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                manifest = {
                    'created_at': datetime.now().isoformat(),
                    'version': 3,
                    'scope': 'full_site',
                    'includes': {
                        'mode': 'walk_root_with_excludes',
                        'root': '.',
                        'excluded_dir_names': sorted(backup_excluded_dir_names),
                        'excluded_file_names': sorted(backup_excluded_file_names),
                        'excluded_suffixes': list(backup_excluded_suffixes)
                    },
                    'stats': {
                        'file_count': len(included_files)
                    }
                }
                zf.writestr('backup_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

                for abs_path, rel_posix in included_files:
                    zf.write(abs_path, rel_posix)

            @after_this_request
            def cleanup_temp_file(resp):
                try:
                    if os.path.exists(temp_zip):
                        os.remove(temp_zip)
                except Exception:
                    pass
                return resp

            return send_file(
                temp_zip,
                as_attachment=True,
                download_name=backup_name,
                mimetype='application/zip'
            )
        except Exception:
            try:
                if os.path.exists(temp_zip):
                    os.remove(temp_zip)
            except Exception:
                pass
            return jsonify({'success': False, 'message': '备份生成失败'}), 500

    @app.route('/api/backup/restore', methods=['POST'])
    @login_required
    def restore_backup():
        """Restore backup zip after docker redeploy."""
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '请上传备份文件'}), 400
        if not str(file.filename).lower().endswith('.zip'):
            return jsonify({'success': False, 'message': '仅支持 ZIP 备份文件'}), 400

        with tempfile.TemporaryDirectory(prefix='yx_restore_') as td:
            temp_dir = Path(td)
            temp_zip = temp_dir / 'upload.zip'
            file.save(temp_zip)

            extracted_rel_paths = set()

            try:
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        norm_name = normalize_backup_rel_path(info.filename)
                        if not norm_name:
                            continue
                        if norm_name in backup_meta_files:
                            continue
                        if not should_include_site_backup_path(norm_name):
                            continue

                        out_path = temp_dir / norm_name
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info, 'r') as src, open(out_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        extracted_rel_paths.add(norm_name)
            except zipfile.BadZipFile:
                return jsonify({'success': False, 'message': '备份文件损坏或格式不正确'}), 400

            if not extracted_rel_paths:
                return jsonify({'success': False, 'message': '备份包中没有可恢复的有效站点文件'}), 400

            restored_top_entries = set()
            restored_files = 0
            for rel_path in sorted(extracted_rel_paths):
                src_file = temp_dir / rel_path
                if not src_file.exists() or not src_file.is_file():
                    continue
                dst_file = root / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                restored_files += 1
                restored_top_entries.add(rel_path.split('/', 1)[0])

        return jsonify({
            'success': True,
            'message': '备份恢复成功，建议重启服务后刷新后台。',
            'restored_files': restored_files,
            'restored_entries': len(restored_top_entries)
        })

