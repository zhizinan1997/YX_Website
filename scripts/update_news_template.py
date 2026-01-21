#!/usr/bin/env python3
"""
Script to update all news detail pages to the new Vaisala v2.0 design system.
Preserves the original article content while wrapping it in the new template.
"""

import os
import re
import glob

# Directory containing news files
NEWS_DIR = "/Users/zhizinan/Desktop/YX_Website/news"

# Template for the new news detail page
TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{title} - 湖南元芯传感科技有限责任公司</title>
    
    <!-- Vaisala Style V2.0 -->
    <link rel="stylesheet" href="../templates/lqgd/css/vaisala-style.css">
    
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        .article-hero {{
            position: relative;
            background: linear-gradient(135deg, rgba(0, 31, 63, 0.9) 0%, rgba(0, 31, 63, 0.7) 100%), url('../templates/lqgd/images/section2_bj.jpg') center/cover;
            height: 40vh;
            min-height: 300px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: white;
            padding: 0 20px;
        }}
        .article-hero__title {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 16px;
            max-width: 900px;
            line-height: 1.4;
        }}
        .article-hero__meta {{
            font-size: 16px;
            opacity: 0.8;
        }}
        .article-container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }}
        .article-content {{
            font-size: 17px;
            line-height: 1.9;
            color: #333;
        }}
        .article-content p {{
            margin-bottom: 20px;
        }}
        .article-content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 24px 0;
        }}
        .article-content strong {{
            color: var(--color-primary);
        }}
        .article-content ul, .article-content ol {{
            margin: 20px 0;
            padding-left: 30px;
        }}
        .article-content li {{
            margin-bottom: 10px;
        }}
        .article-nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 40px 0;
            border-top: 1px solid #eee;
            margin-top: 40px;
        }}
        .article-nav a {{
            color: var(--color-primary);
            text-decoration: none;
            font-weight: 500;
        }}
        .article-nav a:hover {{
            text-decoration: underline;
        }}
        .back-btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: var(--color-primary);
            color: white;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
        }}
        .back-btn:hover {{
            background: var(--color-accent-blue);
            transform: translateY(-2px);
        }}
    </style>
</head>
<body>
    <!-- Header -->
    <header class="vs-header">
        <div class="vs-container vs-header__inner">
            <div style="display: flex; align-items: center;">
                <a href="../index.html" class="vs-logo">
                    <img src="../templates/lqgd/images/logo.png" alt="Metachip Logo" style="filter: brightness(0) invert(1);">
                    METACHIP
                </a>
            </div>
            <nav class="vs-nav" style="margin-left: auto; margin-right: 40px;">
                <ul class="vs-nav__list">
                    <li class="vs-nav__item">
                        <a href="../news.aspx_category_id_0.html" class="vs-nav__link active">洞察与资讯</a>
                    </li>
                    <li class="vs-nav__item">
                        <a href="../about.aspx_page_about.html" class="vs-nav__link">关于元芯</a>
                    </li>
                    <li class="vs-nav__item">
                        <a href="../contact.aspx_page_contact.html" class="vs-nav__link">联系我们</a>
                    </li>
                </ul>
            </nav>
            <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#"><i class="fas fa-search"></i></a>
                <a href="#" style="font-size: 14px; font-weight: 500;">CN / EN</a>
            </div>
        </div>
    </header>

    <main>
        <!-- Article Hero -->
        <section class="article-hero">
            <h1 class="article-hero__title">{title}</h1>
            <div class="article-hero__meta"><i class="far fa-calendar-alt"></i> {date}</div>
        </section>

        <!-- Article Content -->
        <article class="article-container">
            <div class="article-content">
                {content}
            </div>
            
            <div class="article-nav">
                <a href="../news.aspx_category_id_0.html" class="back-btn">
                    <i class="fas fa-arrow-left"></i> 返回新闻列表
                </a>
            </div>
        </article>
    </main>

    <!-- Footer -->
    <footer class="vs-footer">
        <div class="vs-container">
            <div class="vs-footer__grid">
                <div class="vs-footer__col" style="padding-right: 40px;">
                    <a href="../index.html" class="vs-logo" style="margin-bottom: 24px;">
                        <img src="../templates/lqgd/images/logo.png" style="filter: brightness(0) invert(1);" alt="Logo">
                        METACHIP
                    </a>
                    <p style="color: rgba(255, 255, 255, 0.6); line-height: 1.8;">
                        湖南元芯传感科技有限责任公司<br>
                        专注于先进生物与化学传感技术<br>
                        致力于成为全球领先的智能传感解决方案提供商
                    </p>
                </div>
                <div class="vs-footer__col">
                    <h4>公司信息</h4>
                    <a href="../about.aspx_page_about.html" class="vs-footer__link">关于我们</a>
                    <a href="../news.aspx_category_id_0.html" class="vs-footer__link">新闻中心</a>
                    <a href="../contact.aspx_page_contact.html" class="vs-footer__link">联系方式</a>
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

def extract_content(html_content):
    """Extract title, date, and main content from the old page."""
    
    # Extract title from <title> tag or <h1>
    title_match = re.search(r'<title>([^<]+?)(?:-湖南元芯传感科技有限责任公司)?</title>', html_content)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content)
        title = title_match.group(1).strip() if title_match else "新闻详情"
    
    # Extract date
    date_match = re.search(r'发布时间[：:]?\s*(\d{4}-\d{2}-\d{2})', html_content)
    date = date_match.group(1) if date_match else ""
    
    # Extract main content (from keyword_light div)
    content_match = re.search(r'<div class="keyword_light">(.*?)</div>\s*(?=<table|</div>\s*<table)', html_content, re.DOTALL)
    if content_match:
        content = content_match.group(1).strip()
    else:
        # Try alternate extraction
        content_match = re.search(r'点击次数[：:]\d+\s*</div>\s*(.*?)\s*<table', html_content, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            content = ""
    
    # Clean up content - remove data-lark attributes and empty spans
    content = re.sub(r'<span[^>]*data-lark[^>]*>[^<]*</span>', '', content)
    content = re.sub(r'data-[a-z-]+="[^"]*"', '', content)
    content = re.sub(r'class="[^"]*lark[^"]*"', '', content)
    content = re.sub(r'class="ace-line[^"]*"', '', content)
    content = re.sub(r'<div>\s*</div>', '', content)
    
    return title, date, content

def process_file(filepath):
    """Process a single news file."""
    print(f"Processing: {filepath}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        title, date, content = extract_content(html_content)
        
        if not content:
            print(f"  Warning: No content extracted from {filepath}")
            return False
        
        # Generate new page
        new_html = TEMPLATE.format(
            title=title,
            date=date,
            content=content
        )
        
        # Write new file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_html)
        
        print(f"  Success: Updated with title '{title}'")
        return True
        
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    """Process all news files."""
    news_files = glob.glob(os.path.join(NEWS_DIR, "news_show.aspx_id_*.html"))
    
    print(f"Found {len(news_files)} news files to process.\n")
    
    success_count = 0
    for filepath in sorted(news_files):
        if process_file(filepath):
            success_count += 1
    
    print(f"\n{'='*50}")
    print(f"Completed: {success_count}/{len(news_files)} files updated successfully.")

if __name__ == "__main__":
    main()
