from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from flask import Flask, Response

from app.request_security import is_anti_crawl_strict_private_path
from app.routes.public_site import register_public_site_routes


class PublicSiteSeoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "pages" / "gassensing").mkdir(parents=True)
        (self.root / "pages" / "news").mkdir(parents=True)
        (self.root / "pages" / "biosensing").mkdir(parents=True)
        (self.root / "cdn_assets").mkdir()
        (self.root / "cdn_assets" / "product.webp").write_bytes(b"RIFFtestWEBP")

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
    <img src="/cdn_assets/product.webp">
  </main>
</body>
</html>
"""
        (self.root / "pages" / "gassensing" / "mc_ld_h2.html").write_text(polluted_html, encoding="utf-8")
        (self.root / "pages" / "gassensing" / "mc_mgm_01_new.html").write_text(
            """<!doctype html>
<html lang="zh-CN"><head><title>旧版动态配气仪 - 元芯传感</title></head>
<body><h1>旧版动态配气仪</h1><p>该页面仅用于验证旧 URL 重定向与索引排除。</p></body></html>
""",
            encoding="utf-8",
        )
        (self.root / "pages" / "news" / "news_show.aspx_id_76.html").write_text(
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
        (self.root / "pages" / "biosensing" / "index.html").write_text(
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
            is_anti_crawl_strict_private_path=is_anti_crawl_strict_private_path,
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
            get_gassensing_products_with_settings=lambda: [{
                "id": "mc_ld_h2",
                "name": "MC-LD-H2型手持氢气检测仪",
                "description": "用于涉氢场景的快速泄漏检测与安全预警。",
                "image": "/cdn_assets/product.webp",
                "sku": "MC-LD-H2",
                "category": "detector",
                "indexable": True,
                "technicalProperties": [{"name": "检测对象", "value": "氢气"}],
            }],
            get_image_asset=lambda url, owner_page='': {
                'url': '/cdn_assets/product.webp',
                'ownerPage': '/pages/gassensing/mc_ld_h2.html',
                'alt': 'MC-LD-H2 手持式氢气检测仪主图',
                'title': 'MC-LD-H2 手持式氢气检测仪',
                'role': 'primary',
                'indexable': True,
                'width': 1200,
                'height': 900,
            } if 'product.webp' in str(url) else None,
            get_indexable_images_for_page=lambda path: [{
                'url': '/cdn_assets/product.webp',
                'alt': 'MC-LD-H2 手持式氢气检测仪主图',
                'title': 'MC-LD-H2 手持式氢气检测仪',
                'caption': '适用于涉氢场景的便携检测设备',
                'role': 'primary',
                'indexable': True,
            }] if path == '/pages/gassensing/mc_ld_h2.html' else [],
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_public_page_replaces_api_canonical_pollution(self):
        response = self.client.get("/pages/gassensing/mc_ld_h2.html")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store, no-cache, max-age=0, must-revalidate")
        self.assertEqual(response.headers.get("CDN-Cache-Control"), "no-store")
        self.assertEqual(response.headers.get("Cloudflare-CDN-Cache-Control"), "no-store")
        self.assertEqual(response.headers.get("Surrogate-Control"), "no-store")
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
        self.assertIn('"@type": "Product"', body)
        self.assertIn('"sku": "MC-LD-H2"', body)
        self.assertIn('alt="MC-LD-H2 手持式氢气检测仪主图"', body)
        self.assertIn('width="1200"', body)
        self.assertIn('height="900"', body)
        self.assertIn('fetchpriority="high"', body)

    def test_split_and_image_sitemaps_are_available(self):
        index_response = self.client.get('/sitemap-index.xml')
        self.assertEqual(index_response.status_code, 200)
        self.assertIn('/sitemap-products.xml', index_response.get_data(as_text=True))
        pages_response = self.client.get('/sitemap-pages.xml')
        pages_body = pages_response.get_data(as_text=True)
        self.assertIn('https://www.hnmetachip.cn/pages/biosensing/</loc>', pages_body)
        self.assertNotIn('https://www.hnmetachip.cn/pages/biosensing//', pages_body)
        image_response = self.client.get('/sitemap-images.xml')
        self.assertEqual(image_response.status_code, 200)
        image_body = image_response.get_data(as_text=True)
        self.assertIn('<image:image>', image_body)
        self.assertIn('https://www.hnmetachip.cn/cdn_assets/product.webp', image_body)

    def test_robots_points_to_sitemap_index(self):
        response = self.client.get('/robots.txt')
        self.assertIn('Sitemap: https://www.hnmetachip.cn/sitemap-index.xml', response.get_data(as_text=True))

    def test_bare_domain_get_and_head_redirect_to_www(self):
        for method in ('get', 'head'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    '/pages/news/news.html?utm_source=bare-domain',
                    base_url='https://hnmetachip.cn',
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 301)
                self.assertEqual(
                    response.headers.get('Location'),
                    'https://www.hnmetachip.cn/pages/news/news.html?utm_source=bare-domain',
                )

    def test_bare_domain_write_request_uses_method_preserving_redirect(self):
        response = self.client.post(
            '/api/contact?source=bare-domain',
            base_url='https://hnmetachip.cn',
            data={'name': 'SEO test'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 308)
        self.assertEqual(
            response.headers.get('Location'),
            'https://www.hnmetachip.cn/api/contact?source=bare-domain',
        )

    def test_canonical_and_local_hosts_do_not_redirect(self):
        canonical = self.client.get('/', base_url='https://www.hnmetachip.cn', follow_redirects=False)
        local = self.client.get('/', base_url='http://localhost:8000', follow_redirects=False)
        self.assertEqual(canonical.status_code, 200)
        self.assertEqual(local.status_code, 200)

    def test_private_paths_keep_strict_x_robots_header(self):
        response = self.client.get('/admin', headers={'User-Agent': 'Mozilla/5.0 Chrome/136'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_missing_h1_gets_accessible_fallback_heading(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn('class="seo-fallback-heading"', body)
        self.assertIn('id="seo-fallback-heading-style"', body)
        self.assertEqual(len(re.findall(r"<h1\b", body, flags=re.I)), 1)

    def test_duplicate_and_empty_h1_are_normalized_on_canonical_news_page(self):
        response = self.client.get("/pages/news/news_show.aspx_id_76.html")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        response.close()
        self.assertIn(
            '<link rel="canonical" href="https://www.hnmetachip.cn/pages/news/news_show.aspx_id_76.html">',
            body,
        )
        self.assertNotIn("婀栧崡", body)
        self.assertNotIn("<h1><br></h1>", body)
        self.assertEqual(len(re.findall(r"<h1\b", body, flags=re.I)), 1)
        self.assertGreaterEqual(len(re.findall(r"<h2\b", body, flags=re.I)), 1)

    def test_legacy_public_urls_redirect_once_to_final_targets(self):
        redirects = {
            "/pages/biosensing/index_page_2.html": "/pages/biosensing/",
            "/pages/careers/job-detail.html": "/pages/careers/jobs.html",
            "/pages/contact/feedback.aspx_attach_id.html": "/pages/contact/feedback.html",
            "/pages/about/history.html": "/pages/about/about.html",
            "/pages/about/culture.html": "/pages/about/values.html",
            "/pages/about/micro-nano.html": "/pages/research/micro-nano.html",
            "/pages/about/research.html": "/pages/research/cooperation.html",
            "/pages/services/service.html": "/pages/research/",
            "/pages/services/core-service.html": "/pages/research/development.html",
            "/pages/honors/honor.html": "/pages/gassensing/service-cases.html",
            "/pages/honors/honor-page2.html": "/pages/gassensing/service-cases.html",
            "/pages/news/news_show.aspx_id_75.html": "/pages/news/news_show.aspx_id_76.html",
            "/pages/news/news_show.aspx_id_50.html": "/pages/news/news_show.aspx_id_47.html",
            "/pages/news/news_show.aspx_id_32.html": "/pages/news/news.html#industry",
            "/pages/products/index.html": "/pages/gassensing/all-products.html",
            "/pages/products/gas_sensors.html": "/pages/gassensing/all-products.html",
            "/pages/gas_sensors.html": "/pages/gassensing/all-products.html",
            "/pages/products/products_mems.html": "/pages/research/micro-nano.html",
            "/pages/products/carbon_bio_platform.html": "/pages/biosensing/carbon_bio_platform.html",
            "/pages/products/respiratory_virus_chip.html": "/pages/biosensing/respiratory_virus_chip.html",
            "/pages/products/igzo_device.html": "/pages/biosensing/igzo_device.html",
            "/pages/solutions/jjfa.html": "/pages/solutions/solutions-index.html",
            "/pages/news/news.aspx_category_id_43.html": "/pages/news/news.html#science",
            "/pages/news/news.aspx_category_id_9.html": "/pages/news/news.html#enterprise",
            "/pages/news/news.aspx_category_id_8.html": "/pages/news/news.html#industry",
            "/pages/news/index.html": "/pages/news/news.html",
            "/pages/honors/honor.aspx@category_id=0&page=2.html": "/pages/gassensing/service-cases.html",
            "/pages/gassensing/mc_mgm_01_new.html": "/pages/gassensing/mc_mgm_01.html",
        }
        for source, target in redirects.items():
            with self.subTest(source=source):
                response = self.client.get(source, follow_redirects=False)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response.headers.get("Location"), target)

    def test_legacy_redirect_keeps_query_before_fragment(self):
        response = self.client.get("/pages/news/news_show.aspx_id_32.html?utm_source=archive")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers.get("Location"), "/pages/news/news.html?utm_source=archive#industry")

    def test_deleted_legacy_pages_are_absent_from_sitemap_and_search(self):
        sitemap = self.client.get("/sitemap.xml").get_data(as_text=True)
        self.assertNotIn("news_show.aspx_id_75.html", sitemap)
        self.assertNotIn("index_page_2.html", sitemap)
        self.assertNotIn("mc_mgm_01_new.html", sitemap)
        search = self.client.get("/api/search?q=兆瓦级氢能飞机").get_json()
        self.assertTrue(all("news_show.aspx_id_75.html" not in item["url"] for item in search["results"]))
        alias_search = self.client.get("/api/search?q=旧版动态配气仪").get_json()
        self.assertTrue(all("mc_mgm_01_new.html" not in item["url"] for item in alias_search["results"]))

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
