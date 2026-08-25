from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify, request

from app import app_config
from app.request_security import CSRF_HEADER_NAME, CSRF_SESSION_KEY, is_same_origin_request
from app.routes import contact_messages
from app.routes.admin import BEIJING_TZ, _format_blocked_until


class ReportedBugFixTests(unittest.TestCase):
    def test_contact_rate_limit_uses_shared_store_key(self):
        old_deps = dict(contact_messages._DEPS)
        try:
            contact_messages.configure_contact_messages(
                get_config=lambda: {},
                get_turnstile_settings=lambda _config: {},
                verify_turnstile_token=lambda **_kwargs: (True, ''),
                get_client_ip=lambda: '127.0.0.1',
                clean_job_text=lambda value: str(value or ''),
                now_beijing=lambda: None,
                messages_dir=Path(tempfile.gettempdir()),
                messages_meta_file=Path(tempfile.gettempdir()) / 'yx-test-messages-meta.json',
                resume_uploads_dir=Path(tempfile.gettempdir()),
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )
            with patch.object(contact_messages, 'check_and_record', return_value=(True, 0, 1)) as check:
                self.assertTrue(contact_messages.check_rate_limit('203.0.113.10'))
            check.assert_called_once_with('contact:203.0.113.10', limit=5, window=3600)
        finally:
            contact_messages._DEPS.clear()
            contact_messages._DEPS.update(old_deps)

    def test_resume_size_is_measured_from_end_after_validation(self):
        app = Flask('resume_size_test')
        app.secret_key = 'test-secret'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages_dir = root / 'messages'
            resumes_dir = root / 'resumes'
            messages_dir.mkdir()
            resumes_dir.mkdir()

            contact_messages.register_contact_message_routes(
                app,
                login_required=lambda fn: fn,
                get_config=lambda: {},
                get_turnstile_settings=lambda _config: {},
                verify_turnstile_token=lambda **_kwargs: (True, ''),
                get_client_ip=lambda: '127.0.0.1',
                clean_job_text=lambda value: str(value or '').strip(),
                now_beijing=lambda: datetime(2026, 1, 1, tzinfo=app_config.BEIJING_TZ),
                messages_dir=messages_dir,
                messages_meta_file=root / 'messages_meta.json',
                resume_uploads_dir=resumes_dir,
                allowed_resume_extensions={'.pdf'},
                rate_limit_max=5,
                rate_limit_window=3600,
            )

            fields = {
                'name': '测试用户',
                'age': '30',
                'ethnicity': '汉',
                'gender': '男',
                'address': '湖南',
                'phone': '13800000000',
                'email': 'test@example.com',
                'education': '本科',
                'school': '测试大学',
                'work_experience': '无',
                'project_experience': '无',
                'self_statement': '测试',
            }
            payload = {**fields, 'resume_file': (io.BytesIO(b'0123456789'), 'resume.pdf')}

            with patch.object(contact_messages, 'check_rate_limit', return_value=True), \
                    patch.object(contact_messages, 'validate_uploaded_resume', side_effect=lambda uploaded: uploaded.stream.read(3) is not None), \
                    patch.object(contact_messages, '_start_admin_notification'):
                response = app.test_client().post('/api/job-application', data=payload, content_type='multipart/form-data')

            self.assertEqual(response.status_code, 200)
            messages = list(messages_dir.glob('*.json'))
            self.assertEqual(len(messages), 1)
            message = json.loads(messages[0].read_text(encoding='utf-8'))
            self.assertEqual(message['resume_size_bytes'], 10)
            saved_resume = resumes_dir / message['resume_stored_filename']
            self.assertEqual(saved_resume.read_bytes(), b'0123456789')

    def test_missing_origin_or_referer_requires_session_csrf_token(self):
        app = Flask('csrf_fallback_test')
        app.secret_key = 'test-secret'

        @app.post('/write')
        def write():
            return jsonify({'ok': is_same_origin_request(request)})

        client = app.test_client()
        with client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = 'session-token'

        accepted = client.post('/write', headers={CSRF_HEADER_NAME: 'session-token'})
        rejected = client.post('/write', headers={CSRF_HEADER_NAME: 'wrong-token'})
        self.assertTrue(accepted.get_json()['ok'])
        self.assertFalse(rejected.get_json()['ok'])

    def test_blocked_until_is_formatted_in_beijing_time(self):
        timestamp = 1_700_000_000
        expected = datetime.fromtimestamp(timestamp, tz=BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        self.assertEqual(_format_blocked_until(timestamp), expected)

    def test_persisted_placeholder_secret_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_root = app_config.APP_ROOT
            old_secret = app_config.os.environ.get('SECRET_KEY')
            try:
                app_config.APP_ROOT = Path(tmp)
                app_config.os.environ.pop('SECRET_KEY', None)
                secret_file = Path(tmp) / 'data' / '.flask_secret_key'
                secret_file.parent.mkdir(parents=True)
                secret_file.write_text('your-secret-key-change-in-production', encoding='utf-8')

                generated = app_config.load_or_create_secret_key()

                self.assertGreaterEqual(len(generated), 32)
                self.assertNotIn(generated, app_config.PLACEHOLDER_SECRET_KEYS)
                self.assertEqual(secret_file.read_text(encoding='utf-8'), generated)
            finally:
                app_config.APP_ROOT = old_root
                if old_secret is None:
                    app_config.os.environ.pop('SECRET_KEY', None)
                else:
                    app_config.os.environ['SECRET_KEY'] = old_secret


if __name__ == '__main__':
    unittest.main()
