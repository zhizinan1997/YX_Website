#!/usr/bin/env python3
"""
Migrate product detail page content from source to new Vaisala style.
Extracts ALL content (product details, advantages, applications, specs, related news, related products)
from source files and creates new pages with modern styling.
"""

import os
import re
from pathlib import Path

# Directories
BASE_DIR = Path('/Users/zhizinan/Desktop/YX_Website')
SOURCE_DIR = BASE_DIR / 'hnmetachip_site' / 'www.hnmetachip.cn'
TARGET_DIR = BASE_DIR / 'pages' / 'products'


def get_template():
    """Get the new page template"""
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
        /* Product Detail Page Styles */
        .vs-product-hero {{
            background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
            padding: 120px 0 80px;
            color: white;
        }}
        
        .vs-product-hero__inner {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 60px;
            align-items: center;
        }}
        
        .vs-product-hero__image {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .vs-product-hero__image img {{
            max-width: 100%;
            max-height: 400px;
            object-fit: contain;
        }}
        
        .vs-product-hero__content h1 {{
            font-size: 42px;
            font-weight: 700;
            margin-bottom: 20px;
        }}
        
        .vs-product-hero__desc {{
            font-size: 18px;
            opacity: 0.9;
            line-height: 1.7;
            margin-bottom: 30px;
        }}
        
        .vs-feature-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        
        .vs-feature-list li {{
            padding: 8px 0;
            padding-left: 28px;
            position: relative;
            font-size: 15px;
        }}
        
        .vs-feature-list li::before {{
            content: '✓';
            position: absolute;
            left: 0;
            color: #4CAF50;
            font-weight: bold;
        }}
        
        .vs-product-section {{
            padding: 60px 0;
        }}
        
        .vs-product-section:nth-child(even) {{
            background: #f8fafc;
        }}
        
        .vs-product-section__title {{
            font-size: 28px;
            font-weight: 600;
            color: var(--color-primary);
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 3px solid var(--color-accent-orange);
            display: inline-block;
        }}
        
        .vs-product-section__content {{
            font-size: 16px;
            line-height: 1.8;
            color: #444;
        }}
        
        .vs-product-section__content p {{
            margin-bottom: 16px;
        }}
        
        .vs-product-section__content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 10px 5px;
        }}
        
        .vs-product-section__content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        
        .vs-product-section__content table td {{
            padding: 12px 16px;
            border: 1px solid #e0e0e0;
        }}
        
        .vs-product-section__content table tr:nth-child(odd) td:first-child {{
            background: var(--color-primary);
            color: white;
            font-weight: 600;
            width: 200px;
        }}
        
        .vs-product-section__content table tr:nth-child(even) {{
            background: #f9f9f9;
        }}
        
        .vs-breadcrumb {{
            padding: 15px 0;
            font-size: 14px;
            color: rgba(255,255,255,0.8);
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
        
        /* Related Products */
        .vs-related-products {{
            background: #f8fafc;
            padding: 60px 0;
        }}
        
        .vs-related-products h2 {{
            font-size: 28px;
            font-weight: 600;
            color: var(--color-primary);
            text-align: center;
            margin-bottom: 40px;
        }}
        
        .vs-related-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 24px;
        }}
        
        .vs-related-item {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .vs-related-item:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        
        .vs-related-item img {{
            width: 100%;
            height: 160px;
            object-fit: contain;
            background: #f0f4f8;
            padding: 20px;
        }}
        
        .vs-related-item h4 {{
            padding: 16px;
            font-size: 14px;
            font-weight: 600;
            color: #333;
            text-align: center;
        }}
        
        /* Related News */
        .vs-related-news {{
            padding: 60px 0;
        }}
        
        .vs-related-news h2 {{
            font-size: 28px;
            font-weight: 600;
            color: var(--color-primary);
            text-align: center;
            margin-bottom: 40px;
        }}
        
        .vs-news-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 30px;
        }}
        
        .vs-news-item {{
            display: flex;
            gap: 20px;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .vs-news-item:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.12);
        }}
        
        .vs-news-item img {{
            width: 180px;
            height: 140px;
            object-fit: cover;
            flex-shrink: 0;
        }}
        
        .vs-news-item__content {{
            padding: 20px 20px 20px 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        
        .vs-news-item__content h4 {{
            font-size: 16px;
            font-weight: 600;
            color: #222;
            margin-bottom: 10px;
            line-height: 1.4;
        }}
        
        .vs-news-item__content p {{
            font-size: 14px;
            color: #666;
            line-height: 1.6;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        
        .vs-cta-section {{
            background: linear-gradient(135deg, var(--color-primary) 0%, #004d8c 100%);
            padding: 60px 0;
            text-align: center;
            color: white;
        }}
        
        .vs-cta-section h3 {{
            font-size: 28px;
            margin-bottom: 20px;
        }}
        
        .vs-cta-section p {{
            font-size: 16px;
            opacity: 0.9;
            margin-bottom: 30px;
        }}
        
        @media (max-width: 992px) {{
            .vs-related-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (max-width: 768px) {{
            .vs-product-hero__inner {{
                grid-template-columns: 1fr;
                gap: 30px;
            }}
            
            .vs-product-hero__content h1 {{
                font-size: 28px;
            }}
            
            .vs-news-grid {{
                grid-template-columns: 1fr;
            }}
            
            .vs-related-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (max-width: 576px) {{
            .vs-related-grid {{
                grid-template-columns: 1fr;
            }}
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
        <!-- Breadcrumb -->
        <div style="background: var(--color-primary);">
            <div class="vs-container vs-breadcrumb">
                <a href="../../index.html">首页</a>
                <span>|</span>
                <a href="../../pages/products/products.aspx_category_id_0.html">产品</a>
                <span>|</span>
                {title}
            </div>
        </div>

        <!-- Product Hero -->
        <section class="vs-product-hero">
            <div class="vs-container">
                <div class="vs-product-hero__inner">
                    <div class="vs-product-hero__image">
                        <img src="{main_image}" alt="{title}">
                    </div>
                    <div class="vs-product-hero__content">
                        <h1>{title}</h1>
                        <p class="vs-product-hero__desc">{description}</p>
                        {features_html}
                        <div style="margin-top: 30px;">
                            <a href="../../pages/contact/feedback.html" class="vs-btn vs-btn--primary">
                                <i class="fas fa-envelope" style="margin-right: 8px;"></i>咨询报价
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Product Details -->
        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">产品详情</h2>
                <div class="vs-product-section__content">
                    {product_details}
                </div>
            </div>
        </section>

{advantages_section}

{applications_section}

        <!-- Technical Specifications -->
        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">技术指标</h2>
                <div class="vs-product-section__content">
                    {specs_content}
                </div>
            </div>
        </section>

{related_news_section}

{related_products_section}

        <!-- CTA Section -->
        <section class="vs-cta-section">
            <div class="vs-container">
                <h3>需要了解更多？</h3>
                <p>我们的技术团队随时为您提供专业的产品咨询和解决方案</p>
                <a href="../../pages/contact/contact.html" class="vs-btn vs-btn--secondary" style="background: white; color: var(--color-primary);">
                    <i class="fas fa-phone" style="margin-right: 8px;"></i>联系我们
                </a>
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
    """Extract product title"""
    match = re.search(r'<h3>([^<]+)</h3>', content)
    if match:
        return match.group(1).strip()
    
    match = re.search(r'<title>([^-<]+)', content)
    if match:
        return match.group(1).strip()
    
    return "产品详情"


def extract_main_image(content):
    """Extract main product image"""
    match = re.search(r'<div class="bd_liimg">\s*<img src=[\'"]([^\'"]+)[\'"]', content)
    if match:
        return match.group(1)
    
    match = re.search(r'class="bd_liimg"[^>]*>.*?<img[^>]+src=[\'"]([^\'"]+)[\'"]', content, re.DOTALL)
    if match:
        return match.group(1)
    
    return ""


def extract_description(content):
    """Extract product description"""
    match = re.search(r'<div class="product_top_ms">\s*(.*?)\s*</div>', content, re.DOTALL)
    if match:
        desc = match.group(1).strip()
        desc = re.sub(r'<[^>]+>', '', desc)
        return desc.strip()
    return ""


def extract_features(content):
    """Extract product features"""
    match = re.search(r'<div class="product_top_td">(.*?)</div>', content, re.DOTALL)
    if match:
        features_html = match.group(1)
        # Extract text from <p> tags
        features = re.findall(r'<p[^>]*>◆?\s*(.+?)</p>', features_html)
        features = [re.sub(r'<[^>]+>', '', f).strip() for f in features]
        features = [f for f in features if f and f != '◆']
        
        if features:
            html = '<ul class="vs-feature-list">\n'
            for f in features:
                f = f.replace('◆', '').replace('&nbsp;', ' ').strip()
                if f:
                    html += f'                                <li>{f}</li>\n'
            html += '                            </ul>'
            return html
    return ""


def extract_product_details(content):
    """Extract product details section"""
    match = re.search(r'id="cpxq"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return "<p>暂无详细信息</p>"


def extract_advantages(content):
    """Extract product advantages section"""
    match = re.search(r'id="cpys"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        advantages = match.group(1).strip()
        if advantages and len(advantages) > 10:
            return f'''
        <!-- Product Advantages -->
        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">产品优势</h2>
                <div class="vs-product-section__content">
                    {advantages}
                </div>
            </div>
        </section>
'''
    return ""


def extract_applications(content):
    """Extract main applications section"""
    match = re.search(r'id="cpyy"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        apps = match.group(1).strip()
        if apps and len(apps) > 10:
            return f'''
        <!-- Main Applications -->
        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">主要应用</h2>
                <div class="vs-product-section__content">
                    {apps}
                </div>
            </div>
        </section>
'''
    return ""


def extract_specs(content):
    """Extract technical specifications"""
    match = re.search(r'id="cpzb"[^>]*>.*?<div class="product_bottom_xx[^"]*">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return "<p>暂无技术指标</p>"


def extract_related_news(content):
    """Extract related news section"""
    match = re.search(r'<div class="ny_product_news">(.*?)</div>\s*</div>\s*</div>', content, re.DOTALL)
    if not match:
        return ""
    
    news_section = match.group(1)
    news_items = re.findall(r'<li>\s*<a href="([^"]+)">(.*?)</a>\s*</li>', news_section, re.DOTALL)
    
    if not news_items:
        return ""
    
    news_html = '''
        <!-- Related News -->
        <section class="vs-related-news">
            <div class="vs-container">
                <h2>相关新闻</h2>
                <div class="vs-news-grid">
'''
    
    for href, item in news_items[:4]:  # Limit to 4 items
        # Extract image
        img_match = re.search(r'<img src="([^"]+)"', item)
        img = img_match.group(1) if img_match else ""
        
        # Extract title
        title_match = re.search(r'<h4>([^<]+)</h4>', item)
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract description
        desc_match = re.search(r'<p>([^<]+)</p>', item)
        desc = desc_match.group(1).strip() if desc_match else ""
        
        # Fix href
        href = href.replace('.aspx_id_', '_show.aspx_id_')
        if not href.startswith('../../'):
            href = f'../../pages/news/{href}'
        
        news_html += f'''                    <a href="{href}" class="vs-news-item">
                        <img src="{img}" alt="{title}">
                        <div class="vs-news-item__content">
                            <h4>{title}</h4>
                            <p>{desc}</p>
                        </div>
                    </a>
'''
    
    news_html += '''                </div>
            </div>
        </section>
'''
    return news_html


def extract_related_products(content):
    """Extract related products section"""
    match = re.search(r'id="xgcp"[^>]*>.*?<div class="swiper-wrapper">(.*?)</div>\s*</div>', content, re.DOTALL)
    if not match:
        return ""
    
    products_section = match.group(1)
    products = re.findall(r'<div class="swiper-slide">\s*<a href="([^"]+)">(.*?)</a>\s*</div>', products_section, re.DOTALL)
    
    if not products:
        return ""
    
    html = '''
        <!-- Related Products -->
        <section class="vs-related-products">
            <div class="vs-container">
                <h2>相关产品</h2>
                <div class="vs-related-grid">
'''
    
    count = 0
    for href, item in products:
        if count >= 8:  # Limit to 8 items
            break
            
        # Extract image
        img_match = re.search(r'<img src="([^"]+)"', item)
        img = img_match.group(1) if img_match else ""
        
        # Extract title
        title_match = re.search(r'<h3>([^<]+)</h3>', item)
        title = title_match.group(1).strip() if title_match else ""
        
        if not title:
            continue
        
        # Fix href
        if not href.startswith('../../'):
            href = f'../../pages/products/{href}'
        
        html += f'''                    <a href="{href}" class="vs-related-item">
                        <img src="{img}" alt="{title}">
                        <h4>{title}</h4>
                    </a>
'''
        count += 1
    
    html += '''                </div>
            </div>
        </section>
'''
    return html


def migrate_product(filename):
    """Migrate a single product page"""
    source_path = SOURCE_DIR / filename
    target_path = TARGET_DIR / filename
    
    if not source_path.exists():
        print(f"  Source not found: {filename}")
        return False
    
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract all content
    title = extract_title(content)
    main_image = extract_main_image(content)
    description = extract_description(content)
    features_html = extract_features(content)
    product_details = extract_product_details(content)
    advantages_section = extract_advantages(content)
    applications_section = extract_applications(content)
    specs_content = extract_specs(content)
    related_news_section = extract_related_news(content)
    related_products_section = extract_related_products(content)
    
    print(f"  Title: {title}")
    print(f"  Image: {'Yes' if main_image else 'No'}")
    print(f"  Features: {'Yes' if features_html else 'No'}")
    print(f"  Advantages: {'Yes' if advantages_section else 'No'}")
    print(f"  Applications: {'Yes' if applications_section else 'No'}")
    print(f"  Related News: {'Yes' if related_news_section else 'No'}")
    print(f"  Related Products: {'Yes' if related_products_section else 'No'}")
    
    # Generate new page
    template = get_template()
    new_content = template.format(
        title=title,
        main_image=main_image,
        description=description,
        features_html=features_html,
        product_details=product_details,
        advantages_section=advantages_section,
        applications_section=applications_section,
        specs_content=specs_content,
        related_news_section=related_news_section,
        related_products_section=related_products_section
    )
    
    # Write new file
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True


def main():
    """Main function"""
    # Find all product show files in source
    source_files = list(SOURCE_DIR.glob('products_show.aspx_id_*.html'))
    print(f"Found {len(source_files)} product detail pages in source\n")
    
    migrated = 0
    for source_file in sorted(source_files):
        filename = source_file.name
        print(f"Migrating: {filename}")
        
        if migrate_product(filename):
            migrated += 1
            print(f"  ✓ Done\n")
        else:
            print(f"  ✗ Failed\n")
    
    print(f"\nMigrated {migrated} of {len(source_files)} product pages")


if __name__ == '__main__':
    main()
