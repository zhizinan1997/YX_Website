from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from app.routes.image_seo import _image_dimensions, configure_image_seo, register_image_seo_routes, scan_image_assets


class ImageSeoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        (self.root / 'assets').mkdir()
        (self.root / 'pages' / 'news').mkdir(parents=True)
        # 1x1 transparent PNG.
        (self.root / 'assets' / 'product.png').write_bytes(
            bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489')
        )
        self.page = self.root / 'pages' / 'news' / 'item.html'
        self.page.write_text('<html><body><img src="/assets/product.png"><img src="/assets/missing.png" alt="图片"></body></html>', encoding='utf-8')
        (self.root / 'index.html').write_text('<html><body><img src="/assets/product.png" alt="产品图"></body></html>', encoding='utf-8')
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        register_image_seo_routes(
            self.app,
            login_required=lambda fn: fn,
            app_root=self.root,
            data_dir=self.root / 'data',
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_is_read_only_for_pages_and_builds_report(self):
        before = self.page.read_text(encoding='utf-8')
        report = scan_image_assets(persist=True)
        self.assertEqual(before, self.page.read_text(encoding='utf-8'))
        self.assertGreaterEqual(report['summary']['total'], 2)
        self.assertTrue((self.root / 'data' / 'image_seo_assets.json').exists())
        missing = next(item for item in report['items'] if item['url'] == '/assets/missing.png')
        self.assertIn('missing_file', missing['issues'])

    def test_lossy_vp8_webp_dimensions_are_detected(self):
        webp = self.root / 'assets' / 'lossy.webp'
        # Minimal bytes required for the VP8 frame header: start code,
        # little-endian width 1279 and height 870.
        payload = b'RIFF' + (30).to_bytes(4, 'little') + b'WEBPVP8 ' + (10).to_bytes(4, 'little')
        payload += b'\xf0\x87\x03\x9d\x01\x2a\xff\x04\x66\x03'
        webp.write_bytes(payload)
        self.assertEqual(_image_dimensions(webp), (1279, 870))

    def test_update_and_bulk_only_change_selected_assets(self):
        report = scan_image_assets(persist=True)
        items = report['items']
        first, second = items[0], items[1]
        response = self.client.put(f"/api/admin/image-seo/assets/{first['assetId']}", json={
            'alt': '已审核的产品图片', 'ownerPage': '/pages/news/item.html', 'role': 'news', 'indexable': True,
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/api/admin/image-seo/assets/bulk', json={
            'assetIds': [first['assetId']], 'patch': {'role': 'decorative'},
        })
        self.assertEqual(response.status_code, 200)
        stored = json.loads((self.root / 'data' / 'image_seo_assets.json').read_text(encoding='utf-8'))['items']
        by_id = {item['assetId']: item for item in stored}
        self.assertEqual(by_id[first['assetId']]['role'], 'decorative')
        self.assertFalse(by_id[first['assetId']]['indexable'])
        self.assertEqual(by_id[second['assetId']]['role'], second['role'])

    def test_alt_drafts_are_not_persisted(self):
        item = scan_image_assets(persist=True)['items'][0]
        before = (self.root / 'data' / 'image_seo_assets.json').read_text(encoding='utf-8')
        response = self.client.post('/api/admin/image-seo/alt-drafts', json={'assetIds': [item['assetId']]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['persisted'])
        self.assertEqual(before, (self.root / 'data' / 'image_seo_assets.json').read_text(encoding='utf-8'))

    def test_ignored_assets_are_hidden_from_active_list_and_can_be_restored(self):
        item = scan_image_assets(persist=True)['items'][0]
        response = self.client.put(f"/api/admin/image-seo/assets/{item['assetId']}", json={'ignored': True})
        self.assertEqual(response.status_code, 200)
        ignored_item = response.get_json()['item']
        self.assertTrue(ignored_item['ignored'])
        self.assertFalse(ignored_item['indexable'])

        # A new scan must preserve the manual ignore decision.
        scan_image_assets(persist=True)
        active = self.client.get('/api/admin/image-seo/assets?status=active&scan_if_empty=0').get_json()['items']
        ignored = self.client.get('/api/admin/image-seo/assets?status=ignored&scan_if_empty=0').get_json()['items']
        self.assertNotIn(item['assetId'], {row['assetId'] for row in active})
        self.assertIn(item['assetId'], {row['assetId'] for row in ignored})

        response = self.client.put(f"/api/admin/image-seo/assets/{item['assetId']}", json={'ignored': False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['item']['ignored'])

    def test_report_summary_reflects_ignore_changes_without_rescan(self):
        item = scan_image_assets(persist=True)['items'][0]
        response = self.client.put(f"/api/admin/image-seo/assets/{item['assetId']}", json={'ignored': True})
        self.assertEqual(response.status_code, 200)
        report = self.client.get('/api/admin/image-seo/report').get_json()['report']
        self.assertEqual(report['summary']['ignored'], 1)

    def test_owner_page_accepts_absolute_site_url_and_resolves_image_url(self):
        item = scan_image_assets(persist=True)['items'][0]
        response = self.client.put(f"/api/admin/image-seo/assets/{item['assetId']}", json={
            'ownerPage': 'https://www.hnmetachip.cn/pages/gassensing/mc_ld_h2.html',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['item']['ownerPage'], '/pages/gassensing/mc_ld_h2.html')

    def test_mutations_reject_failed_same_origin_check(self):
        app = Flask('image_seo_csrf_test')
        app.secret_key = 'test'
        register_image_seo_routes(
            app,
            login_required=lambda fn: fn,
            app_root=self.root,
            data_dir=self.root / 'data',
            is_same_origin_request=lambda _request: False,
        )
        client = app.test_client()
        response = client.post('/api/admin/image-seo/scan')
        self.assertEqual(response.status_code, 403)

    def test_dynamic_sidebar_keeps_image_seo_in_content_operations(self):
        state_script = (Path(__file__).resolve().parents[1] / 'admin' / 'js' / 'state.js').read_text(encoding='utf-8')
        self.assertIn("'image-seo': '图片 SEO'", state_script)
        content_line = next(line for line in state_script.splitlines() if "key: 'content'" in line)
        overview_line = next(line for line in state_script.splitlines() if "key: 'overview'" in line)
        self.assertIn("{ type: 'view', key: 'image-seo' }", content_line)
        self.assertNotIn("image-seo", overview_line)

    def test_image_seo_editor_exposes_field_guides_and_action_details(self):
        script = (Path(__file__).resolve().parents[1] / 'admin' / 'js' / 'legacy-admin.js').read_text(encoding='utf-8')
        html = (Path(__file__).resolve().parents[1] / 'admin' / 'index.html').read_text(encoding='utf-8')
        for topic in ('owner', 'alt', 'title', 'caption', 'save', 'ignore', 'scan'):
            self.assertIn(f"showImageSeoHelp('{topic}')", script + html)
        self.assertNotIn('generateImageSeoDrafts()">生成 Alt 草稿', html)
        self.assertIn('Alt 替代文本', script)
        self.assertIn('图片标题（可选）', script)
        self.assertIn('图片说明（可选）', script)
        self.assertIn('image-seo-hover-help', script + html)
        self.assertIn('data-help=', script + html)
        self.assertNotIn('<i class="fas fa-circle-info"></i> 详情', html)

    def test_image_thumbnails_open_large_preview(self):
        script = (Path(__file__).resolve().parents[1] / 'admin' / 'js' / 'legacy-admin.js').read_text(encoding='utf-8')
        self.assertIn("onclick=\"previewImageSeo('", script)
        self.assertIn('function previewImageSeo(imageUrl)', script)
        self.assertIn('图片 SEO 大图预览', script)

    def test_csv_export_uses_chinese_round_trip_headers(self):
        self.assertIn("'资产编号', '图片显示', '图片地址'", (Path(__file__).resolve().parents[1] / 'app' / 'routes' / 'image_seo.py').read_text(encoding='utf-8'))
        html = (Path(__file__).resolve().parents[1] / 'admin' / 'index.html').read_text(encoding='utf-8')
        script = (Path(__file__).resolve().parents[1] / 'admin' / 'js' / 'legacy-admin.js').read_text(encoding='utf-8')
        self.assertIn('上传覆盖 Excel', html)
        self.assertIn('/api/admin/image-seo/import-csv', script)
        self.assertIn('导出 Excel', html)
        self.assertIn('/api/admin/image-seo/report.xlsx', script)
        self.assertIn('waitSeconds: 3', script)
        self.assertIn('慎重：上传覆盖图片 SEO Excel', script)

    def test_csv_export_contains_chinese_role_and_issue_values(self):
        scan_image_assets(persist=True)
        response = self.client.get('/api/admin/image-seo/report.csv')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('资产编号,图片显示,图片地址', body)
        self.assertIn('产品详情图', body)
        self.assertIn('泛化 Alt', body)


if __name__ == '__main__':
    unittest.main()
