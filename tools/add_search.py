"""
批量为所有 HTML 页面添加搜索功能
Auto-adds search CSS and JS to all HTML pages
"""

import os
import re
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 需要处理的目录
PAGES_DIR = ROOT_DIR / 'pages'

# 排除的目录
EXCLUDE_DIRS = {'admin', 'hnmetachip_site'}

def get_relative_path(html_file, target_file):
    """计算从 HTML 文件到目标文件的相对路径"""
    html_dir = html_file.parent
    try:
        rel = os.path.relpath(ROOT_DIR / target_file, html_dir)
        return rel.replace('\\', '/')
    except ValueError:
        return target_file

def add_search_to_file(html_file):
    """为单个 HTML 文件添加搜索功能"""
    try:
        content = html_file.read_text(encoding='utf-8')
        original_content = content
        modified = False
        
        # 计算相对路径
        css_path = get_relative_path(html_file, 'assets/css/search.css')
        js_path = get_relative_path(html_file, 'assets/js/search.js')
        
        # 1. 添加搜索 CSS (在 </head> 前，或 chatbot.css 后)
        if 'search.css' not in content:
            # 尝试在 chatbot.css 后添加
            if 'chatbot.css' in content:
                pattern = r'(<link[^>]*chatbot\.css[^>]*>)'
                replacement = r'\1\n  <!-- Site Search -->\n  <link rel="stylesheet" href="' + css_path + '">'
                new_content = re.sub(pattern, replacement, content, count=1)
                if new_content != content:
                    content = new_content
                    modified = True
            # 否则在 </head> 前添加
            elif '</head>' in content:
                content = content.replace(
                    '</head>',
                    f'  <!-- Site Search -->\n  <link rel="stylesheet" href="{css_path}">\n</head>'
                )
                modified = True
        
        # 2. 添加搜索 JS (在 </body> 前，或 chatbot.js 后)
        if 'search.js' not in content:
            # 尝试在 chatbot.js 后添加
            if 'chatbot.js' in content:
                pattern = r'(<script[^>]*chatbot\.js[^>]*>\s*</script>)'
                replacement = r'\1\n\n  <!-- 全站搜索 -->\n  <script src="' + js_path + '"></script>'
                new_content = re.sub(pattern, replacement, content, count=1)
                if new_content != content:
                    content = new_content
                    modified = True
            # 否则在 </body> 前添加
            elif '</body>' in content:
                content = content.replace(
                    '</body>',
                    f'\n  <!-- 全站搜索 -->\n  <script src="{js_path}"></script>\n</body>'
                )
                modified = True
        
        # 3. 更新搜索按钮 (添加 vs-search-trigger 类)
        # 查找搜索图标链接并添加类
        search_icon_pattern = r'<a\s+href="#"\s*>\s*<i\s+class="fas fa-search"'
        if re.search(search_icon_pattern, content) and 'vs-search-trigger' not in content:
            content = re.sub(
                r'(<a\s+href="#")(\s*>)(\s*<i\s+class="fas fa-search")',
                r'\1 class="vs-search-trigger" title="搜索 (Ctrl+K)"\2\3',
                content
            )
            modified = True
        
        if modified:
            html_file.write_text(content, encoding='utf-8')
            return True
        return False
        
    except Exception as e:
        print(f"  Error processing {html_file}: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("批量添加搜索功能到所有 HTML 页面")
    print("=" * 60)
    
    # 收集所有 HTML 文件
    html_files = []
    
    # 主页
    index_file = ROOT_DIR / 'index.html'
    if index_file.exists():
        html_files.append(index_file)
    
    # pages 目录下的所有 HTML 文件
    for html_file in PAGES_DIR.rglob('*.html'):
        # 跳过排除的目录
        skip = False
        for exclude in EXCLUDE_DIRS:
            if exclude in str(html_file):
                skip = True
                break
        if not skip:
            html_files.append(html_file)
    
    print(f"\n找到 {len(html_files)} 个 HTML 文件")
    
    # 处理每个文件
    updated = 0
    skipped = 0
    
    for html_file in html_files:
        rel_path = html_file.relative_to(ROOT_DIR)
        if add_search_to_file(html_file):
            print(f"  ✓ 更新: {rel_path}")
            updated += 1
        else:
            skipped += 1
    
    print("\n" + "=" * 60)
    print(f"完成! 更新: {updated}, 跳过: {skipped}")
    print("=" * 60)

if __name__ == '__main__':
    main()
