from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from flask import Flask

from app.routes import ai_chatbot as chatbot
from app.routes import contact_messages
from app.routes import promotion_links


class FakePdfPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf2:
    class PdfReader:
        def __init__(self, fh):
            raw = fh.read()
            self.pages = [FakePdfPage(raw.decode("utf-8", errors="ignore"))]


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge_dir = self.root / "knowledge"
        self.knowledge_dir.mkdir()
        chatbot.reset_knowledge_cache()
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"
        chatbot.register_ai_chatbot_routes(
            self.app,
            login_required=lambda f: f,
            get_config=lambda: {},
            update_config=lambda updates: None,
            require_super_admin_api=lambda: None,
            get_client_ip=lambda: "127.0.0.1",
            resolve_ip_location=lambda _ip: "unknown",
            sanitize_public_link_url=lambda url: url,
            validate_uploaded_pdf=lambda _file: True,
            knowledge_dir=self.knowledge_dir,
            conversation_log_file=self.root / "chatbot_logs.jsonl",
            pdf_support=True,
            pypdf2_module=FakePdf2,
            requests_support=False,
            requests_module=None,
            httpx_support=False,
            httpx_module=None,
            get_gassensing_products_with_settings=lambda: [],
            get_biosensing_products_with_settings_data=lambda: [],
        )
        self.client = self.app.test_client()
        self._login()

    def tearDown(self):
        chatbot.reset_knowledge_cache()
        self.tmp.cleanup()

    def _login(self, *, super_admin=True, permissions=None):
        with self.client.session_transaction() as sess:
            sess["admin_logged_in"] = True
            sess["admin_is_super_admin"] = super_admin
            sess["admin_permissions"] = permissions if permissions is not None else ["chatbot"]

    def _post_pdf(self, name: str, payload: bytes = b"%PDF-1.4 test"):
        return self.client.post(
            "/api/chatbot/knowledge/upload",
            data={"files": (io.BytesIO(payload), name)},
            content_type="multipart/form-data",
        )

    def test_text_only_upload_creates_incremental_entry(self):
        response = self.client.post(
            "/api/chatbot/knowledge/upload",
            data={"knowledge_text": "alpha knowledge"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["text_saved"])

        listing = self.client.get("/api/chatbot/knowledge").get_json()
        self.assertEqual(len(listing["text_entries"]), 1)
        self.assertIn("alpha knowledge", listing["text_content"])
        self.assertIn("alpha knowledge", chatbot.load_knowledge_base())

    def test_pdf_only_upload_keeps_existing_text_entries(self):
        self.client.post(
            "/api/chatbot/knowledge/upload",
            data={"knowledge_text": "existing text"},
        )

        response = self._post_pdf("doc.pdf", b"%PDF-1.4 pdf text")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["uploaded"], ["doc.pdf"])

        listing = self.client.get("/api/chatbot/knowledge").get_json()
        self.assertEqual(len(listing["text_entries"]), 1)
        self.assertEqual(len(listing["files"]), 1)
        self.assertIn("existing text", listing["text_content"])

    def test_text_and_pdf_upload_together(self):
        response = self.client.post(
            "/api/chatbot/knowledge/upload",
            data={
                "knowledge_text": "combo text",
                "files": (io.BytesIO(b"%PDF-1.4 combo pdf"), "combo.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["text_saved"])
        self.assertEqual(data["uploaded"], ["combo.pdf"])

        listing = self.client.get("/api/chatbot/knowledge").get_json()
        self.assertEqual(len(listing["text_entries"]), 1)
        self.assertEqual(len(listing["files"]), 1)

    def test_text_entry_get_update_delete(self):
        created = self.client.post(
            "/api/chatbot/knowledge/upload",
            data={"knowledge_text": "draft text"},
        ).get_json()["text_entry"]
        entry_id = created["id"]

        detail = self.client.get(f"/api/chatbot/knowledge/text/{entry_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["entry"]["content"], "draft text")

        updated = self.client.put(
            f"/api/chatbot/knowledge/text/{entry_id}",
            json={"title": "Updated title", "content": "updated text"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["entry"]["title"], "Updated title")
        self.assertIn("updated text", chatbot.load_knowledge_base())

        deleted = self.client.delete(f"/api/chatbot/knowledge/text/{entry_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn("updated text", chatbot.load_knowledge_base())
        self.assertEqual(
            self.client.get(f"/api/chatbot/knowledge/text/{entry_id}").status_code,
            404,
        )

    def test_legacy_manual_text_migrates_once_and_can_be_deleted(self):
        legacy_path = self.knowledge_dir / chatbot.MANUAL_KNOWLEDGE_FILENAME
        legacy_path.write_text("legacy manual text", encoding="utf-8")

        listing = self.client.get("/api/chatbot/knowledge").get_json()
        self.assertEqual(len(listing["text_entries"]), 1)
        self.assertEqual(listing["text_entries"][0]["content"], "legacy manual text")
        self.assertTrue(legacy_path.exists())

        entry_id = listing["text_entries"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/chatbot/knowledge/text/{entry_id}").status_code, 200)
        listing_after_delete = self.client.get("/api/chatbot/knowledge").get_json()
        self.assertEqual(listing_after_delete["text_entries"], [])
        self.assertTrue(legacy_path.exists())
        self.assertNotIn("legacy manual text", chatbot.load_knowledge_base())

    def test_duplicate_pdf_upload_uses_unique_filename(self):
        first = self._post_pdf("same.pdf", b"%PDF-1.4 first")
        second = self._post_pdf("same.pdf", b"%PDF-1.4 second")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        listing = self.client.get("/api/chatbot/knowledge").get_json()
        names = sorted(file["name"] for file in listing["files"])
        self.assertEqual(names, ["same.pdf", "same_2.pdf"])
        self.assertEqual((self.knowledge_dir / "same.pdf").read_bytes(), b"%PDF-1.4 first")
        self.assertEqual((self.knowledge_dir / "same_2.pdf").read_bytes(), b"%PDF-1.4 second")

    def test_pdf_view_download_delete_validate_path_and_permission(self):
        self._post_pdf("sample.pdf", b"%PDF-1.4 sample")

        view = self.client.get("/api/chatbot/knowledge/sample.pdf/view")
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view.mimetype, "application/pdf")
        view.close()

        download = self.client.get("/api/chatbot/knowledge/sample.pdf/download")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers.get("Content-Disposition", ""))
        download.close()

        self.assertEqual(
            self.client.get("/api/chatbot/knowledge/..evil.pdf/view").status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/chatbot/knowledge/..evil.pdf/download").status_code,
            400,
        )
        self.assertEqual(
            self.client.delete("/api/chatbot/knowledge/..evil.pdf").status_code,
            400,
        )

        self._login(super_admin=False, permissions=[])
        self.assertEqual(
            self.client.get("/api/chatbot/knowledge/sample.pdf/view").status_code,
            403,
        )

        self._login()
        self.assertEqual(self.client.delete("/api/chatbot/knowledge/sample.pdf").status_code, 200)
        self.assertEqual(
            self.client.get("/api/chatbot/knowledge/sample.pdf/download").status_code,
            404,
        )


class ContactAttributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.links_file = Path(self.tmp.name) / "promotion_links.json"
        self._old_links_file = promotion_links.PROMOTION_LINKS_FILE
        promotion_links.PROMOTION_LINKS_FILE = self.links_file
        self.addCleanup(setattr, promotion_links, "PROMOTION_LINKS_FILE", self._old_links_file)

    def _write_links(self, items):
        self.links_file.write_text(
            json.dumps({"version": 1, "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _cookie(self, mark: str, source: str = "wechat", medium: str = "article") -> str:
        payload = {
            "first_touch": {
                "utm": {"source": source, "medium": medium, "campaign": "hydrogen", "id": mark},
                "promotion_mark": mark,
                "landing_page": "/?utm_id=" + mark,
            },
            "last_touch": {
                "utm": {"source": source, "medium": medium, "campaign": "hydrogen", "id": mark},
                "promotion_mark": mark,
                "landing_page": "/pages/gassensing/mc_ld_r1.html",
            },
        }
        return quote(json.dumps(payload, separators=(",", ":")))

    def _extract(self, mark: str, source: str = "wechat", medium: str = "article") -> dict:
        app = Flask(__name__)
        cookie = self._cookie(mark, source=source, medium=medium)
        with app.test_request_context(headers={"Cookie": f"yx_site_attribution={cookie}"}):
            return contact_messages._extract_request_attribution({})

    def test_extract_request_attribution_from_cookie(self):
        self._write_links([
            {"name": "微信文章", "promotion_mark": "wechat-article-a", "archived_at": ""},
        ])
        attr = self._extract("wechat-article-a")
        self.assertEqual(attr["last_touch"]["utm_source"], "wechat")
        self.assertEqual(attr["last_touch"]["promotion_mark"], "wechat-article-a")

    def test_archived_promotion_mark_is_dropped(self):
        self._write_links([
            {"name": "pku", "promotion_mark": "pku-promotion", "archived_at": "2026-07-09T17:04:04+08:00"},
        ])
        attr = self._extract("pku-promotion", source="pku")
        self.assertEqual(attr["last_touch"]["utm_source"], "pku")
        self.assertEqual(attr["last_touch"]["promotion_mark"], "")
        self.assertEqual(attr["last_touch"]["utm_id"], "")


if __name__ == "__main__":
    unittest.main()
