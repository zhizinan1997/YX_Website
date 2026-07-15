from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from app.routes.admin import _load_login_attempts
from app.routes.navigation_content import register_navigation_content_routes


class CleanupRegressionTests(unittest.TestCase):
    def test_malformed_login_attempts_json_falls_back_to_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts_file = Path(tmp) / "admin_login_attempts.json"
            attempts_file.write_text('{"ips":', encoding="utf-8")

            self.assertEqual(_load_login_attempts(attempts_file), {"ips": {}})

    def test_measurement_targets_has_one_get_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            app = Flask(__name__)

            register_navigation_content_routes(
                app,
                login_required=lambda func: func,
                app_root=root,
                data_dir=data_dir,
                normalize_scanned_image_path=lambda image, _prefix: image,
                extract_solution_meta_from_html=lambda _path: None,
                extract_case_meta_from_html=lambda _path: None,
                extract_product_meta_from_html=lambda _path: None,
            )

            get_rules = [
                rule
                for rule in app.url_map.iter_rules()
                if rule.rule == "/api/measurement-targets" and "GET" in rule.methods
            ]
            self.assertEqual(len(get_rules), 1)

    def test_navigation_apis_emit_canonical_final_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / 'recommendations.json').write_text(json.dumps({
                'latestReleases': [{'name': '首页', 'url': '/index.html'}],
                'applicationAreas': [{'name': '科研服务', 'url': '/pages/research/index.html'}],
            }, ensure_ascii=False), encoding='utf-8')
            (data_dir / 'measurement_targets.json').write_text(json.dumps({
                'items': [{'name': '科研服务', 'url': '../research/index.html'}],
            }, ensure_ascii=False), encoding='utf-8')
            app = Flask('canonical_navigation_test')
            register_navigation_content_routes(
                app,
                login_required=lambda func: func,
                app_root=root,
                data_dir=data_dir,
                normalize_scanned_image_path=lambda image, _prefix: image,
                extract_solution_meta_from_html=lambda _path: None,
                extract_case_meta_from_html=lambda _path: None,
                extract_product_meta_from_html=lambda _path: None,
            )
            client = app.test_client()
            recommendations = client.get('/api/recommendations').get_json()
            measurements = client.get('/api/measurement-targets').get_json()
            self.assertEqual(recommendations['latestReleases'][0]['url'], '/')
            self.assertEqual(recommendations['applicationAreas'][0]['url'], '/pages/research/')
            self.assertEqual(measurements['items'][0]['url'], '/pages/research/')


if __name__ == "__main__":
    unittest.main()
