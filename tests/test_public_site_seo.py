from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from flask import Flask, Response

from app.routes.public_site import register_public_site_routes


class PublicSiteSeoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "pages" / "gassensing").mkdir(parents=True)
        (self.root / "pages" / "news").mkdir(parents=True)
        (self.root / "pages" / "biosensing").mkdir(parents=True)
        (self.root / "cdn_assets").mkdir()

        (self.root / "index.html").write_text(
            """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>湖南元芯传感科技 - 先进生物与化学传感技术解决方案</title>
</head>
<body>
  <main><p>元芯传感提供先进传感技术解决方案。</p></main>
</body>
</html>
""",
            encoding="utf-8",
        )

        polluted_html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>MC-LD-H2型手持氢气检测仪 - 元芯传感</title>
  <link rel="canonical" href="https://www.hnmetachip.cn/api/products/code/download">
  <script type="application/ld+json">{"url":"https://www.hnmetachip.cn/api/products/code/download"}</script>
</head>
<body>
  <main>
    <h1>MC-LD-H2型手持氢气检测仪</h1>
    <p>搭载高性能碳基传感芯片，为涉氢场景提供氢气泄漏快速检测与安全预警。</p>
  </main>
</body>
</html>
"""
        (self.root / "pages" / "gassensing" / "mc_ld_h2.html").write_text(polluted_html, encoding="utf-8")
        (self.root / "pages" / "news" / "news_show.aspx_id_75.html").write_text(
            """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>兆瓦级氢能飞机株洲成功首飞，安全检测何以“氢”而易举？ - 婀栧崡鍏冭姱浼犳劅绉戞妧鏈夐檺璐ｄ换鍏徃</title>
</head>
<body>
  <main>
    <h1>兆瓦级氢能飞机株洲成功首飞，安全检测何以“氢”而易举？</h1>
    <article>
      <h1><br></h1>
      <h1>兆瓦级氢能飞机株洲成功首飞，安全检测何以“氢”而易举？</h1>
      <p>氢能应用加速落地，氢安全检测成为不可或缺的一环。</p>
    </article>
  </main>
</body>
</html>
""",
            encoding="utf-8",
        )
        (self.root / "pages" / "biosensing" / "index_page_2.html").write_text(
            """<!doctype html>
<html lang="zh-CN"><head><title>生物传感 - 元芯传感</title></head><body><h1>生物传感</h1></body></html>
""",
            encoding="utf-8",
        )

        self.app = Flask(__name__)

        @self.app.route("/api/products/code/download")
        def download_product_code():
            return Response(
                "<html><head><title>Downloaded source</title></head><body>source</body></html>",
                mimetype="text/html",
                headers={"Content-Disposition": 'attachment; filename="mc_ld_h2.html"'},
            )

        register_public_site_routes(
            self.app,
            login_required=lambda f: f,
            app_root=self.root,
            cdn_assets_dir=self.root / "cdn_assets",
            site_favicon_relative_path="images/common/site-favicon.png",
            public_static_exact_files={"index.html", "robots.txt"},
            public_static_root_dirs={"pages"},
            private_static_prefixes=("data", ".git"),
            get_public_base_url=lambda: "https://www.hnmetachip.cn",
            first_forwarded_value=lambda value: str(value or "").split(",", 1)[0].strip(),
            is_anti_crawl_strict_private_path=lambda _path: False,
            strict_anti_crawl_headers="noindex, nofollow",
            public_html_content_security_policy="base-uri 'self'",
            public_referrer_policy="strict-origin-when-cross-origin",
            chem_subscript_script_src="/assets/js/chem-subscript.js",
            site_analytics_script_src="/assets/js/site-analytics.js",
            site_brand_name="元芯传感",
            site_company_name="湖南元芯传感科技有限责任公司",
            site_display_name="湖南元芯传感科技",
            site_default_description="元芯传感提供先进传感技术解决方案。",
            site_logo_path="/cdn_assets/images/common/site-favicon.png",
            seo_default_robots="index,follow,max-image-preview:large",
            seo_section_descriptions=(
                ("/pages/gassensing/", "元芯传感提供氢气检测、纯度分析与工业安全监测产品。"),
                ("/pages/news/", "查看元芯传感在氢安全、生物传感、产业动态、技术解读与企业资讯方面的最新内容。"),
                ("/pages/biosensing/", "元芯传感提供碳基生物传感平台、检测芯片、工作站与定制服务。"),
            ),
            seo_breadcrumb_labels={"pages": "", "gassensing": "气体传感", "news": "洞察与资讯", "biosensing": "生物传感"},
            seo_breadcrumb_targets={"gassensing": "/pages/gassensing/", "news": "/pages/news/news.html", "biosensing": "/pages/biosensing/"},
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_public_page_replaces_api_canonical_pollution(self):
        response = self.client.get("/pages/gassensing/mc_ld_h2.html")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-cache, max-age=0, must-revalidate")
        body = response.get_data(as_text=True)
        response.close()
        self.assertNotIn("/api/products/code/download", body)
        self.assertIn(
            '<link rel="canonical" href="https://www.hnmetachip.cn/pages/gassensing/mc_ld_h2.html">',
            body,
        )
        self.assertIn('property="og:title"', body)
        self.assertIn('property="og:image"', body)
        self.assertIn('name="twitter:card" content="summary_large_image"', body)
        self.assertIn('type="application/ld+json"', body)

    def test_missing_h1_gets_accessible_fallback_heading(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn('class="seo-fallback-heading"', body)
        self.assertIn('id="seo-fallback-heading-style"', body)
        self.assertEqual(len(re.findall(r"<h1\b", body, flags=re.I)), 1)

    def test_duplicate_and_empty_h1_are_normalized(self):
        response = self.client.get("/pages/news/news_show.aspx_id_75.html")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn(
            "<title>兆瓦级氢能飞机株洲首飞安全检测方案 - 湖南元芯传感科技有限责任公司</title>",
            body,
        )
        self.assertIn(
            '<link rel="canonical" href="https://www.hnmetachip.cn/pages/news/news_show.aspx_id_76.html">',
            body,
        )
        self.assertIn('name="robots" content="noindex,follow,max-image-preview:large"', body)
        self.assertNotIn("婀栧崡", body)
        self.assertNotIn("<h1><br></h1>", body)
        self.assertEqual(len(re.findall(r"<h1\b", body, flags=re.I)), 1)
        self.assertGreaterEqual(len(re.findall(r"<h2\b", body, flags=re.I)), 1)

    def test_duplicate_title_override_for_known_paginated_page(self):
        response = self.client.get("/pages/biosensing/index_page_2.html")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn("<title>生物传感产品第 2 页 - 元芯传感</title>", body)

    def test_api_html_attachment_skips_public_seo_injection(self):
        response = self.client.get("/api/products/code/download")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn("Downloaded source", body)
        self.assertNotIn('rel="canonical"', body)
        self.assertNotIn('name="description"', body)


if __name__ == "__main__":
    unittest.main()
