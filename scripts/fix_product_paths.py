#!/usr/bin/env python3
"""
更新产品页面内部链接脚本
将移动到 products/ 文件夹后的产品页面中的相对路径全部更新
"""

import os
import re
from pathlib import Path

PRODUCTS_DIR = Path('/Users/zhizinan/Desktop/YX_Website/products')

def update_product_page(file_path):
    """更新单个产品页面的所有相对路径"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ⚠️ 无法读取 {file_path.name}: {e}")
        return False
    
    original = content
    
    # 需要添加 ../ 前缀的路径模式
    path_updates = [
        # CSS 和 JS 资源
        (r'href="templates/', 'href="../templates/'),
        (r"href='templates/", "href='../templates/"),
        (r'src="templates/', 'src="../templates/'),
        (r"src='templates/", "src='../templates/"),
        (r'src="scripts/', 'src="../scripts/'),
        (r'href="css/', 'href="../css/'),
        
        # 页面链接（非 http 开头）
        (r'href="index\.html"', 'href="../index.html"'),
        (r'href="about\.aspx_', 'href="../about.aspx_'),
        (r'href="contact\.aspx_', 'href="../contact.aspx_'),
        (r'href="news\.aspx_', 'href="../news.aspx_'),
        (r'href="products\.aspx_', 'href="../products.aspx_'),
        (r'href="rlzy\.aspx_', 'href="../rlzy.aspx_'),
        (r'href="jobs\.aspx_', 'href="../jobs.aspx_'),
        (r'href="feedbook\.aspx', 'href="../feedbook.aspx'),
        (r'href="jjfa\.aspx_', 'href="../jjfa.aspx_'),
        (r'href="service\.aspx_', 'href="../service.aspx_'),
        (r'href="wnjg\.aspx_', 'href="../wnjg.aspx_'),
        (r'href="hxfw\.aspx_', 'href="../hxfw.aspx_'),
        (r'href="cxyj\.aspx_', 'href="../cxyj.aspx_'),
        (r'href="honor\.aspx_', 'href="../honor.aspx_'),
        (r'href="hydrogen-solutions\.html"', 'href="../hydrogen-solutions.html"'),
        (r'href="industry-', 'href="../industry-'),
        
        # 新闻链接
        (r'href="news_show\.aspx_', 'href="../news/news_show.aspx_'),
    ]
    
    for pattern, replacement in path_updates:
        # 避免重复替换（已经有 ../ 的不要再加）
        content = re.sub(pattern, replacement, content)
    
    # 如果有变化，保存文件
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=" * 50)
    print("🔧 更新产品页面内部链接")
    print("=" * 50)
    
    product_files = list(PRODUCTS_DIR.glob('*.html'))
    print(f"\n📋 找到 {len(product_files)} 个产品页面")
    
    updated_count = 0
    for file in product_files:
        if update_product_page(file):
            print(f"  ✅ 更新: {file.name}")
            updated_count += 1
        else:
            print(f"  ⏭️ 无需更新: {file.name}")
    
    print(f"\n🎉 完成！更新了 {updated_count} 个文件")

if __name__ == '__main__':
    main()
