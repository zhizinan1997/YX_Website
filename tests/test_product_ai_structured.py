from __future__ import annotations

import json
import tempfile
import unittest
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, session

from app.routes import product_editor as pe


REFERENCE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>旧产品 - 元芯传感</title>
</head>
<body>
<main>
    <section class="vs-product-hero">
        <div class="vs-container">
            <div class="vs-product-gallery">
                <div class="vs-gallery-main"><img id="mainImage" src="/old.png" alt="旧产品"></div>
                <div class="vs-gallery-thumbs">
                    <div class="vs-gallery-thumb active" onclick="changeImage(this, '/old.png')">
                        <img src="/old.png" alt="产品图1">
                    </div>
                </div>
            </div>
            <div class="vs-product-hero__content">
                <h1>旧产品</h1>
                <p class="vs-product-hero__desc">旧描述</p>
                <ul class="vs-feature-list">
                    <li>旧亮点</li>
                </ul>
            </div>
        </div>
    </section>
    <section class="vs-product-section">
        <div class="vs-container">
            <h2 class="vs-product-section__title">产品详情</h2>
            <div class="vs-product-section__content">
                <p>旧详情</p>
            </div>
        </div>
    </section>
    <section class="vs-product-section alt-bg">
        <div class="vs-container">
            <h2 class="vs-product-section__title">产品优势</h2>
            <div class="vs-advantages-grid">
                <div class="vs-advantage-card">
                    <i class="fas fa-check-circle"></i>
                    <h4>旧优势</h4>
                    <p>旧优势描述</p>
                </div>
            </div>
        </div>
    </section>
    <section class="vs-product-section">
        <div class="vs-container">
            <h2 class="vs-product-section__title">主要应用</h2>
            <div class="vs-product-section__content vs-applications-intro">旧应用介绍</div>
            <div class="vs-application-highlights">
                <article class="vs-application-highlight">
                    <div class="vs-application-content">
                        <div class="vs-application-content__head">
                            <i class="fas fa-industry"></i>
                            <h4>旧应用</h4>
                        </div>
                        <p>旧应用描述</p>
                        <div class="vs-application-scenarios">旧场景</div>
                    </div>
                </article>
            </div>
        </div>
    </section>
    <section class="vs-product-section alt-bg">
        <div class="vs-container">
            <h2 class="vs-product-section__title">技术指标</h2>
            <table class="vs-specs-table">
                <tr><td>旧参数</td><td>旧值</td></tr>
            </table>
        </div>
    </section>
    <section class="vs-related-news">
        <div class="vs-container">
            <h2>相关新闻</h2>
            <div class="vs-news-grid">
                <a href="#" class="vs-news-item">
                    <img src="/old-news.png" alt="新闻图片">
                    <div class="vs-news-item__content"><h4>旧新闻</h4><p>旧新闻描述</p></div>
                </a>
            </div>
        </div>
    </section>
    <section class="vs-related-products">
        <div class="vs-container">
            <h2>相关产品</h2>
            <div class="vs-related-grid">
                <a href="#" class="vs-related-item">
                    <img src="/old-related.png" alt="旧相关">
                    <h4>旧相关</h4>
                </a>
            </div>
        </div>
    </section>
    <section class="vs-cta-section">
        <div class="vs-container">
            <h3>旧 CTA</h3>
            <p>旧 CTA 描述</p>
        </div>
    </section>
