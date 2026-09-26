"""Checks for CDN paths kept alive after removing duplicate asset files."""

import tempfile
import unittest
from pathlib import Path

from app.cdn_asset_aliases import CDN_ASSET_ALIASES, existing_cdn_asset_path
from app.asset_versioning import resolve_asset_path


class CdnAssetAliasTests(unittest.TestCase):
    def test_all_aliases_resolve_to_a_remaining_asset(self):
        root = Path(__file__).resolve().parents[1] / 'cdn_assets'
        self.assertEqual(len(CDN_ASSET_ALIASES), 78)
        for old_path, kept_path in CDN_ASSET_ALIASES.items():
            with self.subTest(old_path=old_path):
                self.assertFalse((root / old_path).exists())
                self.assertTrue((root / kept_path).is_file())
                self.assertEqual(Path(old_path).suffix.lower(), Path(kept_path).suffix.lower())
                self.assertEqual(existing_cdn_asset_path(root, old_path), kept_path)

    def test_existing_local_file_takes_precedence_over_alias(self):
        old_path, kept_path = next(iter(CDN_ASSET_ALIASES.items()))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / kept_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'default')
            self.assertEqual(existing_cdn_asset_path(root, old_path), kept_path)

            local = root / old_path
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b'customer override')
            self.assertEqual(existing_cdn_asset_path(root, old_path), old_path)

    def test_asset_versioning_resolves_alias_to_physical_file(self):
        old_path, kept_path = next(iter(CDN_ASSET_ALIASES.items()))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / 'cdn_assets' / kept_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'default')
            self.assertEqual(resolve_asset_path('/cdn_assets/' + old_path, root), target)

    def test_missing_and_unsafe_paths_do_not_resolve(self):
        root = Path(__file__).resolve().parents[1] / 'cdn_assets'
        for path in ('../secret', '/etc/passwd', 'images//x.png', 'missing.png'):
            with self.subTest(path=path):
                self.assertIsNone(existing_cdn_asset_path(root, path))


if __name__ == '__main__':
    unittest.main()
