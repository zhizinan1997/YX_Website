from __future__ import annotations

import json
import tempfile
import unittest
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, session

from app.routes.home_content import (
    build_hero_api_payload,
    get_hero_config,
    register_home_content_routes,
    save_hero_config,
)
from app.upload_utils import validate_uploaded_image_extension, validate_uploaded_video_extension


def _sanitize_url(value, *, enforce_remote_public=False):
    text = str(value or "").strip()
    if enforce_remote_public and not (text.startswith("https://") or text.startswith("http://") or text.startswith("/")):
        return ""
    return text


class HomeHeroConfigTests(unittest.TestCase):
    def test_default_cta_buttons_visible_is_true(self):
        with tempfile.TemporaryDirectory() as td:
            hero_file = Path(td) / "hero.json"

            config = get_hero_config(hero_file, _sanitize_url)

            self.assertTrue(config["cta_buttons_visible"])

    def test_save_and_payload_preserve_cta_buttons_visibility(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hero_file = root / "hero.json"
            manifest_file = root / "manifest.json"
            manifest_file.write_text(json.dumps({"items": {}}), encoding="utf-8")

            saved = save_hero_config(
                {
                    "interval_seconds": 7,
                    "cta_buttons_visible": False,
                    "items": [
                        {
                            "id": "hero-1",
                            "type": "image",
                            "url": "/media/hero/example.jpg",
                            "mobile_url": "/media/hero/example-mobile.jpg",
                            "source": "upload",
                        }
                    ],
                },
                hero_config_file=hero_file,
                sanitize_public_media_url=_sanitize_url,
            )

            self.assertFalse(saved["cta_buttons_visible"])
            self.assertEqual(saved["items"][0]["mobile_url"], "/media/hero/example-mobile.jpg")
            payload = build_hero_api_payload(
                hero_config_file=hero_file,
                sanitize_public_media_url=_sanitize_url,
                hero_derived_manifest_file=manifest_file,
                pil_support=False,
                image_module=None,
                image_ops_module=None,
                pil_features=None,
                hero_uploads_dir=root,
                hero_derived_dir=root,
                hero_source_image_extensions={"jpg", "jpeg", "png"},
                hero_derived_widths=(960,),
                hero_derived_formats=("webp",),
            )

            self.assertEqual(payload["interval_seconds"], 7)
            self.assertFalse(payload["cta_buttons_visible"])
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["mobile_fallback"], "/media/hero/example-mobile.jpg")


class HomeHeroMobileImageRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hero_file = self.root / "hero.json"
        self.hero_uploads = self.root / "uploads"
        self.hero_derived = self.root / "derived"
        self.hero_uploads.mkdir()
        self.hero_derived.mkdir()
        self.manifest_file = self.hero_derived / "manifest.json"
        self.manifest_file.write_text(json.dumps({"version": 1, "items": {}}), encoding="utf-8")

        app = Flask(__name__)
        app.secret_key = "test-secret"

        def login_required(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not session.get("admin_logged_in"):
                    return jsonify({"success": False}), 401
                return fn(*args, **kwargs)
            return wrapper

        register_home_content_routes(
            app,
            login_required=login_required,
            cached_json_response=lambda payload: jsonify(payload),
            sanitize_public_media_url=_sanitize_url,
            validate_uploaded_video_extension=validate_uploaded_video_extension,
            validate_uploaded_image_extension=validate_uploaded_image_extension,
            allowed_partner_extensions={".png"},
            hero_config_file=self.hero_file,
            hero_uploads_dir=self.hero_uploads,
            hero_derived_dir=self.hero_derived,
            hero_derived_manifest_file=self.manifest_file,
            hero_source_image_extensions={".webp", ".png", ".jpg", ".jpeg"},
            hero_derived_widths=(768,),
            hero_derived_formats=("webp",),
            h2_home_video_uploads_dir=self.root,
            partners_config_file=self.root / "partners.json",
            partners_uploads_dir=self.root,
            home_section_visibility_file=self.root / "visibility.json",
            allowed_hero_extensions={".webp", ".png", ".jpg", ".jpeg", ".mp4"},
            media_immutable_cache_control="public, max-age=31536000",
            pil_support=False,
            image_module=None,
            image_ops_module=None,
            pil_features=None,
        )
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def webp_file(name="mobile.webp"):
        content = b"RIFF" + (12).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 8
        return BytesIO(content), name

    def write_items(self, items):
        self.hero_file.write_text(
            json.dumps({"interval_seconds": 5, "cta_buttons_visible": True, "items": items}),
            encoding="utf-8",
        )

    def test_upload_replace_and_delete_mobile_image(self):
        (self.hero_uploads / "desktop.jpg").write_bytes(b"desktop")
        self.write_items([{
            "id": "image-1", "type": "image", "url": "/media/hero/desktop.jpg", "source": "upload"
        }])

        first = self.client.post(
            "/api/hero/items/image-1/mobile-image",
            data={"file": self.webp_file()},
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 200)
        first_url = first.get_json()["item"]["mobile_url"]
        first_path = self.hero_uploads / first_url.replace("/media/hero/", "")
        self.assertTrue(first_path.exists())

        second = self.client.post(
            "/api/hero/items/image-1/mobile-image",
            data={"file": self.webp_file("replacement.webp")},
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 200)
        second_url = second.get_json()["item"]["mobile_url"]
        self.assertNotEqual(first_url, second_url)
        self.assertFalse(first_path.exists())

        deleted = self.client.delete("/api/hero/items/image-1/mobile-image")
        self.assertEqual(deleted.status_code, 200)
        config = get_hero_config(self.hero_file, _sanitize_url)
        self.assertNotIn("mobile_url", config["items"][0])
        self.assertFalse((self.hero_uploads / second_url.replace("/media/hero/", "")).exists())

        third = self.client.post(
            "/api/hero/items/image-1/mobile-image",
            data={"file": self.webp_file("third.webp")},
            content_type="multipart/form-data",
        )
        third_url = third.get_json()["item"]["mobile_url"]
        removed_item = self.client.delete("/api/hero/items/image-1")
        self.assertEqual(removed_item.status_code, 200)
        self.assertFalse((self.hero_uploads / "desktop.jpg").exists())
        self.assertFalse((self.hero_uploads / third_url.replace("/media/hero/", "")).exists())

    def test_video_item_rejects_mobile_image(self):
        self.write_items([{
            "id": "video-1", "type": "video", "url": "/media/hero/video.mp4", "source": "upload"
        }])
        response = self.client.post(
            "/api/hero/items/video-1/mobile-image",
            data={"file": self.webp_file()},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("只有图片", response.get_json()["message"])

    def test_invalid_file_and_missing_item_are_rejected(self):
        self.write_items([{
            "id": "image-1", "type": "image", "url": "/media/hero/desktop.jpg", "source": "upload"
        }])
        invalid = self.client.post(
            "/api/hero/items/image-1/mobile-image",
            data={"file": (BytesIO(b"not an image"), "fake.webp")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 400)

        missing = self.client.post(
            "/api/hero/items/missing/mobile-image",
            data={"file": self.webp_file()},
            content_type="multipart/form-data",
        )
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
