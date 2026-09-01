"""
备份与恢复路由模块。

本模块提供网站数据的完整备份和恢复功能，确保数据安全。
采用ZIP压缩格式，包含完整的站点文件和备份元数据。

主要功能：
1. 整站备份下载（/api/backup/download）
   - 遍历项目所有文件
   - 排除缓存和开发文件
   - 生成时间戳命名的ZIP文件
   - 包含备份清单（backup_manifest.json）
   - 自动清理临时文件

2. 备份恢复（/api/backup/restore）
   - 验证上传的ZIP文件格式
   - 提取文件到临时目录
   - 校验文件路径安全性
   - 恢复到项目根目录
   - 返回恢复统计信息

安全特性：
- 路径穿越防护（防止../等路径操作）
- 仅支持ZIP格式
- 元文件白名单保护
- 排除危险文件类型（.pyc、.tmp等）
- 排除敏感目录（.git、node_modules等）

备份范围：
包含的文件类型：
- HTML页面（.html）
- 静态资源（CSS、JS、图片）
- 配置文件（JSON、YAML）
- 数据文件

排除的文件类型：
- Python字节码（.pyc、.pyo）
- 临时文件（.swp、.tmp）
- 缓存文件（__pycache__）
- 开发目录（.git、node_modules、venv）

备份清单内容（backup_manifest.json）：
- created_at: 备份创建时间
- version: 备份格式版本
- scope: 备份范围（full_site）
- includes: 备份包含规则详情
- stats: 文件统计信息

使用场景：
- 定期数据备份
- 系统迁移前备份
- 重大更新前备份
- 灾难恢复

作者：元芯传感技术团队
"""

import json
import os
import posixpath
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import after_this_request, jsonify, request, send_file

BEIJING_TZ = timezone(timedelta(hours=8))
MAX_RESTORE_ZIP_BYTES = 64 * 1024 * 1024
MAX_RESTORE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_RESTORE_FILES = 5000

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)



