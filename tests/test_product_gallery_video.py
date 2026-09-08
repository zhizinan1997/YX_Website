from __future__ import annotations

import tempfile
import unittest
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, session

from app.routes import product_editor as pe
from app.routes.product_settings import (
    ALLOWED_PRODUCT_GALLERY_VIDEO_EXTENSIONS,
    MAX_PRODUCT_GALLERY_VIDEO_BYTES,
    register_product_settings_routes,
)
from app.upload_utils import validate_uploaded_image_extension, validate_uploaded_video_extension


GALLERY_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>测试产品 - 元芯传感</title>
</head>
<body>
<main>
    <section class="vs-product-hero">
        <div class="vs-container">
            <div class="vs-product-gallery">
                <div class="vs-gallery-main"><img id="mainImage" src="/old.png" alt="测试产品"></div>
                <div class="vs-gallery-thumbs">
                    <div class="vs-gallery-thumb active" onclick="changeImage(this, '/old.png')">
                        <img src="/old.png" alt="产品图1">
                    </div>
                </div>
            </div>
            <h1>测试产品</h1>
        </div>
    </section>
</main>
<script>
    function changeImage(thumb, src) {
        document.getElementById('mainImage').src = src;
    }
    function prevImage() { switchImageByOffset(-1); }
</script>
</body>
</html>
"""

MP4_SAMPLE = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
WEBM_SAMPLE = b"\x1aE\xdf\xa3" + b"0" * 64


def _build_upload_app(root: Path) -> Flask:
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
        data_dir=root / "data",
        sanitize_public_product_settings=lambda value: value if isinstance(value, dict) else {},
        sanitize_public_text=lambda value, **_kwargs: str(value or ""),
        sanitize_public_media_url=lambda value, **_kwargs: str(value or ""),
        sanitize_public_link_url=lambda value, **_kwargs: str(value or ""),
        get_products_with_settings_data=lambda: [],
        get_biosensing_products_with_settings_data=lambda: [],
        product_card_uploads_dir=root / "data" / "product_cards" / "uploads",
        cdn_assets_dir=root / "cdn_assets",
        allowed_product_card_extensions={".png", ".jpg", ".jpeg", ".webp"},
        validate_uploaded_image_extension=validate_uploaded_image_extension,
        validate_uploaded_video_extension=validate_uploaded_video_extension,
    )
    return app


class ProductGalleryVideoUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = _build_upload_app(self.root)
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True

    def tearDown(self):
        self.tmp.cleanup()

    def test_gas_gallery_video_upload(self):
        response = self.client.post(
            "/api/products/gallery-media/upload",
            data={"file": (BytesIO(MP4_SAMPLE), "demo-video.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["url"].startswith("/cdn_assets/videos/gassensing/"))
        self.assertTrue(data["url"].endswith(".mp4"))
        self.assertEqual(data["mediaType"], "video")
        self.assertTrue((self.root / "cdn_assets" / data["url"].replace("/cdn_assets/", "")).exists())

    def test_bio_gallery_video_upload(self):
        response = self.client.post(
            "/api/bio-products/gallery-media/upload",
            data={"file": (BytesIO(WEBM_SAMPLE), "demo-video.webm")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["url"].startswith("/cdn_assets/videos/biosensing/"))
        self.assertTrue((self.root / "cdn_assets" / data["url"].replace("/cdn_assets/", "")).exists())

    def test_gallery_video_upload_rejects_non_video_file(self):
        response = self.client.post(
            "/api/products/gallery-media/upload",
            data={"file": (BytesIO(b"\x89PNG\r\n\x1a\nnot-a-video"), "fake.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_gallery_video_upload_rejects_oversized_file(self):
        oversized = BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"0" * (MAX_PRODUCT_GALLERY_VIDEO_BYTES + 1))
        response = self.client.post(
            "/api/products/gallery-media/upload",
            data={"file": (oversized, "big.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("100MB", response.get_json()["message"])

    def test_gallery_video_upload_requires_login(self):
        client = self.app.test_client()
        response = client.post(
            "/api/products/gallery-media/upload",
            data={"file": (BytesIO(MP4_SAMPLE), "demo.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 401)

    def test_allowed_video_extensions_match_frontend_accept(self):
        self.assertEqual(ALLOWED_PRODUCT_GALLERY_VIDEO_EXTENSIONS, {".mp4", ".webm"})


class ProductGalleryVideoPatchTests(unittest.TestCase):
    def test_patch_and_extract_round_trip_with_video(self):
        sections = {
            "images": [
                "/cdn_assets/images/gassensing/p1.png",
                "/cdn_assets/videos/gassensing/p1-demo.mp4",
            ],
        }
        patched = pe.patch_vs_product_sections(GALLERY_PAGE_HTML, sections)

        # 视频缩略图 DOM 结构。
        self.assertIn('class="vs-gallery-thumb vs-gallery-thumb--video"', patched)
        self.assertIn('data-media-type="video"', patched)
        self.assertIn('<video src="/cdn_assets/videos/gassensing/p1-demo.mp4" muted preload="metadata" playsinline></video>', patched)
        self.assertIn('<span class="vs-gallery-thumb__play"', patched)
        # onclick 签名保持，保证 extract 兼容。
        self.assertIn('onclick="changeImage(this, this.dataset.imageSrc)"', patched)
        # 主图仍指向第一张图片，并注入视频播放器与控制按钮。
        self.assertIn('<img id="mainImage" src="/cdn_assets/images/gassensing/p1.png"', patched)
        self.assertIn('id="mainVideo"', patched)
        self.assertIn("toggleGalleryVideoMute(event)", patched)
        self.assertIn("toggleGalleryVideoFullscreen()", patched)

        extracted = pe.extract_vs_product_sections(patched)
        self.assertEqual(
            extracted["images"],
            [
                "/cdn_assets/images/gassensing/p1.png",
                "/cdn_assets/videos/gassensing/p1-demo.mp4",
            ],
        )

    def test_patch_is_idempotent_for_video_gallery(self):
        sections = {
            "images": [
                "/cdn_assets/videos/gassensing/only-demo.mp4",
                "/cdn_assets/images/gassensing/p1.png",
            ],
        }
        once = pe.patch_vs_product_sections(GALLERY_PAGE_HTML, sections)
        twice = pe.patch_vs_product_sections(once, sections)
        self.assertEqual(once, twice)

    def test_first_video_item_keeps_main_image_element(self):
        sections = {"images": ["/cdn_assets/videos/gassensing/only-demo.mp4"]}
        patched = pe.patch_vs_product_sections(GALLERY_PAGE_HTML, sections)
        # 全视频时不得把 mp4 写入 <img> src。
        self.assertNotIn('<img id="mainImage" src="/cdn_assets/videos/', patched)
        self.assertIn('id="mainVideo"', patched)
        extracted = pe.extract_vs_product_sections(patched)
        self.assertEqual(extracted["images"], ["/cdn_assets/videos/gassensing/only-demo.mp4"])

    def test_legacy_gallery_script_is_upgraded_once(self):
        sections = {"images": ["/cdn_assets/images/gassensing/p1.png"]}
        patched = pe.patch_vs_product_sections(GALLERY_PAGE_HTML, sections)
        self.assertIn("vsGalleryIsVideoUrl", patched)
        self.assertIn("toggleGalleryVideoFullscreen", patched)
        self.assertEqual(patched.count("function changeImage"), 1)
        # 再次修补（无视频场景）不应重复注入脚本。
        again = pe.patch_vs_product_sections(patched, {"title": "测试产品"})
        self.assertEqual(again.count("function changeImage"), 1)
        self.assertIn("vsGalleryIsVideoUrl", again)

    def test_image_only_gallery_keeps_legacy_dom_shape(self):
        sections = {"images": ["/cdn_assets/images/gassensing/p1.png"]}
        patched = pe.patch_vs_product_sections(GALLERY_PAGE_HTML, sections)
        self.assertNotIn("vs-gallery-thumb--video", patched)
        self.assertIn('data-image-src="/cdn_assets/images/gassensing/p1.png"', patched)
        extracted = pe.extract_vs_product_sections(patched)
        self.assertEqual(extracted["images"], ["/cdn_assets/images/gassensing/p1.png"])

    def test_video_thumb_fallback_extraction(self):
        # 无 onclick 的病态页面也能从 <video src> 提取。
        html = GALLERY_PAGE_HTML.replace(
            'onclick="changeImage(this, \'/old.png\')"', 'data-broken="1"'
        ).replace('<img src="/old.png" alt="产品图1">', '<video src="/cdn_assets/videos/gassensing/x.mp4" muted></video>')
        extracted = pe.extract_vs_product_sections(html)
        self.assertEqual(extracted["images"], ["/cdn_assets/videos/gassensing/x.mp4"])

    def test_sanitize_keeps_cdn_video_url(self):
        safe = pe._sanitize_product_media_url("/cdn_assets/videos/gassensing/p1-demo.mp4")
        self.assertEqual(safe, "/cdn_assets/videos/gassensing/p1-demo.mp4")

    def test_is_product_gallery_video_url(self):
        self.assertTrue(pe._is_product_gallery_video_url("/cdn_assets/videos/a.mp4"))
        self.assertTrue(pe._is_product_gallery_video_url("/cdn_assets/videos/a.webm?v=123"))
        self.assertFalse(pe._is_product_gallery_video_url("/cdn_assets/images/a.png"))
        self.assertFalse(pe._is_product_gallery_video_url("/cdn_assets/videos/a.mov"))


if __name__ == "__main__":
    unittest.main()
