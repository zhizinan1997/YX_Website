#!/usr/bin/env python3
"""
Convert old-style product listing pages to new Vaisala style.
Preserves ALL original content (product items, images, descriptions, links, pagination).
Only updates the styling framework to match the homepage.
Uses pure regex - no external dependencies.
"""

import os
import re
from pathlib import Path
import html

# Base directory
BASE_DIR = Path('/Users/zhizinan/Desktop/YX_Website')
PRODUCTS_DIR = BASE_DIR / 'pages' / 'products'

def get_new_html_template():
    return '''<!DOCTYPE html>
<html lang="zh-CN">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 元芯传感</title>
    <link rel="stylesheet" href="../../assets/css/vaisala-style.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* Product List Page Styles */
        .vs-page-hero {{
            background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
            padding: 120px 0 60px;
            color: white;
            text-align: center;
        }}
        
        .vs-page-hero h1 {{
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        
        .vs-page-hero p {{
            font-size: 18px;
            opacity: 0.9;
        }}
        
        .vs-breadcrumb {{
            padding: 15px 0;
            font-size: 14px;
            color: rgba(255,255,255,0.8);
            text-align: left;
        }}
        
        .vs-breadcrumb a {{
            color: rgba(255,255,255,0.8);
            text-decoration: none;
        }}
        
        .vs-breadcrumb a:hover {{
            color: white;
        }}
        
        .vs-breadcrumb span {{
            margin: 0 10px;
            opacity: 0.6;
        }}
        
        /* Category Navigation */
        .vs-category-nav {{
            background: #f8fafc;
            border-bottom: 1px solid #e0e0e0;
            padding: 0;
        }}
        
        .vs-category-nav ul {{
            display: flex;
            flex-wrap: wrap;
            list-style: none;
            padding: 0;
            margin: 0;
            justify-content: center;
            gap: 8px;
            padding: 20px 0;
        }}
        
        .vs-category-nav li a {{
            display: inline-block;
            padding: 10px 24px;
            font-size: 14px;
            font-weight: 500;
            color: #555;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 30px;
            transition: all 0.2s;
        }}
        
        .vs-category-nav li a:hover,
        .vs-category-nav li a.active {{
            background: var(--color-primary);
            color: white;
            border-color: var(--color-primary);
        }}
        
        /* Product Grid */
        .vs-products-section {{
            padding: 60px 0;
        }}
        
        .vs-products-header {{
            text-align: center;
            margin-bottom: 48px;
        }}
        
        .vs-products-header h2 {{
            font-size: 32px;
            font-weight: 600;
            color: var(--color-primary);
            margin-bottom: 8px;
        }}
        
        .vs-products-header p {{
            color: #666;
            font-size: 16px;
        }}
        
        .vs-products-list {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        
        @media (max-width: 992px) {{
            .vs-products-list {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (max-width: 576px) {{
            .vs-products-list {{
                grid-template-columns: 1fr;
            }}
            .vs-page-hero h1 {{
                font-size: 32px;
            }}
        }}
        
        .vs-products-list > li {{
            margin: 0;
        }}
        
        .vs-products-list > li > a {{
            display: block;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .vs-products-list > li > a:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.15);
        }}
        
        .vs-product-img {{
            height: 220px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f8fafc;
            padding: 20px;
            overflow: hidden;
        }}
        
        .vs-product-img img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }}
        
        .vs-product-info {{
            padding: 24px;
        }}
        
        .vs-product-info h5 {{
            font-size: 18px;
            font-weight: 600;
            color: #222;
            margin-bottom: 12px;
            line-height: 1.4;
        }}
        
        .vs-product-info p {{
            font-size: 14px;
            color: #666;
            line-height: 1.6;
            margin-bottom: 16px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        
        .vs-product-more {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 14px;
            font-weight: 600;
            color: var(--color-primary);
        }}
        
        .vs-product-more::after {{
            content: '→';
            transition: transform 0.2s;
        }}
        
        .vs-products-list > li > a:hover .vs-product-more::after {{
            transform: translateX(4px);
        }}
        
        /* Pagination */
        .vs-pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            margin-top: 48px;
            flex-wrap: wrap;
        }}
        
        .vs-pagination span,
        .vs-pagination a {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 40px;
            height: 40px;
            padding: 0 12px;
            font-size: 14px;
            border-radius: 8px;
            transition: all 0.2s;
        }}
        
        .vs-pagination a {{
            background: white;
            color: #555;
            border: 1px solid #e0e0e0;
            text-decoration: none;
        }}
        
        .vs-pagination a:hover {{
            background: var(--color-primary);
            color: white;
            border-color: var(--color-primary);
        }}
        
        .vs-pagination .current {{
            background: var(--color-primary);
            color: white;
        }}
        
        .vs-pagination .disabled {{
            color: #aaa;
            cursor: not-allowed;
        }}
    </style>
</head>

<body>

    <header class="vs-header">
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
                        <a href="../../pages/products/products.aspx_category_id_0.html" class="vs-nav__link">产品</a>
                    </li>
                    <li class="vs-nav__item"><a href="../../pages/solutions/hydrogen.html" class="vs-nav__link">解决方案</a>
                    </li>
                    <li class="vs-nav__item"><a href="../../pages/news/news.html" class="vs-nav__link">洞察与资讯</a></li>
                    <li class="vs-nav__item"><a href="../../pages/about/about.html" class="vs-nav__link">公司简介</a></li>
                    <li class="vs-nav__item"><a href="../../pages/contact/contact.html" class="vs-nav__link">联系我们</a>
                    </li>
                </ul>
            </nav>

            <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#"><i class="fas fa-search"></i></a>
                <a href="#" style="font-size: 14px; font-weight: 500;">CN / EN</a>
            </div>
        </div>
    </header>

    <main style="padding-top: 90px;">
        <!-- Page Hero -->
        <section class="vs-page-hero">
            <div class="vs-container">
                <div class="vs-breadcrumb">
                    <a href="../../index.html">首页</a>
                    <span>|</span>
                    <a href="../../pages/products/products.aspx_category_id_0.html">产品</a>
                    <span>|</span>
                    {breadcrumb_title}
                </div>
                <h1>{page_title}</h1>
                <p>致力于先进生物与化学传感技术解决方案</p>
            </div>
        </section>

        <!-- Category Navigation -->
        <nav class="vs-category-nav">
            <div class="vs-container">
                <ul>
                    <li><a href="../../pages/products/products.aspx_category_id_0.html">全部产品</a></li>
                    <li><a href="../../pages/products/products.aspx_category_id_38.html">生物传感</a></li>
                    <li><a href="../../pages/products/products.aspx_category_id_37.html">气体传感</a></li>
                    <li><a href="../../pages/products/products_mems.html">MEMS 传感器芯片</a></li>
                    <li><a href="../../pages/products/products.aspx_category_id_36.html">OEM产品</a></li>
                </ul>
            </div>
        </nav>

        <!-- Products Section -->
        <section class="vs-products-section">
            <div class="vs-container">
                <div class="vs-products-header">
                    <h2>产品展示</h2>
                    <p>浏览我们的全系列传感器产品</p>
                </div>

                <ul class="vs-products-list">
{product_items}
                </ul>
                
                <div class="vs-pagination">
                    {pagination}
                </div>
            </div>
        </section>
    </main>

    <footer class="vs-footer">
        <div class="vs-container">
            <div class="vs-footer__grid">
                <div class="vs-footer__col" style="padding-right: 40px;">
                    <a href="../../index.html" class="vs-logo" style="margin-bottom: 24px;">
                        <img src="../../assets/images/logo.png" style="filter: brightness(0) invert(1);" alt="Logo">
                        METACHIP
                    </a>
                    <p style="color: rgba(255,255,255,0.6); line-height: 1.8;">
                        湖南元芯传感科技有限责任公司<br>
                        湖南省湘潭市高新区双马街道书院路38号
                    </p>
                </div>
            </div>
            <div class="vs-footer__bottom">
                <span>© 2024 湖南元芯传感科技有限责任公司. All rights reserved.</span>
            </div>
        </div>
    </footer>

</body>

</html>
'''


