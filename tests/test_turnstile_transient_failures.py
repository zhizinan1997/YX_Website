"""验证码瞬态失败（transient）分类回归测试。

背景（2026-09-15）：源站直连 Cloudflare siteverify 跨境链路抖动——请求已
到达 CF 并消耗令牌，但响应未在超时内返回；代码随后用同一令牌经代理重试，
必然得到 timeout-or-duplicate，导致正常用户被误判登录失败并触发延迟保护。

修复：
1. 直连超时 6s → 10s；
2. _verify_admin_captcha 返回 (ok, reason, transient) 三态；
   timeout-or-duplicate 与“验证码服务…”网络错误均视为 transient；
3. 登录/发码端点对 transient 失败返回 503 且不计入失败次数
   （email-code/send 已有 IP 硬限流，不计数不会造成滥用）。
"""

from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.routes import admin as admin_routes
from app.routes.admin import (
    TURNSTILE_DIRECT_TIMEOUT_SECONDS,
    _verify_admin_captcha,
)


SETTINGS = {
    'enabled': True,
    'provider': 'cloudflare',
    'site_key': 'site-key',
    'secret_key': 'secret-key',
    'proxy_url': 'http://glash:7890',
    'proxy_fallback_enabled': True,
    'esa_identity': '',
    'esa_scene_id': '',
    'esa_region': 'cn',
}


class TurnstileTransientTests(unittest.TestCase):
    def setUp(self):
        self._original = admin_routes._request_turnstile_siteverify

    def tearDown(self):
        admin_routes._request_turnstile_siteverify = self._original

    def test_direct_timeout_bumped_to_10s(self):
        # 跨境链路抖动下 6s 过短：请求可能已到达 CF 并消耗令牌但响应超时。
        self.assertGreaterEqual(TURNSTILE_DIRECT_TIMEOUT_SECONDS, 10)

    def test_siteverify_success_is_not_transient(self):
        admin_routes._request_turnstile_siteverify = mock.Mock(
            return_value={'success': True}
        )
        ok, reason, transient = _verify_admin_captcha(SETTINGS, 'token', '1.2.3.4')
        self.assertTrue(ok)
        self.assertEqual(reason, '')
        self.assertFalse(transient)

    def test_timeout_or_duplicate_is_transient(self):
        # 现场复现：直连已到达 CF 消耗令牌但响应超时 → 代理重试 → duplicate。
        def fake_request(secret_key, token, *, remote_ip='', timeout=10, proxy_url=''):
            if not proxy_url:
                raise socket.timeout('direct timed out')
            return {'success': False, 'error-codes': ['timeout-or-duplicate']}

        admin_routes._request_turnstile_siteverify = fake_request
        ok, reason, transient = _verify_admin_captcha(SETTINGS, 'token', '1.2.3.4')
        self.assertFalse(ok)
        self.assertIn('timeout-or-duplicate', reason)
        self.assertTrue(transient, '令牌过期/重试消耗必须归类为 transient')

    def test_network_error_both_paths_is_transient(self):
        def fake_request(secret_key, token, *, remote_ip='', timeout=10, proxy_url=''):
            raise ConnectionError(f'cannot reach {proxy_url or "cloudflare"}')

        admin_routes._request_turnstile_siteverify = fake_request
        ok, reason, transient = _verify_admin_captcha(SETTINGS, 'token', '1.2.3.4')
        self.assertFalse(ok)
        self.assertTrue(transient, '网络错误必须归类为 transient')

    def test_invalid_token_is_not_transient(self):
        # 攻击面：伪造/无效令牌必须继续计入登录失败。
        admin_routes._request_turnstile_siteverify = mock.Mock(
            return_value={'success': False, 'error-codes': ['invalid-input-response']}
        )
        ok, reason, transient = _verify_admin_captcha(SETTINGS, 'garbage', '1.2.3.4')
        self.assertFalse(ok)
        self.assertIn('invalid-input-response', reason)
        self.assertFalse(transient)

    def test_disabled_or_missing_token(self):
        ok, reason, transient = _verify_admin_captcha(
            dict(SETTINGS, enabled=False), 'token', '1.2.3.4'
        )
        self.assertTrue(ok and reason == '' and transient is False)

        ok, reason, transient = _verify_admin_captcha(SETTINGS, '', '1.2.3.4')
        self.assertFalse(ok)
        self.assertEqual(reason, '请先完成人机验证。')
        self.assertFalse(transient, '缺令牌属可判定行为，必须计数')

    def test_esa_provider_shape_gate(self):
        ok, reason, transient = _verify_admin_captcha(
            dict(SETTINGS, provider='aliyun_esa'), 'x' * 64, '1.2.3.4'
        )
        self.assertTrue(ok and transient is False)
        ok, reason, transient = _verify_admin_captcha(
            dict(SETTINGS, provider='aliyun_esa'), 'short', '1.2.3.4'
        )
        self.assertFalse(ok)
        self.assertFalse(transient)


if __name__ == '__main__':
    unittest.main()
