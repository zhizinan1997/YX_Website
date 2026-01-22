#!/usr/bin/env python3
"""
Beautify product detail pages - clean up HTML entities and improve styling.
"""

import os
import re
from pathlib import Path
import html

# Directories
BASE_DIR = Path('/Users/zhizinan/Desktop/YX_Website')
TARGET_DIR = BASE_DIR / 'pages' / 'products'


def clean_html_content(content):
    """Clean up HTML entities and malformed content"""
    
    # Decode HTML entities
    content = html.unescape(content)
    
    # Fix common encoding issues
    content = content.replace('&#39;', "'")
    content = content.replace('&amp;', '&')
    content = content.replace('&nbsp;', ' ')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    
    # Clean up empty style attributes
    content = re.sub(r'style="[^"]*font-family:\s*\'\'[^"]*"', '', content)
    content = re.sub(r'style=";[^"]*"', '', content)
    
    # Clean up excessive whitespace in inline styles
    content = re.sub(r'\s+', ' ', content)
    
    # Fix broken closing tags
    content = content.replace('<br/>', '<br>')
    content = content.replace('/>', '>')
    
    return content


def get_improved_template():
    """Return improved page template with cleaner styles"""
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
        /* Product Detail Page - Enhanced Styles */
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
            font-size: 44px;
            font-weight: 700;
            margin-bottom: 20px;
            line-height: 1.2;
        }}
        
        .vs-product-hero__desc {{
            font-size: 18px;
            opacity: 0.95;
            line-height: 1.7;
            margin-bottom: 28px;
        }}
        
        .vs-feature-list {{
            list-style: none;
            padding: 0;
            margin: 0 0 30px 0;
            display: grid;
            gap: 12px;
        }}
        
        .vs-feature-list li {{
            padding: 10px 16px 10px 44px;
            position: relative;
            font-size: 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            backdrop-filter: blur(10px);
        }}
        
        .vs-feature-list li::before {{
            content: '✓';
            position: absolute;
            left: 16px;
            color: #4ADE80;
            font-weight: bold;
            font-size: 16px;
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
            margin-bottom: 18px;
        }}
        
        .vs-product-section__content img {{
            max-width: 100%;
            height: auto;
            border-radius: 12px;
            margin: 16px 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        
        /* Specs Table */
        .vs-specs-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}
        
        .vs-specs-table td {{
            padding: 16px 24px;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        .vs-specs-table tr:last-child td {{
            border-bottom: none;
        }}
        
        .vs-specs-table tr td:first-child {{
            background: var(--color-primary);
            color: white;
            font-weight: 600;
            width: 200px;
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
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-top: 24px;
        }}
        
        .vs-advantage-card {{
            background: white;
            padding: 32px;
            border-radius: 16px;
            text-align: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            transition: all 0.3s ease;
        }}
        
        .vs-advantage-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.12);
        }}
        
        .vs-advantage-card i {{
            font-size: 40px;
            color: var(--color-accent-orange);
            margin-bottom: 16px;
        }}
        
        .vs-advantage-card h4 {{
            font-size: 18px;
            font-weight: 600;
            color: var(--color-primary);
            margin-bottom: 8px;
        }}
        
        .vs-advantage-card p {{
            font-size: 14px;
            color: #64748b;
            line-height: 1.6;
        }}
        
        /* Applications Section */
        .vs-applications-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-top: 24px;
        }}
        
        .vs-application-card {{
            position: relative;
            border-radius: 16px;
            overflow: hidden;
            aspect-ratio: 16/10;
        }}
        
        .vs-application-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            margin: 0 !important;
            border-radius: 0 !important;
        }}
        
        .vs-application-card__overlay {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
            color: white;
        }}
        
        .vs-application-card__overlay h4 {{
            font-size: 16px;
            font-weight: 600;
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
            background: white;
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
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
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
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .vs-breadcrumb {{
            padding: 16px 0;
            font-size: 14px;
            color: rgba(255,255,255,0.85);
        }}
        
        .vs-breadcrumb a {{
            color: rgba(255,255,255,0.85);
            text-decoration: none;
            transition: color 0.2s;
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
            .vs-related-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}
            .vs-advantages-grid,
            .vs-applications-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (max-width: 768px) {{
            .vs-product-hero__inner {{
                grid-template-columns: 1fr;
                gap: 40px;
            }}
            
            .vs-product-hero__content h1 {{
                font-size: 32px;
            }}
            
            .vs-news-grid {{
                grid-template-columns: 1fr;
            }}
            
            .vs-related-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            
            .vs-advantages-grid,
            .vs-applications-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        @media (max-width: 576px) {{
            .vs-related-grid {{
                grid-template-columns: 1fr;
            }}
            
            .vs-news-item {{
                flex-direction: column;
            }}
            
            .vs-news-item img {{
                width: 100%;
                height: 200px;
            }}
            
            .vs-news-item__content {{
                padding: 20px;
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
                        <div>
                            <a href="../../pages/contact/feedback.html" class="vs-btn vs-btn--primary" style="padding: 14px 32px; font-size: 16px;">
                                <i class="fas fa-envelope" style="margin-right: 10px;"></i>咨询报价
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
        <section class="vs-product-section alt-bg">
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
    match = re.search(r'<h1>([^<]+)</h1>', content)
    if match:
        return clean_text(match.group(1))
    return "产品详情"


def extract_main_image(content):
    """Extract main product image"""
    match = re.search(r'vs-product-hero__image[^>]*>\s*<img src="([^"]+)"', content)
    if match:
        return match.group(1)
    return ""


def extract_description(content):
    """Extract product description"""
    match = re.search(r'vs-product-hero__desc[^>]*>([^<]+)<', content)
    if match:
        return clean_text(match.group(1))
    return ""


def extract_features(content):
    """Extract product features"""
    match = re.search(r'<ul class="vs-feature-list">(.*?)</ul>', content, re.DOTALL)
    if match:
        features_html = match.group(1)
        # Extract individual features
        features = re.findall(r'<li>([^<]+)</li>', features_html)
        if features:
            html = '<ul class="vs-feature-list">\n'
            for f in features:
                f = clean_text(f)
                if f:
                    html += f'                            <li>{f}</li>\n'
            html += '                        </ul>'
            return html
    return ""


def extract_product_details(content):
    """Extract product details section"""
    match = re.search(r'产品详情</h2>\s*<div class="vs-product-section__content">(.*?)</div>\s*</div>\s*</section>', content, re.DOTALL)
    if match:
        details = match.group(1).strip()
        return clean_html(details)
    return "<p>暂无详细信息</p>"


def extract_advantages(content):
    """Extract product advantages section"""
    match = re.search(r'产品优势</h2>\s*<div class="vs-product-section__content">(.*?)</div>\s*</div>\s*</section>', content, re.DOTALL)
    if match:
        advantages = match.group(1).strip()
        advantages = clean_html(advantages)
        
        # Try to convert to nice cards
        items = re.findall(r'<p>([^<]+)</p>', advantages)
        if items and len(items) >= 2:
            icons = ['fa-bolt', 'fa-shield-alt', 'fa-microchip', 'fa-cogs', 'fa-check-circle', 'fa-chart-line']
            cards_html = '<div class="vs-advantages-grid">\n'
            for i, item in enumerate(items[:6]):
                item = clean_text(item)
                if item:
                    icon = icons[i % len(icons)]
                    cards_html += f'''                    <div class="vs-advantage-card">
                        <i class="fas {icon}"></i>
                        <h4>{item}</h4>
                    </div>
'''
            cards_html += '                </div>'
            
            return f'''
        <!-- Product Advantages -->
        <section class="vs-product-section alt-bg">
            <div class="vs-container">
                <h2 class="vs-product-section__title">产品优势</h2>
                {cards_html}
            </div>
        </section>
'''
        elif advantages and len(advantages) > 20:
            return f'''
        <!-- Product Advantages -->
        <section class="vs-product-section alt-bg">
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
    match = re.search(r'主要应用</h2>\s*<div class="vs-product-section__content">(.*?)</div>\s*</div>\s*</section>', content, re.DOTALL)
    if match:
        apps = match.group(1).strip()
        apps = clean_html(apps)
        
        if apps and len(apps) > 20:
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
    match = re.search(r'技术指标</h2>\s*<div class="vs-product-section__content">(.*?)</div>\s*</div>\s*</section>', content, re.DOTALL)
    if match:
        specs = match.group(1).strip()
        
        # Clean up table
        specs = re.sub(r'<table[^>]*>', '<table class="vs-specs-table">', specs)
        specs = re.sub(r'<tbody>', '', specs)
        specs = re.sub(r'</tbody>', '', specs)
        specs = re.sub(r'class="firstRow"', '', specs)
        specs = re.sub(r'width="[^"]*"', '', specs)
        specs = re.sub(r'valign="[^"]*"', '', specs)
        specs = re.sub(r'style="[^"]*"', '', specs)
        specs = re.sub(r'<strong>', '', specs)
        specs = re.sub(r'</strong>', '', specs)
        
        return clean_html(specs)
    return "<p>暂无技术指标</p>"


def extract_related_news(content):
    """Extract related news section"""
    match = re.search(r'<section class="vs-related-news">(.*?)</section>', content, re.DOTALL)
    if match:
        return f'''
        <!-- Related News -->
        <section class="vs-related-news">
{match.group(1)}        </section>
'''
    return ""


def extract_related_products(content):
    """Extract related products section"""
    match = re.search(r'<section class="vs-related-products">(.*?)</section>', content, re.DOTALL)
    if match:
        return f'''
        <!-- Related Products -->
        <section class="vs-related-products">
{match.group(1)}        </section>
'''
    return ""


def clean_text(text):
    """Clean up text content"""
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_html(content):
    """Clean up HTML content"""
    if not content:
        return ""
    
    # Decode HTML entities
    content = html.unescape(content)
    
    # Clean common issues
    content = content.replace('&nbsp;', ' ')
    content = re.sub(r'style="[^"]*font-family:\s*\'[^\']*\'[^"]*"', '', content)
    content = re.sub(r'style=";[^"]*"', '', content)
    content = re.sub(r'style="text-wrap:\s*wrap;?"', '', content)
    
    # Fix image sizing issues
    content = re.sub(r'width="1"\s*height="1"[^>]*style="width:\s*1px;\s*height:\s*1px;"', 'style="display:none"', content)
    
    # Clean excessive breaks
    content = re.sub(r'(<br\s*/?>){3,}', '<br><br>', content)
    content = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', content)
    
    return content.strip()


def beautify_product_page(filepath):
    """Beautify a single product page"""
    print(f"Beautifying: {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
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
    
    # Generate new page with improved template
    template = get_improved_template()
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
    
    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True


def main():
    """Main function"""
    product_files = list(TARGET_DIR.glob('products_show.aspx_id_*.html'))
    print(f"Found {len(product_files)} product pages to beautify\n")
    
    beautified = 0
    for filepath in sorted(product_files):
        if beautify_product_page(filepath):
            beautified += 1
            print(f"  ✓ Done")
        else:
            print(f"  ✗ Failed")
    
    print(f"\nBeautified {beautified} pages")


if __name__ == '__main__':
    main()