def extract_title(content):
    """Extract page title from old HTML"""
    match = re.search(r'<title>([^<]+)</title>', content)
    if match:
        title = match.group(1)
        title = title.replace('-湖南元芯传感科技有限责任公司', '')
        title = title.replace('湖南元芯传感科技有限责任公司', '')
        return title.strip()
    return '产品列表'


def extract_products(content):
    """Extract product items from old HTML using regex"""
    products = []
    
    # Find the ny_product_all section
    section_match = re.search(r'<div class="ny_product_all">(.*?)</div>\s*</div>\s*<div class="footer"', content, re.DOTALL)
    if not section_match:
        # Try alternative pattern
        section_match = re.search(r'<div class="ny_product_all">(.*?)<div class="digg">', content, re.DOTALL)
    
    if not section_match:
        print("    Could not find product section")
        return ''
    
    section = section_match.group(1)
    
    # Find the ul with products
    ul_match = re.search(r'<ul>(.*?)</ul>', section, re.DOTALL)
    if not ul_match:
        print("    Could not find product list")
        return ''
    
    ul_content = ul_match.group(1)
    
    # Extract each li item
    li_pattern = r'<li>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>\s*</li>'
    li_matches = re.findall(li_pattern, ul_content, re.DOTALL)
    
    for href, li_content in li_matches:
        # Extract image src
        img_match = re.search(r'<img\s+[^>]*src="([^"]+)"', li_content)
        img_src = img_match.group(1) if img_match else ''
        
        # Extract title from h5
        h5_match = re.search(r'<h5>([^<]+)</h5>', li_content)
        title = h5_match.group(1).strip() if h5_match else '产品'
        
        # Extract description from ny_soli_p
        desc_match = re.search(r'<div class="ny_soli_p">\s*<p>\s*(.*?)\s*</p>', li_content, re.DOTALL)
        desc = desc_match.group(1).strip() if desc_match else ''
        # Clean up description
        desc = re.sub(r'\s+', ' ', desc)
        
        product_html = f'''                    <li>
                        <a href="{href}">
                            <div class="vs-product-img">
                                <img src="{img_src}" alt="{title}">
                            </div>
                            <div class="vs-product-info">
                                <h5>{title}</h5>
                                <p>{desc}</p>
                                <span class="vs-product-more">查看详情</span>
                            </div>
                        </a>
                    </li>'''
        products.append(product_html)
    
    return '\n'.join(products)


