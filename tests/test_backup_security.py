from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from flask import Flask, jsonify, session

from app.app_config import (
    BACKUP_EXCLUDED_DIR_NAMES,
    BACKUP_EXCLUDED_FILE_NAMES,
    BACKUP_EXCLUDED_SUFFIXES,
    BACKUP_META_FILES,
    BACKUP_SENSITIVE_DATA_DIRS,
    BACKUP_SENSITIVE_REL_PATHS,
    RESTORE_BLOCKED_SUFFIXES,
)
from app.routes.backup import register_backup_routes


def _login_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "login required"}), 401
        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    return wrapper


def _build_app(root: Path, *, super_admin: bool):
    app = Flask(__name__)
    app.secret_key = "test-secret"

    def require_super_admin_api():
        if not session.get("admin_is_super_admin"):
            return jsonify({"success": False, "message": "仅超级管理员"}), 403
        return None

    register_backup_routes(
        app,
        login_required=_login_required,
        project_root=root,
        backup_meta_files=BACKUP_META_FILES,
        backup_excluded_dir_names=BACKUP_EXCLUDED_DIR_NAMES,
        backup_excluded_file_names=BACKUP_EXCLUDED_FILE_NAMES,
        backup_excluded_suffixes=BACKUP_EXCLUDED_SUFFIXES,
        require_super_admin_api=require_super_admin_api,
        backup_sensitive_rel_paths=BACKUP_SENSITIVE_REL_PATHS,
        backup_sensitive_data_dirs=BACKUP_SENSITIVE_DATA_DIRS,
        restore_blocked_suffixes=RESTORE_BLOCKED_SUFFIXES,
    )
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_is_super_admin"] = super_admin
    return client


class BackupDownloadSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "data" / "config.json").write_text("{}", encoding="utf-8")
        (self.root / "data" / ".flask_secret_key").write_text("secret", encoding="utf-8")
        (self.root / "data" / "admin_users.json").write_text("{}", encoding="utf-8")
        (self.root / "data" / "messages").mkdir()
        (self.root / "data" / "messages" / "m1.json").write_text("{}", encoding="utf-8")
        (self.root / "data" / "resumes").mkdir()
        (self.root / "data" / "resumes" / "r1").write_text("resume", encoding="utf-8")
        (self.root / "index.html").write_text("<html></html>", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_download_excludes_sensitive_paths(self):
        client = _build_app(self.root, super_admin=True)
        response = client.get("/api/backup/download")
        self.assertEqual(response.status_code, 200)
        zf = zipfile.ZipFile(io.BytesIO(response.data))
        names = set(zf.namelist())
        self.assertIn("index.html", names)
        self.assertNotIn("data/config.json", names)
        self.assertNotIn("data/.flask_secret_key", names)
        self.assertNotIn("data/admin_users.json", names)
        self.assertFalse(any(n.startswith("data/messages/") for n in names), names)
        self.assertFalse(any(n.startswith("data/resumes/") for n in names), names)


class BackupRestoreSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _restore_zip(self, client, entries):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for name, payload in entries.items():
                zf.writestr(name, payload)
        buffer.seek(0)
        return client.post(
            "/api/backup/restore",
            data={"file": (buffer, "backup.zip")},
            content_type="multipart/form-data",
        )

    def test_restore_rejects_sub_admin(self):
        client = _build_app(self.root, super_admin=False)
        response = self._restore_zip(client, {"index.html": "<html></html>"})
        self.assertEqual(response.status_code, 403)

    def test_restore_blocks_source_and_sensitive_paths_even_for_super_admin(self):
        client = _build_app(self.root, super_admin=True)
        response = self._restore_zip(client, {
            "index.html": "<html>restored</html>",
            "app/evil.py": "import os",
            "evil.sh": "rm -rf /",
            ".env": "SECRET=x",
            "data/config.json": "{}",
            "data/admin_users.json": "{}",
            "data/messages/m2.json": "{}",
        })
        self.assertEqual(response.status_code, 200)
        # 仅 index.html 被恢复。
        self.assertEqual(response.get_json().get("restored_files"), 1)
        self.assertTrue((self.root / "index.html").exists())
        self.assertFalse((self.root / "app" / "evil.py").exists())
        self.assertFalse((self.root / "evil.sh").exists())
        self.assertFalse((self.root / ".env").exists())
        self.assertFalse((self.root / "data" / "messages" / "m2.json").exists())


if __name__ == "__main__":
    unittest.main()
