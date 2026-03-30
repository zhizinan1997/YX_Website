#!/usr/bin/env python3
"""Sanitize historical news article files and refresh news cards."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('APP_ENV', 'test')

import server  # noqa: E402

NEWS_DIR = ROOT / 'pages' / 'news'
NEWS_INDEX = NEWS_DIR / 'news.html'


def sanitize_article_file(file_path: Path):
    original_html = file_path.read_text(encoding='utf-8')
    detail = server.parse_news_article_html(file_path)
    if not detail:
        return False, None

    rebuilt_html = server.build_news_article_html(
        detail.get('title', ''),
        detail.get('date', ''),
        detail.get('image_url', ''),
        detail.get('content_html', ''),
    )
    if rebuilt_html != original_html:
        file_path.write_text(rebuilt_html, encoding='utf-8')
        changed = True
    else:
        changed = False

    refreshed = server.parse_news_article_html(file_path)
    return changed, refreshed or detail


def main() -> int:
    if not NEWS_DIR.exists() or not NEWS_INDEX.exists():
        print('news directory or news index is missing', file=sys.stderr)
        return 1

    article_files = sorted(NEWS_DIR.glob('news_show.aspx_id_*.html'))
    if not article_files:
        print('no article files found')
        return 0

    items_by_filename = {}
    for item in server.get_all_news_items():
        filename = Path(str(item.get('link') or '')).name
        if filename:
            items_by_filename[filename] = item

    article_changed = 0
    article_skipped = []
    card_payloads = []

    for file_path in article_files:
        changed, detail = sanitize_article_file(file_path)
        if detail is None:
            article_skipped.append(file_path.name)
            continue
        if changed:
            article_changed += 1

        meta = items_by_filename.get(file_path.name, {})
        title = detail.get('title') or meta.get('title', '')
        date = detail.get('date') or meta.get('date', '')
        image_url = detail.get('image_url') or meta.get('image', '')
        image_url, summary = server.derive_news_cover_and_summary(
            detail.get('content_html', ''),
            image_url,
            meta.get('desc', ''),
        )
        card_payloads.append(
            (
                file_path.name,
                server.build_news_card_html(
                    file_path.name,
                    str(meta.get('category') or 'enterprise'),
                    str(meta.get('division') or ''),
                    image_url,
                    date,
                    title,
                    summary,
                    hidden=bool(meta.get('hidden', False)),
                ).lstrip(),
            )
        )

    index_original = NEWS_INDEX.read_text(encoding='utf-8')
    index_updated = index_original
    cards_replaced = 0
    missing_cards = []

    for filename, card_html in card_payloads:
        pattern = server.build_news_card_regex(filename)
        index_updated, count = pattern.subn(card_html, index_updated, count=1)
        if count:
            cards_replaced += 1
            index_updated, _ = server.dedupe_news_cards(index_updated, filename)
        else:
            missing_cards.append(filename)

    index_updated = re.sub(r'\n(?:[ \t]*\n){2,}', '\n\n', index_updated)

    index_changed = index_updated != index_original
    if index_changed:
        NEWS_INDEX.write_text(index_updated, encoding='utf-8')

    print(
        f'sanitized_articles={article_changed} '
        f'total_articles={len(article_files)} '
        f'updated_cards={cards_replaced} '
        f'index_changed={int(index_changed)}'
    )
    if article_skipped:
        print('skipped_articles=' + ','.join(article_skipped))
    if missing_cards:
        print('missing_cards=' + ','.join(missing_cards))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
