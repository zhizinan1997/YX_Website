from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from app.routes import promotion_links as pl


class PromotionLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self._old_file = pl.PROMOTION_LINKS_FILE

        app = Flask(__name__)
        app.secret_key = 'test-secret'
        pl.register_promotion_link_routes(
            app,
            login_required=lambda f: f,
            data_dir=self.data_dir,
            get_public_base_url=lambda: 'https://www.example.com',
        )
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        pl.PROMOTION_LINKS_FILE = self._old_file
        self.tmp.cleanup()

    def _login(self, permissions=None, super_admin=False):
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_is_super_admin'] = bool(super_admin)
            sess['admin_permissions'] = list(permissions or [])

    def test_requires_promotion_links_permission(self):
        self._login([])
        response = self.client.get('/api/admin/promotion-links')
        self.assertEqual(response.status_code, 403)

    def test_create_duplicate_and_archive(self):
        self._login(['promotion-links'])
        payload = {
            'name': '微信公众号文章 A',
            'promotion_mark': 'wechat-article-a',
            'target_path': '/pages/gassensing/mc_ld_r1.html',
            'utm_source': 'wechat',
            'utm_medium': 'article',
            'utm_campaign': 'hydrogen',
            'utm_content': 'article-a',
        }
        created = self.client.post('/api/admin/promotion-links', json=payload)
        self.assertEqual(created.status_code, 200)
        item = created.get_json()['item']
        self.assertIn('utm_id=wechat-article-a', item['url'])
        self.assertIn('utm_source=wechat', item['url'])

        duplicate = self.client.post('/api/admin/promotion-links', json=payload)
        self.assertEqual(duplicate.status_code, 400)

        archived = self.client.delete(f"/api/admin/promotion-links/{item['id']}")
        self.assertEqual(archived.status_code, 200)
        listed = self.client.get('/api/admin/promotion-links')
        self.assertEqual(listed.get_json()['items'], [])

    def test_rejects_cross_origin_target_url(self):
        self._login(['promotion-links'])
        response = self.client.post('/api/admin/promotion-links', json={
            'name': 'Bad',
            'promotion_mark': 'bad-link',
            'target_path': 'https://evil.example/path',
        })
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
