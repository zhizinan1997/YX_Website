from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.routes import product_editor as pe


RELATED_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>测试产品</title></head>
<body>
<main>
    <section class="vs-product-hero"><h1>测试产品</h1></section>
    <section class="vs-related-news">
        <div class="vs-container">
            <h2>相关新闻</h2>
            <div class="vs-news-grid">
                <a href="/pages/news/news.html" class="vs-news-item">
                    <img src="/news.png" alt="新闻图片">
                    <div class="vs-news-item__content"><h4>新闻标题</h4><p>新闻摘要</p></div>
                </a>
            </div>
        </div>
    </section>
    <section class="vs-related-products">
        <div class="vs-container">
            <h2>相关产品</h2>
            <div class="vs-related-grid">
                <a href="#" class="vs-related-item">
                    <img src="/related.png" alt="相关产品">
                    <h4>相关产品A</h4>
                </a>
            </div>
        </div>
    </section>
    <section class="vs-cta-section">
        <div class="vs-container">
            <h3>咨询我们</h3>
            <p>联系方式</p>
        </div>
    </section>
</main>
</body>
</html>
"""

LINKS = [
    {
        'href': '/pages/news/news.html',
        'img': '/cdn_assets/images/gassensing/link-a.png',
        'title': '技术白皮书',
        'desc': '深入了解气体传感核心技术。',
    },
    {
        'href': 'https://www.example.com/demo',
        'img': '/cdn_assets/images/gassensing/link-b.png',
        'title': '在线演示',
        'desc': '预约产品在线演示。',
    },
]


class RelatedLinksPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        gas_dir = self.root / "pages" / "gassensing"
        gas_dir.mkdir(parents=True)
        (gas_dir / "mc_ld_h2.html").write_text(RELATED_PAGE_HTML, encoding="utf-8")
        assets_dir = self.root / "assets"
        assets_dir.mkdir()
        (assets_dir / "test-product.png").write_bytes(b"\x89PNG\r\n\x1a\nproduct")
        link_img_dir = self.root / "cdn_assets" / "images" / "gassensing"
        link_img_dir.mkdir(parents=True)
        self.link_img_path = link_img_dir / "link-a.png"
        self.link_img_path.write_bytes(b"\x89PNG\r\n\x1a\nlink")
        self._prev_app_root = pe._DEPS.get("app_root")
        pe._DEPS["app_root"] = self.root

    def tearDown(self):
        if self._prev_app_root is None:
            pe._DEPS.pop("app_root", None)
        else:
            pe._DEPS["app_root"] = self._prev_app_root
        self.tmp.cleanup()

    def test_patch_inserts_section_between_news_and_products(self):
        patched = pe.patch_vs_product_sections(RELATED_PAGE_HTML, {'related_links': LINKS})
        self.assertIn('<section class="vs-related-links">', patched)
        self.assertIn('<h2>相关链接</h2>', patched)
        self.assertEqual(patched.count('class="vs-link-item"'), 2)
        self.assertIn('<img src="/cdn_assets/images/gassensing/link-a.png"', patched)
        self.assertIn('<h4>技术白皮书</h4>', patched)
        self.assertIn('<p>深入了解气体传感核心技术。</p>', patched)
        self.assertIn('href="https://www.example.com/demo"', patched)
        # 位置：相关新闻 < 相关链接 < 相关产品
        news_pos = patched.find('vs-related-news')
        links_pos = patched.find('vs-related-links')
        products_pos = patched.find('vs-related-products')
        self.assertTrue(news_pos < links_pos < products_pos)

    def test_extract_round_trip(self):
        patched = pe.patch_vs_product_sections(RELATED_PAGE_HTML, {'related_links': LINKS})
        extracted = pe.extract_vs_product_sections(patched)
        self.assertEqual(extracted['related_links'], LINKS)
        # 原有新闻/相关产品提取不受影响
        self.assertEqual(len(extracted['news']), 1)
        self.assertEqual(len(extracted['related_products']), 1)

    def test_empty_links_remove_section(self):
        with_links = pe.patch_vs_product_sections(RELATED_PAGE_HTML, {'related_links': LINKS})
        cleared = pe.patch_vs_product_sections(with_links, {'related_links': []})
        self.assertNotIn('vs-related-links', cleared)
        # 再次保存空列表也是安全的
        again = pe.patch_vs_product_sections(cleared, {'related_links': []})
        self.assertNotIn('vs-related-links', again)

    def test_patch_is_idempotent(self):
        once = pe.patch_vs_product_sections(RELATED_PAGE_HTML, {'related_links': LINKS})
        twice = pe.patch_vs_product_sections(once, {'related_links': LINKS})
        self.assertEqual(once, twice)

    def test_partial_items_are_kept_and_sanitized(self):
        sections = {'related_links': [
            {'title': '只有标题', 'href': 'javascript:alert(1)'},
            'not-a-dict',
        ]}
        patched = pe.patch_vs_product_sections(RELATED_PAGE_HTML, sections)
        self.assertIn('<h4>只有标题</h4>', patched)
        self.assertNotIn('javascript:', patched.lower())
        # href 被清空时回退为 '#'
        self.assertIn('href="#"', patched)
        # 无图片时不渲染 img，正文补全内边距
        link_item = patched[patched.find('class="vs-link-item"') - 20:]
        item_block = patched[patched.find('vs-link-item'):patched.find('</a>', patched.find('vs-link-item'))]
        self.assertNotIn('<img', item_block)
        self.assertIn('style="padding: 28px;"', patched)

    def test_xss_is_escaped(self):
        sections = {'related_links': [{'title': '<script>alert(1)</script>', 'desc': 'x" onmouseover="alert(1)'}]}
        patched = pe.patch_vs_product_sections(RELATED_PAGE_HTML, sections)
        self.assertNotIn('<script>alert(1)</script>', patched)
        self.assertIn('&lt;script&gt;', patched)
        self.assertNotIn('onmouseover="alert(1)"', patched)

    def test_ai_generated_page_has_no_related_links(self):
        # AI 建页流程：sections 不含 related_links → 页面不出现该模块
        page_html, normalized = pe.render_product_page_from_sections(
            product_family='gas',
            title='测试仪',
            short_name='MC-T',
            category='detector',
            image_url='/assets/test-product.png',
            summary='测试摘要',
            sections={'title': '测试仪'},
        )
        self.assertNotIn('vs-related-links', page_html)
        self.assertEqual(normalized.get('related_links'), [])

    def test_version_local_asset_urls_for_related_links(self):
        sections = {'related_links': [{'img': '/cdn_assets/images/gassensing/link-a.png', 'title': 'A'}]}
        versioned = pe.version_product_section_image_urls(dict(sections))
        versioned_img = versioned['related_links'][0]['img']
        self.assertTrue(versioned_img.startswith('/cdn_assets/images/gassensing/link-a.png?v='))
        self.assertNotEqual(versioned_img, '/cdn_assets/images/gassensing/link-a.png')

    def test_normalize_caps_two_items(self):
        items = [{'title': f'卡{i}', 'desc': 'd', 'href': f'/p{i}', 'img': f'/i{i}.png'} for i in range(5)]
        normalized = pe._normalize_product_sections({'related_links': items}, partial=True)
        self.assertEqual(len(normalized['related_links']), 2)
        self.assertEqual(normalized['related_links'][0]['title'], '卡0')

    def test_normalize_drops_fully_empty_items(self):
        normalized = pe._normalize_product_sections(
            {'related_links': [{'title': ''}, {'title': '有内容'}]}, partial=True
        )
        self.assertEqual(len(normalized['related_links']), 1)
        self.assertEqual(normalized['related_links'][0]['title'], '有内容')


if __name__ == '__main__':
    unittest.main()