def extract_pagination(content):
    """Extract pagination from old HTML"""
    # Find the digg div
    digg_match = re.search(r'<div class="digg">(.*?)</div>', content, re.DOTALL)
    if not digg_match:
        return ''
    
    pagination = digg_match.group(1).strip()
    
    # Fix relative links
    pagination = pagination.replace('products.aspx@category_id=', 'products.aspx_category_id_')
    pagination = pagination.replace('&amp;page=', '_page_')
    
    return pagination


def convert_file(filepath):
    """Convert a single file to new style"""
    print(f"Converting: {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already using new style
    if 'vaisala-style.css' in content and 'vs-products-list' in content:
        print(f"  Skipped (already converted)")
        return False
    
    # Extract content from old format
    title = extract_title(content)
    product_items = extract_products(content)
    pagination = extract_pagination(content)
    
    if not product_items:
        print(f"  ERROR: Could not extract products!")
        return False
    
    # Count products
    product_count = product_items.count('<li>')
    print(f"  Extracted {product_count} products")
    
    # Generate new HTML
    template = get_new_html_template()
    new_content = template.format(
        title=title,
        breadcrumb_title=title,
        page_title=title,
        product_items=product_items,
        pagination=pagination
    )
    
    # Write new file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  Converted successfully!")
    return True


def main():
    """Main function to convert all old-style product pages"""
    
    # Find all files using old index.css
    old_style_files = []
    
    for filepath in PRODUCTS_DIR.glob('products.aspx_category_id_*.html'):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'assets/css/index.css' in content:
            old_style_files.append(filepath)
    
    print(f"Found {len(old_style_files)} files to convert:\n")
    
    converted_count = 0
    for filepath in sorted(old_style_files):
        if convert_file(filepath):
            converted_count += 1
    
    print(f"\nDone! Converted {converted_count} files.")


if __name__ == '__main__':
    main()
