"""
Remove 联系电话 and 公司邮箱 from the contact mega menu across all HTML files.
"""
import re
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")

# Pattern to match the li items we want to remove
# These are in the vs-mega-list-v2 for 联系方式 panel
patterns = [
    r'<li><a href="[^"]*">联系电话</a></li>\s*\r?\n?',
    r'<li><a href="[^"]*">公司邮箱</a></li>\s*\r?\n?',
    r"<li><a href='[^']*'>联系电话</a></li>\s*\r?\n?",
    r"<li><a href='[^']*'>公司邮箱</a></li>\s*\r?\n?",
]

def fix_file(file_path: Path):
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        try:
            content = file_path.read_text(encoding='gbk')
        except:
            return False
    
    original = content
    
    for pattern in patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)
    
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
    
    print(f"\nDone! Removed menu items from {fixed_count} files.")

if __name__ == '__main__':
    main()
