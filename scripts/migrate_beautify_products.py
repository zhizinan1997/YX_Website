#!/usr/bin/env python3
"""
Complete migration and beautification of product detail pages.
Extracts content from source and applies beautiful styling.
"""

import os
import re
from pathlib import Path
import html

# Directories
BASE_DIR = Path('/Users/zhizinan/Desktop/YX_Website')
SOURCE_DIR = BASE_DIR / 'hnmetachip_site' / 'www.hnmetachip.cn'
TARGET_DIR = BASE_DIR / 'pages' / 'products'


def clean_text(text):
    """Clean up text content"""
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_html_content(content):
    """Clean up HTML content"""
    if not content:
        return ""
    
    # Decode HTML entities
    content = html.unescape(content)
    content = content.replace('&nbsp;', ' ')
    
    # Remove problematic style attributes
    content = re.sub(r'style="[^"]*font-family:\s*\'[^\']*\'[^"]*"', '', content)
    content = re.sub(r'style=";[^"]*"', '', content)
    content = re.sub(r'style="text-wrap:\s*wrap;?"', '', content)
    
    # Fix hidden images
    content = re.sub(r'width="1"\s*height="1"[^>]*style="width:\s*1px;\s*height:\s*1px;"', 'style="display:none"', content)
    
    # Clean excessive breaks
    content = re.sub(r'(<br\s*/?>){3,}', '<br><br>', content)
    content = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', content)
    
    return content.strip()


