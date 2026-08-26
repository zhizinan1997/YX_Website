from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from app.routes import navigation_content as nav
from app.routes.admin import resolve_permission_for_path


class NavLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self._old_file = nav.NAV_LABELS_FILE

        app = Flask(__name__)
        app.secret_key = 'test-secret'
        nav.register_navigation_content_routes(
            app,
            login_required=lambda f: f,
            app_root=Path(__file__).resolve().parents[1],
            data_dir=self.data_dir,
            normalize_scanned_image_path=lambda image, prefix: image or '',
            extract_solution_meta_from_html=lambda filepath: None,
            extract_case_meta_from_html=lambda filepath: None,
            extract_product_meta_from_html=lambda filepath: None,
        )
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        nav.NAV_LABELS_FILE = self._old_file
        self.tmp.cleanup()

    def _login(self, permissions=None, super_admin=False):
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_is_super_admin'] = bool(super_admin)
            sess['admin_permissions'] = list(permissions or [])

    def _builtin_keys(self):
        return [item['key'] for item in nav.BUILTIN_NAV_ITEMS]

    def test_get_returns_builtin_defaults_without_file(self):
        response = self.client.get('/api/nav-labels')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        items = payload['items']
        self.assertEqual([item['key'] for item in items], self._builtin_keys())
        self.assertTrue(all(item['locked'] for item in items))
        mega_flags = {item['key']: item['has_mega'] for item in items}
        self.assertEqual(
            mega_flags,
            {'bio': False, 'gas': False, 'news': True, 'about': True, 'store': False, 'contact': True},
        )

    def test_post_requires_home_permission(self):
        self._login([])
        response = self.client.post('/api/admin/nav-labels', json={'items': []})
        self.assertEqual(response.status_code, 403)

    def test_post_rejects_missing_builtin_items(self):
        self._login(['home'])
        items = [
            {'key': key, 'label': '标题', 'url': '/pages/news/news.html'}
            for key in self._builtin_keys()[:-1]
        ]
        response = self.client.post('/api/admin/nav-labels', json={'items': items})
        self.assertEqual(response.status_code, 400)
        self.assertIn('不可删除', response.get_json()['message'])

    def test_post_saves_reorder_rename_and_url(self):
        self._login(['home'])
        keys = self._builtin_keys()
        reordered = list(reversed(keys))
        items = [
            {'key': key, 'label': f'模块-{key}', 'url': '/pages/about/about.html'}
            for key in reordered
        ]
        response = self.client.post('/api/admin/nav-labels', json={'items': items})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([item['key'] for item in payload['items']], reordered)

        saved = json.loads(nav.NAV_LABELS_FILE.read_text(encoding='utf-8'))
        self.assertEqual([item['key'] for item in saved['items']], reordered)

        public = self.client.get('/api/nav-labels')
        self.assertEqual([item['label'] for item in public.get_json()['items']], [
            f'模块-{key}' for key in reordered
        ])

    def test_post_adds_and_removes_custom_items(self):
        self._login(['home'])
        items = [
            {'key': key, 'label': label, 'url': url}
            for key, label, url in zip(self._builtin_keys(), ['A', 'B', 'C', 'D', 'E', 'F'], ['/a'] * 6)
        ]
        items.append({'label': '自定义模块', 'url': '/pages/contact/contact.html'})
        created = self.client.post('/api/admin/nav-labels', json={'items': items})
        self.assertEqual(created.status_code, 200)
        saved = created.get_json()['items']
        self.assertEqual(len(saved), 7)
        custom = saved[-1]
        self.assertTrue(custom['key'].startswith('custom-'))
        self.assertFalse(custom['locked'])

        remaining = [item for item in items if item.get('label') != '自定义模块']
        updated = self.client.post('/api/admin/nav-labels', json={'items': remaining})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(len(updated.get_json()['items']), 6)

    def test_post_rejects_unsafe_custom_url_only(self):
        self._login(['home'])
        items = [
            {'key': key, 'label': label, 'url': url}
            for key, label, url in zip(self._builtin_keys(), ['A', 'B', 'C', 'D', 'E', 'F'], ['/a'] * 6)
        ]
        items.append({'label': '坏链接模块', 'url': 'javascript:alert(1)'})
        response = self.client.post('/api/admin/nav-labels', json={'items': items})
        # 非法自定义项被丢弃，其余保存成功。
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()['items']), 6)

    def test_post_label_length_limit(self):
        self._login(['home'])
        long_label = '超' * 40
        items = [
            {'key': key, 'label': long_label, 'url': '/a'}
            for key in self._builtin_keys()
        ]
        response = self.client.post('/api/admin/nav-labels', json={'items': items})
        self.assertEqual(response.status_code, 200)
        for item in response.get_json()['items']:
            self.assertLessEqual(len(item['label']), nav.NAV_LABEL_MAX_LENGTH)

    def test_corrupt_file_falls_back_to_defaults(self):
        nav.NAV_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        nav.NAV_LABELS_FILE.write_text('{broken json', encoding='utf-8')
        response = self.client.get('/api/nav-labels')
        self.assertEqual(response.status_code, 200)
        items = response.get_json()['items']
        self.assertEqual([item['key'] for item in items], self._builtin_keys())

    def test_permission_resolution_for_paths(self):
        # 公开读取接口不要求后台权限；保存接口归属「首页设置」权限。
        self.assertIsNone(resolve_permission_for_path('/api/nav-labels', 'GET'))
        self.assertEqual(resolve_permission_for_path('/api/admin/nav-labels', 'POST'), 'home')


if __name__ == '__main__':
    unittest.main()
