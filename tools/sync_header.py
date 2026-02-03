import os
import re

# Base paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCE_FILE = 'pages/gassensing/index.html'

# Content from <header>...</header> in pages/gassensing/index.html
# I will use a placeholder for relative paths to reconstruct later.
# 
# Key Links in Source (located in pages/gassensing/):
# ../../index.html -> ROOT/index.html
# ../../assets/images/logo.png -> ROOT/assets/images/logo.png
# all-products.html -> ROOT/pages/gassensing/all-products.html
# ... (lots of links)
# 
# Strategy:
# 1. Take the RAW header HTML string.
# 2. Identify all `href="..."` and `src="..."`.
# 3. Convert them to absolute-like paths (starting with /) based on the source file location.
#    e.g. href="all-products.html" -> href="/pages/gassensing/all-products.html"
#    e.g. href="../../index.html" -> href="/index.html"
# 4. For each target file:
#    a. Calculate relative path to root (e.g. ../../)
#    b. Replace all absolute-like paths in the template with `rel_prefix + path_without_leading_slash`.
#    c. Replace the file's header.

RAW_HEADER = r'''<header class="vs-header">
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
                    <li class="vs-nav__item vs-nav__item--has-mega">
                        <a href="all-products.html" class="vs-nav__link">产品</a>
                        <!-- Compact Inficon Style Mega Menu -->
                        <div class="vs-mega-menu">
                            <div class="vs-mega-sidebar">
                                <div class="vs-mega-tab active" onmouseover="showPanel('new', this)">
                                    新品推荐 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanel('industry', this)">
                                    行业分类 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanel('target', this)">
                                    测量对象 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanel('type', this)">
                                    产品种类 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanel('list', this)">
                                    产品列表 <i class="fas fa-chevron-right"></i>
                                </div>
                            </div>
                            <div class="vs-mega-content">
                                <!-- Panel: New -->
                                <div id="panel-new" class="vs-mega-panel active">
                                    <h3>新品推荐</h3>
                                    <div class="vs-mega-grid-v2" id="recommendationsPanel">
                                        <div>
                                            <span class="vs-mega-sublist-title">最新发布</span>
                                            <ul class="vs-mega-list-v2" id="latestReleasesList">
                                                <li><a href="#">加载中...</a></li>
                                            </ul>
                                        </div>
                                        <div>
                                            <span class="vs-mega-sublist-title">应用领域</span>
                                            <ul class="vs-mega-list-v2" id="applicationAreasList">
                                                <li><a href="#">加载中...</a></li>
                                            </ul>
                                        </div>
                                    </div>
                                    <div class="vs-mega-action">
                                        <a href="#" class="vs-btn-search">搜索产品 <i class="fas fa-search"></i></a>
                                    </div>
                                </div>

                                <!-- Panel: Industry -->
                                <div id="panel-industry" class="vs-mega-panel">
                                    <h3>行业分类</h3>
                                    <div class="vs-mega-grid-v2">
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="../../pages/solutions/industry-hydrogen.html">氢能源产业链</a>
                                                </li>
                                                <li><a
                                                        href="../../pages/solutions/industry-power-safety.html">智慧电力安全</a>
                                                </li>
                                                <li><a
                                                        href="../../pages/solutions/industry-leak-detection.html">工业检漏监测</a>
                                                </li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a
                                                        href="../../pages/solutions/industry-energy-storage.html">绿色能源存储</a>
                                                </li>
                                                <li><a href="../../pages/solutions/industry-environment.html">大气环境监测</a>
                                                </li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>

                                <!-- Panel: Target -->
                                <div id="panel-target" class="vs-mega-panel">
                                    <h3>测量对象</h3>
                                    <div class="vs-mega-grid-v2">
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="../../pages/measurement/measurement-hydrogen.html">氢气
                                                        (H2)</a></li>
                                                <li><a href="../../pages/measurement/measurement-humidity.html">湿度
                                                        (RH)</a></li>
                                                <li><a
                                                        href="../../pages/measurement/measurement-dissolved-hydrogen.html">溶解氢</a>
                                                </li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a
                                                        href="../../pages/measurement/measurement-oil-water.html">油中水含量</a>
                                                </li>
                                                <li><a href="../../pages/measurement/measurement-dewpoint.html">露点
                                                        (Td)</a></li>
                                                <li><a href="../../pages/measurement/measurement-pressure.html">压力
                                                        (P)</a>
                                                </li>

                                            </ul>
                                        </div>
                                    </div>
                                </div>

                                <!-- Panel: Type -->
                                <div id="panel-type" class="vs-mega-panel">
                                    <h3>产品种类</h3>
                                    <div class="vs-mega-grid-v2" id="categoriesPanel">
                                        <div>
                                            <ul class="vs-mega-list-v2" id="categoriesLeft">
                                                <li><a href="#">加载中...</a></li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2" id="categoriesRight">
                                                <li><a href="#">加载中...</a></li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>

                                <!-- Panel: List -->
                                <div id="panel-list" class="vs-mega-panel">
                                    <h3>产品列表</h3>
                                    <div class="vs-mega-grid-v2" id="dynamic-product-list">
                                        <!-- 产品由JS动态生成 -->
                                    </div>
                                    <div style="margin-top: 20px;">
                                        <a href="all-products.html" class="vs-mega-view-all"
                                            style="color: var(--color-primary); font-weight: 600;">查看所有产品 <i
                                                class="fas fa-arrow-right"
                                                style="margin-left: 6px; font-size: 12px;"></i></a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </li>
                    <li class="vs-nav__item vs-nav__item--has-mega">
                        <a href="../solutions/solutions-index.html" class="vs-nav__link">解决方案</a>
                        <div class="vs-mega-menu vs-mega-menu--contact">
                            <div class="vs-mega-sidebar">
                                <div class="vs-mega-tab active" onmouseover="showPanelSolutions('industry', this)">
                                    行业解决方案 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanelSolutions('research', this)">
                                    科研服务 <i class="fas fa-chevron-right"></i>
                                </div>
                            </div>
                            <div class="vs-mega-content">
                                <div id="panel-solutions-industry" class="vs-mega-panel active">
                                    <h3>行业解决方案</h3>
                                    <div class="vs-mega-grid-v2">
                                        <ul class="vs-mega-list-v2">
                                            <li><a href="../../pages/solutions/industry-hydrogen.html">氢能源产业链</a></li>
                                            <li><a href="../../pages/solutions/industry-power-safety.html">智慧电力安全</a>
                                            </li>
                                            <li><a href="../../pages/solutions/industry-leak-detection.html">工业检漏监测</a>
                                            </li>
                                            <li><a href="../../pages/solutions/industry-energy-storage.html">绿色能源存储</a>
                                            </li>
                                            <li><a href="../../pages/solutions/industry-environment.html">大气环境监测</a>
                                            </li>
                                        </ul>
                                    </div>
                                </div>
                                <div id="panel-solutions-research" class="vs-mega-panel">
                                    <h3>科研服务</h3>
                                    <div class="vs-mega-grid-v2">
                                        <ul class="vs-mega-list-v2">
                                            <li><a href="../research/micro-nano.html">传感器微纳加工</a></li>
                                            <li><a href="../research/development.html">传感器开发、测试与应用</a></li>
                                            <li><a href="../research/cooperation.html">产学研深度合作</a></li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </li>
                    <li class="vs-nav__item vs-nav__item--has-mega">
                        <a href="service-cases.html" class="vs-nav__link">服务案例</a>
                        <div class="vs-mega-menu vs-mega-menu--contact">
                            <div class="vs-mega-sidebar">
                                <div class="vs-mega-tab active" onmouseover="showPanelCases('featured', this)">
                                    精选案例 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanelCases('all', this)">
                                    所有案例 <i class="fas fa-chevron-right"></i>
                                </div>
                            </div>
                            <div class="vs-mega-content">
                                <!-- Panel: Featured -->
                                <div id="panel-cases-featured" class="vs-mega-panel active">
                                    <h3>精选案例</h3>
                                    <div class="vs-mega-grid-v2">
                                        <ul class="vs-mega-list-v2">
                                            <li><a href="cases/case-1-truck.html">氢能重卡氢气检测</a></li>
                                            <li><a href="cases/case-6-train.html">氢能源列车检测</a></li>
                                            <li><a href="cases/case-4-pipeline-safety.html">输氢管道人员安全</a></li>
                                            <li><a href="cases/case-12-gas-system.html">科研实验室配气</a></li>
                                            <li><a href="cases/case-13-diesel-engine.html">柴油机真空检漏</a></li>
                                        </ul>
                                    </div>
                                </div>
                                <!-- Panel: All -->
                                <div id="panel-cases-all" class="vs-mega-panel">
                                    <h3>更多案例</h3>
                                    <p style="margin-bottom:20px; color:#666; font-size:14px;">浏览我们在各个行业的成功应用案例。</p>
                                    <a href="service-cases.html" class="vs-mega-view-all"
                                        style="color: var(--color-primary); font-weight: 600;">查看全部案例 <i
                                            class="fas fa-arrow-right"
                                            style="margin-left: 6px; font-size: 12px;"></i></a>
                                </div>
                            </div>
                        </div>
                    </li>
                    <li class="vs-nav__item"><a href="../about/about.html" class="vs-nav__link">公司简介</a></li>
                    <li class="vs-nav__item"><a href="https://shop176972283.taobao.com" target="_blank"
                            class="vs-nav__link">线上店铺</a></li>
                    <li class="vs-nav__item vs-nav__item--has-mega">
                        <a href="../../pages/contact/contact.html" class="vs-nav__link">联系我们</a>
                        <div class="vs-mega-menu vs-mega-menu--contact">
                            <div class="vs-mega-sidebar">
                                <div class="vs-mega-tab active" onmouseover="showPanelContact('join', this)">
                                    加入我们 <i class="fas fa-chevron-right"></i>
                                </div>
                                <div class="vs-mega-tab" onmouseover="showPanelContact('contact', this)">
                                    联系方式 <i class="fas fa-chevron-right"></i>
                                </div>
                            </div>
                            <div class="vs-mega-content">
                                <!-- Panel: Join -->
                                <div id="panel-contact-join" class="vs-mega-panel active">
                                    <h3>加入我们</h3>
                                    <div class="vs-mega-grid-v2">
                                        <ul class="vs-mega-list-v2">
                                            <li><a href="../../pages/careers/partners.html">合作招募</a></li>
                                            <li><a href="../../pages/careers/growth.html">成长空间</a></li>
                                            <li><a href="../../pages/careers/talent.html">人才理念</a></li>
                                            <li><a href="../../pages/careers/jobs.html">在线招聘</a></li>
                                        </ul>
                                    </div>
                                </div>
                                <!-- Panel: Contact -->
                                <div id="panel-contact-contact" class="vs-mega-panel">
                                    <h3>联系方式</h3>
                                    <div class="vs-mega-grid-v2">
                                        <ul class="vs-mega-list-v2">
                                            <li><a href="../../pages/contact/contact.html">联系我们</a></li>
                                            <li><a href="../../pages/contact/feedback.html">在线留言</a></li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </li>
                </ul>
            </nav>

            <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#" class="vs-search-trigger" title="搜索 (Ctrl+K)"><i class="fas fa-search"></i></a>
                <span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="../../pages_en/gassensing/index.html" style="font-size: 14px; font-weight: 500;">EN</a>
            </div>
        </div>
        <script>
        function showPanel(panelId, tab) {
            document.querySelectorAll('.vs-mega-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.vs-mega-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-' + panelId).classList.add('active');
        }
        function showPanelContact(panelId, tab) {
            const menu = tab.closest('.vs-mega-menu');
            menu.querySelectorAll('.vs-mega-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-contact-' + panelId).classList.add('active');
        }
        function showPanelSolutions(panelId, tab) {
            const menu = tab.closest('.vs-mega-menu');
            menu.querySelectorAll('.vs-mega-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-solutions-' + panelId).classList.add('active');
        }
        function showPanelCases(panelId, tab) {
            const menu = tab.closest('.vs-mega-menu');
            menu.querySelectorAll('.vs-mega-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-cases-' + panelId).classList.add('active');
        }
        </script>
    </header>'''

