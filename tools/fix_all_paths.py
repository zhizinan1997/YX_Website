"""
Comprehensive fix for all broken paths after project reorganization.
Fixes:
1. Logo links (index.html -> correct relative path)
2. News page paths
3. Image/CSS/JS paths that weren't updated by the first script
4. Product page links
"""
import os
import re
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")


def get_relative_prefix(file_path: Path) -> str:
    """Calculate the relative path prefix to go back to root from a file's location."""
    rel = file_path.relative_to(ROOT)
    depth = len(rel.parts) - 1  # Subtract 1 for the file itself
    if depth == 0:
        return ''
    return '../' * depth


def fix_file(file_path: Path):
    """Fix all broken paths in a single HTML file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        try:
            content = file_path.read_text(encoding='gbk')
        except:
            print(f"Skipping {file_path} - encoding issue")
            return False

    original = content
    prefix = get_relative_prefix(file_path)
    
    # Skip files in root (no prefix needed)
    if not prefix:
        return False
    
    # Fix 1: Logo link (href="index.html" -> href="../../index.html" etc)
    content = re.sub(
        r'href=["\']index\.html["\']',
        f'href="{prefix}index.html"',
        content
    )
    
    # Fix 2: Standalone index.html links (in breadcrumbs etc)
    content = re.sub(
        r'href=["\']\.\/index\.html["\']',
        f'href="{prefix}index.html"',
        content
    )
    
    # Fix 3: Old paths that still use templates/lqgd format
    content = content.replace('templates/lqgd/css/', f'{prefix}assets/css/')
    content = content.replace('templates/lqgd/js/', f'{prefix}assets/js/')
    content = content.replace('templates/lqgd/images/', f'{prefix}assets/images/')
    
    # Fix 4: Old paths using scripts/ instead of assets/js/
    if 'src="scripts/' in content or "src='scripts/" in content:
        content = content.replace('src="scripts/', f'src="{prefix}assets/js/')
        content = content.replace("src='scripts/", f"src='{prefix}assets/js/")
    
    # Fix 5: Old paths using css/ instead of assets/css/
    if 'href="css/' in content or "href='css/" in content:
        content = content.replace('href="css/', f'href="{prefix}assets/css/')
        content = content.replace("href='css/", f"href='{prefix}assets/css/")
    
    # Fix 6: Old paths using images/ instead of assets/images/
    if 'src="images/' in content or "src='images/" in content:
        content = content.replace('src="images/', f'src="{prefix}assets/images/')
        content = content.replace("src='images/", f"src='{prefix}assets/images/")
    
    # Fix 7: Old paths using Video/ instead of assets/video/
    if 'src="Video/' in content or "src='Video/" in content:
        content = content.replace('src="Video/', f'src="{prefix}assets/video/')
        content = content.replace("src='Video/", f"src='{prefix}assets/video/")
    
    # Fix 8: Products links - products/ folder no longer exists in root
    content = re.sub(
        r'href=["\']products/products_show\.aspx',
        f'href="{prefix}pages/products/products_show.aspx',
        content
    )
    
    # Fix 9: News links - news/ -> pages/news/
    content = re.sub(
        r'href=["\']news/news_show\.aspx',
        f'href="{prefix}pages/news/news_show.aspx',
        content
    )
    
    # Fix 10: Direct news.aspx links
    content = content.replace('href="news.aspx', f'href="{prefix}pages/news/news.aspx')
    
    # Fix 11: f_logo.png path if still using old structure
    content = content.replace('src="f_logo.png"', f'src="{prefix}assets/images/f_logo.png"')
    
    # Fix 12: Other asset paths that might be relative but wrong
    # Handle paths that go up incorrectly (e.g., ../../ when they should be different)
    # This is tricky - we need to be careful here
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    
    return False


def main():
    html_files = list(ROOT.rglob('*.html'))
    print(f"Scanning {len(html_files)} HTML files...")
    
    fixed_count = 0
    for file_path in html_files:
        if 'archive' in str(file_path) or '原网页代码' in str(file_path):
            continue
        if fix_file(file_path):
            print(f"Fixed: {file_path}")
            fixed_count += 1
    
    print(f"\nDone! Fixed {fixed_count} files.")


if __name__ == '__main__':
    main()
