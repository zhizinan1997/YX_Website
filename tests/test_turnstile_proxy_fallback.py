from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from flask import Flask

from app.routes import admin as admin_routes
from app.routes.admin import register_admin_routes


class TurnstileProxyFallbackFunctionTests(unittest.TestCase):
    def setUp(self):
        self.original_request = admin_routes._request_turnstile_siteverify

    def tearDown(self):
        admin_routes._request_turnstile_siteverify = self.original_request

    def test_direct_success_does_not_call_proxy(self):
        calls = []

        def fake_request(*_args, **kwargs):
            calls.append(kwargs)
            return {"success": True}

        admin_routes._request_turnstile_siteverify = fake_request

        ok, detail = admin_routes._verify_turnstile_token(
            "secret",
            "token",
            proxy_url="http://glash:7890",
            proxy_fallback_enabled=True,
        )

        self.assertTrue(ok)
        self.assertEqual(detail, "")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].get("proxy_url"), None)

    def test_cloudflare_validation_failure_does_not_call_proxy(self):
        calls = []

        def fake_request(*_args, **kwargs):
            calls.append(kwargs)
            return {"success": False, "error-codes": ["invalid-input-response"]}

        admin_routes._request_turnstile_siteverify = fake_request

        ok, detail = admin_routes._verify_turnstile_token(
            "secret",
            "token",
            proxy_url="http://glash:7890",
            proxy_fallback_enabled=True,
        )

        self.assertFalse(ok)
        self.assertIn("invalid-input-response", detail)
        self.assertEqual(len(calls), 1)

    def test_network_error_uses_proxy_when_fallback_enabled(self):
        calls = []

        def fake_request(*_args, **kwargs):
            calls.append(kwargs)
            if kwargs.get("proxy_url"):
                return {"success": True}
            raise URLError("timed out")

        admin_routes._request_turnstile_siteverify = fake_request

        ok, detail = admin_routes._verify_turnstile_token(
            "secret",
            "token",
            proxy_url="http://glash:7890",
            proxy_fallback_enabled=True,
        )

        self.assertTrue(ok)
        self.assertEqual(detail, "")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["proxy_url"], "http://glash:7890")

    def test_network_error_without_fallback_fails_directly(self):
        calls = []

        def fake_request(*_args, **kwargs):
            calls.append(kwargs)
            raise TimeoutError("timed out")

        admin_routes._request_turnstile_siteverify = fake_request

        ok, detail = admin_routes._verify_turnstile_token(
            "secret",
            "token",
            proxy_url="http://glash:7890",
            proxy_fallback_enabled=False,
        )

        self.assertFalse(ok)
        self.assertIn("验证码服务请求失败", detail)
        self.assertEqual(len(calls), 1)

    def test_connectivity_result_treats_cloudflare_json_as_reachable(self):
        def fake_request(*_args, **_kwargs):
            return {"success": False, "error-codes": ["invalid-input-response"]}

        admin_routes._request_turnstile_siteverify = fake_request

        result = admin_routes._build_turnstile_connectivity_result(secret_key="secret")

        self.assertTrue(result["success"])
        self.assertFalse(result["cloudflare_success"])
        self.assertEqual(result["error_codes"], "invalid-input-response")


class AdminTurnstileProxyRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = {
            "turnstile_enabled": True,
            "turnstile_site_key": "site-key",
            "turnstile_secret_key": "secret-key",
            "turnstile_proxy_url": "http://glash:7890",
            "turnstile_proxy_fallback_enabled": True,
        }
        self.original_request = admin_routes._request_turnstile_siteverify

        app = Flask(__name__)
        app.secret_key = "test-secret"

        def get_config():
            return dict(self.config)

        def update_config(updates):
            self.config.update(updates or {})
            return dict(self.config)

        register_admin_routes(
            app,
            login_required=lambda f: f,
            get_config=get_config,
            update_config=update_config,
            append_admin_login_log=lambda **_kwargs: None,
            load_admin_login_logs=lambda: [],
            admin_login_log_lock=None,
            project_root=self.root,
            resolve_ip_location=lambda _ip: "unknown",
            resolve_ip_country_code=lambda _ip: "CN",
        )
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin_is_super_admin"] = True

    def tearDown(self):
        admin_routes._request_turnstile_siteverify = self.original_request
        self.tmp.cleanup()

    def _post(self, path, payload):
        return self.client.post(
            path,
            json=payload,
            headers={"Origin": "http://localhost"},
        )

    def test_config_get_returns_proxy_fields(self):
        response = self.client.get("/api/admin/security/turnstile")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["proxy_url"], "http://glash:7890")
        self.assertTrue(data["proxy_fallback_enabled"])

    def test_config_get_returns_legacy_cloudflare_provider(self):
        response = self.client.get("/api/admin/security/turnstile")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["provider"], "cloudflare")

    def test_config_post_saves_proxy_fields(self):
        response = self._post("/api/admin/security/turnstile", {
            "enabled": True,
            "site_key": "next-site",
            "secret_key": "",
            "proxy_url": "http://proxy.local:7890",
            "proxy_fallback_enabled": True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(self.config["turnstile_site_key"], "next-site")
        self.assertEqual(self.config["turnstile_secret_key"], "secret-key")
        self.assertEqual(self.config["turnstile_proxy_url"], "http://proxy.local:7890")
        self.assertTrue(self.config["turnstile_proxy_fallback_enabled"])

    def test_config_post_saves_aliyun_esa_provider(self):
        response = self._post("/api/admin/security/turnstile", {
            "enabled": True,
            "provider": "aliyun_esa",
            "site_key": "",
            "secret_key": "",
            "esa_identity": "esa-identity",
            "esa_scene_id": "scene-id",
            "esa_region": "cn",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(self.config["admin_captcha_provider"], "aliyun_esa")
        self.assertEqual(self.config["admin_esa_identity"], "esa-identity")
        self.assertEqual(self.config["admin_esa_scene_id"], "scene-id")

    def test_aliyun_esa_accepts_captcha_param_without_cloudflare_request(self):
        settings = admin_routes._get_admin_captcha_settings({
            "turnstile_enabled": True,
            "admin_captcha_provider": "aliyun_esa",
            "admin_esa_identity": "identity",
            "admin_esa_scene_id": "scene",
        })

        real_shape_param = "x" * 32 + "+abc/==-_.~"
        ok, detail = admin_routes._verify_admin_captcha(settings, real_shape_param)

        self.assertTrue(ok)
        self.assertEqual(detail, "")

    def test_aliyun_esa_rejects_short_or_malformed_captcha_param(self):
        settings = {
            "enabled": True,
            "provider": "aliyun_esa",
        }

        for junk in ("", "x", "captcha-param", "a" * 31, "has space" * 5, "控制字符\t" * 5):
            ok, _detail = admin_routes._verify_admin_captcha(settings, junk)
            self.assertFalse(ok, f"junk ESA captcha param should be rejected: {junk!r}")

    def test_config_post_rejects_fallback_without_proxy_url(self):
        response = self._post("/api/admin/security/turnstile", {
            "enabled": False,
            "site_key": "",
            "secret_key": "",
            "proxy_url": "",
            "proxy_fallback_enabled": True,
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_config_post_rejects_invalid_proxy_scheme(self):
        response = self._post("/api/admin/security/turnstile", {
            "enabled": False,
            "site_key": "",
            "secret_key": "",
            "proxy_url": "socks5://glash:7890",
            "proxy_fallback_enabled": False,
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_connectivity_test_endpoint_reports_reachable_json(self):
        def fake_request(*_args, **_kwargs):
            return {"success": False, "error-codes": ["invalid-input-response"]}

        admin_routes._request_turnstile_siteverify = fake_request

        direct = self._post("/api/admin/security/turnstile/test-direct", {})
        proxy = self._post("/api/admin/security/turnstile/test-proxy", {
            "proxy_url": "http://glash:7890",
        })

        self.assertEqual(direct.status_code, 200)
        self.assertTrue(direct.get_json()["success"])
        self.assertEqual(proxy.status_code, 200)
        self.assertTrue(proxy.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
