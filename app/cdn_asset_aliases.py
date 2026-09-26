"""Resolve removed duplicate CDN files without changing their public URLs."""

from __future__ import annotations

import json
from pathlib import Path


_ALIASES_FILE = Path(__file__).with_name('cdn_asset_aliases.json')
CDN_ASSET_ALIASES: dict[str, str] = json.loads(_ALIASES_FILE.read_text(encoding='utf-8'))


def existing_cdn_asset_path(asset_root: Path, relative_path: str) -> str | None:
    """Return an existing path under asset_root, preferring a local override."""
    relative_path = str(relative_path or '')
    if (
        not relative_path
        or relative_path.startswith('/')
        or '\\' in relative_path
        or any(part in {'', '.', '..'} for part in relative_path.split('/'))
    ):
        return None

    root = Path(asset_root).resolve()
    for candidate_path in (relative_path, CDN_ASSET_ALIASES.get(relative_path)):
        if not candidate_path:
            continue
        candidate = (root / candidate_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate_path
    return None
