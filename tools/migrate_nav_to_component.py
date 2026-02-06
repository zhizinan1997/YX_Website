#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

TARGET_MAPPING = {
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

EXCLUDE = set()

SCRIPT_TAG = '<script src="/assets/js/nav-loader.js"></script>'


def iter_target_files():
    for profile, entries in TARGET_MAPPING.items():
        for entry in entries:
            if entry.is_file() and entry.suffix == '.html':
                if entry in EXCLUDE:
                    continue
                yield profile, entry
            elif entry.is_dir():
                for f in sorted(entry.glob('*.html')):
                    if f in EXCLUDE:
                        continue
                    yield profile, f


def build_mount_block(profile: str) -> str:
    fallback_path = f'/assets/partials/nav-{profile}-noscript.html'
    try:
        fallback_html = (ROOT / fallback_path.lstrip('/')).read_text(encoding='utf-8')
    except Exception:
        fallback_html = '<div>导航不可用</div>'

    return (
        f'<div id="mc-nav-root" data-nav-profile="{profile}"></div>\n'
        f'<noscript>{fallback_html}</noscript>\n'
        f'{SCRIPT_TAG}'
    )


def strip_old_nav_scripts(content: str) -> str:
    # remove script blocks that only define legacy nav switch functions
    pattern = re.compile(r'<script>\s*(?:(?!</script>).)*(?:function\s+showPanel\s*\(|function\s+showPanelContact\s*\(|function\s+showPanelSolutions\s*\(|function\s+showPanelCases\s*\(|function\s+showPanelNews\s*\(|function\s+activateLinkTab\s*\().*?</script>', re.S)
    content = re.sub(pattern, '', content)

    # remove previously injected sync_nav dynamic block
    content = re.sub(r'\s*<!-- NAV_DYNAMIC_DATA_START -->.*?<!-- NAV_DYNAMIC_DATA_END -->\s*', '\n', content, flags=re.S)

    return content


def migrate_file(profile: str, path: Path) -> bool:
    text = path.read_text(encoding='utf-8', errors='ignore')
    original = text

    text = strip_old_nav_scripts(text)

    mount = build_mount_block(profile)
    if '<header class="vs-header">' in text:
        text2, n = re.subn(r'<header class="vs-header">.*?</header>', mount, text, count=1, flags=re.S)
        if n == 0:
            return False
    elif f'data-nav-profile="{profile}"' in text and 'id="mc-nav-root"' in text:
        text2 = re.sub(
            r'<div id="mc-nav-root" data-nav-profile="[a-z]+"></div>.*?<script src="/assets/js/nav-loader.js"></script>(?:\s*</noscript>)?',
            mount,
            text,
            count=1,
            flags=re.S
        )
    else:
        return False

    # Ensure nav-loader included exactly once in case file already had one
    first = text2.find(SCRIPT_TAG)
    if first != -1:
        second = text2.find(SCRIPT_TAG, first + len(SCRIPT_TAG))
        while second != -1:
            text2 = text2[:second] + text2[second + len(SCRIPT_TAG):]
            second = text2.find(SCRIPT_TAG, first + len(SCRIPT_TAG))

    # Remove any leftover legacy headers that may remain after historical sync artifacts.
    # Keep only the component mount block + noscript + loader.
    text2 = re.sub(r'\s*<header class="vs-header">.*?</header>\s*', '\n', text2, flags=re.S)

    # Deduplicate mount blocks if historical edits introduced duplicates.
    mount_block_pattern = re.compile(
        r'<div id="mc-nav-root" data-nav-profile="[a-z]+"></div>\s*<noscript>.*?</noscript>\s*<script src="/assets/js/nav-loader.js"></script>',
        re.S
    )
    blocks = list(mount_block_pattern.finditer(text2))
    if len(blocks) > 1:
        keep = blocks[0]
        cleaned = text2[:keep.end()]
        cursor = keep.end()
        for b in blocks[1:]:
            cleaned += text2[cursor:b.start()]
            cursor = b.end()
        cleaned += text2[cursor:]
        text2 = cleaned

    if text2 != original:
        path.write_text(text2, encoding='utf-8')
        return True
    return False


def main():
    changed = 0
    total = 0
    for profile, file in iter_target_files():
        total += 1
        if migrate_file(profile, file):
            changed += 1
            print(f'[OK] {file.relative_to(ROOT)} -> {profile}')
    print(f'\nDone. changed={changed}, scanned={total}')


if __name__ == '__main__':
    main()
