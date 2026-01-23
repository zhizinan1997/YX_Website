"""
Update all path references in HTML files after reorganization.
This script updates:
1. CSS references (templates/lqgd/css/ -> assets/css/, css/ -> assets/css/)
2. JS references (scripts/ -> assets/js/)
3. Image references (images/ -> assets/images/, huoban/ -> assets/images/huoban/)
4. Video references (Video/ -> assets/video/)
5. Page links (old .html names -> new paths in pages/)
"""
import os
import re
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")

# Mapping from old paths to new paths
PATH_MAPPINGS = [
    # CSS
    (r'templates/lqgd/css/', 'assets/css/'),
    (r'css/', 'assets/css/'),
    # JS
    (r'scripts/', 'assets/js/'),
    # Images
    (r'templates/lqgd/images/', 'assets/images/'),
    (r'images/', 'assets/images/'),
    (r'huoban/', 'assets/images/huoban/'),
    # Video
    (r'Video/', 'assets/video/'),
]

# Page link mappings (old file -> new path)
PAGE_MAPPINGS = {
    'about.aspx_page_about.html': 'pages/about/about.html',
    'about.aspx_page_fzlc.html': 'pages/about/history.html',
    'about.aspx_page_qywh.html': 'pages/about/culture.html',
    'contact.aspx_page_contact.html': 'pages/contact/contact.html',
    'feedbook.aspx.html': 'pages/contact/feedback.html',
    'feedback.aspx_attach_id.html': 'pages/contact/feedback-attach.html',
    'hydrogen-solutions.html': 'pages/gassensing/index.html',
    'industry-energy-storage.html': 'pages/solutions/industry-energy-storage.html',
    'industry-environment.html': 'pages/solutions/industry-environment.html',
    'industry-hydrogen.html': 'pages/solutions/industry-hydrogen.html',
    'industry-leak-detection.html': 'pages/solutions/industry-leak-detection.html',
    'industry-power-safety.html': 'pages/solutions/industry-power-safety.html',
    'measurement-dewpoint.html': 'pages/measurement/measurement-dewpoint.html',
    'measurement-humidity.html': 'pages/measurement/measurement-humidity.html',
    'measurement-hydrogen.html': 'pages/measurement/measurement-hydrogen.html',
    'measurement-oil-water.html': 'pages/measurement/measurement-oil-water.html',
    'measurement-dissolved-hydrogen.html': 'pages/measurement/measurement-dissolved-hydrogen.html',
    'measurement-pressure.html': 'pages/measurement/measurement-pressure.html',
    'jobs.aspx_category_id_0.html': 'pages/careers/jobs.html',
    'job.aspx.html': 'pages/careers/job-detail.html',
    'rlzy.aspx_page_hzzm.html': 'pages/careers/partners.html',
    'rlzy.aspx_page_jskj.html': 'pages/careers/growth.html',
    'rlzy.aspx_page_rcln.html': 'pages/careers/talent.html',
    'service.aspx_category_id_0.html': 'pages/services/service.html',
    'hxfw.aspx_category_id_0.html': 'pages/services/core-service.html',
    'jjfa.aspx_category_id_0.html': 'pages/solutions/jjfa.html',
    'honor.aspx_category_id_0.html': 'pages/honors/honor.html',
    'honor.aspx_category_id_0_page_2.html': 'pages/honors/honor-page2.html',
    'cxyj.aspx_category_id_0.html': 'pages/about/research.html',
    'wnjg.aspx_category_id_0.html': 'pages/about/micro-nano.html',
    'policy.aspx.html': 'pages/about/policy.html',
    'news.aspx_category_id_0.html': 'pages/news/news.html',
}

# Add products mappings
for i in range(6):
    suffix = '' if i == 0 else f'_page_{i}'
    old = f'products.aspx_category_id_0{suffix}.html' if i > 0 else 'products.aspx_category_id_0.html'
    if i == 0:
        PAGE_MAPPINGS['products.aspx_category_id_0.html'] = 'pages/gassensing/all-products.html'
    else:
        PAGE_MAPPINGS[f'products.aspx_category_id_0_page_{i}.html'] = f'pages/products/products.aspx_category_id_0_page_{i}.html'

for cat in [36, 37, 38]:
    PAGE_MAPPINGS[f'products.aspx_category_id_{cat}.html'] = f'pages/products/products.aspx_category_id_{cat}.html'
    for page in [2, 3]:
        key = f'products.aspx_category_id_{cat}_page_{page}.html'
        PAGE_MAPPINGS[key] = f'pages/products/{key}'

for suffix in ['handheld', 'mems', 'modules', 'systems']:
    PAGE_MAPPINGS[f'products_{suffix}.html'] = f'pages/products/products_{suffix}.html'


def get_relative_prefix(file_path: Path) -> str:
    """Calculate the relative path prefix to go back to root from a file's location."""
    rel = file_path.relative_to(ROOT)
    depth = len(rel.parts) - 1  # Subtract 1 for the file itself
    if depth == 0:
        return ''
    return '../' * depth


def update_file(file_path: Path):
    """Update all references in a single HTML file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        try:
            content = file_path.read_text(encoding='gbk')
        except:
            print(f"Skipping {file_path} - encoding issue")
            return

    original = content
    prefix = get_relative_prefix(file_path)

    # Update path mappings (for assets)
    for old_path, new_path in PATH_MAPPINGS:
        # Handle both quoted and unquoted paths
        content = content.replace(f'"{old_path}', f'"{prefix}{new_path}')
        content = content.replace(f"'{old_path}", f"'{prefix}{new_path}")
        content = content.replace(f'({old_path}', f'({prefix}{new_path}')

    # Update page links
    for old_page, new_page in PAGE_MAPPINGS.items():
        # Full href replacement
        content = content.replace(f'href="{old_page}"', f'href="{prefix}{new_page}"')
        content = content.replace(f"href='{old_page}'", f"href='{prefix}{new_page}'")

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"Updated: {file_path}")


def main():
    # Find all HTML files
    html_files = list(ROOT.rglob('*.html'))
    print(f"Found {len(html_files)} HTML files")
    
    for file_path in html_files:
        # Skip archive folder
        if 'archive' in str(file_path) or '原网页代码' in str(file_path):
            continue
        update_file(file_path)
    
    print("Done!")


if __name__ == '__main__':
    main()
