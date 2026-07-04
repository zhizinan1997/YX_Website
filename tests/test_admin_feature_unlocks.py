from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from flask import Flask

from app import admin_feature_unlocks as afu
from app.auth_guards import login_required
from app.routes import promotion_links as pl
from app.routes.admin import ADMIN_SESSION_SCHEMA_VERSION, register_admin_routes


class AdminFeatureUnlocksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_file = afu.ADMIN_FEATURE_UNLOCKS_FILE
        afu.clear_admin_feature_unlocks_cache()

    def tearDown(self):
        afu.ADMIN_FEATURE_UNLOCKS_FILE = self.old_file
        afu.clear_admin_feature_unlocks_cache()
        self.tmp.cleanup()

    def _use_config(self, payload=None):
        path = self.root / 'admin_feature_unlocks.json'
        afu.ADMIN_FEATURE_UNLOCKS_FILE = path
        afu.clear_admin_feature_unlocks_cache()
        if payload is not None:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def test_missing_config_defaults_to_unlocked(self):
        self._use_config()
        self.assertTrue(afu.is_admin_feature_unlocked('promotion-links'))
        self.assertTrue(afu.is_admin_feature_unlocked('new-future-feature'))

    def test_explicit_false_locks_feature_and_unlisted_keys_default_unlocked(self):
        self._use_config({
            'version': 1,
            'default_unlocked': True,
            'features': {'promotion-links': False},
        })

        self.assertFalse(afu.is_admin_feature_unlocked('promotion-links'))
        self.assertTrue(afu.is_admin_feature_unlocked('messages'))
        self.assertEqual(
            afu.get_admin_feature_unlocks(['promotion-links', 'messages']),
            {'promotion-links': False, 'messages': True},
        )

    def test_invalid_config_uses_safe_defaults(self):
        path = self._use_config()
        path.write_text('{bad json', encoding='utf-8')
        afu.clear_admin_feature_unlocks_cache()

        with self.assertLogs('app.admin_feature_unlocks', level='WARNING'):
            self.assertTrue(afu.is_admin_feature_unlocked('promotion-links'))

    def test_repository_default_config_locks_promotion_links(self):
        afu.ADMIN_FEATURE_UNLOCKS_FILE = Path(__file__).resolve().parents[1] / 'data' / 'admin_feature_unlocks.json'
        afu.clear_admin_feature_unlocks_cache()

        self.assertFalse(afu.is_admin_feature_unlocked('promotion-links'))


class AdminFeatureUnlockRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / 'data'
        self.data_dir.mkdir()
        self.old_unlock_file = afu.ADMIN_FEATURE_UNLOCKS_FILE
        self.old_promotion_file = pl.PROMOTION_LINKS_FILE
        afu.ADMIN_FEATURE_UNLOCKS_FILE = self.data_dir / 'admin_feature_unlocks.json'
        afu.ADMIN_FEATURE_UNLOCKS_FILE.write_text(json.dumps({
            'version': 1,
            'default_unlocked': True,
            'features': {'promotion-links': False},
        }), encoding='utf-8')
        afu.clear_admin_feature_unlocks_cache()

    def tearDown(self):
        afu.ADMIN_FEATURE_UNLOCKS_FILE = self.old_unlock_file
        pl.PROMOTION_LINKS_FILE = self.old_promotion_file
        afu.clear_admin_feature_unlocks_cache()
        self.tmp.cleanup()

    def _login(self, client, *, super_admin=False, permissions=None):
        with client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_username'] = 'admin'
            sess['admin_is_super_admin'] = bool(super_admin)
            sess['admin_permissions'] = list(permissions or [])
            sess['admin_login_at'] = int(time.time())
            sess['admin_session_ttl'] = 3600
            sess['admin_session_schema'] = ADMIN_SESSION_SCHEMA_VERSION

    def test_locked_promotion_links_api_blocks_super_admin_and_sub_admin(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        pl.register_promotion_link_routes(
            app,
            login_required=login_required,
            data_dir=self.data_dir,
            get_public_base_url=lambda: 'https://www.example.com',
        )
        client = app.test_client()

        for super_admin in (True, False):
            with self.subTest(super_admin=super_admin):
                self._login(client, super_admin=super_admin, permissions=['promotion-links'])
                response = client.get('/api/admin/promotion-links')
                self.assertEqual(response.status_code, 403)

    def test_admin_check_filters_catalog_and_reports_feature_unlocks(self):
        users_file = self.data_dir / 'admin_users.json'
        users_file.write_text(json.dumps({
            'version': 1,
            'users': [{
                'username': 'admin',
                'password_hash': 'test-hash',
                'role': 'super_admin',
                'enabled': True,
                'permissions': ['site-reports', 'promotion-links'],
            }],
        }), encoding='utf-8')

        config = {
            'admin_username': 'admin',
            'admin_password_hash': 'test-hash',
            'admin_password': '',
        }

        def get_config():
            return dict(config)

        def update_config(updates):
            config.update(updates or {})
            return dict(config)

        app = Flask(__name__)
        app.secret_key = 'test-secret'
        register_admin_routes(
            app,
            login_required=lambda f: f,
            get_config=get_config,
            update_config=update_config,
            append_admin_login_log=lambda **_kwargs: None,
            load_admin_login_logs=lambda: [],
            admin_login_log_lock=None,
            project_root=self.root,
            resolve_ip_location=lambda _ip: 'unknown',
            resolve_ip_country_code=lambda _ip: 'CN',
        )
        client = app.test_client()
        self._login(client, super_admin=True, permissions=['promotion-links'])

        response = client.get('/admin/check')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        catalog_keys = [item['key'] for item in data['permission_catalog']]
        self.assertNotIn('promotion-links', catalog_keys)
        self.assertFalse(data['feature_unlocks']['promotion-links'])
        self.assertNotIn('promotion-links', data['unlocked_features'])
        self.assertNotIn('promotion-links', data['permissions'])


if __name__ == '__main__':
    unittest.main()
