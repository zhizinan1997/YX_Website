"""
Fix missing mega menu panels in all HTML files.
Adds panel-target, panel-type, panel-list content where missing.
"""
import os
import re
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")

# The HTML to insert after panel-new closing div
MISSING_PANELS = '''                                <div id="panel-target" class="vs-mega-panel">
                                    <h3>测量对象</h3>
                                    <div class="vs-mega-grid-v2">
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/solutions/measurement-hydrogen.html">氢气检测</a></li>
                                                <li><a href="{prefix}pages/solutions/measurement-humidity.html">湿度检测</a></li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/solutions/measurement-dewpoint.html">露点检测</a></li>
                                                <li><a href="{prefix}pages/solutions/measurement-oil-water.html">油中水分检测</a></li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                                <div id="panel-type" class="vs-mega-panel">
                                    <h3>产品种类</h3>
                                    <div class="vs-mega-grid-v2">
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/products/products_mems.html">MEMS芯片</a></li>
                                                <li><a href="{prefix}pages/products/products_modules.html">传感器模组</a></li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/products/products_handheld.html">手持式仪表</a></li>
                                                <li><a href="{prefix}pages/products/products_systems.html">在线监测系统</a></li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                                <div id="panel-list" class="vs-mega-panel">
                                    <h3>产品列表</h3>
                                    <div class="vs-mega-grid-v2">
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/products/products.aspx_category_id_37.html">生化传感器</a></li>
                                                <li><a href="{prefix}pages/products/products.aspx_category_id_38.html">气体传感器</a></li>
                                            </ul>
                                        </div>
                                        <div>
                                            <ul class="vs-mega-list-v2">
                                                <li><a href="{prefix}pages/products/products.aspx_category_id_36.html">检测仪器</a></li>
                                                <li><a href="{prefix}pages/products/products.aspx_category_id_0.html">全部产品</a></li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>
'''


def get_relative_prefix(file_path: Path) -> str:
    """Calculate the relative path prefix to go back to root from a file's location."""
    rel = file_path.relative_to(ROOT)
    depth = len(rel.parts) - 1  # Subtract 1 for the file itself
    if depth == 0:
        return ''
    return '../' * depth


def fix_file(file_path: Path):
    """Fix missing mega menu panels in a single HTML file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        try:
            content = file_path.read_text(encoding='gbk')
        except:
            return False

    # Check if file has the mega menu with showPanel('target'
    if "showPanel('target'" not in content:
        return False  # File doesn't have this mega menu structure
    
    # Check if panel-target already exists
    if 'id="panel-target"' in content:
        return False  # Already fixed
    
    # Check if panel-new exists (we insert after it)
    if 'id="panel-new"' not in content:
        return False  # Different structure
    
    prefix = get_relative_prefix(file_path)
    panels_html = MISSING_PANELS.format(prefix=prefix)
    
    # Find the closing of panel-new and insert after it
    # Pattern: </div> closing panel-new, then </div> closing vs-mega-content
    pattern = r'(id="panel-new"[^}]*?</div>\s*</div>\s*</div>)(\s*)(</div>)'
    
    # Simpler approach: find panel-new closing and insert before vs-mega-content closing
    # Look for the pattern after panel-new content ends
    
    # Find where panel-new ends and vs-mega-content ends
    marker = '</div>\n                            </div>\n                        </div>\n                    </li>'
    
    if marker not in content:
        # Try alternate spacing
        marker = '</div>\r\n                            </div>\r\n                        </div>\r\n                    </li>'
    
    if marker not in content:
        print(f"  Could not find insertion point in {file_path}")
        return False
    
    # We need to be more precise. Let's find panel-new closing specifically
    # The structure is: panel-new div -> closes -> vs-mega-content closes -> vs-mega-menu closes -> li closes
    
    # Use regex to find: after panel-new's last </div>, before </div> that closes vs-mega-content
    old_pattern = '</div>\n                            </div>\n                        </div>\n                    </li>'
    new_content = panels_html + '                            </div>\n                        </div>\n                    </li>'
    
    # Actually simpler: search for the point right after panel-new closes
    # Pattern: look for id="panel-new" ... (content) ... </div>\n                            </div>
    
    # Let's use a different approach - find the exact location using the known structure
    search_str = '</div>\r\n                            </div>\r\n                        </div>\r\n                    </li>\r\n                    <li class="vs-nav__item"><a href='
    
    if search_str in content and 'id="panel-new"' in content:
        # Split and check if we're at the right spot (after panel-new, before nav items)
        parts = content.split('id="panel-new"', 1)
        if len(parts) == 2:
            before_panel_new = parts[0]
            after_panel_new = parts[1]
            
            # Find where panel-new's content ends
            # Look for the closing pattern that marks end of vs-mega-content after panel-new
            close_pattern = '</div>\r\n                            </div>\r\n                        </div>\r\n                    </li>'
            if close_pattern in after_panel_new:
                # Insert before the last 3 </div> and </li>
                after_parts = after_panel_new.split(close_pattern, 1)
                if len(after_parts) == 2:
                    new_after = after_parts[0] + '</div>\r\n' + panels_html + '                            </div>\r\n                        </div>\r\n                    </li>' + after_parts[1]
                    content = before_panel_new + 'id="panel-new"' + new_after
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
