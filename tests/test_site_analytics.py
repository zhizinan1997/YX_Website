from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from app.routes import site_analytics as sa


class SiteAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self._old_paths = {
            "log": sa.SITE_ANALYTICS_LOG_FILE,
            "jsonl": sa.SITE_ANALYTICS_AI_REPORTS_FILE,
            "dir": sa.SITE_ANALYTICS_AI_REPORTS_DIR,
            "index": sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE,
            "pdf": sa.SITE_ANALYTICS_AI_REPORTS_PDF_DIR,
            "jobs": sa.SITE_ANALYTICS_AI_JOBS_DIR,
            "gen_lock": sa.SITE_ANALYTICS_AI_GENERATION_LOCK_FILE,
            "pdf_lock": sa.SITE_ANALYTICS_AI_PDF_LOCK_FILE,
        }
        self._old_config = sa._site_report_get_config_fn
        self._old_requests_support = sa._site_report_requests_support
        self._old_requests_module = sa._site_report_requests_module
        self._old_httpx_support = sa._site_report_httpx_support
        self._old_httpx_module = sa._site_report_httpx_module
        self._old_limit = sa.SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self._configure_paths(self.data_dir)

    def tearDown(self):
        self.tmp.cleanup()
        sa.SITE_ANALYTICS_LOG_FILE = self._old_paths["log"]
        sa.SITE_ANALYTICS_AI_REPORTS_FILE = self._old_paths["jsonl"]
        sa.SITE_ANALYTICS_AI_REPORTS_DIR = self._old_paths["dir"]
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = self._old_paths["index"]
        sa.SITE_ANALYTICS_AI_REPORTS_PDF_DIR = self._old_paths["pdf"]
        sa.SITE_ANALYTICS_AI_JOBS_DIR = self._old_paths["jobs"]
        sa.SITE_ANALYTICS_AI_GENERATION_LOCK_FILE = self._old_paths["gen_lock"]
        sa.SITE_ANALYTICS_AI_PDF_LOCK_FILE = self._old_paths["pdf_lock"]
        sa._site_report_get_config_fn = self._old_config
        sa._site_report_requests_support = self._old_requests_support
        sa._site_report_requests_module = self._old_requests_module
        sa._site_report_httpx_support = self._old_httpx_support
        sa._site_report_httpx_module = self._old_httpx_module
        sa.SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT = self._old_limit

    def _configure_paths(self, data_dir: Path):
        sa.SITE_ANALYTICS_LOG_FILE = data_dir / "site_analytics_events.jsonl"
        sa.SITE_ANALYTICS_AI_REPORTS_FILE = data_dir / "site_analytics_ai_reports.jsonl"
        sa.SITE_ANALYTICS_AI_REPORTS_DIR = data_dir / "site_analytics_ai_reports"
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = sa.SITE_ANALYTICS_AI_REPORTS_DIR / "index.json"
        sa.SITE_ANALYTICS_AI_REPORTS_PDF_DIR = sa.SITE_ANALYTICS_AI_REPORTS_DIR / "pdf_cache"
        sa.SITE_ANALYTICS_AI_JOBS_DIR = data_dir / "site_analytics_ai_jobs"
        sa.SITE_ANALYTICS_AI_GENERATION_LOCK_FILE = data_dir / "site_analytics_ai_report_generation.lock"
        sa.SITE_ANALYTICS_AI_PDF_LOCK_FILE = data_dir / "site_analytics_ai_report_pdf.lock"

    def _sample_record(self, report_id: str, *, period="month", created_ts=1):
        return {
            "id": report_id,
            "period": period,
            "period_label": "月报",
            "title": f"Report {report_id}",
            "report": "body",
            "generated_at": "2026-06-01T00:00:00+08:00",
            "created_ts": created_ts,
            "model": "test-model",
            "anchor_date": "2026-06-01",
            "current_range": {"start_date": "2026-06-01", "end_date": "2026-06-01"},
            "previous_range": {"start_date": "2026-05-01", "end_date": "2026-05-01"},
            "comparison": {},
            "current_summary": {},
            "current_detail": {},
        }

    def test_ai_config_uses_whole_group_fallback(self):
        sa._site_report_get_config_fn = lambda: {
            "site_report_ai_api_key": "site-key",
            "site_report_ai_api_base": "",
            "site_report_ai_model": "",
            "product_ai_api_key": "product-key",
            "product_ai_api_base": "https://product.example/v1",
            "product_ai_model": "product-model",
            "chatbot_api_key": "chat-key",
            "chatbot_api_base": "https://chat.example/v1",
            "chatbot_model": "chat-model",
        }
        cfg = sa._site_report_get_ai_config()
        self.assertEqual(cfg["api_key"], "site-key")
        self.assertEqual(cfg["api_base"], "https://api.openai.com/v1")
        self.assertEqual(cfg["model"], "gpt-4o-mini")
        self.assertEqual(cfg["source"], "site_report")

    def test_call_site_report_ai_sends_limits_and_parses_text(self):
        captured = {}

        class Response:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "ok report"}}]}

        class Requests:
            @staticmethod
            def post(url, json, headers, timeout):
                captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
                return Response()

        sa._site_report_get_config_fn = lambda: {
            "chatbot_api_key": "key",
            "chatbot_api_base": "https://api.example/v1",
            "chatbot_model": "model-a",
            "site_report_ai_max_tokens": 1234,
            "site_report_ai_temperature": 0.3,
        }
        sa._site_report_requests_support = True
        sa._site_report_requests_module = Requests
        sa._site_report_httpx_support = False
        result = sa._call_site_report_ai([{"role": "user", "content": "hi"}])
        self.assertEqual(result["text"], "ok report")
        self.assertIsNone(result["error"])
        self.assertEqual(captured["json"]["max_tokens"], 1234)
        self.assertEqual(captured["json"]["temperature"], 0.3)

    def test_invalid_anchor_date_is_rejected(self):
        with self.assertRaises(ValueError):
            sa.build_site_analytics_ai_report_context(period="month", anchor_date="2026-99-99")

    def test_report_store_prunes_and_deletes(self):
        sa.SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT = 2
        sa._append_site_analytics_ai_report_record(self._sample_record("old", created_ts=1))
        sa._append_site_analytics_ai_report_record(self._sample_record("middle", created_ts=2))
        sa._append_site_analytics_ai_report_record(self._sample_record("new", created_ts=3))
        records = sa._iter_site_analytics_ai_report_records()
        self.assertEqual([item["id"] for item in records], ["new", "middle"])
        self.assertFalse(sa._analytics_report_file_path("old").exists())
        self.assertTrue(sa._delete_site_analytics_ai_report_record("middle"))
        self.assertEqual([item["id"] for item in sa._iter_site_analytics_ai_report_records()], ["new"])

    def test_pdf_cache_prevents_regeneration(self):
        calls = {"count": 0}
        old_chromium = sa._generate_site_analytics_ai_report_pdf_chromium
        old_reportlab = sa._generate_site_analytics_ai_report_pdf_reportlab

        def fake_chromium(_record):
            calls["count"] += 1
            return io.BytesIO(b"%PDF-1.4 test")

        try:
            sa._generate_site_analytics_ai_report_pdf_chromium = fake_chromium
            sa._generate_site_analytics_ai_report_pdf_reportlab = lambda _record: io.BytesIO(b"fallback")
            record = self._sample_record("pdf-report")
            first = sa._generate_site_analytics_ai_report_pdf(record).getvalue()
            second = sa._generate_site_analytics_ai_report_pdf(record).getvalue()
            self.assertEqual(first, b"%PDF-1.4 test")
            self.assertEqual(second, b"%PDF-1.4 test")
            self.assertEqual(calls["count"], 1)
        finally:
            sa._generate_site_analytics_ai_report_pdf_chromium = old_chromium
            sa._generate_site_analytics_ai_report_pdf_reportlab = old_reportlab

    def test_site_reports_get_requires_site_reports_permission(self):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        sa.register_site_analytics_routes(
            app,
            login_required=lambda f: f,
            data_dir=self.data_dir,
            get_client_ip=lambda: "127.0.0.1",
            resolve_ip_location=lambda _ip: "unknown",
            beijing_tz=sa.BEIJING_TZ,
            get_config=lambda: {},
            requests_support=False,
            requests_module=None,
            httpx_support=False,
            httpx_module=None,
        )
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["admin_logged_in"] = True
            sess["admin_is_super_admin"] = False
            sess["admin_permissions"] = []
        response = client.get("/api/admin/site-reports")
        self.assertEqual(response.status_code, 403)

    def test_markdown_table_renders_as_table(self):
        html = sa._analytics_markdown_to_report_html("| A | B |\n|---|---:|\n| x | 1 |")
        self.assertIn("<table", html)
        self.assertIn("<th>A</th>", html)
        self.assertIn("<td>1</td>", html)

    def test_pdf_html_uses_formal_summary_and_split_data_pages(self):
        record = self._sample_record("formal-report")
        html = sa._build_site_analytics_ai_report_html(record)
        for banned in ("\u7ed9\u8001\u677f", "\u5927\u767d\u8bdd", "\u8001\u677f\u9700\u8981\u76ef", "\u4e00\u53e5\u8bdd\u7ed9\u8001\u677f"):
            self.assertNotIn(banned, html)
        self.assertIn("<h2>简要总结</h2>", html)
        self.assertIn("<span>总体判断</span>", html)
        self.assertIn("<h3>当前需重点关注</h3>", html)
        self.assertIn("<h2>内容与地域分布</h2>", html)
        self.assertIn(sa.SITE_ANALYTICS_AI_PDF_TEMPLATE_VERSION, str(sa._analytics_report_pdf_cache_path("formal-report")))


if __name__ == "__main__":
    unittest.main()
