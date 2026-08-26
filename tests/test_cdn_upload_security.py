from __future__ import annotations

import tempfile
import unittest
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, session

from app.routes.cdn_assets import (
    MAX_CDN_UPLOAD_BYTES,
    register_cdn_assets_routes,
)
from app.routes.image_seo import configure_image_seo


class CdnUploadSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cdn_dir = self.root / "cdn_assets"
        self.cdn_dir.mkdir()
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        # CDN 上传会同步注册图片 SEO 资产，必须指向临时数据目录，
        # 否则会写入仓库内真实的 data/image_seo_assets.json。
        configure_image_seo(data_dir=self.data_dir)

        app = Flask(__name__)
        app.secret_key = "test-secret"

        def login_required(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not session.get("admin_logged_in"):
                    return jsonify({"success": False, "message": "login required"}), 401
                return fn(*args, **kwargs)

            return wrapper

        register_cdn_assets_routes(
            app,
            cdn_assets_dir=self.cdn_dir,
            site_config_file=self.root / "data" / "site_config.json",
            login_required=login_required,
        )

        self.app = app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True

    def tearDown(self):
        # 恢复全局配置，避免影响同进程内后续测试。
        configure_image_seo(data_dir=Path(__file__).resolve().parents[1] / "data")
        self.tmp.cleanup()

    def test_upload_accepts_image_extension(self):
        response = self.client.post(
            "/api/cdn/assets/upload",
            data={"file": (BytesIO(b"\x89PNG\r\n\x1a\nok"), "ok.png"), "path": ""},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.cdn_dir / response.get_json()["file"]["url"].replace("/cdn_assets/", "")).exists())

    def test_upload_rejects_html_svg_and_script_extensions(self):
        for filename in ("evil.html", "evil.svg", "evil.js", "evil.xml", "evil.xhtml", "noext"):
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/api/cdn/assets/upload",
                    data={"file": (BytesIO(b"<script>alert(1)</script>"), filename), "path": ""},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 400)

    def test_upload_rejects_oversized_file(self):
        payload = BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_CDN_UPLOAD_BYTES + 1))
        response = self.client.post(
            "/api/cdn/assets/upload",
            data={"file": (payload, "big.png"), "path": ""},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)

    def test_unauthenticated_request_is_rejected(self):
        client = self.app.test_client()
        response = client.post(
            "/api/cdn/assets/upload",
            data={"file": (BytesIO(b"x"), "x.png"), "path": ""},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 401)

    def test_registered_endpoints_are_wrapped_by_login_guard(self):
        # 统一鉴权管线必须覆盖全部 CDN 管理端点。
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint.startswith("cdn_assets."):
                view = self.app.view_functions[rule.endpoint]
                self.assertTrue(getattr(view, "__wrapped__", None) is not None, rule.endpoint)


if __name__ == "__main__":
    unittest.main()
