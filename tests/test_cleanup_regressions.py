from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