# Helper to normalize source paths to root-absolute paths
def normalize_path(path_in_source):
    # path_in_source relative to pages/gassensing/
    if path_in_source.startswith('http') or path_in_source.startswith('#') or path_in_source.startswith('mailto:'):
        return path_in_source
    
    # We are in pages/gassensing/
    # So ../../ becomes / (root)
    # ../ becomes /pages/
    # filename becomes /pages/gassensing/filename
    
    if path_in_source.startswith('../../'):
        return '/' + path_in_source[6:]
    elif path_in_source.startswith('../'):
        return '/pages/' + path_in_source[3:]
    else:
        return '/pages/gassensing/' + path_in_source

# Helper to convert root-absolute path to relative path for a target file
def rel_path_from_root(abs_path, target_rel_dir):
    # abs_path starts with /
    # target_rel_dir is relative from root, e.g. "pages/contact"
    
    if abs_path.startswith('http') or abs_path.startswith('#') or abs_path == '#':
        return abs_path
    
    # Remove leading slash to make it "root relative path string"
    path_from_root = abs_path.lstrip('/')
    
    # Calculate relative path from target_rel_dir to path_from_root
    # os.path.relpath('/a/b', 'c/d') -> calc path from c/d to /a/b
    # Actually simpler:
    # We are at ROOT/target_rel_dir
    # We want to go to ROOT/path_from_root
    
    rel = os.path.relpath(os.path.join(ROOT_DIR, path_from_root), os.path.join(ROOT_DIR, target_rel_dir))
    return rel

