from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask
from werkzeug.security import generate_password_hash

from app.routes.admin import register_admin_routes


def _build_client(root: Path, *, is_super_admin: bool):
    password_hash = generate_password_hash("test-password")
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "admin_users.json").write_text(json.dumps({
        "version": 1,
        "users": [
            {
                "username": "admin", "password_hash": password_hash,
                "role": "super_admin", "enabled": True, "permissions": [],
            },
            {
                "username": "alice", "password_hash": password_hash,
                "role": "sub_admin", "enabled": True, "permissions": ["messages"],
            },
        ],
    }), encoding="utf-8")
    config = {
        "admin_username": "admin", "admin_password_hash": password_hash,
        "admin_password": "", "passkey_enabled": False,
    }
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
        get_public_base_url=lambda: "https://admin.example.com",
    )
    client = app.test_client()
    with client.session_transaction(base_url="https://admin.example.com") as session:
        session["admin_logged_in"] = True
        session["admin_username"] = "admin" if is_super_admin else "alice"
        session["admin_is_super_admin"] = is_super_admin
        session["admin_is_hidden"] = False
    return client


def _read_users(root: Path):
    raw = json.loads((root / "data" / "admin_users.json").read_text(encoding="utf-8"))
    return {user["username"]: user for user in raw.get("users", [])}


class SubAccountEmailTests(unittest.TestCase):
    def _post_create(self, client, payload):
        return client.post(
            "/api/admin/subaccounts",
            json=payload,
            base_url="https://admin.example.com",
            headers={"Origin": "https://admin.example.com"},
        )

    def test_super_admin_can_create_subaccount_with_verified_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _build_client(root, is_super_admin=True)
            response = self._post_create(client, {
                "username": "bob",
                "password": "bob-password",
                "email": "Bob@Example.com",
                "enabled": True,
                "permissions": ["messages"],
            })
            self.assertEqual(response.status_code, 200, response.get_json())
            bob = _read_users(root)["bob"]
            self.assertEqual(bob["email"], "bob@example.com")
            self.assertTrue(bob["email_verified"])
            self.assertTrue(bob["email_bound_at"])

    def test_create_rejects_email_already_bound_to_another_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _build_client(root, is_super_admin=True)
            first = self._post_create(client, {
                "username": "bob", "password": "bob-password",
                "email": "shared@example.com", "permissions": ["messages"],
            })
            self.assertEqual(first.status_code, 200, first.get_json())
            second = self._post_create(client, {
                "username": "carol", "password": "carol-password",
                "email": "shared@example.com", "permissions": ["messages"],
            })
            self.assertEqual(second.status_code, 400, second.get_json())
            self.assertIn("已被账号", second.get_json()["message"])

    def test_super_admin_can_force_change_subaccount_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _build_client(root, is_super_admin=True)
            response = client.put(
                "/api/admin/subaccounts/alice/email",
                json={"email": "new-alice@example.com"},
                base_url="https://admin.example.com",
                headers={"Origin": "https://admin.example.com"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            alice = _read_users(root)["alice"]
            self.assertEqual(alice["email"], "new-alice@example.com")
            self.assertTrue(alice["email_verified"])

    def test_non_super_admin_cannot_change_subaccount_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _build_client(root, is_super_admin=False)
            response = client.put(
                "/api/admin/subaccounts/alice/email",
                json={"email": "new-alice@example.com"},
                base_url="https://admin.example.com",
                headers={"Origin": "https://admin.example.com"},
            )
            self.assertEqual(response.status_code, 403, response.get_json())


class SubAccountPanelFrontendTests(unittest.TestCase):
    def test_subaccount_module_uses_progressive_panels(self):
        html = (Path(__file__).resolve().parents[1] / "admin" / "index.html").read_text(encoding="utf-8")
        # 一级列表 + 二级新增/编辑面板
        self.assertIn('id="subPanelList"', html)
        self.assertIn('id="subPanelCreate" hidden', html)
        self.assertIn('id="subPanelEdit" hidden', html)
        # 面板间导航入口
        self.assertIn('id="subCreateOpenBtn"', html)
        self.assertIn('id="subEditBackBtn"', html)
        # 编辑面板保留全部原有功能控件
        for element_id in (
            "subAccountEditForm", "subEditSelect", "subForceEmailBtn",
            "subEditEmailCurrent", "subEditPermissionsGrid", "subDeleteBtn",
            "subEditPasskeyBtn", "subEditStatusBadge",
        ):
            self.assertIn(f'id="{element_id}"', html)


if __name__ == "__main__":
    unittest.main()
