from __future__ import annotations

import json
import importlib
import tempfile
import unittest
from pathlib import Path

from check_app import config, mailer, main_site, monitor, storage


class MainSiteConfigTests(unittest.TestCase):
    def test_loads_smtp_and_verified_admins(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            (data_dir / "config.json").write_text(
                json.dumps(
                    {
                        "smtp_host": "smtp.example.com",
                        "smtp_port": 465,
                        "smtp_username": "notice@example.com",
                        "smtp_password_or_app_code": "secret",
                        "smtp_from_email": "notice@example.com",
                        "smtp_use_ssl": True,
                        "turnstile_enabled": True,
                        "turnstile_site_key": "site-key",
                        "turnstile_secret_key": "secret-key",
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "admin_users.json").write_text(
                json.dumps(
                    {
                        "users": [
                            {
                                "username": "admin",
                                "role": "super_admin",
                                "enabled": True,
                                "email": "admin@example.com",
                                "email_verified": True,
                            },
                            {
                                "username": "draft",
                                "role": "sub_admin",
                                "enabled": True,
                                "email": "draft@example.com",
                                "email_verified": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            smtp = main_site.get_smtp_settings(data_dir)
            self.assertTrue(smtp.configured)
            self.assertEqual(smtp.host, "smtp.example.com")
            self.assertEqual(main_site.get_verified_admin_emails(data_dir), ["admin@example.com"])
            turnstile = main_site.get_turnstile_settings(data_dir)
            self.assertTrue(turnstile.enabled)
            self.assertEqual(turnstile.site_key, "site-key")
            self.assertEqual(turnstile.secret_key, "secret-key")

    def test_turnstile_requires_complete_keys(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            (data_dir / "config.json").write_text(
                json.dumps({"turnstile_enabled": True, "turnstile_site_key": "site-key", "turnstile_secret_key": ""}),
                encoding="utf-8",
            )
            self.assertFalse(main_site.get_turnstile_settings(data_dir).enabled)


class StorageTests(unittest.TestCase):
    def test_seeds_targets_and_normalizes_relative_url(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            storage.init_db(data_dir)
            targets = storage.list_targets(data_dir)
            self.assertGreaterEqual(len(targets), 7)
            self.assertEqual(storage.normalize_url("/pages/news/news.html"), "https://www.hnmetachip.cn/pages/news/news.html")

    def test_auth_code_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            storage.init_db(data_dir)
            storage.store_auth_code("Admin@Example.com", "123456", "salt", data_dir)
            self.assertTrue(storage.verify_auth_code("admin@example.com", "123456", data_dir))
            self.assertFalse(storage.verify_auth_code("admin@example.com", "123456", data_dir))

    def test_records_run_and_closes_incident_on_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            storage.init_db(data_dir)
            target = storage.list_targets(data_dir)[0]
            failed = {
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:00:01+00:00",
                "status": "down",
                "http_status": 500,
                "latency_ms": 1000,
                "resource_total": 1,
                "resource_failed": 1,
                "console_error_count": 0,
                "render_ok": False,
                "error_summary": "HTTP 500",
                "resources": [],
            }
            storage.record_run(target, failed, attempt=1, trigger="test", data_dir=data_dir)
            self.assertIsNotNone(storage.get_open_incident(target["id"], data_dir))

            ok = dict(failed)
            ok.update({"status": "ok", "http_status": 200, "resource_failed": 0, "render_ok": True, "error_summary": ""})
            storage.record_run(target, ok, attempt=2, trigger="test", data_dir=data_dir)
            self.assertIsNone(storage.get_open_incident(target["id"], data_dir))


class MonitorTests(unittest.TestCase):
    def test_same_origin_and_classification(self):
        self.assertTrue(monitor.same_origin("https://www.hnmetachip.cn/a.css", "https://www.hnmetachip.cn/"))
        self.assertFalse(monitor.same_origin("https://cdn.example.com/a.css", "https://www.hnmetachip.cn/"))
        self.assertTrue(
            monitor.is_critical_same_origin_failure(
                {"same_origin": True, "kind": "script", "status": "failed"}
            )
        )
        self.assertFalse(
            monitor.is_critical_same_origin_failure(
                {"same_origin": True, "kind": "image", "status": "failed"}
            )
        )
        self.assertEqual(
            monitor.classify_result(
                document_failed=False,
                render_ok=True,
                same_origin_resource_failed=0,
                console_error_count=0,
            ),
            "ok",
        )
        self.assertEqual(
            monitor.classify_result(
                document_failed=False,
                render_ok=True,
                same_origin_resource_failed=1,
                console_error_count=0,
            ),
            "degraded",
        )
        self.assertEqual(
            monitor.classify_result(
                document_failed=False,
                render_ok=True,
                same_origin_resource_failed=0,
                console_error_count=3,
            ),
            "ok",
        )
        self.assertEqual(
            monitor.classify_result(
                document_failed=True,
                render_ok=False,
                same_origin_resource_failed=0,
                console_error_count=0,
            ),
            "down",
        )

    def test_display_latency_prefers_first_successful_response(self):
        self.assertEqual(
            monitor.choose_display_latency(
                first_success_latency_ms=123,
                main_document_latency_ms=456,
                dom_content_ms=789,
                fallback_latency_ms=1000,
            ),
            123,
        )
        self.assertEqual(
            monitor.choose_display_latency(
                first_success_latency_ms=None,
                main_document_latency_ms=456,
                dom_content_ms=789,
                fallback_latency_ms=1000,
            ),
            456,
        )


class AuthRouteTests(unittest.TestCase):
    def test_verify_code_does_not_require_turnstile_after_email_code_is_sent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main_data_dir = root / "main"
            check_data_dir = root / "check"
            main_data_dir.mkdir()
            check_data_dir.mkdir()
            email = "admin@example.com"
            (main_data_dir / "config.json").write_text(
                json.dumps(
                    {
                        "turnstile_enabled": True,
                        "turnstile_site_key": "site-key",
                        "turnstile_secret_key": "secret-key",
                    }
                ),
                encoding="utf-8",
            )
            (main_data_dir / "admin_users.json").write_text(
                json.dumps(
                    {
                        "users": [
                            {
                                "username": "admin",
                                "role": "super_admin",
                                "enabled": True,
                                "email": email,
                                "email_verified": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            storage.init_db(check_data_dir)
            storage.store_auth_code(email, "123456", "salt", check_data_dir)

            old_check_data_dir = config.CHECK_DATA_DIR
            old_main_data_dir = config.MAIN_DATA_DIR
            old_scheduler_enabled = config.SCHEDULER_ENABLED
            old_secret_key = config.SECRET_KEY
            old_verify_turnstile_token = main_site.verify_turnstile_token
            turnstile_called = {"value": False}

            def fake_verify_turnstile_token(*_args, **_kwargs):
                turnstile_called["value"] = True
                return False, "验证码登录不应再次要求人机验证"

            try:
                config.CHECK_DATA_DIR = check_data_dir
                config.MAIN_DATA_DIR = main_data_dir
                config.SCHEDULER_ENABLED = False
                config.SECRET_KEY = "test-secret"
                main_site.verify_turnstile_token = fake_verify_turnstile_token
                app_module = importlib.import_module("check_app.app")
                flask_app = app_module.create_app()
                client = flask_app.test_client()

                response = client.post("/api/auth/verify-code", json={"email": email, "code": "123456"})

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["success"])
                self.assertFalse(turnstile_called["value"])
                with client.session_transaction() as session:
                    self.assertEqual(session.get("check_admin_email"), email)
            finally:
                config.CHECK_DATA_DIR = old_check_data_dir
                config.MAIN_DATA_DIR = old_main_data_dir
                config.SCHEDULER_ENABLED = old_scheduler_enabled
                config.SECRET_KEY = old_secret_key
                main_site.verify_turnstile_token = old_verify_turnstile_token


class MailerTests(unittest.TestCase):
    def test_smtp_check_reports_missing_config_without_sending(self):
        result = mailer.check_smtp_connection(main_site.SmtpSettings(configured=False))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "missing")
        self.assertIn("配置不完整", result["message"])


if __name__ == "__main__":
    unittest.main()
