from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.routes.home_content import build_hero_api_payload, get_hero_config, save_hero_config


def _sanitize_url(value, *, enforce_remote_public=False):
    text = str(value or "").strip()
    if enforce_remote_public and not (text.startswith("https://") or text.startswith("http://") or text.startswith("/")):
        return ""
    return text


class HomeHeroConfigTests(unittest.TestCase):
    def test_default_cta_buttons_visible_is_true(self):
        with tempfile.TemporaryDirectory() as td:
            hero_file = Path(td) / "hero.json"

            config = get_hero_config(hero_file, _sanitize_url)

            self.assertTrue(config["cta_buttons_visible"])

    def test_save_and_payload_preserve_cta_buttons_visibility(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hero_file = root / "hero.json"
            manifest_file = root / "manifest.json"
            manifest_file.write_text(json.dumps({"items": {}}), encoding="utf-8")

            saved = save_hero_config(
                {
                    "interval_seconds": 7,
                    "cta_buttons_visible": False,
                    "items": [
                        {
                            "id": "hero-1",
                            "type": "image",
                            "url": "/media/hero/example.jpg",
                            "source": "upload",
                        }
                    ],
                },
                hero_config_file=hero_file,
                sanitize_public_media_url=_sanitize_url,
            )

            self.assertFalse(saved["cta_buttons_visible"])
            payload = build_hero_api_payload(
                hero_config_file=hero_file,
                sanitize_public_media_url=_sanitize_url,
                hero_derived_manifest_file=manifest_file,
                pil_support=False,
                image_module=None,
                image_ops_module=None,
                pil_features=None,
                hero_uploads_dir=root,
                hero_derived_dir=root,
                hero_source_image_extensions={"jpg", "jpeg", "png"},
                hero_derived_widths=(960,),
                hero_derived_formats=("webp",),
            )

            self.assertEqual(payload["interval_seconds"], 7)
            self.assertFalse(payload["cta_buttons_visible"])
            self.assertEqual(len(payload["items"]), 1)


if __name__ == "__main__":
    unittest.main()
