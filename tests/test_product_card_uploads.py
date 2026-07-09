from __future__ import annotations

import tempfile
import unittest
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, session

from app.routes.product_settings import register_product_settings_routes
from app.upload_utils import validate_uploaded_image_extension


class ProductCardUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.legacy_uploads = self.root / "data" / "product_cards" / "uploads"
        self.legacy_uploads.mkdir(parents=True)
        self.cdn_assets = self.root / "cdn_assets"

        app = Flask(__name__)
        app.secret_key = "test-secret"

        def login_required(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not session.get("admin_logged_in"):
                    return jsonify({"success": False, "message": "login required"}), 401
                return fn(*args, **kwargs)

            return wrapper

        register_product_settings_routes(
            app,
            login_required=login_required,
            data_dir=self.root / "data",
            sanitize_public_product_settings=lambda value: value if isinstance(value, dict) else {},
            sanitize_public_text=lambda value, **_kwargs: str(value or ""),
            sanitize_public_media_url=lambda value, **_kwargs: str(value or ""),
            sanitize_public_link_url=lambda value, **_kwargs: str(value or ""),
            get_products_with_settings_data=lambda: [],
            get_biosensing_products_with_settings_data=lambda: [],
            product_card_uploads_dir=self.legacy_uploads,
            cdn_assets_dir=self.cdn_assets,
            allowed_product_card_extensions={".png", ".jpg", ".jpeg", ".webp"},
            validate_uploaded_image_extension=validate_uploaded_image_extension,
        )

        self.app = app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True

    def tearDown(self):
        self.tmp.cleanup()

    def test_product_card_uploads_go_to_matching_cdn_folder(self):
        gas_response = self.client.post(
            "/api/products/card-image/upload",
            data={"file": (BytesIO(b"\x89PNG\r\n\x1a\ngas"), "gas.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(gas_response.status_code, 200)
        gas_data = gas_response.get_json()
        self.assertTrue(gas_data["url"].startswith("/cdn_assets/images/gassensing/"))
        self.assertEqual(gas_data["folder"], "images/gassensing")
        self.assertTrue((self.cdn_assets / gas_data["url"].replace("/cdn_assets/", "")).exists())

        bio_response = self.client.post(
            "/api/bio-products/card-image/upload",
            data={"file": (BytesIO(b"\x89PNG\r\n\x1a\nbio"), "bio.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(bio_response.status_code, 200)
        bio_data = bio_response.get_json()
        self.assertTrue(bio_data["url"].startswith("/cdn_assets/images/biosensing/"))
        self.assertEqual(bio_data["folder"], "images/biosensing")
        self.assertTrue((self.cdn_assets / bio_data["url"].replace("/cdn_assets/", "")).exists())

        self.assertEqual(list(self.legacy_uploads.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
