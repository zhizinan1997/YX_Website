#!/usr/bin/env python3
"""
产品列表自动更新脚本
扫描 pages/gassensing/ 目录下的产品HTML文件，提取产品信息并更新 products-data.js

使用方法：
    python scripts/update-products.py

产品HTML文件需要包含以下meta标签：
    <meta name="product-name" content="产品全称">
    <meta name="product-short-name" content="产品简称（用于菜单显示）">
    <meta name="product-description" content="产品描述">
    <meta name="product-image" content="产品图片URL">
    <meta name="product-category" content="sensor|module|detector|alarm|system|iot|probe|service">
"""

import os
import re
import json
from pathlib import Path
from html.parser import HTMLParser

# 配置
GASSENSING_DIR = Path(__file__).parent.parent / 'pages' / 'gassensing'
OUTPUT_FILE = Path(__file__).parent.parent / 'assets' / 'js' / 'products-data.js'

# 排除的文件（索引页、分类页等）
EXCLUDED_FILES = {
    'index.html',
    'gas_sensors.html',
    'gas_sensors_page_2.html', 
    'gas_sensors_page_3.html',
    'products_mems.html',
    'products_handheld.html',
    'products_systems.html',
    'products_modules.html'
}

class ProductMetaParser(HTMLParser):
    """解析产品HTML文件中的meta标签"""
    
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title = ''
        self.in_title = False
        
    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs_dict = dict(attrs)
            name = attrs_dict.get('name', '')
            content = attrs_dict.get('content', '')
            if name.startswith('product-'):
                key = name.replace('product-', '')
                self.meta[key] = content
        elif tag == 'title':
            self.in_title = True
            
    def handle_data(self, data):
        if self.in_title:
            self.title = data.strip()
            
    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

def extract_product_info_from_html(filepath):
    """从HTML文件中提取产品信息"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  警告: 无法读取 {filepath}: {e}")
        return None
    
    parser = ProductMetaParser()
    try:
        parser.feed(content)
    except Exception as e:
        print(f"  警告: 解析 {filepath} 失败: {e}")
        return None
    
    # 如果有meta标签，使用meta标签信息
    if parser.meta.get('name'):
        return {
            'id': filepath.stem,
            'name': parser.meta.get('name', ''),
            'shortName': parser.meta.get('short-name', parser.meta.get('name', '')),
            'image': parser.meta.get('image', ''),
            'description': parser.meta.get('description', ''),
            'category': parser.meta.get('category', 'module')
        }
    
    # 否则尝试从title和页面内容推断
    name = parser.title.replace(' - 元芯传感', '').replace(' - 气体传感产品', '').strip()
    if name:
        return {
            'id': filepath.stem,
            'name': name,
            'shortName': name,
            'image': '',
            'description': '',
            'category': 'module'
        }
    
    return None

def scan_products():
    """扫描产品目录，获取所有产品信息"""
    products = []
    
    if not GASSENSING_DIR.exists():
        print(f"错误: 产品目录不存在: {GASSENSING_DIR}")
        return products
    
    print(f"扫描目录: {GASSENSING_DIR}")
    
    for filepath in sorted(GASSENSING_DIR.glob('*.html')):
        if filepath.name in EXCLUDED_FILES:
            continue
            
        print(f"  处理: {filepath.name}")
        product = extract_product_info_from_html(filepath)
        if product:
            products.append(product)
            print(f"    ✓ {product['name']}")
        else:
            print(f"    ✗ 无法提取产品信息")
    
    return products

def generate_js_file(products):
    """生成 products-data.js 文件"""
    
    # 按类别排序（优先级：iot > module > sensor > detector > alarm > system > probe > service）
    category_order = {'iot': 0, 'module': 1, 'sensor': 2, 'detector': 3, 'alarm': 4, 'system': 5, 'probe': 6, 'service': 7}
    products.sort(key=lambda p: (category_order.get(p.get('category', 'module'), 99), p.get('name', '')))
    
    js_content = '''/**
 * 共享产品数据 (自动生成)
 * 
 * ⚠️ 此文件由 scripts/update-products.py 自动生成
 * 请勿手动编辑，修改会被覆盖
 * 
 * 添加新产品步骤：
 * 1. 在 pages/gassensing/ 目录下创建产品HTML文件
 * 2. 在HTML文件中添加 product-* meta标签
 * 3. 运行 python scripts/update-products.py
 */

const GAS_SENSING_PRODUCTS = '''
    
    # 格式化输出
    js_content += json.dumps(products, ensure_ascii=False, indent=4)
    js_content += ";\n"
    
    # 写入文件
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    print(f"\n已生成: {OUTPUT_FILE}")
    print(f"共 {len(products)} 个产品")

def main():
    print("=" * 50)
    print("产品列表自动更新脚本")
    print("=" * 50)
    
    products = scan_products()
    
    if not products:
        print("\n警告: 没有找到任何产品")
        return
    
    generate_js_file(products)
    
    print("\n完成！刷新网页即可看到更新。")

if __name__ == '__main__':
    main()
