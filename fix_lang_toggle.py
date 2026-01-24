#!/usr/bin/env python3
"""
Script to fix language toggle on all English pages (pages_en).
Changes <span>CN</span> to a clickable link pointing to the corresponding Chinese page.
"""
import os
import re
from pathlib import Path

# Base directory
ROOT_DIR = Path(__file__).parent
PAGES_EN_DIR = ROOT_DIR / 'pages_en'

def get_chinese_page_path(english_path):
    """Convert English page path to corresponding Chinese page path."""
    # Get relative path from pages_en
    rel_path = english_path.relative_to(PAGES_EN_DIR)
    
    # Map to pages folder
    # pages_en/gassensing/xxx.html -> pages/gassensing/xxx.html
    # pages_en/biosensing/xxx.html -> pages/biosensing/xxx.html
    # etc.
    return f"../../pages/{rel_path}"

def fix_language_toggle(filepath):
    """Fix the language toggle in a single file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        
        # Calculate correct Chinese page path
        chinese_page_path = get_chinese_page_path(filepath)
        
        # Pattern 1: <span style="...">CN</span> / <a href="...">EN</a>
        # Replace to: <a href="chinese_path" style="...">CN</a> / <span style="...">EN</span>
        
        # Find and fix the language toggle pattern
        # Current incorrect pattern (CN is span, EN is link):
        # <span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="..." style="font-size: 14px; font-weight: 500;">EN</a>
        
        pattern1 = r'<span style="font-size: 14px; font-weight: 700; color:white;">CN</span>\s*/\s*<a href="[^"]*" style="font-size: 14px; font-weight: 500;">EN</a>'
        
        replacement1 = f'<a href="{chinese_page_path}" style="font-size: 14px; font-weight: 500;">CN</a> / <span style="font-size: 14px; font-weight: 700; color:white;">EN</span>'
        
        if re.search(pattern1, content):
            content = re.sub(pattern1, replacement1, content)
        
        # Also handle variations without inline styles
        pattern2 = r'<span[^>]*>CN</span>\s*/\s*<a[^>]*>EN</a>'
        if re.search(pattern2, content) and content == original_content:
            # Only apply if first pattern didn't match
            content = re.sub(pattern2, 
                f'<a href="{chinese_page_path}" style="font-size: 14px; font-weight: 500;">CN</a> / <span style="font-size: 14px; font-weight: 700; color:white;">EN</span>', 
                content)
        
        # Only write if content changed
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            print(f"  Fixed: {filepath.name}")
            return True
        else:
            print(f"  No changes: {filepath.name}")
            return False
            
    except Exception as e:
        print(f"  Error fixing {filepath.name}: {e}")
        return False

def main():
    print("=" * 60)
    print("Fixing Language Toggle on English Pages")
    print("=" * 60)
    print(f"Target folder: {PAGES_EN_DIR}")
    print()
    print("Change: CN (text) -> CN (link to Chinese page)")
    print("        EN (link) -> EN (text, current page)")
    print()
    
    fixed_count = 0
    
    # Process all subfolders
    subfolders = ['gassensing', 'biosensing', 'about', 'contact', 'news', 'careers', 
                  'customization', 'honors', 'research', 'solutions', 'measurement']
    
    for subfolder in subfolders:
        folder_path = PAGES_EN_DIR / subfolder
        if folder_path.exists():
            print(f"Processing pages_en/{subfolder}/:")
            for filepath in sorted(folder_path.glob('*.html')):
                if fix_language_toggle(filepath):
                    fixed_count += 1
            
            # Also check for subdirectories
            for subdir in folder_path.iterdir():
                if subdir.is_dir():
                    print(f"Processing pages_en/{subfolder}/{subdir.name}/:")
                    for filepath in sorted(subdir.glob('*.html')):
                        if fix_language_toggle(filepath):
                            fixed_count += 1
            print()
    
    print("=" * 60)
    print(f"Complete! Fixed {fixed_count} files.")
    print("=" * 60)

if __name__ == '__main__':
    main()