# Pre-process header: find all href/src and tokenise them
# We will use regex to find replace
link_pattern = re.compile(r'(href|src)="([^"]*)"')

def get_normalized_header():
    # Find all unique links
    links = set()
    for match in link_pattern.finditer(RAW_HEADER):
        links.add(match.group(2))
    
    # Map raw link -> absolute link
    link_map = {l: normalize_path(l) for l in links}
    return link_map

def generate_header_for_file(target_file_path, link_map):
    target_rel_path = os.path.relpath(target_file_path, ROOT_DIR)
    target_rel_dir = os.path.dirname(target_rel_path)
    
    def replacer(match):
        attr = match.group(1)
        original_link = match.group(2)
        if original_link not in link_map:
             return match.group(0) # Should not happen if we parsed correctly
        
        abs_link = link_map[original_link]
        new_rel_link = rel_path_from_root(abs_link, target_rel_dir)
        return f'{attr}="{new_rel_link}"'
        
    new_header = link_pattern.sub(replacer, RAW_HEADER)
    return new_header

def main():
    link_map = get_normalized_header()
    
    count = 0
    for dirpath, _, filenames in os.walk(ROOT_DIR):
        for filename in filenames:
            if not filename.endswith('.html'):
                continue
            
            file_path = os.path.join(dirpath, filename)
            rel_file_path = os.path.relpath(file_path, ROOT_DIR)
            
            # EXCLUSION RULES
            if rel_file_path == 'index.html':
                 print(f"Skipping ROOT {rel_file_path}")
                 continue
            if 'pages/biosensing' in rel_file_path:
                 print(f"Skipping BIOSENSING {rel_file_path}")
                 continue
            if '.gemini' in rel_file_path or 'ionrendering' in rel_file_path:
                 continue
            if 'pages/gassensing/index.html' in rel_file_path:
                 print("Skipping Source")
                 continue
                 
            # Process
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Regex replace header
                # Note: Regex matching multiline <header ...>...</header> is tricky if nested.
                # Assuming standard structure <header class="vs-header"> ... </header>
                header_regex = re.compile(r'<header class="vs-header">.*?</header>', re.DOTALL)
                
                if not header_regex.search(content):
                    print(f"No header found in {rel_file_path}")
                    continue
                
                new_header = generate_header_for_file(file_path, link_map)
                
                # Use lambda to avoid backslash interpretation in replacement string
                new_content = header_regex.sub(lambda m: new_header, content)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {rel_file_path}")
                count += 1
                
            except Exception as e:
                print(f"Error {rel_file_path}: {e}")

    print(f"Total updated: {count}")

if __name__ == '__main__':
    main()
