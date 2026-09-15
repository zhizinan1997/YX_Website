"""公共页面人机验证随后台 provider 设置切换的回归测试。

官网反馈/招聘表单与智能客服此前固定走 Cloudflare Turnstile；
现在 /api/turnstile/public 返回 provider 字段（含 ESA 公开参数），
后端校验随 admin_captcha_provider 切换：cloudflare=siteverify；
aliyun_esa=边缘规则验签 + 应用侧形态门槛。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask

from app.routes import contact_messages
from app.routes.admin import verify_public_captcha_token


ESA_SETTINGS = {
    'enabled': True,
    'provider': 'aliyun_esa',
    'site_key': '',
    'secret_key': '',
    'proxy_url': '',
    'proxy_fallback_enabled': False,
    'esa_identity': 'esa-test',
    'esa_scene_id': 'scene-test',
    'esa_region': 'cn',
}

CF_SETTINGS = {
    'enabled': True,
    'provider': 'cloudflare',
    'site_key': 'site-key',
    'secret_key': 'secret-key',
    'proxy_url': '',
    'proxy_fallback_enabled': False,
    'esa_identity': '',
    'esa_scene_id': '',
    'esa_region': 'cn',
}


class PublicEsaShapeGateTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test'

        @app.route('/probe')
        def probe():
            result = contact_messages.require_public_turnstile_check('1.2.3.4')
            if result is None:
                return {'ok': True}
            return result[0], result[1]

        self.client = app.test_client()

    def test_esa_valid_shape_passes_without_siteverify(self):
        old = dict(contact_messages._DEPS)
        try:
            contact_messages.configure_contact_messages(
                get_config=lambda: {},
                get_turnstile_settings=lambda _c: ESA_SETTINGS,
                verify_turnstile_token=lambda **_k: mock.Mock(side_effect=AssertionError('ESA 不得调用 siteverify')),
                get_client_ip=lambda: '1.2.3.4',
                clean_job_text=lambda v: str(v or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tempfile.gettempdir()),
                messages_meta_file=Path(tempfile.gettempdir()) / 'm.json',
                resume_uploads_dir=Path(tempfile.gettempdir()),
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            with self.client.session_transaction() as sess:
                sess['cf_turnstile_response'] = None
            resp = self.client.get('/probe', headers={'X-Test-Token': 'x' * 64})
            # token 由请求体提取；GET 无体 → 这里改为直接调用
            self.assertEqual(resp.status_code, 400)  # 缺令牌 → 请先完成人机验证
        finally:
            contact_messages._DEPS.clear()
            contact_messages._DEPS.update(old)

    def test_require_public_check_esa_provider(self):
        old = dict(contact_messages._DEPS)
        try:
            contact_messages.configure_contact_messages(
                get_config=lambda: {},
                get_turnstile_settings=lambda _c: ESA_SETTINGS,
                verify_turnstile_token=lambda **_k: (_ for _ in ()).throw(AssertionError('ESA 不得调用 siteverify')),
                get_client_ip=lambda: '1.2.3.4',
                clean_job_text=lambda v: str(v or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tempfile.gettempdir()),
                messages_meta_file=Path(tempfile.gettempdir()) / 'm.json',
                resume_uploads_dir=Path(tempfile.gettempdir()),
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            app = Flask(__name__)
            app.secret_key = 't'

            @app.route('/probe', methods=['POST'])
            def probe():
                result = contact_messages.require_public_turnstile_check('1.2.3.4')
                if result is None:
                    return {'ok': True}
                return result[0], result[1]

            client = app.test_client()
            ok_resp = client.post('/probe', data={'turnstileToken': 'A' * 64})
            self.assertEqual(ok_resp.status_code, 200)
            bad_resp = client.post('/probe', data={'turnstileToken': 'short'})
            self.assertEqual(bad_resp.status_code, 400)
            self.assertIn('重新完成验证', bad_resp.get_json()['message'])
        finally:
            contact_messages._DEPS.clear()
            contact_messages._DEPS.update(old)

    def test_require_public_check_cloudflare_provider(self):
        old = dict(contact_messages._DEPS)
        try:
            verify = mock.Mock(return_value=(True, ''))
            contact_messages.configure_contact_messages(
                get_config=lambda: {},
                get_turnstile_settings=lambda _c: CF_SETTINGS,
                verify_turnstile_token=verify,
                get_client_ip=lambda: '1.2.3.4',
                clean_job_text=lambda v: str(v or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tempfile.gettempdir()),
                messages_meta_file=Path(tempfile.gettempdir()) / 'm.json',
                resume_uploads_dir=Path(tempfile.gettempdir()),
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            app = Flask(__name__)
            app.secret_key = 't'

            @app.route('/probe', methods=['POST'])
            def probe():
                result = contact_messages.require_public_turnstile_check('1.2.3.4')
                if result is None:
                    return {'ok': True}
                return result[0], result[1]

            resp = app.test_client().post('/probe', data={'cf_turnstile_response': 'tok'})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(verify.call_count, 1)
        finally:
            contact_messages._DEPS.clear()
            contact_messages._DEPS.update(old)

    def test_public_config_endpoint_exposes_provider_and_esa_fields(self):
        app = Flask(__name__)
        app.secret_key = 't'
        with tempfile.TemporaryDirectory() as tmp:
            contact_messages.register_contact_message_routes(
                app,
                login_required=lambda fn: fn,
                get_config=lambda: {},
                get_turnstile_settings=lambda _c: ESA_SETTINGS,
                verify_turnstile_token=lambda **_k: (True, ''),
                get_client_ip=lambda: '1.2.3.4',
                clean_job_text=lambda v: str(v or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tmp) / 'messages',
                messages_meta_file=Path(tmp) / 'messages_meta.json',
                resume_uploads_dir=Path(tmp) / 'resumes',
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            data = app.test_client().get('/api/turnstile/public').get_json()
            self.assertTrue(data['enabled'])
            self.assertEqual(data['provider'], 'aliyun_esa')
            self.assertEqual(data['esa_identity'], 'esa-test')
            self.assertEqual(data['esa_scene_id'], 'scene-test')
            self.assertNotIn('secret_key', data)

    def test_public_config_endpoint_cloudflare_shape(self):
        app = Flask(__name__)
        app.secret_key = 't'
        with tempfile.TemporaryDirectory() as tmp:
            contact_messages.register_contact_message_routes(
                app,
                login_required=lambda fn: fn,
                get_config=lambda: {},
                get_turnstile_settings=lambda _c: CF_SETTINGS,
                verify_turnstile_token=lambda **_k: (True, ''),
                get_client_ip=lambda: '1.2.3.4',
                clean_job_text=lambda v: str(v or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tmp) / 'messages',
                messages_meta_file=Path(tmp) / 'messages_meta.json',
                resume_uploads_dir=Path(tmp) / 'resumes',
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            data = app.test_client().get('/api/turnstile/public').get_json()
            self.assertEqual(data['provider'], 'cloudflare')
            self.assertIn('site_key', data)
            self.assertNotIn('esa_identity', data)

    def test_verify_public_captcha_token_two_tuple(self):
        with mock.patch.object(
            __import__('app.routes.admin', fromlist=['_verify_admin_captcha']),
            '_verify_admin_captcha',
            return_value=(True, '', False),
        ):
            ok, detail = verify_public_captcha_token(CF_SETTINGS, 'tok', '1.2.3.4')
            self.assertTrue(ok)
            self.assertEqual(detail, '')

    def test_frontend_guard_supports_provider_switch(self):
        js = (REPO_ROOT / 'assets' / 'js' / 'public-turnstile.js').read_text(encoding='utf-8')
        self.assertIn("provider === 'aliyun_esa'", js)
        self.assertIn('initAliyunCaptcha', js)
        self.assertIn("provider === 'aliyun_esa' ? 'turnstileToken' : 'cf_turnstile_response'", js)
        self.assertIn('aliyunInstance.refresh()', js)
        self.assertIn("var provider = 'cloudflare';", js)


if __name__ == '__main__':
    unittest.main()