# 路由注册入口。
def register_backup_routes(
    app,
    *,
    login_required,
    project_root,
    backup_meta_files,
    backup_excluded_dir_names,
    backup_excluded_file_names,
    backup_excluded_suffixes,
    require_super_admin_api=None,
    backup_sensitive_rel_paths=(),
    backup_sensitive_data_dirs=(),
    restore_blocked_suffixes=(),
):
    """注册整站备份与恢复相关路由。"""
    root = Path(project_root)
    sensitive_rel_paths = {str(p) for p in (backup_sensitive_rel_paths or ())}
    sensitive_data_dirs = {str(d) for d in (backup_sensitive_data_dirs or ())}
    blocked_restore_suffixes = tuple(str(s).lower() for s in (restore_blocked_suffixes or ()))

    def normalize_backup_rel_path(raw_path: str) -> str:
        """规范化备份相对路径并防止路径穿越。

        仅剥离开头的 `../` 与 `/`；不能使用 lstrip('./')——那会把
        `.env`、`.htaccess` 等点开头的文件名整体破坏成 `env`。
        """
        if not raw_path:
            return ''
        normalized = posixpath.normpath(str(raw_path).replace('\\', '/'))
        while normalized.startswith('../'):
            normalized = normalized[3:]
        normalized = normalized.lstrip('/')
        if not normalized or normalized in {'.', '..'}:
            return ''
        return normalized

    def should_include_site_backup_path(rel_path: str) -> bool:
        """判断相对路径是否应纳入整站备份。"""
        normalized = normalize_backup_rel_path(rel_path)
        if not normalized:
            return False
        if normalized in backup_meta_files:
            return False

        parts = [p for p in normalized.split('/') if p and p != '.']
        if not parts:
            return False

        # 排除任意层级下的缓存目录和开发目录。
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

    def is_sensitive_backup_rel_path(norm_name: str) -> bool:
        """判断相对路径是否属于不应离开服务器的敏感数据。"""
        if norm_name in sensitive_rel_paths:
            return True
        # data/ 下的留言、简历目录整体排除。
        for dir_name in sensitive_data_dirs:
            prefix = f'data/{dir_name}'
            if norm_name == prefix or norm_name.startswith(f'{prefix}/'):
                return True
        return False

    def is_blocked_restore_rel_path(norm_name: str) -> str:
        """返回恢复拦截原因；空字符串表示允许恢复。"""
        if is_sensitive_backup_rel_path(norm_name):
            return '敏感数据不允许通过备份包覆盖'
        filename_lower = norm_name.rsplit('/', 1)[-1].lower()
        if any(filename_lower.endswith(suffix) for suffix in blocked_restore_suffixes):
            return '源码与脚本文件不允许通过备份包覆盖'
        return ''

    def iter_site_backup_files():
        """遍历可备份文件，并产出（绝对路径，相对 POSIX 路径）。"""
        for current_root, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in backup_excluded_dir_names]

            current_dir = Path(current_root)
            for filename in filenames:
                abs_path = current_dir / filename
                if not abs_path.is_file() or abs_path.is_symlink():
                    continue
                rel_posix = abs_path.relative_to(root).as_posix()
                if should_include_site_backup_path(rel_posix) and not is_sensitive_backup_rel_path(rel_posix):
                    yield abs_path, rel_posix

    @app.route('/api/backup/download', methods=['GET'])
    @login_required
    def download_backup():
        """下载整站备份，排除缓存目录与开发目录。"""
        ts = now_beijing().strftime('%Y%m%d_%H%M%S')
        backup_name = f'yx_backup_{ts}.zip'

        fd, temp_zip = tempfile.mkstemp(prefix='yx_backup_', suffix='.zip')
        os.close(fd)

        try:
            included_files = list(iter_site_backup_files())

            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                manifest = {
                    'created_at': now_beijing().isoformat(),
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
        """在 Docker 重部署后恢复备份 ZIP（仅超级管理员）。"""
        if require_super_admin_api is not None:
            denied = require_super_admin_api()
            if denied is not None:
                return denied

        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '请上传备份文件'}), 400
        if not str(file.filename).lower().endswith('.zip'):
            return jsonify({'success': False, 'message': '仅支持 ZIP 备份文件'}), 400

        with tempfile.TemporaryDirectory(prefix='yx_restore_') as td:
            temp_dir = Path(td)
            temp_zip = temp_dir / 'upload.zip'
            file.save(temp_zip)
            if temp_zip.stat().st_size > MAX_RESTORE_ZIP_BYTES:
                return jsonify({'success': False, 'message': '备份文件过大，无法恢复'}), 413

            extracted_rel_paths = set()

            try:
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    infos = [info for info in zf.infolist() if not info.is_dir()]
                    if len(infos) > MAX_RESTORE_FILES:
                        return jsonify({'success': False, 'message': '备份文件数量超过限制'}), 413
                    total_uncompressed = sum(max(0, int(info.file_size or 0)) for info in infos)
                    if total_uncompressed > MAX_RESTORE_UNCOMPRESSED_BYTES:
                        return jsonify({'success': False, 'message': '备份解压后体积超过限制'}), 413

                    # 恶意 ZIP 可在中央目录声明小体积、实际解压出任意大文件（ZIP 炸弹），
                    # 因此必须按分块复制的真实写入字节数复核上限。
                    actual_uncompressed = 0
                    for info in infos:
                        norm_name = normalize_backup_rel_path(info.filename)
                        if not norm_name:
                            continue
                        if norm_name in backup_meta_files:
                            continue
                        if not should_include_site_backup_path(norm_name):
                            continue
                        if is_blocked_restore_rel_path(norm_name):
                            continue

                        out_path = temp_dir / norm_name
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        # 手动分块复制（1MB），累计实际写入字节并即时核对上限。
                        with zf.open(info, 'r') as src, open(out_path, 'wb') as dst:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                dst.write(chunk)
                                actual_uncompressed += len(chunk)
                                if actual_uncompressed > MAX_RESTORE_UNCOMPRESSED_BYTES:
                                    return jsonify({'success': False, 'message': '备份解压后体积超过限制'}), 413
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
