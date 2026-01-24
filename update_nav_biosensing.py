#!/usr/bin/env python3
"""
Script to update navigation bars for all pages in /pages/biosensing folder.
Removes "解决方案" and "洞察与资讯" navigation items.
Changes "产品" link to point to index.html?filter=sensor
"""
import os
import re
from pathlib import Path

# Base directory
BIOSENSING_DIR = Path(__file__).parent / 'pages' / 'biosensing'

# Define the new simplified navigation bar for biosensing pages
BIOSENSING_NAV_TEMPLATE = '''<header class="vs-header">
        <div class="vs-container vs-header__inner">
            <div style="display: flex; align-items: center;">
                <a href="../../index.html" class="vs-logo">
                    <img src="../../assets/images/logo.png" alt="Metachip Logo"
                        style="filter: brightness(0) invert(1);">
                    METACHIP
                </a>
            </div>

            <nav class="vs-nav">
                <ul class="vs-nav__list">
                    <li class="vs-nav__item">
                        <a href="index.html?filter=sensor" class="vs-nav__link">产品</a>
                    </li>
                    <li class="vs-nav__item"><a href="../../pages/about/about.html" class="vs-nav__link">公司简介</a></li>
                    <li class="vs-nav__item"><a href="../../pages/contact/contact.html" class="vs-nav__link">联系我们</a>
                    </li>
                </ul>
            </nav>

            <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#" class="vs-search-trigger" title="搜索 (Ctrl+K)"><i class="fas fa-search"></i></a>
                <span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="../../pages_en/biosensing/index.html" style="font-size: 14px; font-weight: 500;">EN</a>
            </div>
        </div>
    </header>'''


def update_nav_in_file(filepath):
    """Update the navigation in a single file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        
        # Find and replace the existing header
        header_pattern = r'<header class="vs-header">.*?</header>'
        header_match = re.search(header_pattern, content, re.DOTALL)
        
        if not header_match:
            print(f"  Skipping {filepath.name}: No header found")
            return False
        
        # Replace the header
        content = re.sub(header_pattern, BIOSENSING_NAV_TEMPLATE, content, flags=re.DOTALL)
        
        # Only write if content changed
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            print(f"  Updated: {filepath.name}")
            return True
        else:
            print(f"  No changes: {filepath.name}")
            return False
            
    except Exception as e:
        print(f"  Error updating {filepath.name}: {e}")
        return False

def main():
    print("=" * 60)
    print("Updating Biosensing Navigation Bars")
    print("=" * 60)
    print(f"Target folder: {BIOSENSING_DIR}")
    print()
    print("Changes applied:")
    print("  - Removed: 解决方案")
    print("  - Removed: 洞察与资讯")
    print("  - Changed: 产品 -> index.html?filter=sensor")
    print()
    
    updated_count = 0
    
    # Process all HTML files in biosensing folder
    print("Processing files in pages/biosensing/:")
    for filepath in sorted(BIOSENSING_DIR.glob('*.html')):
        if update_nav_in_file(filepath):
            updated_count += 1
    
    print()
    print("=" * 60)
    print(f"Complete! Updated {updated_count} files.")
    print("=" * 60)

if __name__ == '__main__':
    main()
