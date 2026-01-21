"""
Second pass fix for remaining path issues.
Fixes:
1. Over-corrected paths (e.g., ../../../ when should be ../../)
2. Old page references like news.aspx_category_id_0.html
3. Wrong relative index.html paths
"""
import os
import re
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")


def get_correct_prefix(file_path: Path) -> str:
    """Calculate the correct relative path prefix from file to root."""
    rel = file_path.relative_to(ROOT)
    depth = len(rel.parts) - 1
    if depth == 0:
        return ''
    return '../' * depth


def fix_news_pages(file_path: Path):
    """Fix paths in news pages specifically."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        try:
            content = file_path.read_text(encoding='gbk')
        except:
            return False
    
    original = content
    prefix = get_correct_prefix(file_path)
    
    # Fix over-corrected paths (3 levels back when should be 2)
    # For files in pages/news/, prefix should be ../../
    if 'pages/news' in str(file_path) or 'pages\\news' in str(file_path):
        # Fix ../../../ to ../../
        content = content.replace('../../../assets/', '../../assets/')
        content = content.replace('../../../pages/', '../../pages/')
        content = content.replace('../../../index.html', '../../index.html')
        
        # Fix old ../index.html to ../../index.html
        content = re.sub(r'href=["\']\.\.\/index\.html["\']', 'href="../../index.html"', content)
        
        # Fix old news page references
        content = content.replace('href="../news.aspx_category_id_0.html"', 'href="news.html"')
        content = content.replace("href='../news.aspx_category_id_0.html'", "href='news.html'")
        
        # Fix old about page references
        content = content.replace('../about.aspx_page_about.html', '../../pages/about/about.html')
        
        # Fix old contact page references
        content = content.replace('../contact.aspx_page_contact.html', '../../pages/contact/contact.html')
    
    # Fix for pages in pages/products/
    if 'pages/products' in str(file_path) or 'pages\\products' in str(file_path):
        content = content.replace('../../../assets/', '../../assets/')
        content = content.replace('../../../pages/', '../../pages/')
        content = content.replace('../../../index.html', '../../index.html')
        content = re.sub(r'href=["\']\.\.\/index\.html["\']', 'href="../../index.html"', content)
    
    # Fix for other pages folders (about, contact, careers, etc.)
    for folder in ['about', 'contact', 'careers', 'services', 'honors', 'solutions']:
        if f'pages/{folder}' in str(file_path) or f'pages\\{folder}' in str(file_path):
            content = content.replace('../../../assets/', '../../assets/')
            content = content.replace('../../../pages/', '../../pages/')
            content = content.replace('../../../index.html', '../../index.html')
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def main():
    html_files = list(ROOT.rglob('*.html'))
    print(f"Scanning {len(html_files)} HTML files for second pass fixes...")
    
    fixed_count = 0
    for file_path in html_files:
        if 'archive' in str(file_path) or '原网页代码' in str(file_path):
            continue
        if fix_news_pages(file_path):
            print(f"Fixed: {file_path}")
            fixed_count += 1
    
    print(f"\nDone! Fixed {fixed_count} files in second pass.")


if __name__ == '__main__':
    main()
