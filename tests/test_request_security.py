from __future__ import annotations

import unittest

from flask import Flask, jsonify

from app.request_security import register_strict_anti_crawl_guard


CRAWLER_USER_AGENTS = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "Mozilla/5.0 (compatible; Applebot/0.3; +http://www.apple.com/go/applebot)",
    "AdsBot-Google (+http://www.google.com/adsbot.html)",
    "Mozilla/5.0 (compatible; Storebot-Google/1.0; +http://www.google.com/bot.html)",
    "Mozilla/5.0 AppleWebKit/537.36; compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "ExampleCrawler/1.0 bot",
    "",
)


class StrictAntiCrawlGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        register_strict_anti_crawl_guard(self.app)

        @self.app.route("/")
        def index():
            return "public page"

        @self.app.route("/assets/test.css")
        def public_css():
            return "body{}", 200, {"Content-Type": "text/css"}

        @self.app.route("/cdn_assets/test.webp")
        def public_image():
            return b"RIFFtestWEBP", 200, {"Content-Type": "image/webp"}

        @self.app.route("/media/test.jpg")
        def public_media():
            return b"test", 200, {"Content-Type": "image/jpeg"}

        @self.app.route("/admin")
        def admin():
            return "admin login"

        @self.app.route("/api/admin/settings")
        def admin_api():
            return jsonify({"success": True})

        @self.app.route("/data/private.json")
        def private_data():
            return jsonify({"private": True})

        @self.app.route("/update_logs/release.md")
        def private_update_log():
            return "private log"

        self.client = self.app.test_client()

    def test_public_pages_and_resources_are_available_to_all_crawlers(self):
        public_paths = (
            "/",
            "/assets/test.css?cache-miss=1",
            "/cdn_assets/test.webp?cache-miss=1",
            "/media/test.jpg?cache-miss=1",
        )
        for user_agent in CRAWLER_USER_AGENTS:
            for path in public_paths:
                with self.subTest(user_agent=user_agent, path=path):
                    response = self.client.get(path, headers={"User-Agent": user_agent})
                    self.assertEqual(response.status_code, 200)

    def test_crawlers_are_still_blocked_from_private_paths(self):
        private_paths = (
            "/admin",
            "/api/admin/settings",
            "/data/private.json",
            "/update_logs/release.md",
        )
        for user_agent in CRAWLER_USER_AGENTS:
            for path in private_paths:
                with self.subTest(user_agent=user_agent, path=path):
                    response = self.client.get(path, headers={"User-Agent": user_agent})
                    self.assertEqual(response.status_code, 403)

    def test_regular_browser_can_reach_admin_login_and_authenticated_routes(self):
        headers = {"User-Agent": "Mozilla/5.0 Chrome/136 Safari/537.36"}
        self.assertEqual(self.client.get("/admin", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/settings", headers=headers).status_code, 200)


if __name__ == "__main__":
    unittest.main()