</main>
</body>
</html>
"""


def _write_reference_pages(root: Path) -> None:
    (root / "pages" / "gassensing").mkdir(parents=True)
    (root / "pages" / "biosensing").mkdir(parents=True)
    (root / "templates").mkdir(parents=True)
    (root / "pages" / "gassensing" / "mc_ld_h2.html").write_text(REFERENCE_HTML, encoding="utf-8")
    (root / "pages" / "biosensing" / "blood_potassium_chip.html").write_text(REFERENCE_HTML, encoding="utf-8")
    (root / "templates" / "gassensing-product-template.html").write_text(REFERENCE_HTML, encoding="utf-8")


class ProductAiStructuredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_reference_pages(self.root)
        self.ai_response = "{}"
        self._original_call = pe.call_openai_api_sync_with_custom_config

        def fake_ai_call(_messages, _config):
            return self.ai_response, None

        pe.call_openai_api_sync_with_custom_config = fake_ai_call

        app = Flask(__name__)
        app.secret_key = "test-secret"

        def login_required(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not session.get("admin_logged_in"):
                    return jsonify({"success": False, "message": "login required"}), 401
                return fn(*args, **kwargs)

            return wrapper

        def require_super_admin_api():
            if not session.get("admin_is_super_admin"):
                return jsonify({"success": False, "message": "super admin required"}), 403
            return None

        def normalize_test_ai_image_extension(filename, mime, sample):
            name = str(filename or "").lower()
            clean_mime = str(mime or "").split(";")[0].strip().lower()
            sample_lower = (sample or b"").lower()
            if name.endswith(".svg") or clean_mime == "image/svg+xml":
                return ""
            if name.endswith(".png") or clean_mime == "image/png" or (sample or b"").startswith(b"\x89PNG\r\n\x1a\n"):
                return ".png"
            if b"<svg" in sample_lower:
                return ""
            return ""

        def infer_test_ai_image_extension_from_mime(mime):
            return ".png" if str(mime or "").split(";")[0].strip().lower() == "image/png" else ""

        pe.register_product_editor_routes(
            app,
            login_required=login_required,
            app_root=self.root,
            require_super_admin_api=require_super_admin_api,
            render_markdown=lambda text: text,
            get_product_page_ai_config=lambda: {
                "enabled": True,
                "api_key": "test-key",
                "api_base": "https://api.example.com/v1",
                "model": "test-model",
            },
            get_product_page_ai_system_prompt=lambda: "You write structured JSON.",
            get_product_settings=lambda: {},
            save_product_settings=lambda _settings: None,
            product_featured_file=self.root / "data" / "product_featured.json",
            excluded_product_files=set(),
            hydrogen_solutions_config_file=self.root / "data" / "hydrogen_solutions_config.json",
            get_hydrogen_solution_products_config=lambda: {},
            save_hydrogen_solution_products_config=lambda _config: None,
            default_product_categories={},
            normalize_ai_product_image_extension=normalize_test_ai_image_extension,
            infer_ai_product_image_extension_from_mime=infer_test_ai_image_extension_from_mime,
            allowed_ai_product_image_mime_types={"image/png"},
        )
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        pe.call_openai_api_sync_with_custom_config = self._original_call
        self.tmp.cleanup()

    def _login(self, *, super_admin=True):
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True
            sess["admin_username"] = "admin"
            sess["admin_is_super_admin"] = super_admin

    def _sample_sections(self):
        return {
            "title": "测试氢气检测仪",
            "description": "用于氢气安全检测。",
            "images": ["/assets/test-product.png"],
            "highlights": ["响应快速", "低功耗"],
            "detail": "第一段详情。\n\n第二段详情。",
            "advantages": [{"icon": "fas fa-bolt", "title": "快速响应", "desc": "秒级响应。"}],
            "app_intro": "适用于多类涉氢场景。",
            "applications": [{"icon": "fas fa-industry", "title": "加氢站", "desc": "现场巡检。", "scenario": "加氢站"}],
            "specs": [{"key": "检测范围", "value": "0-1000 ppm"}],
            "news": [{"href": "/pages/news/a.html", "img": "/assets/news.png", "title": "新闻", "desc": "新闻摘要"}],
            "related_products": [{"href": "mc_ld_h2.html", "img": "/assets/related.png", "title": "相关产品"}],
            "cta_title": "获取方案",
            "cta_desc": "联系我们获取支持。",
        }

    def test_draft_crud_family_isolation_and_auth(self):
        self.assertEqual(self.client.get("/api/products/ai-drafts").status_code, 401)
        self._login()

        created = self.client.post("/api/products/ai-drafts", json={
            "slug": "draft_product",
            "title": "草稿产品",
            "source_text": "产品资料",
            "sections": self._sample_sections(),
        })
        self.assertEqual(created.status_code, 200)
        draft = created.get_json()["draft"]
        self.assertEqual(draft["family"], "gas")
        self.assertEqual(draft["updated_by"], "admin")

        gas_list = self.client.get("/api/products/ai-drafts").get_json()
        bio_list = self.client.get("/api/bio-products/ai-drafts").get_json()
        self.assertEqual(gas_list["count"], 1)
        self.assertEqual(bio_list["count"], 0)

        updated = self.client.put(f"/api/products/ai-drafts/{draft['id']}", json={"title": "更新后草稿"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["draft"]["title"], "更新后草稿")

        self.assertEqual(self.client.get("/api/products/ai-drafts/bad").status_code, 400)
        deleted = self.client.delete(f"/api/products/ai-drafts/{draft['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/products/ai-drafts").get_json()["count"], 0)

    def test_render_product_page_from_sections(self):
        self._login()
        page_html, sections = pe.render_product_page_from_sections(
            product_family="gas",
            title="测试氢气检测仪",
            short_name="MC-TEST",
            category="detector",
            image_url="/assets/test-product.png",
            summary="用于氢气安全检测。",
            sections=self._sample_sections(),
            source_text="产品资料",
        )
        self.assertEqual(sections["title"], "测试氢气检测仪")
        self.assertIn('<meta name="product-name" content="测试氢气检测仪"', page_html)
        self.assertIn("0-1000 ppm", page_html)
        self.assertIn("mc_ld_h2.html", page_html)
        self.assertIn("MC_PRODUCT_ADMIN_DATA:", page_html)

    def test_ai_generate_and_revise_sections(self):
        self._login()
        self.ai_response = json.dumps({"sections": self._sample_sections()}, ensure_ascii=False)
        generated = self.client.post("/api/products/ai-generate-sections", json={
            "title": "测试氢气检测仪",
            "short_name": "MC-TEST",
            "category": "detector",
            "image_url": "/assets/test-product.png",
            "summary": "用于氢气安全检测。",
            "context_text": "产品资料",
        })
        self.assertEqual(generated.status_code, 200)
        data = generated.get_json()
        self.assertEqual(data["sections"]["title"], "测试氢气检测仪")
        self.assertIn("测试氢气检测仪", data["page_html"])

        self.ai_response = json.dumps({"patch": {"title": "新标题"}}, ensure_ascii=False)
        revised = self.client.post("/api/products/ai-revise-sections", json={
            "title": "测试氢气检测仪",
            "short_name": "MC-TEST",
            "category": "detector",
            "sections": data["sections"],
            "instruction": "把标题改成新标题",
        })
        self.assertEqual(revised.status_code, 200)
        revised_data = revised.get_json()
        self.assertEqual(revised_data["sections"]["title"], "新标题")
        self.assertEqual(revised_data["sections"]["specs"][0]["value"], "0-1000 ppm")

    def test_create_from_sections_writes_family_paths_and_detects_conflict(self):
        self._login(super_admin=True)
        payload = {
            "title": "测试氢气检测仪",
            "short_name": "MC-TEST",
            "category": "detector",
            "slug": "mc_test_product",
            "summary": "用于氢气安全检测。",
            "image_url": "/assets/test-product.png",
            "sections": self._sample_sections(),
        }
        created = self.client.post("/api/products/ai-create-from-sections", json=payload)
        self.assertEqual(created.status_code, 200)
        self.assertTrue((self.root / "pages" / "gassensing" / "mc_test_product.html").exists())

        duplicate = self.client.post("/api/products/ai-create-from-sections", json=payload)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("更换", duplicate.get_json()["message"])

        too_many_images = self.client.post("/api/products/ai-create-from-sections", json={
            **payload,
            "slug": "mc_test_too_many_images",
            "image_urls": [f"/assets/product-{idx}.png" for idx in range(pe.MAX_AI_PRODUCT_IMAGES + 1)],
        })
        self.assertEqual(too_many_images.status_code, 400)
        self.assertIn("12", too_many_images.get_json()["message"])

        bio_payload = {
            **payload,
            "category": "sensor",
            "slug": "bio_test_product",
        }
        bio_created = self.client.post("/api/bio-products/ai-create-from-sections", json=bio_payload)
        self.assertEqual(bio_created.status_code, 200)
        self.assertTrue((self.root / "pages" / "biosensing" / "bio_test_product.html").exists())

    def test_create_from_sections_rejects_html_mode(self):
        self._login(super_admin=True)
        payload = {
            "title": "测试氢气检测仪",
            "short_name": "MC-TEST",
            "category": "detector",
            "slug": "mc_html_wrong_endpoint",
            "summary": "用于氢气安全检测。",
            "mode": "html",
            "sections": self._sample_sections(),
        }
        response = self.client.post("/api/products/ai-create-from-sections", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("HTML源码模式", response.get_json()["message"])

    def test_create_html_updates_draft_and_writes_same_html_mode(self):
        self._login(super_admin=True)
        created = self.client.post("/api/products/ai-drafts", json={
            "slug": "html_mode_product",
            "title": "HTML 草稿",
            "short_name": "HTML-DRAFT",
            "category": "detector",
            "source_text": "产品资料",
            "sections": self._sample_sections(),
            "mode": "html",
        })
        self.assertEqual(created.status_code, 200)
        draft_id = created.get_json()["draft"]["id"]
        old_marker = pe.encode_product_admin_data({"title": "旧标记"})
        html = f"""<!DOCTYPE html>
