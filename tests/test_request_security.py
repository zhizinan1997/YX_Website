from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from flask import Flask, jsonify, request

from app.request_security import (
    get_request_client_ip,
    get_trusted_forwarded_host_proto,
    is_trusted_remote_fetch_service_url,
    register_strict_anti_crawl_guard,
    should_trust_proxy_headers,
    validate_safe_remote_fetch_url,
)


CRAWLER_USER_AGENTS = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "Mozilla/5.0 (compatible; Applebot/0.3; +http://www.apple.com/go/applebot)",
    "AdsBot-Google (+http://www.google.com/adsbot.html)",
    "Mozilla/5.0 (compatible; Storebot-Google/1.0; +http://www.google.com/bot.html)",
    "Mozilla/5.0 AppleWebKit/537.36; compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "ExampleCrawler/1.0 bot",
    "",
)


class StrictAntiCrawlGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        register_strict_anti_crawl_guard(self.app)

        @self.app.route("/")
        def index():
            return "public page"

        @self.app.route("/assets/test.css")
        def public_css():
            return "body{}", 200, {"Content-Type": "text/css"}

        @self.app.route("/cdn_assets/test.webp")
        def public_image():
            return b"RIFFtestWEBP", 200, {"Content-Type": "image/webp"}

        @self.app.route("/media/test.jpg")
        def public_media():
            return b"test", 200, {"Content-Type": "image/jpeg"}

        @self.app.route("/admin")
        def admin():
            return "admin login"

        @self.app.route("/api/admin/settings")
        def admin_api():
            return jsonify({"success": True})

        @self.app.route("/data/private.json")
        def private_data():
            return jsonify({"private": True})

        @self.app.route("/update_logs/release.md")
        def private_update_log():
            return "private log"

        self.client = self.app.test_client()

    def test_public_pages_and_resources_are_available_to_all_crawlers(self):
        public_paths = (
            "/",
            "/assets/test.css?cache-miss=1",
            "/cdn_assets/test.webp?cache-miss=1",
            "/media/test.jpg?cache-miss=1",
        )
        for user_agent in CRAWLER_USER_AGENTS:
            for path in public_paths:
                with self.subTest(user_agent=user_agent, path=path):
                    response = self.client.get(path, headers={"User-Agent": user_agent})
                    self.assertEqual(response.status_code, 200)

    def test_crawlers_are_still_blocked_from_private_paths(self):
        private_paths = (
            "/admin",
            "/api/admin/settings",
            "/data/private.json",
            "/update_logs/release.md",
        )
        for user_agent in CRAWLER_USER_AGENTS:
            for path in private_paths:
                with self.subTest(user_agent=user_agent, path=path):
                    response = self.client.get(path, headers={"User-Agent": user_agent})
                    self.assertEqual(response.status_code, 403)

    def test_regular_browser_can_reach_admin_login_and_authenticated_routes(self):
        headers = {"User-Agent": "Mozilla/5.0 Chrome/136 Safari/537.36"}
        self.assertEqual(self.client.get("/admin", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/settings", headers=headers).status_code, 200)

    def test_proxy_host_and_proto_are_used_only_when_explicitly_trusted(self):
        headers = {
            'X-Forwarded-Host': 'www.hnmetachip.cn',
            'X-Forwarded-Proto': 'https',
        }
        with self.app.test_request_context('/', headers=headers):
            with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': 'false'}):
                self.assertEqual(get_trusted_forwarded_host_proto(request, default=False), ('', ''))
            with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': 'true'}):
                self.assertEqual(
                    get_trusted_forwarded_host_proto(request, default=False),
                    ('www.hnmetachip.cn', 'https'),
                )

    def test_standard_forwarded_header_is_supported_as_fallback(self):
        with self.app.test_request_context('/', headers={
            'Forwarded': 'for=203.0.113.9;proto=https;host="www.hnmetachip.cn"',
        }):
            with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': 'true'}):
                self.assertEqual(
                    get_trusted_forwarded_host_proto(request, default=False),
                    ('www.hnmetachip.cn', 'https'),
                )


class TrustedProxyDecisionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_explicit_env_values_are_honoured(self):
        with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': 'true'}):
            self.assertTrue(should_trust_proxy_headers())
        with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': 'false'}):
            self.assertFalse(should_trust_proxy_headers())

    def test_unconfigured_env_trusts_only_private_or_listed_proxies(self):
        with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': '', 'TRUSTED_PROXY_CIDRS': ''}):
            # 回环/私网直连：本地反向代理场景，信任代理头。
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
                self.assertTrue(should_trust_proxy_headers(request))
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '10.0.0.8'}):
                self.assertTrue(should_trust_proxy_headers(request))
            # 公网直连：视为客户端本身，不信任代理头。
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '1.2.3.4'}):
                self.assertFalse(should_trust_proxy_headers(request))

        with patch.dict(os.environ, {
            'TRUST_PROXY_HEADERS': '',
            'TRUSTED_PROXY_CIDRS': '1.2.3.0/24, 8.8.4.4',
        }):
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '1.2.3.4'}):
                self.assertTrue(should_trust_proxy_headers(request))
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '8.8.4.4'}):
                self.assertTrue(should_trust_proxy_headers(request))
            with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '9.9.9.9'}):
                self.assertFalse(should_trust_proxy_headers(request))

    def test_client_ip_ignores_spoofed_headers_from_public_peer(self):
        headers = {
            'CF-Connecting-IP': '4.4.4.4',
            'X-Forwarded-For': '4.4.4.4',
        }
        with patch.dict(os.environ, {'TRUST_PROXY_HEADERS': '', 'TRUSTED_PROXY_CIDRS': ''}):
            with self.app.test_request_context('/', headers=headers, environ_base={'REMOTE_ADDR': '1.2.3.4'}):
                self.assertEqual(get_request_client_ip(request), '1.2.3.4')
            with self.app.test_request_context('/', headers=headers, environ_base={'REMOTE_ADDR': '10.0.0.8'}):
                self.assertEqual(get_request_client_ip(request), '4.4.4.4')


class TrustedRemoteFetchServiceTests(unittest.TestCase):
    def test_official_feishu_suffixes_match(self):
        for host in ('internal-api.feishu.cn', 'feishu.cn', 'open.larksuite.com'):
            with self.subTest(host=host):
                self.assertTrue(is_trusted_remote_fetch_service_url('https', host, '/'))

    def test_lookalike_hosts_do_not_match(self):
        for host in ('evil-feishu.com', 'feishu.evil.com', 'evilfeishu.cn', 'larksuite.com.evil.io'):
            with self.subTest(host=host):
                self.assertFalse(is_trusted_remote_fetch_service_url('https', host, '/'))

    def test_private_resolution_is_rejected_for_untrusted_hosts(self):
        # 字面量 IP：私网/保留地址拒绝，公网地址放行。
        ok, _, _ = validate_safe_remote_fetch_url('https://10.0.0.5/file')
        self.assertFalse(ok)
        ok, _, _ = validate_safe_remote_fetch_url('https://1.2.3.4/file')
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
