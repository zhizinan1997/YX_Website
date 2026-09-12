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
            "promotion": sa.PROMOTION_LINKS_FILE,
            "jsonl": sa.SITE_ANALYTICS_AI_REPORTS_FILE,
            "dir": sa.SITE_ANALYTICS_AI_REPORTS_DIR,
            "index": sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE,
            "index_lock": sa.SITE_ANALYTICS_AI_REPORTS_INDEX_LOCK_FILE,
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
        sa.invalidate_site_report_caches()

    def tearDown(self):
        sa.invalidate_site_report_caches()
        self.tmp.cleanup()
        sa.SITE_ANALYTICS_LOG_FILE = self._old_paths["log"]
        sa.PROMOTION_LINKS_FILE = self._old_paths["promotion"]
        sa.SITE_ANALYTICS_AI_REPORTS_FILE = self._old_paths["jsonl"]
        sa.SITE_ANALYTICS_AI_REPORTS_DIR = self._old_paths["dir"]
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = self._old_paths["index"]
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_LOCK_FILE = self._old_paths["index_lock"]
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
        sa.PROMOTION_LINKS_FILE = data_dir / "promotion_links.json"
        sa.SITE_ANALYTICS_AI_REPORTS_FILE = data_dir / "site_analytics_ai_reports.jsonl"
        sa.SITE_ANALYTICS_AI_REPORTS_DIR = data_dir / "site_analytics_ai_reports"
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = sa.SITE_ANALYTICS_AI_REPORTS_DIR / "index.json"
        sa.SITE_ANALYTICS_AI_REPORTS_INDEX_LOCK_FILE = sa.SITE_ANALYTICS_AI_REPORTS_DIR / "index.lock"
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

    def test_log_trim_reduces_below_threshold_without_noop_rewrites(self):
        old_max = sa.ANALYTICS_LOG_MAX_BYTES
        old_keep_bytes = sa.ANALYTICS_LOG_TRIM_KEEP_BYTES
        old_keep_lines = sa.ANALYTICS_LOG_TRIM_KEEP_LINES
        try:
            sa.ANALYTICS_LOG_MAX_BYTES = 4 * 1024
            sa.ANALYTICS_LOG_TRIM_KEEP_BYTES = 2 * 1024
            sa.ANALYTICS_LOG_TRIM_KEEP_LINES = 10000
            line = '{"event_type":"pageview","pad":"' + "x" * 100 + '"}\n'
            sa.SITE_ANALYTICS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            sa.SITE_ANALYTICS_LOG_FILE.write_text(line * 100, encoding="utf-8")
            sa._append_site_analytics_records([{"event_type": "pageview", "page_path": "/trim-check"}])
            size_after = sa.SITE_ANALYTICS_LOG_FILE.stat().st_size
            # 初始文件约 13KB（> 4KB 上限）：裁剪必须真正把文件压回上限
            # 以内并保留新追加的记录，而不是原样整写一遍。
            self.assertLessEqual(size_after, sa.ANALYTICS_LOG_MAX_BYTES)
            content = sa.SITE_ANALYTICS_LOG_FILE.read_text(encoding="utf-8")
            self.assertIn("/trim-check", content)
        finally:
            sa.ANALYTICS_LOG_MAX_BYTES = old_max
            sa.ANALYTICS_LOG_TRIM_KEEP_BYTES = old_keep_bytes
            sa.ANALYTICS_LOG_TRIM_KEEP_LINES = old_keep_lines

    def test_range_buckets_are_capped(self):
        from datetime import date

        start = date(1, 1, 1)
        end = date(9999, 12, 31)
        bucket_keys, buckets = sa._analytics_build_range_buckets(start, end, "day")
        self.assertLessEqual(len(bucket_keys), sa._ANALYTICS_MAX_RANGE_BUCKETS)
        self.assertEqual(len(buckets), len(bucket_keys))

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
            def post(url, json, headers, timeout, **kwargs):
                captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout, **kwargs})
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

    def test_promotion_breakdown_and_ai_context_include_utm_id(self):
        now_ts = int(sa.time.time())
        sa.PROMOTION_LINKS_FILE.write_text(
            '{"version":1,"items":[{"id":"1","name":"微信公众号文章 A","promotion_mark":"wechat-article-a","utm_source":"wechat","utm_medium":"article","utm_campaign":"hydrogen"}]}',
            encoding="utf-8",
        )
        sa._append_site_analytics_records([
            {
                "ts": now_ts,
                "event_type": "pageview",
                "event_name": "page_view",
                "page_path": "/",
                "source": "campaign",
                "utm_source": "wechat",
                "utm_medium": "article",
                "utm_campaign": "hydrogen",
                "utm_id": "wechat-article-a",
                "promotion_mark": "wechat-article-a",
                "visitor_id": "v1",
                "session_id": "s1",
            },
            {
                "ts": now_ts,
                "event_type": "event",
                "event_name": "contact_submit",
                "page_path": "/",
                "source": "campaign",
                "utm_source": "wechat",
                "utm_medium": "article",
                "utm_campaign": "hydrogen",
                "utm_id": "wechat-article-a",
                "promotion_mark": "wechat-article-a",
                "visitor_id": "v1",
                "session_id": "s1",
            },
        ])
        report = sa.build_site_analytics_report(range_days=7)
        self.assertEqual(report["promotion_breakdown"][0]["promotion_mark"], "wechat-article-a")
        self.assertEqual(report["promotion_breakdown"][0]["name"], "微信公众号文章 A")
        self.assertEqual(report["promotion_breakdown"][0]["conversion_events"], 1)
        context = sa.build_site_analytics_ai_report_context(period="month")
        self.assertEqual(context["current"]["promotion_breakdown"][0]["promotion_mark"], "wechat-article-a")

    def test_archived_or_unknown_promotion_mark_is_excluded_from_breakdown(self):
        now_ts = int(sa.time.time())
        sa.PROMOTION_LINKS_FILE.write_text(
            '{"version":1,"items":['
            '{"id":"1","name":"有效链接","promotion_mark":"active-mark"},'
            '{"id":"2","name":"已删除链接","promotion_mark":"deleted-mark","archived_at":"2026-08-01T00:00:00"}'
            ']}',
            encoding="utf-8",
        )
        for mark in ("active-mark", "deleted-mark", "ghost-mark"):
            sa._append_site_analytics_records([
                {
                    "ts": now_ts,
                    "event_type": "pageview",
                    "event_name": "page_view",
                    "page_path": "/",
                    "source": "campaign",
                    "utm_id": mark,
                    "promotion_mark": mark,
                    "visitor_id": f"v-{mark}",
                    "session_id": f"s-{mark}",
                },
            ])
        report = sa.build_site_analytics_report(range_days=7)
        marks = [row["promotion_mark"] for row in report["promotion_breakdown"]]
        self.assertEqual(marks, ["active-mark"])

        sanitized = sa._analytics_sanitize_event(
            {
                "event_type": "pageview",
                "page_path": "/",
                "utm": {"id": "deleted-mark"},
                "visitor_id": "v2",
                "session_id": "s2",
            },
            "example.com",
            "Mozilla/5.0",
            "127.0.0.1",
        )
        self.assertEqual(sanitized["promotion_mark"], "")
        self.assertEqual(sanitized["utm_id"], "")

        kept = sa._analytics_sanitize_event(
            {
                "event_type": "pageview",
                "page_path": "/",
                "utm": {"id": "active-mark"},
                "visitor_id": "v3",
                "session_id": "s3",
            },
            "example.com",
            "Mozilla/5.0",
            "127.0.0.1",
        )
        self.assertEqual(kept["promotion_mark"], "active-mark")

    def test_automated_agent_classification_and_openharmony(self):
        baidu = sa._analytics_classify_automated_agent(
            "Mozilla/5.0 (compatible; Baiduspider-render/2.0; +http://www.baidu.com/search/spider.html)"
        )
        self.assertEqual(baidu["traffic_type"], "crawler")
        self.assertEqual(baidu["crawler_key"], "baidu")
        internal = sa._analytics_classify_automated_agent(
            "Mozilla/5.0 (compatible; MetachipCheck/1.0; +https://check.hnmetachip.cn)"
        )
        self.assertEqual(internal["traffic_type"], "internal_check")
        self.assertEqual(
            sa._analytics_classify_os("Mozilla/5.0 (Phone; OpenHarmony 6.1) AppleWebKit/537.36"),
            "harmonyos",
        )

    def test_internal_checker_is_discarded_and_crawler_is_tagged(self):
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
        response = app.test_client().post(
            "/api/analytics/collect",
            json={"event_type": "pageview", "page_path": "/", "visitor_id": "v-check", "session_id": "s-check"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; MetachipCheck/1.0; +https://check.hnmetachip.cn)"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["accepted"], 0)
        self.assertEqual(sa._iter_site_analytics_records(), [])
        crawler_response = app.test_client().post(
            "/api/analytics/collect",
            json={"event_type": "pageview", "page_path": "/news", "visitor_id": "v-bot", "session_id": "s-bot"},
            headers={"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"},
        )
        self.assertEqual(crawler_response.status_code, 200)
        self.assertEqual(crawler_response.get_json()["accepted"], 1)
        crawler_record = sa._iter_site_analytics_records()[0]
        self.assertEqual(crawler_record["traffic_type"], "crawler")
        self.assertEqual(crawler_record["crawler_key"], "bing")
        self.assertIn("bingbot", crawler_record["crawler_user_agent"])

    def test_crawler_sessions_are_separated_from_human_metrics(self):
        now_ts = int(sa.time.time())
        sa._append_site_analytics_records([
            {
                "ts": now_ts,
                "event_type": "pageview",
                "page_path": "/human",
                "source": "direct",
                "device": "desktop",
                "os": "windows",
                "traffic_type": "human",
                "ip": "203.0.113.10",
                "visitor_id": "v-human",
                "session_id": "s-human",
            },
            {
                "ts": now_ts,
                "event_type": "pageview",
                "page_path": "/crawler-entry",
                "source": "direct",
                "device": "desktop",
                "os": "unknown",
                "traffic_type": "crawler",
                "crawler_key": "baidu",
                "crawler_name": "百度爬虫",
                "crawler_vendor": "百度",
                "crawler_user_agent": "Baiduspider-render/2.0",
                "ip": "220.181.141.40",
                "country": "中国",
                "location": "中国 / 北京",
                "visitor_id": "v-bot",
                "session_id": "s-bot",
            },
        ])
        report = sa.build_site_analytics_report(range_days=7)
        self.assertEqual(report["summary"]["sessions"], 1)
        self.assertEqual(report["summary"]["pageviews"], 1)
        self.assertEqual(report["os_breakdown"], [{"os": "windows", "sessions": 1, "ratio": 100.0}])
        self.assertEqual(report["top_pages"][0]["path"], "/human")
        self.assertEqual(report["crawler_summary"]["sessions"], 1)
        self.assertEqual(report["crawler_summary"]["pageviews"], 1)
        self.assertEqual(report["crawler_breakdown"][0]["crawler_key"], "baidu")
        self.assertEqual(report["crawler_breakdown"][0]["top_paths"][0]["path"], "/crawler-entry")
        self.assertEqual(report["crawler_recent"][0]["ip"], "220.181.141.40")

    def test_ai_report_context_storage_and_html_include_crawler_data(self):
        current_report = {
            "summary": {"pageviews": 100, "unique_visitors": 30, "sessions": 40},
            "trend": [],
            "source_breakdown": [],
            "campaign_breakdown": [],
            "promotion_breakdown": [],
            "device_breakdown": [],
            "os_breakdown": [],
            "province_breakdown": [],
            "continent_breakdown": [],
            "country_breakdown": [],
            "top_pages": [],
            "top_events": [],
            "crawler_summary": {"sessions": 12, "pageviews": 20, "events": 3, "unique_ips": 8, "sources": 1},
            "crawler_breakdown": [{
                "crawler_key": "baidu",
                "crawler_name": "百度爬虫",
                "crawler_vendor": "百度",
                "sessions": 12,
                "pageviews": 20,
                "events": 3,
                "unique_ips": 8,
                "ratio": 100.0,
                "first_seen": "2026-06-01 01:00:00",
                "last_seen": "2026-06-01 02:00:00",
                "top_paths": [{"path": "/news", "pageviews": 15}],
                "countries": [{"country": "中国", "sessions": 12}],
                "user_agents": [{"user_agent": "Baiduspider-render/2.0", "sessions": 12}],
            }],
        }
        previous_report = {
            **current_report,
            "summary": {"pageviews": 80, "unique_visitors": 25, "sessions": 32},
            "crawler_summary": {"sessions": 6, "pageviews": 9, "events": 1, "unique_ips": 4, "sources": 1},
            "crawler_breakdown": [],
        }
        reports = iter([current_report, previous_report])
        old_builder = sa.build_site_analytics_report
        sa.build_site_analytics_report = lambda **_kwargs: next(reports)
        try:
            context = sa.build_site_analytics_ai_report_context(period="month", anchor_date="2026-06-01")
        finally:
            sa.build_site_analytics_report = old_builder

        self.assertEqual(context["current"]["crawler_summary"]["sessions"], 12)
        self.assertEqual(context["current"]["crawler_breakdown"][0]["crawler_key"], "baidu")
        self.assertNotIn("user_agents", context["current"]["crawler_breakdown"][0])
        self.assertEqual(context["crawler_comparison"]["sessions"]["change"], 6)
        messages = sa._build_site_analytics_ai_messages(context)
        self.assertIn("真人访问指标已经排除已识别爬虫", messages[1]["content"])
        self.assertIn("crawler_comparison", messages[1]["content"])
        self.assertNotIn("可能包含爬虫或测试访问", sa.SITE_ANALYTICS_AI_SYSTEM_PROMPT)

        record = sa._build_site_analytics_ai_report_record(
            "## 爬虫与技术流量\n百度爬虫抓取增加。",
            context,
            "test-model",
            "2026-06-01T12:00:00+08:00",
        )
        self.assertEqual(record["crawler_comparison"]["sessions"]["current"], 12)
        self.assertEqual(record["current_detail"]["crawler_summary"]["sessions"], 12)
        self.assertEqual(record["current_detail"]["crawler_breakdown"][0]["crawler_name"], "百度爬虫")
        public_row = sa._analytics_public_ai_report_row(record)
        self.assertEqual(public_row["current_crawler_summary"]["sessions"], 12)
        self.assertEqual(public_row["crawler_comparison"]["sessions"]["change"], 6)
        html = sa._build_site_analytics_ai_report_html(record)
        self.assertIn("爬虫与技术流量", html)
        self.assertIn("百度爬虫", html)
        self.assertIn("已与真人经营指标分离", html)
        email_html = sa._build_report_email_html(
            title="月度报告",
            period_label="月报",
            range_label="2026-06-01 至 2026-06-30",
            comparison=context["comparison"],
            crawler_summary=context["current"]["crawler_summary"],
        )
        email_text = sa._build_report_email_text(
            title="月度报告",
            period_label="月报",
            range_label="2026-06-01 至 2026-06-30",
            crawler_summary=context["current"]["crawler_summary"],
        )
        self.assertIn("爬虫与技术流量已独立统计", email_html)
        self.assertIn("已从真人访问指标中剥离", email_text)

    def test_delete_promotion_analytics_removes_entire_linked_session(self):
        sa._append_site_analytics_records([
            {"event_type": "pageview", "promotion_mark": "link-a", "session_id": "session-a"},
            {"event_type": "event", "session_id": "session-a"},
            {"event_type": "pageview", "promotion_mark": "link-b", "session_id": "session-b"},
        ])
        deleted = sa.delete_site_analytics_records_by_promotion_mark("link-a")
        self.assertEqual(deleted, 2)
        records = sa._iter_site_analytics_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["promotion_mark"], "link-b")

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
