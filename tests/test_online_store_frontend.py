from __future__ import annotations

import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class StoreParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.cards = []
        self.filters = []
        self.elements = {}
        self.card = None
        self.button = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if attrs.get("id"):
            self.elements[attrs["id"]] = attrs
        if tag == "li" and "os-product-card" in classes:
            self.card = {"category": attrs["data-category"], "images": [], "links": []}
            self.cards.append(self.card)
        if self.card is not None and tag == "img":
            self.card["images"].append(attrs)
        if self.card is not None and tag == "a":
            self.card["links"].append(attrs)
        if tag == "button" and "os-filter-btn" in classes:
            self.button = {**attrs, "text": ""}
            self.filters.append(self.button)

    def handle_data(self, data):
        if self.button is not None:
            self.button["text"] += data

    def handle_endtag(self, tag):
        if tag == "li":
            self.card = None
        if tag == "button":
            self.button = None


class OnlineStoreFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "pages/gassensing/online-store.html").read_text(encoding="utf-8")
        cls.page = StoreParser(cls.html)

    def test_category_counts_match_products_and_initial_selection(self):
        counts = Counter(card["category"] for card in self.page.cards)
        self.assertEqual(counts, {"gas": 12, "bio": 10})
        for button in self.page.filters:
            category = button["data-category"]
            expected = len(self.page.cards) if category == "all" else counts[category]
            self.assertEqual(int(re.search(r"\d+\s*$", button["text"])[0]), expected)
            self.assertEqual(button["aria-controls"], "osTrack")
            self.assertEqual(button["aria-pressed"], "true" if category == "all" else "false")

    def test_every_product_retains_image_detail_and_trial_destination(self):
        for card in self.page.cards:
            self.assertEqual(len(card["images"]), 1)
            image = card["images"][0]
            self.assertTrue(image["alt"])
            self.assertTrue((ROOT / urlsplit(image["src"]).path.lstrip("/")).is_file())
            self.assertEqual(len(card["links"]), 2)
            for link in card["links"]:
                url = urlsplit(link["href"])
                self.assertTrue((ROOT / url.path.lstrip("/")).is_file())
                if "os-btn-trial" in link["class"]:
                    self.assertEqual(url.path, "/pages/contact/feedback.html")
                    query = parse_qs(url.query)
                    self.assertTrue(query["product"][0])
                    self.assertTrue(query["title"][0])

    def test_scrolling_has_accessible_pause_and_keyboard_controls(self):
        self.assertEqual(self.page.elements["osTrack"]["tabindex"], "0")
        self.assertTrue(self.page.elements["osTrack"]["aria-label"])
        for name in ("osAutoToggle", "osScrollPrev", "osScrollNext"):
            self.assertTrue(self.page.elements[name]["aria-label"])
            self.assertTrue(self.page.elements[name]["title"])
        self.assertIn("reducedMotion.matches", self.html)
        self.assertIn("track.addEventListener('focusin'", self.html)
        self.assertIn("track.addEventListener('touchcancel'", self.html)

    def test_product_styles_match_markup_and_desktop_container_is_wide(self):
        for name in ("img-box", "body", "title", "desc", "actions"):
            self.assertRegex(self.html, rf"\.os-product-card__{name}\s*\{{")
        image_rule = re.search(r"\.os-product-card__img-box img\s*\{([^}]+)", self.html)[1]
        self.assertIn("height: 100%", image_rule)
        self.assertIn("object-fit: contain", image_rule)
        container_rule = re.search(r"\.os-page \.vs-container\s*\{([^}]+)", self.html)[1]
        max_width = int(re.search(r"max-width:\s*(\d+)px", container_rule)[1])
        self.assertGreaterEqual(max_width, 1600)


if __name__ == "__main__":
    unittest.main()