<html><head><title>HTML 源码产品</title></head>
<body><main><h1>HTML 源码产品</h1><p>源码模式内容</p></main>{old_marker}</body></html>"""
        response = self.client.post("/api/products/ai-create-html", json={
            "draft_id": draft_id,
            "title": "HTML 源码产品",
            "short_name": "HTML-MODE",
            "category": "detector",
            "slug": "html_mode_product",
            "summary": "源码模式摘要",
            "image_url": "/assets/test-product.png",
            "page_html": html,
            "news_urls": ["/pages/news/a.html"],
            "related_product_urls": ["mc_ld_h2.html"],
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["draft"]["status"], "published")
        self.assertEqual(data["draft"]["mode"], "html")
        self.assertEqual(data["draft"]["published_link"], "/pages/gassensing/html_mode_product.html")
        written = (self.root / "pages" / "gassensing" / "html_mode_product.html").read_text(encoding="utf-8")
        self.assertIn("HTML 源码产品", written)
        self.assertEqual(written.count("MC_PRODUCT_ADMIN_DATA:"), 1)

    def test_create_html_requires_super_admin(self):
        self._login(super_admin=False)
        response = self.client.post("/api/products/ai-create-html", json={
            "title": "HTML 源码产品",
            "short_name": "HTML-MODE",
            "category": "detector",
            "slug": "html_mode_denied",
            "summary": "源码模式摘要",
            "page_html": "<!DOCTYPE html><html><body>Denied</body></html>",
        })
        self.assertEqual(response.status_code, 403)

    def test_ai_upload_images_limits_count_size_and_format(self):
        self._login()
        too_many = {
            "slug": "upload_limit",
            "files": [
                (BytesIO(b"\x89PNG\r\n\x1a\n" + bytes([idx])), f"img{idx}.png")
                for idx in range(pe.MAX_AI_PRODUCT_IMAGES + 1)
            ],
        }
        response = self.client.post("/api/products/ai-upload-images", data=too_many, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("最多上传", response.get_json()["message"])

        oversized = BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (pe.MAX_AI_PRODUCT_IMAGE_BYTES + 1))
        response = self.client.post(
            "/api/products/ai-upload-images",
            data={"slug": "upload_big", "files": [(oversized, "big.png")]},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("不能超过", response.get_json()["message"])

        svg = BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        response = self.client.post(
            "/api/products/ai-upload-images",
            data={"slug": "upload_svg", "files": [(svg, "unsafe.svg")]},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(".svg", response.get_json()["message"])

        disguised_svg = BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        response = self.client.post(
            "/api/products/ai-upload-images",
            data={"slug": "upload_disguised_svg", "files": [(disguised_svg, "disguised.png")]},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("PNG/JPG", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
