#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent

TARGETS = {
    'home': [
        ROOT / 'index.html',
        ROOT / 'pages/about',
        ROOT / 'pages/contact',
        ROOT / 'pages/news',
        ROOT / 'pages/careers',
    ],
    'gas': [
        ROOT / 'pages/gassensing',
        ROOT / 'pages/gassensing/cases',
        ROOT / 'pages/solutions',
        ROOT / 'pages/measurement',
        ROOT / 'pages/research',
        ROOT / 'pages/customization',
    ],
    'bio': [
        ROOT / 'pages/biosensing',
    ],
}

EXCLUDE = {
    ROOT / 'assets/partials/nav-home.html',
    ROOT / 'assets/partials/nav-gas.html',
    ROOT / 'assets/partials/nav-bio.html',
}

SCRIPT_TAG = '<script src="/assets/js/nav-loader.js"></script>'


def iter_files():
    for profile, entries in TARGETS.items():
        for entry in entries:
            if entry.is_file() and entry.suffix == '.html':
                yield profile, entry
            elif entry.is_dir():
                for f in sorted(entry.glob('*.html')):
                    yield profile, f


def main():
    errors = []

    for profile, file in iter_files():
        if file in EXCLUDE:
            continue
        try:
            text = file.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            errors.append(f'{file.relative_to(ROOT)}: unreadable ({e})')
            continue

        root_match = re.search(r'<div id="mc-nav-root" data-nav-profile="([a-z]+)"></div>', text)
        legacy_header = '<header class="vs-header">' in text
        legacy_nav = '<nav class="vs-nav' in text

        # Skip pages that are not nav-migrated targets (no mount and no legacy nav)
        if not root_match and not legacy_header and not legacy_nav:
            continue

        if not root_match:
            errors.append(f'{file.relative_to(ROOT)}: missing nav root mount')
        else:
            found = root_match.group(1)
            if found != profile:
                errors.append(f'{file.relative_to(ROOT)}: profile mismatch (found={found}, expected={profile})')
            if legacy_header:
                errors.append(f'{file.relative_to(ROOT)}: legacy header exists')
            if legacy_nav:
                errors.append(f'{file.relative_to(ROOT)}: legacy vs-nav exists')

        if SCRIPT_TAG not in text:
            errors.append(f'{file.relative_to(ROOT)}: missing nav-loader include')

    if errors:
        print('[verify-nav] FAILED')
        for err in errors:
            print(' -', err)
        sys.exit(1)

    print('[verify-nav] OK')


if __name__ == '__main__':
    main()
