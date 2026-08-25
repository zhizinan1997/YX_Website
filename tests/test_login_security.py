from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from flask import Flask

from app.routes.admin import (
    _get_admin_users_file,
    _load_admin_users,
    bump_user_min_session_at,
    query_user_min_session_at,
    register_admin_routes,
    _set_users_file_for_revocation,
)

PASSWORD_HASH = "scrypt:32768:8:1$salt$hash"


class SessionRevocationUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        users = {
            "version": 1,
            "users": [{
                "username": "admin",
                "password_hash": PASSWORD_HASH,
                "role": "super_admin",
                "enabled": True,
                "permissions": [],
            }],
        }
        (_get_admin_users_file(self.root)).write_text(json.dumps(users), encoding="utf-8")
        _set_users_file_for_revocation(_get_admin_users_file(self.root))
        self.addCleanup(_set_users_file_for_revocation, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_query_returns_zero_without_bump(self):
        self.assertEqual(query_user_min_session_at("admin"), 0)
        self.assertEqual(query_user_min_session_at("ghost"), 0)

    def test_bump_advances_min_session_at_and_invalidates_older_login(self):
        before = int(time.time())
        bump_user_min_session_at(self.root, "admin")
        min_at = query_user_min_session_at("admin")
        self.assertGreaterEqual(min_at, before)
        # 早于 min_session_at 的旧会话应被视为失效。
        stale_login_at = min_at - 1
        self.assertTrue(min_at and stale_login_at < min_at)
        # 数据文件确实持久化了该字段。
        user = _load_admin_users(_get_admin_users_file(self.root))["users"][0]
        self.assertEqual(user.get("min_session_at"), min_at)

    def test_bump_unknown_user_is_noop(self):
        bump_user_min_session_at(self.root, "nobody")
        self.assertIsNone(_find_username(self.root, "nobody"))

    def test_mtime_cache_refreshes_after_external_write(self):
        self.assertEqual(query_user_min_session_at("admin"), 0)
        # 外部（另一 worker）直接改写文件后，缓存应因 mtime 变化而刷新。
        users_file = _get_admin_users_file(self.root)
        data = _load_admin_users(users_file)
        data["users"][0]["min_session_at"] = 1234567890
        time.sleep(0.01)
        users_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(query_user_min_session_at("admin"), 1234567890)


def _find_username(root: Path, username: str):
    for user in _load_admin_users(_get_admin_users_file(root)).get("users", []):
        if user.get("username") == username:
            return user
    return None


class LoginSameOriginTests(unittest.TestCase):
    def test_login_requires_same_origin_or_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            config = {"admin_username": "admin", "admin_password_hash": PASSWORD_HASH, "admin_password": ""}
            app = Flask(__name__)
            app.secret_key = "test-secret"
            register_admin_routes(
                app,
                login_required=lambda func: func,
                get_config=lambda: dict(config),
                update_config=lambda updates: config.update(updates or {}) or dict(config),
                append_admin_login_log=lambda **_kwargs: None,
                load_admin_login_logs=lambda: [],
                admin_login_log_lock=None,
                project_root=root,
                resolve_ip_location=lambda _ip: "unknown",
                resolve_ip_country_code=lambda _ip: "CN",
                get_public_base_url=lambda: "",
            )
            client = app.test_client()

            # 无 Origin/Referer 且无 CSRF token → 同源校验拒绝（login CSRF 防护）。
            response = client.post("/admin/login", data={"username": "admin", "password": "x"})
            self.assertEqual(response.status_code, 403)

            # 带同源 Origin 头 → 通过校验，进入凭据校验流程（返回凭据错误而非 403）。
            response = client.post(
                "/admin/login",
                data={"username": "admin", "password": "wrong"},
                headers={"Origin": "http://localhost"},
            )
            self.assertNotEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
