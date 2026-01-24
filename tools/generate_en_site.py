import os
import shutil
import re


# Get the absolute path of the 'tools' directory (where this script resides)
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the project root directory (one level up from 'tools')
ROOT_DIR = os.path.dirname(TOOLS_DIR)

PAGES_CN_DIR = os.path.join(ROOT_DIR, 'pages')
PAGES_EN_DIR = os.path.join(ROOT_DIR, 'pages_en')
INDEX_CN = os.path.join(ROOT_DIR, 'index.html')
INDEX_EN = os.path.join(ROOT_DIR, 'index_en.html')

# Dictionary for static translation (Nav Bar & Footer)
TRANSLATIONS = {
    # Nav
    "产品": "Products",
    "解决方案": "Solutions",
    "服务案例": "Cases",
    "公司简介": "About",
    "线上店铺": "Shop",
    "联系我们": "Contact",
    "首页": "Home",
    
    # Mega Menu
    "新品推荐": "New Arrivals",
    "行业分类": "Industries",
    "测量对象": "Parameters",
    "产品种类": "Categories",
    "产品列表": "All Products",
    "最新发布": "Latest Releases",
    "应用领域": "Applications",
    "搜索产品": "Search",
    "查看所有产品": "View All",
    "行业解决方案": "Solutions",
    "科研服务": "Research",
    "精选案例": "Featured",
    "所有案例": "All Cases",
    "查看全部案例": "View All",
    "加入我们": "Join Us",
    "联系方式": "Contact Info",
    "合作招募": "Partners",
    "成长空间": "Growth",
    "人才理念": "Culture",
    "在线招聘": "Careers",
    "在线留言": "Feedback",
    
    # Common
    "元芯传感": "Metachip",
    "在线服务中": "Online",
    "了解更多": "Learn More",
    "立即咨询": "Contact Us",
    "版权所有": "All Rights Reserved",
    "准备好开始您的项目了吗？": "Ready to start your project?",
    "我们的工程师随时准备为您提供专业建议。": "Our engineers are ready to provide professional advice."
}

def setup_directories():
    if os.path.exists(PAGES_EN_DIR):
        shutil.rmtree(PAGES_EN_DIR)
    shutil.copytree(PAGES_CN_DIR, PAGES_EN_DIR)
    shutil.copy2(INDEX_CN, INDEX_EN)
    print("Static files copied.")

def get_relative_link(from_file, to_file):
    return os.path.relpath(to_file, os.path.dirname(from_file))

