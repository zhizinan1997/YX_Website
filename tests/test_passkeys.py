from __future__ import annotations

import os
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from app.passkeys import PasskeyStore, load_passkey_config
from app.routes.admin import register_admin_routes, resolve_permission_for_path
from werkzeug.security import generate_password_hash


class PasskeyConfigTests(unittest.TestCase):
    def test_own_passkey_routes_are_available_to_authenticated_subaccounts(self):
        self.assertIsNone(resolve_permission_for_path('/api/admin/account/passkeys', 'GET'))
        self.assertIsNone(resolve_permission_for_path('/api/admin/account/passkeys/register/options', 'POST'))

    def test_https_origin_and_parent_rp_id_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "PASSKEY_ENABLED": "true",
            "PASSKEY_ORIGIN": "https://admin.example.com",
            "PASSKEY_RP_ID": "example.com",
            "PASSKEY_DB_PATH": str(Path(tmp) / "passkeys.sqlite3"),
        }, clear=False):
            config = load_passkey_config(Path(tmp))
        self.assertTrue(config.enabled)
        self.assertEqual(config.rp_id, "example.com")

    def test_saved_admin_setting_can_enable_without_passkey_environment_variables(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://admin.example.com",
        }, clear=True):
            config = load_passkey_config(
                Path(tmp),
                "https://admin.example.com",
                {"passkey_enabled": True, "passkey_max_credentials_per_user": 12},
            )
        self.assertTrue(config.enabled)
        self.assertEqual(config.origin, "https://admin.example.com")
        self.assertEqual(config.rp_id, "admin.example.com")
        self.assertEqual(config.max_credentials_per_user, 12)

    def test_environment_toggle_overrides_saved_admin_setting(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "PASSKEY_ENABLED": "false",
        }, clear=True):
            config = load_passkey_config(
                Path(tmp), "https://admin.example.com", {"passkey_enabled": True}
            )
        self.assertFalse(config.enabled)

    def test_project_domain_is_used_as_the_default_origin(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            config = load_passkey_config(Path(tmp), "", {"passkey_enabled": True})
        self.assertTrue(config.enabled)
        self.assertEqual(config.origin, "https://hnmetachip.cn")
        self.assertEqual(config.rp_id, "hnmetachip.cn")

    def test_insecure_non_local_origin_disables_feature(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "PASSKEY_ENABLED": "true",
            "PASSKEY_ORIGIN": "http://admin.example.com",
            "PASSKEY_RP_ID": "admin.example.com",
        }, clear=False):
            config = load_passkey_config(Path(tmp))
        self.assertFalse(config.enabled)
        self.assertIn("HTTPS", config.error)


class PasskeyStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {
            "PASSKEY_ENABLED": "true",
            "PASSKEY_ORIGIN": "http://localhost",
            "PASSKEY_RP_ID": "localhost",
            "PASSKEY_DB_PATH": str(Path(self.tmp.name) / "passkeys.sqlite3"),
            "PASSKEY_MAX_CREDENTIALS_PER_USER": "2",
        }
        self.env = patch.dict(os.environ, env, clear=False)
        self.env.start()
        self.config = load_passkey_config(Path(self.tmp.name))
        self.store = PasskeyStore(self.config)
        self.store.initialize()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_initialize_is_idempotent_and_user_handle_is_stable(self):
        self.store.initialize()
        first = self.store.get_or_create_user_handle("alice")
        second = self.store.get_or_create_user_handle("alice")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)

    def test_challenge_is_session_bound_and_single_use(self):
        request_id = self.store.create_challenge("login", b"challenge", "browser-a")
        self.assertEqual(self.store.load_challenge(request_id, "login", "browser-a"), b"challenge")
        with self.assertRaises(ValueError):
            self.store.load_challenge(request_id, "login", "browser-b")
        self.store.consume_challenge(request_id)
        with self.assertRaises(ValueError):
            self.store.load_challenge(request_id, "login", "browser-a")

    def test_credential_lifecycle_and_limit(self):
        handle = self.store.get_or_create_user_handle("alice")
        self.store.add_credential(
            credential_id=b"credential-one", username="alice", user_handle=handle,
            public_key=b"public-key", sign_count=1, transports=["internal"],
            backup_eligible=False, backup_state=False, device_name="MacBook",
        )
        items = self.store.list_credentials("alice")
        self.assertEqual(items[0]["device_name"], "MacBook")
        credential_id = items[0]["credential_id"]
        self.assertTrue(self.store.rename_credential("alice", credential_id, "Work Mac"))
        self.store.update_usage(credential_id, 2, "127.0.0.1")
        with self.assertRaises(ValueError):
            self.store.update_usage(credential_id, 2, "127.0.0.1")
        self.store.rename_user("alice", "alice-renamed")
        self.assertEqual(self.store.count_credentials("alice"), 0)
        self.assertEqual(self.store.count_credentials("alice-renamed"), 1)
        self.assertEqual(self.store.get_or_create_user_handle("alice-renamed"), handle)
        self.assertTrue(self.store.revoke_credential("alice-renamed", credential_id, "alice-renamed"))
        self.assertEqual(self.store.count_credentials("alice-renamed"), 0)

    def test_rate_limit_is_enforced_per_minute(self):
        for _ in range(3):
            self.assertTrue(self.store.check_rate_limit("127.0.0.1", limit=3))
        self.assertFalse(self.store.check_rate_limit("127.0.0.1", limit=3))


class PasskeyAdminSettingsTests(unittest.TestCase):
    def test_super_admin_can_enable_passkeys_without_passkey_environment_variables(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            (root / "data").mkdir()
            password_hash = generate_password_hash("test-password")
            (root / "data" / "admin_users.json").write_text(json.dumps({
                "version": 1,
                "users": [{
                    "username": "admin", "password_hash": password_hash,
                    "role": "super_admin", "enabled": True, "permissions": [],
                }],
            }), encoding="utf-8")
            config = {
                "admin_username": "admin", "admin_password_hash": password_hash,
                "admin_password": "", "passkey_enabled": False,
                "passkey_max_credentials_per_user": 10,
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
                session["admin_username"] = "admin"
                session["admin_is_super_admin"] = True
                session["admin_is_hidden"] = False

            response = client.post(
                "/api/admin/security/passkeys",
                json={"enabled": True, "max_credentials_per_user": 12},
                base_url="https://admin.example.com",
                headers={"Origin": "https://admin.example.com"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertTrue(config["passkey_enabled"])
            self.assertEqual(config["passkey_max_credentials_per_user"], 12)
            public = client.get("/api/admin/passkey/public-config", base_url="https://admin.example.com").get_json()
            self.assertTrue(public["enabled"])
            self.assertEqual(public["rp_id"], "admin.example.com")


if __name__ == "__main__":
    unittest.main()
