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


class DnsPinningTests(unittest.TestCase):
    def test_detail_validation_returns_resolved_ip_for_domains(self):
        from app import request_security as rs

        def fake_getaddrinfo(host, *args, **kwargs):
            assert host == 'public.example'
            return [(2, 1, 6, '', ('93.184.216.34', 443))]

        with patch.object(rs, '_BASE_GETADDRINFO', fake_getaddrinfo):
            ok, _reason, normalized, pinned_ip = rs.validate_safe_remote_fetch_url_detail(
                'https://public.example/file'
            )
        self.assertTrue(ok)
        self.assertEqual(normalized, 'https://public.example/file')
        self.assertEqual(pinned_ip, '93.184.216.34')

    def test_detail_validation_skips_pin_for_literal_ips(self):
        from app import request_security as rs

        ok, _reason, _normalized, pinned_ip = rs.validate_safe_remote_fetch_url_detail(
            'https://1.2.3.4/file'
        )
        self.assertTrue(ok)
        self.assertEqual(pinned_ip, '')

    def test_pinned_resolution_forces_verified_ip(self):
        import socket as socket_module

        from app import request_security as rs

        resolved_hosts = []

        def fake_getaddrinfo(host, *args, **kwargs):
            resolved_hosts.append(host)
            return [(2, 1, 6, '', ('10.9.8.7', 443))]

        with patch.object(rs, '_BASE_GETADDRINFO', fake_getaddrinfo):
            with rs.pinned_dns_resolution('https://rebind.example/', '93.184.216.34'):
                socket_module.getaddrinfo('rebind.example', 443)
        # 命中 pin 栈：实际解析的是已验证 IP，而不是再次解析域名。
        self.assertEqual(resolved_hosts, ['93.184.216.34'])

    def test_pinned_resolution_is_inert_without_pin_ip(self):
        import socket as socket_module

        from app import request_security as rs

        resolved_hosts = []

        def fake_getaddrinfo(host, *args, **kwargs):
            resolved_hosts.append(host)
            return []

        with patch.object(rs, '_BASE_GETADDRINFO', fake_getaddrinfo):
            with rs.pinned_dns_resolution('https://1.2.3.4/file', ''):
                socket_module.getaddrinfo('1.2.3.4', 443)
        self.assertEqual(resolved_hosts, ['1.2.3.4'])


class RealClientIpHeaderTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def _request(self, headers, remote_addr='10.0.0.9'):
        return self.app.test_request_context('/', headers=headers, environ_base={'REMOTE_ADDR': remote_addr})

    def test_default_prefers_cf_connecting_ip_when_unconfigured(self):
        from app.request_security import get_request_client_ip

        with patch.dict(os.environ, {'REAL_CLIENT_IP_HEADERS': ''}):
            with self._request({'CF-Connecting-IP': '93.184.216.34'}):
                self.assertEqual(get_request_client_ip(request), '93.184.216.34')

    def test_configured_header_wins_over_spoofable_ones(self):
        from app.request_security import get_request_client_ip

        env = {
            'REAL_CLIENT_IP_HEADERS': 'Ali-Real-Client-IP,Ali-CDN-Real-IP',
            'TRUST_PROXY_HEADERS': 'true',
        }
        with patch.dict(os.environ, env):
            with self._request({
                'CF-Connecting-IP': '8.8.4.4',
                'Ali-Real-Client-IP': '93.184.216.34',
                'X-Forwarded-For': '8.8.4.4, 1.0.0.1',
            }):
                self.assertEqual(get_request_client_ip(request), '93.184.216.34')

    def test_strict_mode_ignores_spoofable_headers_when_edge_header_missing(self):
        from app.request_security import get_request_client_ip

        env = {
            'REAL_CLIENT_IP_HEADERS': 'Ali-Real-Client-IP',
            'TRUST_PROXY_HEADERS': 'true',
        }
        with patch.dict(os.environ, env):
            # 绕过 CDN 直连源站的攻击流量：伪造 CF-Connecting-IP / X-Real-IP
            # 不得生效，应收敛到 XFF 最右公网（反代追加的边缘/代理地址）。
            with self._request({
                'CF-Connecting-IP': '8.8.4.4',
                'X-Real-IP': '8.8.4.4',
                'X-Forwarded-For': '8.8.4.4, 1.0.0.1',
            }):
                self.assertEqual(get_request_client_ip(request), '1.0.0.1')

    def test_strict_mode_falls_back_to_direct_when_only_spoofable_headers(self):
        from app.request_security import get_request_client_ip

        env = {
            'REAL_CLIENT_IP_HEADERS': 'Ali-Real-Client-IP',
            'TRUST_PROXY_HEADERS': 'true',
        }
        with patch.dict(os.environ, env):
            # 只有可伪造头、没有 XFF 时：不再采信 CF/X-Real-IP，收敛到直连地址。
            with self._request({'CF-Connecting-IP': '8.8.4.4', 'X-Real-IP': '8.8.4.4'}):
                self.assertEqual(get_request_client_ip(request), '10.0.0.9')


if __name__ == "__main__":
    unittest.main()