def process_file(file_path, is_en):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. Clean up old i18n script
        content = content.replace('<script src="../../assets/js/i18n.js"></script>', '')
        content = content.replace('<script src="../../../assets/js/i18n.js"></script>', '')
        content = content.replace('<script src="assets/js/i18n.js"></script>', '')
        # Regex for robustness
        content = re.sub(r'\s*<script src="[^"]*assets/js/i18n.js"></script>', '', content)
        content = re.sub(r'\s*<!-- I18N Translation -->', '', content)

        rel_path = os.path.relpath(file_path, ROOT_DIR)
        
        # Calculate counterpart path
        if is_en:
            # Current is EN. Counterpart is CN.
            # pages_en/x.html -> pages/x.html
            # index_en.html -> index.html
            if rel_path == 'index_en.html':
                 counterpart_rel = 'index.html'
            else:
                 # rel_path starts with pages_en/
                 counterpart_rel = 'pages/' + rel_path[9:] # strip pages_en/ set pages/
            
            counterpart_abs = os.path.join(ROOT_DIR, counterpart_rel)
            link_to_counterpart = get_relative_link(file_path, counterpart_abs)
            
            # 2. Rewrite Links (EN only)
            # Replace 'pages/' with 'pages_en/' in hrefs
            # Replace 'index.html' with 'index_en.html' in hrefs
            
            def link_rewriter(match):
                prefix = match.group(1) # href="
                url = match.group(2)
                suffix = match.group(3) # "
                
                if url.startswith('http') or url.startswith('#') or url.startswith('mailto'):
                    return match.group(0)
                
                # Rewriting logic
                new_url = url
                
                # Check for pages/ reference
                if '/pages/' in new_url:
                    new_url = new_url.replace('/pages/', '/pages_en/')
                elif new_url.startswith('pages/'):
                    new_url = new_url.replace('pages/', 'pages_en/')
                elif '../pages/' in new_url:
                     new_url = new_url.replace('../pages/', '../pages_en/')
                
                if new_url.endswith('index.html'):
                    if new_url == '../../index.html': # From depth 2 to root
                        new_url = '../../index_en.html'
                    elif new_url == '../../../index.html': # From depth 3
                        new_url = '../../../index_en.html'
                    elif new_url == 'index.html': # If in root
                         pass
                    
                return f'{prefix}{new_url}{suffix}'

            content = re.sub(r'(href=")([^"]*)(")', link_rewriter, content)

            # Toggle Button: "CN" links to counterpart, "EN" is active text
            # Previous HTML: <a href="..." id="language-toggle" ...>CN / EN</a>
            # OR Modified CN HTML: <span ...>CN</span> / <a ...>EN</a>
            # We replace it entirely.
            toggle_pattern = r'(?:<a\s+href="[^"]*"\s+(?:id="language-toggle")?[^>]*>\s*CN\s*/\s*EN\s*</a>)|(?:<span[^>]*>\s*CN\s*</span>\s*/\s*<a[^>]*>\s*EN\s*</a>)'
            new_toggle = f'<a href="{link_to_counterpart}" style="font-size: 14px; font-weight: 500;">CN</a> / <span style="font-size: 14px; font-weight: 700; color:white;">EN</span>'
            content = re.sub(toggle_pattern, new_toggle, content, flags=re.IGNORECASE)
            
            # 3. Translate Text (EN only)
            for ch, en in TRANSLATIONS.items():
                # Simple replace, might be dangerous but efficient for Nav
                # Avoid replacing inside tags (attributes).
                # Regex >text< replace.
                # Pattern: (>)([^<]*?ch[^<]*?)(<)
                # This is hard. Just simple string replace for now, assuming Chinese keys are unique enough.
                if ch in content:
                    content = content.replace(ch, en)
                    
            # Fix Language attribute
            content = content.replace('lang="zh-CN"', 'lang="en"')

        else:
            # Current is CN. Counterpart is EN.
            # pages/x.html -> pages_en/x.html
            # index.html -> index_en.html
            if rel_path == 'index.html':
                 counterpart_rel = 'index_en.html'
            else:
                 counterpart_rel = 'pages_en/' + rel_path[6:]
            
            counterpart_abs = os.path.join(ROOT_DIR, counterpart_rel)
            link_to_counterpart = get_relative_link(file_path, counterpart_abs)
            
            # Toggle Button: "CN" active, "EN" links
            toggle_pattern = r'(<a\s+href="[^"]*"\s+(?:id="language-toggle")?[^>]*>\s*CN\s*/\s*EN\s*</a>)'
            new_toggle = f'<span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="{link_to_counterpart}" style="font-size: 14px; font-weight: 500;">EN</a>'
            
            # Also support finding the one we just replaced in EN (if we process CN after EN? No separate loops)
            # Match the original JS one or the static one
            content = re.sub(toggle_pattern, new_toggle, content, flags=re.IGNORECASE)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    setup_directories()
    
    # Process EN files
    files_en = []
    files_en.append(INDEX_EN)
    for dirpath, _, filenames in os.walk(PAGES_EN_DIR):
        for f in filenames:
            if f.endswith('.html'):
                files_en.append(os.path.join(dirpath, f))
                
    print(f"Processing {len(files_en)} EN files...")
    for f in files_en:
        process_file(f, True)
        
    # Process CN files
    files_cn = []
    files_cn.append(INDEX_CN)
    for dirpath, _, filenames in os.walk(PAGES_CN_DIR):
        for f in filenames:
            if f.endswith('.html'):
                files_cn.append(os.path.join(dirpath, f))
                
    print(f"Processing {len(files_cn)} CN files...")
    for f in files_cn:
        process_file(f, False)
        
    print("Done.")

if __name__ == '__main__':
    main()
