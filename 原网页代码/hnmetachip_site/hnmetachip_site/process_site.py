#!/usr/bin/env python3
"""
处理爬取的网站文件，使其兼容静态服务器部署
1. 重命名包含特殊字符的文件
2. 更新所有 HTML/CSS 文件中的内部链接
"""

import os
import re
from pathlib import Path

SITE_DIR = "/Users/zhizinan/Desktop/yx/hnmetachip_site/www.hnmetachip.cn"

def sanitize_filename(filename):
    """将文件名中的特殊字符替换为下划线"""
    # 保留扩展名
    base, ext = os.path.splitext(filename)
    
    # 替换特殊字符: @ ? & = 等
    sanitized = base.replace('@', '_').replace('?', '_').replace('&', '_').replace('=', '_')
    
    # 连续的下划线替换为单个
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # 移除首尾下划线
    sanitized = sanitized.strip('_')
    
    return sanitized + ext

def get_all_files(directory):
    """获取目录下所有文件"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            files.append(os.path.join(root, filename))
    return files

def create_rename_map(directory):
    """创建重命名映射表"""
    rename_map = {}  # old_name -> new_name
    
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if '@' in filename or '?' in filename or '&' in filename:
                new_filename = sanitize_filename(filename)
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, new_filename)
                
                # 存储相对路径映射（用于替换链接）
                old_rel = os.path.relpath(old_path, directory)
                new_rel = os.path.relpath(new_path, directory)
                
                rename_map[old_rel] = new_rel
                rename_map[filename] = new_filename
    
    return rename_map

def update_links_in_file(filepath, rename_map):
    """更新文件中的链接"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return False
    
    original_content = content
    
    # 按照文件名长度降序排序，避免部分匹配问题
    sorted_keys = sorted(rename_map.keys(), key=len, reverse=True)
    
    for old_name, new_name in [(k, rename_map[k]) for k in sorted_keys]:
        # 替换 href 和 src 属性中的链接
        content = content.replace(f'"{old_name}"', f'"{new_name}"')
        content = content.replace(f"'{old_name}'", f"'{new_name}'")
        content = content.replace(f'href="{old_name}"', f'href="{new_name}"')
        content = content.replace(f"href='{old_name}'", f"href='{new_name}'")
        
        # URL 编码的版本也要替换
        old_encoded = old_name.replace('@', '%40').replace('&', '%26').replace('=', '%3D')
        content = content.replace(old_encoded, new_name)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def rename_files(directory, rename_map):
    """重命名文件"""
    renamed = []
    
    # 收集需要重命名的文件
    files_to_rename = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if '@' in filename or '?' in filename or '&' in filename:
                old_path = os.path.join(root, filename)
                new_filename = sanitize_filename(filename)
                new_path = os.path.join(root, new_filename)
                files_to_rename.append((old_path, new_path, filename, new_filename))
    
    # 执行重命名
    for old_path, new_path, old_name, new_name in files_to_rename:
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)
            renamed.append((old_name, new_name))
            print(f"重命名: {old_name} -> {new_name}")
    
    return renamed

def main():
    print("=" * 60)
    print("开始处理网站文件...")
    print("=" * 60)
    
    # 1. 创建重命名映射
    print("\n[1/3] 分析需要重命名的文件...")
    rename_map = create_rename_map(SITE_DIR)
    print(f"发现 {len(rename_map) // 2} 个需要重命名的文件")
    
    # 2. 更新所有 HTML 和 CSS 文件中的链接
    print("\n[2/3] 更新内部链接...")
    updated_count = 0
    all_files = get_all_files(SITE_DIR)
    
    for filepath in all_files:
        if filepath.endswith(('.html', '.css', '.js')):
            if update_links_in_file(filepath, rename_map):
                updated_count += 1
    
    print(f"更新了 {updated_count} 个文件中的链接")
    
    # 3. 重命名文件
    print("\n[3/3] 重命名文件...")
    renamed = rename_files(SITE_DIR, rename_map)
    print(f"成功重命名 {len(renamed)} 个文件")
    
    print("\n" + "=" * 60)
    print("处理完成！")
    print("=" * 60)
    
    # 统计
    html_files = len([f for f in all_files if f.endswith('.html')])
    print(f"\n📊 统计:")
    print(f"   HTML 页面: {html_files}")
    print(f"   重命名文件: {len(renamed)}")
    print(f"   更新链接文件: {updated_count}")

if __name__ == "__main__":
    main()
