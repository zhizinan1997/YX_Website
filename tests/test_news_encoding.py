import unittest
from pathlib import Path

from app.routes.news_content import build_news_card_html


ROOT = Path(__file__).resolve().parents[1]


class NewsEncodingTests(unittest.TestCase):
    def test_news_index_uses_readable_detail_label(self):
        html = (ROOT / "pages/news/news.html").read_text(encoding="utf-8")

        self.assertIn("查看详情", html)
        self.assertNotIn("鏌ョ湅璇︽儏", html)

    def test_generated_news_card_uses_readable_detail_label(self):
        html = build_news_card_html(
            "news_show.aspx_id_999.html",
            "enterprise",
            "气体传感事业部",
            "/cdn_assets/news/example.jpg",
            "2026-08-20",
            "测试资讯",
            "测试摘要",
        )

        self.assertIn("查看详情", html)
        self.assertNotIn("鏌ョ湅璇︽儏", html)
