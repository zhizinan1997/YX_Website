#!/usr/bin/env python3
"""
整理产品页面脚本
1. 创建 products 文件夹
2. 移动所有 products_show.aspx_id_*.html 文件到该文件夹
3. 更新所有 HTML 文件中的相关链接路径
"""

import os
import re
import shutil
from pathlib import Path

# 工作目录
WORK_DIR = Path('/Users/zhizinan/Desktop/YX_Website')
PRODUCTS_DIR = WORK_DIR / 'products'

def get_product_files():
    """获取所有产品页面文件"""
    return list(WORK_DIR.glob('products_show.aspx_id_*.html'))

def create_products_folder():
    """创建 products 文件夹"""
    if not PRODUCTS_DIR.exists():
        PRODUCTS_DIR.mkdir()
        print(f"✅ 创建文件夹: {PRODUCTS_DIR}")
    else:
        print(f"📁 文件夹已存在: {PRODUCTS_DIR}")

def move_product_files(product_files):
    """移动产品文件到 products 文件夹"""
    moved_files = []
    for file in product_files:
        dest = PRODUCTS_DIR / file.name
        if not dest.exists():
            shutil.move(str(file), str(dest))
            moved_files.append(file.name)
            print(f"  📦 移动: {file.name}")
        else:
            print(f"  ⚠️ 目标已存在，跳过: {file.name}")
    return moved_files

def get_all_html_files():
    """获取所有需要更新链接的 HTML 文件"""
    html_files = []
    # 根目录
    html_files.extend(WORK_DIR.glob('*.html'))
    # news 文件夹
    html_files.extend((WORK_DIR / 'news').glob('*.html'))
    # products 文件夹（新创建的）
    html_files.extend(PRODUCTS_DIR.glob('*.html'))
    return html_files

def update_links_in_file(file_path, product_filenames):
    """更新单个文件中的产品链接"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"    ⚠️ 无法读取文件 {file_path}: {e}")
        return 0
    
    original_content = content
    changes = 0
    
    # 判断当前文件所在位置，确定相对路径前缀
    file_dir = file_path.parent
    
    if file_dir == WORK_DIR:
        # 根目录下的文件：products_show... -> products/products_show...
        prefix = 'products/'
    elif file_dir == PRODUCTS_DIR:
        # products 文件夹内的文件：保持原样或使用相对路径
        prefix = ''  # 同目录下
    elif file_dir.name == 'news':
        # news 文件夹内的文件：../products_show... -> ../products/products_show...
        prefix = '../products/'
    else:
        # 其他子目录
        rel_path = os.path.relpath(PRODUCTS_DIR, file_dir)
        prefix = rel_path.replace('\\', '/') + '/'
    
    for filename in product_filenames:
        # 不同的链接模式
        patterns = [
            # href="products_show.aspx_id_XX.html"
            (f'href="{filename}"', f'href="{prefix}{filename}"'),
            # href='products_show.aspx_id_XX.html'
            (f"href='{filename}'", f"href='{prefix}{filename}'"),
            # href="../products_show.aspx_id_XX.html" (from news folder)
            (f'href="../{filename}"', f'href="../products/{filename}"'),
            # src 属性（以防万一）
            (f'src="{filename}"', f'src="{prefix}{filename}"'),
        ]
        
        for old, new in patterns:
            if old in content and old != new:
                content = content.replace(old, new)
                changes += content.count(new) - original_content.count(new)
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes
    return 0

def update_internal_links_in_products():
    """更新产品页面内部的相对链接（模板资源等）"""
    for file in PRODUCTS_DIR.glob('*.html'):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            continue
        
        original = content
        
        # 更新模板资源路径（从 templates/... 到 ../templates/...）
        # 只有当链接不是以 ../ 或 http 开头时才更新
        replacements = [
            ('href="templates/', 'href="../templates/'),
            ("href='templates/", "href='../templates/"),
            ('src="templates/', 'src="../templates/'),
            ("src='templates/", "src='../templates/"),
            # 更新指向根目录其他页面的链接
            ('href="index.html"', 'href="../index.html"'),
            ('href="about.aspx_', 'href="../about.aspx_'),
            ('href="contact.aspx_', 'href="../contact.aspx_'),
            ('href="news.aspx_', 'href="../news.aspx_'),
            ('href="products.aspx_', 'href="../products.aspx_'),
            ('href="rlzy.aspx_', 'href="../rlzy.aspx_'),
            ('href="jobs.aspx_', 'href="../jobs.aspx_'),
            ('href="feedbook.aspx', 'href="../feedbook.aspx'),
            ('href="hydrogen-solutions.html"', 'href="../hydrogen-solutions.html"'),
            ('href="industry-', 'href="../industry-'),
        ]
        
        for old, new in replacements:
            # 避免重复替换
            if old in content and new not in content.replace(old, new):
                content = content.replace(old, new)
        
        if content != original:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  🔗 更新内部链接: {file.name}")

def main():
    print("=" * 50)
    print("🚀 开始整理产品页面")
    print("=" * 50)
    
    # 1. 获取产品文件
    product_files = get_product_files()
    print(f"\n📋 找到 {len(product_files)} 个产品页面文件")
    
    if not product_files:
        print("没有找到需要移动的产品页面。")
        return
    
    # 2. 创建目标文件夹
    print("\n📁 创建 products 文件夹...")
    create_products_folder()
    
    # 3. 移动文件
    print("\n📦 移动产品页面...")
    product_filenames = [f.name for f in product_files]
    moved_files = move_product_files(product_files)
    print(f"✅ 成功移动 {len(moved_files)} 个文件")
    
    # 4. 更新所有 HTML 文件中的链接
    print("\n🔗 更新相关链接...")
    html_files = get_all_html_files()
    total_changes = 0
    files_updated = 0
    
    for html_file in html_files:
        changes = update_links_in_file(html_file, product_filenames)
        if changes > 0:
            total_changes += changes
            files_updated += 1
            print(f"  ✏️ {html_file.name}: 更新 {changes} 处链接")
    
    # 5. 更新产品页面内部的资源链接
    print("\n🔧 更新产品页面内部链接...")
    update_internal_links_in_products()
    
    print("\n" + "=" * 50)
    print(f"🎉 整理完成!")
    print(f"   - 移动了 {len(moved_files)} 个产品页面到 products/ 文件夹")
    print(f"   - 更新了 {files_updated} 个文件中的 {total_changes} 处链接")
    print("=" * 50)

if __name__ == '__main__':
    main()
