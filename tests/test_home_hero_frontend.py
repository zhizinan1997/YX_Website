from __future__ import annotations

import unittest
from pathlib import Path


class HomeHeroFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")

    def test_desktop_image_fallback_is_contained_on_mobile(self):
        self.assertIn(".hero-slide.uses-desktop-mobile-fallback img", self.index_html)
        self.assertIn("object-fit: contain", self.index_html)
        self.assertIn("object-position: center top", self.index_html)

    def test_mobile_fallback_hero_shrinks_to_header_and_image_height(self):
        self.assertIn(".vs-hero.is-mobile-fallback-compact", self.index_html)
        self.assertIn("height: auto !important", self.index_html)
        self.assertIn("padding-top: var(--header-height, 90px)", self.index_html)
        self.assertIn(".hero-slide.is-active.uses-desktop-mobile-fallback picture", self.index_html)
        self.assertIn("heroSection.classList.add('is-mobile-fallback-compact')", self.index_html)
        self.assertIn("updateMobileFallbackLayout(active)", self.index_html)

    def test_fallback_marker_requires_missing_mobile_media(self):
        self.assertIn("const usesDesktopMobileFallback = item.type === 'image'", self.index_html)
        self.assertIn("&& !item.mobile_url", self.index_html)
        self.assertIn("&& !item.mobile_fallback", self.index_html)
        self.assertIn("&& !hasMobileSources", self.index_html)
        self.assertIn("slide.classList.add('uses-desktop-mobile-fallback')", self.index_html)


if __name__ == "__main__":
    unittest.main()
