from __future__ import annotations

import unittest

from app.public_urls import canonicalize_public_path, canonicalize_public_url


class PublicUrlTests(unittest.TestCase):
    def test_directory_indexes_and_home_are_canonicalized(self):
        self.assertEqual(canonicalize_public_path('/index.html'), '/')
        self.assertEqual(canonicalize_public_path('/pages/research/index.html'), '/pages/research/')
        self.assertEqual(canonicalize_public_path('/pages/biosensing/index.html'), '/pages/biosensing/')

    def test_query_and_fragment_are_preserved(self):
        self.assertEqual(
            canonicalize_public_url('/pages/research/index.html?source=nav#services'),
            '/pages/research/?source=nav#services',
        )
        self.assertEqual(
            canonicalize_public_url('/pages/news/news_show.aspx_id_32.html?utm_source=archive'),
            '/pages/news/news.html?utm_source=archive#industry',
        )

    def test_navigation_relative_urls_become_root_relative(self):
        self.assertEqual(
            canonicalize_public_url('../research/index.html', resolve_page_relative=True),
            '/pages/research/',
        )
        self.assertEqual(
            canonicalize_public_url('../gassensing/mc_ld_h2.html', resolve_page_relative=True),
            '/pages/gassensing/mc_ld_h2.html',
        )

    def test_external_and_non_navigation_urls_are_not_modified(self):
        for value in ('https://example.com/index.html', 'mailto:seo@example.com', '#section', '/assets/index.html'):
            with self.subTest(value=value):
                self.assertEqual(canonicalize_public_url(value), value)


if __name__ == '__main__':
    unittest.main()