def get_template():
    """Return the beautiful page template"""
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
        /* Product Detail Page - Premium Styles */
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
            border-radius: 20px;
            padding: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.2);
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
            line-height: 1.2;
        }}
        
        .vs-product-hero__desc {{
            font-size: 18px;
            opacity: 0.95;
            line-height: 1.8;
            margin-bottom: 28px;
        }}
        
        .vs-feature-list {{
            list-style: none;
            padding: 0;
            margin: 0 0 30px 0;
            display: grid;
            gap: 10px;
        }}
        
        .vs-feature-list li {{
            padding: 12px 16px 12px 44px;
            position: relative;
            font-size: 15px;
            background: rgba(255,255,255,0.12);
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }}
        
        .vs-feature-list li::before {{
            content: '✓';
            position: absolute;
            left: 16px;
            color: #4ADE80;
            font-weight: bold;
            font-size: 18px;
        }}
        
        /* Section Styles */
        .vs-product-section {{
            padding: 80px 0;
        }}
        
        .vs-product-section.alt-bg {{
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        }}
        
        .vs-product-section__title {{
            font-size: 32px;
            font-weight: 700;
            color: var(--color-primary);
            margin-bottom: 32px;
            position: relative;
            display: inline-block;
        }}
        
        .vs-product-section__title::after {{
            content: '';
            position: absolute;
            bottom: -8px;
            left: 0;
            width: 60px;
            height: 4px;
            background: linear-gradient(90deg, var(--color-accent-orange), #ff9500);
            border-radius: 2px;
        }}
        
        .vs-product-section__content {{
            font-size: 16px;
            line-height: 1.9;
            color: #4a5568;
        }}
        
        .vs-product-section__content p {{
            margin-bottom: 16px;
        }}
        
        .vs-product-section__content img {{
            max-width: 280px;
            height: auto;
            border-radius: 12px;
            margin: 12px 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        
        /* Specs Table */
        .vs-specs-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        }}
        
        .vs-specs-table td {{
            padding: 18px 24px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 15px;
        }}
        
        .vs-specs-table tr:last-child td {{
            border-bottom: none;
        }}
        
        .vs-specs-table tr td:first-child {{
            background: var(--color-primary);
            color: white;
            font-weight: 600;
            width: 220px;
        }}
        
        .vs-specs-table tr td:last-child {{
            background: white;
            color: #334155;
        }}
        
        .vs-specs-table tr:nth-child(even) td:last-child {{
            background: #f8fafc;
        }}
        
        /* Advantages Grid */
        .vs-advantages-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 24px;
            margin-top: 24px;
        }}
        
        .vs-advantage-card {{
            background: white;
            padding: 36px 28px;
            border-radius: 16px;
            text-align: center;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06);
            transition: all 0.3s ease;
            border: 1px solid #f1f5f9;
        }}
        
        .vs-advantage-card:hover {{
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.12);
            border-color: var(--color-accent-orange);
        }}
        
        .vs-advantage-card i {{
            font-size: 44px;
            color: var(--color-accent-orange);
            margin-bottom: 20px;
        }}
        
        .vs-advantage-card h4 {{
            font-size: 17px;
            font-weight: 600;
            color: var(--color-primary);
        }}
        
        /* Related Products */
        .vs-related-products {{
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            padding: 80px 0;
        }}
        
        .vs-related-products h2 {{
            font-size: 32px;
            font-weight: 700;
            color: var(--color-primary);
            text-align: center;
            margin-bottom: 48px;
        }}
        
        .vs-related-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 24px;
        }}
        
        .vs-related-item {{
            background: white;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .vs-related-item:hover {{
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.12);
        }}
        
        .vs-related-item img {{
            width: 100%;
            height: 180px;
            object-fit: contain;
            background: #f8fafc;
            padding: 24px;
        }}
        
        .vs-related-item h4 {{
            padding: 20px;
            font-size: 15px;
            font-weight: 600;
            color: #1e293b;
            text-align: center;
        }}
        
        /* Related News */
        .vs-related-news {{
            padding: 80px 0;
        }}
        
        .vs-related-news h2 {{
            font-size: 32px;
            font-weight: 700;
            color: var(--color-primary);
            text-align: center;
            margin-bottom: 48px;
        }}
        
        .vs-news-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 32px;
        }}
        
        .vs-news-item {{
            display: flex;
            gap: 24px;
            background: white;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06);
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .vs-news-item:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.12);
        }}
        
        .vs-news-item img {{
            width: 200px;
            height: 160px;
            object-fit: cover;
            flex-shrink: 0;
        }}
        
        .vs-news-item__content {{
            padding: 24px 24px 24px 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        
        .vs-news-item__content h4 {{
            font-size: 17px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 12px;
            line-height: 1.4;
        }}
        
        .vs-news-item__content p {{
            font-size: 14px;
            color: #64748b;
            line-height: 1.7;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        
        /* CTA Section */
        .vs-cta-section {{
            background: linear-gradient(135deg, var(--color-primary) 0%, #004d8c 100%);
            padding: 80px 0;
            text-align: center;
            color: white;
        }}
        
        .vs-cta-section h3 {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        
        .vs-cta-section p {{
            font-size: 18px;
            opacity: 0.9;
            margin-bottom: 36px;
        }}
        
        .vs-breadcrumb {{
            padding: 16px 0;
            font-size: 14px;
            color: rgba(255,255,255,0.85);
        }}
        
        .vs-breadcrumb a {{
            color: rgba(255,255,255,0.85);
            text-decoration: none;
        }}
        
        .vs-breadcrumb a:hover {{
            color: white;
        }}
        
        .vs-breadcrumb span {{
            margin: 0 12px;
            opacity: 0.5;
        }}
        
        /* Responsive */
        @media (max-width: 1024px) {{
            .vs-related-grid {{ grid-template-columns: repeat(3, 1fr); }}
        }}
        
        @media (max-width: 768px) {{
            .vs-product-hero__inner {{ grid-template-columns: 1fr; gap: 40px; }}
            .vs-product-hero__content h1 {{ font-size: 32px; }}
            .vs-news-grid {{ grid-template-columns: 1fr; }}
            .vs-related-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        
        @media (max-width: 576px) {{
            .vs-related-grid {{ grid-template-columns: 1fr; }}
            .vs-news-item {{ flex-direction: column; }}
            .vs-news-item img {{ width: 100%; height: 200px; }}
        }}
    </style>
</head>

<body>

    <header class="vs-header">
        <div class="vs-container vs-header__inner">
            <div style="display: flex; align-items: center;">
                <a href="../../index.html" class="vs-logo">
                    <img src="../../assets/images/logo.png" alt="Metachip Logo" style="filter: brightness(0) invert(1);">
                    METACHIP
                </a>
            </div>
            <nav class="vs-nav">
                <ul class="vs-nav__list">
                    <li class="vs-nav__item"><a href="../../pages/products/products.aspx_category_id_0.html" class="vs-nav__link">产品</a></li>
                    <li class="vs-nav__item"><a href="../../pages/solutions/hydrogen.html" class="vs-nav__link">解决方案</a></li>
                    <li class="vs-nav__item"><a href="../../pages/news/news.html" class="vs-nav__link">洞察与资讯</a></li>
                    <li class="vs-nav__item"><a href="../../pages/about/about.html" class="vs-nav__link">公司简介</a></li>
                    <li class="vs-nav__item"><a href="../../pages/contact/contact.html" class="vs-nav__link">联系我们</a></li>
                </ul>
            </nav>
            <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#"><i class="fas fa-search"></i></a>
                <a href="#" style="font-size: 14px; font-weight: 500;">CN / EN</a>
            </div>
        </div>
    </header>

    <main style="padding-top: 90px;">
        <div style="background: var(--color-primary);">
            <div class="vs-container vs-breadcrumb">
                <a href="../../index.html">首页</a><span>|</span>
                <a href="../../pages/products/products.aspx_category_id_0.html">产品</a><span>|</span>{title}
            </div>
        </div>

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
                        <div>
                            <a href="../../pages/contact/feedback.html" class="vs-btn vs-btn--primary" style="padding: 14px 32px; font-size: 16px;">
                                <i class="fas fa-envelope" style="margin-right: 10px;"></i>咨询报价
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">产品详情</h2>
                <div class="vs-product-section__content">{product_details}</div>
            </div>
        </section>

{advantages_section}

{applications_section}

        <section class="vs-product-section alt-bg">
            <div class="vs-container">
                <h2 class="vs-product-section__title">技术指标</h2>
                <div class="vs-product-section__content">{specs_content}</div>
            </div>
        </section>

{related_news_section}

{related_products_section}

        <section class="vs-cta-section">
            <div class="vs-container">
                <h3>需要了解更多？</h3>
                <p>我们的技术团队随时为您提供专业的产品咨询和解决方案</p>
                <a href="../../pages/contact/contact.html" class="vs-btn vs-btn--secondary" style="background: white; color: var(--color-primary); padding: 16px 40px; font-size: 16px;">
                    <i class="fas fa-phone" style="margin-right: 10px;"></i>联系我们
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
                        湖南元芯传感科技有限责任公司<br>湖南省湘潭市高新区双马街道书院路38号
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


def extract_from_source(filename):
    """Extract all content from source file"""
    source_path = SOURCE_DIR / filename
    
    if not source_path.exists():
        return None
    
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    data = {}
    
    # Title
    match = re.search(r'<h3>([^<]+)</h3>', content)
    data['title'] = clean_text(match.group(1)) if match else "产品详情"
    
    # Main image
    match = re.search(r"<div class=\"bd_liimg\">\s*<img src='([^']+)'", content)
    data['main_image'] = match.group(1) if match else ""
    
    # Description
    match = re.search(r'<div class="product_top_ms">\s*(.*?)\s*</div>', content, re.DOTALL)
    if match:
        desc = re.sub(r'<[^>]+>', '', match.group(1))
        data['description'] = clean_text(desc)
    else:
        data['description'] = f"专业的{data['title']}解决方案"
    
    # Features
    match = re.search(r'<div class="product_top_td">(.*?)</div>', content, re.DOTALL)
    if match:
        features_html = match.group(1)
        features = re.findall(r'<p[^>]*>([^<]+)</p>', features_html)
        features = [clean_text(f.replace('◆', '').strip()) for f in features if f.strip() and f.strip() != '◆']
        if features:
            html_list = '<ul class="vs-feature-list">\n'
            for f in features:
                if f:
                    html_list += f'                        <li>{f}</li>\n'
            html_list += '                        </ul>'
            data['features_html'] = html_list
        else:
            data['features_html'] = ""
    else:
        data['features_html'] = ""
    
    # Product Details
    match = re.search(r'id="cpxq"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    data['product_details'] = clean_html_content(match.group(1)) if match else "<p>暂无详细信息</p>"
    
    # Advantages
    match = re.search(r'id="cpys"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        advantages = match.group(1).strip()
        items = re.findall(r'<p>([^<]+)</p>', advantages)
        items = [clean_text(i) for i in items if clean_text(i)]
        
        if items:
            icons = ['fa-bolt', 'fa-shield-alt', 'fa-microchip', 'fa-cogs', 'fa-check-circle', 'fa-chart-line']
            cards = '<div class="vs-advantages-grid">\n'
            for i, item in enumerate(items[:6]):
                icon = icons[i % len(icons)]
                cards += f'''                    <div class="vs-advantage-card">
                        <i class="fas {icon}"></i>
                        <h4>{item}</h4>
                    </div>
'''
            cards += '                </div>'
            
            data['advantages_section'] = f'''
        <section class="vs-product-section alt-bg">
            <div class="vs-container">
                <h2 class="vs-product-section__title">产品优势</h2>
                {cards}
            </div>
        </section>
'''
        else:
            data['advantages_section'] = ""
    else:
        data['advantages_section'] = ""
    
    # Applications
    match = re.search(r'id="cpyy"[^>]*>.*?<div class="product_bottom_xx">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        apps = clean_html_content(match.group(1))
        if apps and len(apps) > 20:
            data['applications_section'] = f'''
        <section class="vs-product-section">
            <div class="vs-container">
                <h2 class="vs-product-section__title">主要应用</h2>
                <div class="vs-product-section__content">{apps}</div>
            </div>
        </section>
'''
        else:
            data['applications_section'] = ""
    else:
        data['applications_section'] = ""
    
    # Specs
    match = re.search(r'id="cpzb"[^>]*>.*?<div class="product_bottom_xx[^"]*">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        specs = match.group(1)
        specs = re.sub(r'<table[^>]*>', '<table class="vs-specs-table">', specs)
        specs = re.sub(r'<tbody>', '', specs)
        specs = re.sub(r'</tbody>', '', specs)
        specs = re.sub(r'class="firstRow"', '', specs)
        specs = re.sub(r'width="[^"]*"', '', specs)
        specs = re.sub(r'valign="[^"]*"', '', specs)
        specs = re.sub(r'style="[^"]*"', '', specs)
        specs = re.sub(r'<strong>', '', specs)
        specs = re.sub(r'</strong>', '', specs)
        data['specs_content'] = clean_html_content(specs)
    else:
        data['specs_content'] = "<p>暂无技术指标</p>"
    
    # Related News
    match = re.search(r'<div class="ny_product_news">(.*?)</div>\s*</div>\s*</div>', content, re.DOTALL)
    if match:
        news_section = match.group(1)
        news_items = re.findall(r'<li>\s*<a href="([^"]+)">(.*?)</a>\s*</li>', news_section, re.DOTALL)
        
        if news_items:
            news_html = '''
        <section class="vs-related-news">
            <div class="vs-container">
                <h2>相关新闻</h2>
                <div class="vs-news-grid">
'''
            for href, item in news_items[:4]:
                img_match = re.search(r'<img src="([^"]+)"', item)
                img = img_match.group(1) if img_match else ""
                
                title_match = re.search(r'<h4>([^<]+)</h4>', item)
                title = clean_text(title_match.group(1)) if title_match else ""
                
                desc_match = re.search(r'<p>([^<]+)</p>', item)
                desc = clean_text(desc_match.group(1)) if desc_match else ""
                
                news_html += f'''                    <a href="../../pages/news/{href}" class="vs-news-item">
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
            data['related_news_section'] = news_html
        else:
            data['related_news_section'] = ""
    else:
        data['related_news_section'] = ""
    
    # Related Products
    match = re.search(r'id="xgcp"[^>]*>.*?<div class="swiper-wrapper">(.*?)</div>\s*</div>', content, re.DOTALL)
    if match:
        products_section = match.group(1)
        products = re.findall(r'<div class="swiper-slide">\s*<a href="([^"]+)">(.*?)</a>\s*</div>', products_section, re.DOTALL)
        
        if products:
            html = '''
        <section class="vs-related-products">
            <div class="vs-container">
                <h2>相关产品</h2>
                <div class="vs-related-grid">
'''
            count = 0
            for href, item in products:
                if count >= 8:
                    break
                
                img_match = re.search(r'<img src="([^"]+)"', item)
                img = img_match.group(1) if img_match else ""
                
                title_match = re.search(r'<h3>([^<]+)</h3>', item)
                title = clean_text(title_match.group(1)) if title_match else ""
                
                if not title:
                    continue
                
                html += f'''                    <a href="../../pages/products/{href}" class="vs-related-item">
                        <img src="{img}" alt="{title}">
                        <h4>{title}</h4>
                    </a>
'''
                count += 1
            
            html += '''                </div>
            </div>
        </section>
'''
            data['related_products_section'] = html
        else:
            data['related_products_section'] = ""
    else:
        data['related_products_section'] = ""
    
    return data


def process_file(filename):
    """Process a single file"""
    print(f"Processing: {filename}")
    
    data = extract_from_source(filename)
    if not data:
        print(f"  ✗ Source not found")
        return False
    
    # Generate output
    template = get_template()
    output = template.format(**data)
    
    # Write to target
    target_path = TARGET_DIR / filename
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"  ✓ Done - {data['title']}")
    return True


def main():
    """Main function"""
    source_files = list(SOURCE_DIR.glob('products_show.aspx_id_*.html'))
    print(f"Found {len(source_files)} product pages\n")
    
    processed = 0
    for source_file in sorted(source_files):
        if process_file(source_file.name):
            processed += 1
    
    print(f"\nProcessed {processed} pages")


if __name__ == '__main__':
    main()
