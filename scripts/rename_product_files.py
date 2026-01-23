#!/usr/bin/env python3
"""
批量重命名产品页面文件并更新所有引用
"""

import os
import re
import glob

# 项目根目录
ROOT_DIR = '/Users/zhizinan/Desktop/YX_Website'

# 文件名映射表：旧文件名 -> 新文件名
RENAME_MAP = {
    # 气体传感 (gassensing)
    'products_show.aspx_id_114.html': 'mcect_electrochemical_h2.html',
    'products_show.aspx_id_115.html': 'mctcx_thermal_h2.html',
    'products_show.aspx_id_57.html': 'mchs_palladium_h2.html',
    'products_show.aspx_id_71.html': 'mchf_carbon_fet_h2.html',
    'products_show.aspx_id_72.html': 'mchc_catalytic_h2.html',
    'products_show.aspx_id_73.html': 'mchm_h2_sensor.html',
    'products_show.aspx_id_69.html': 'mc_hfev_module.html',
    'products_show.aspx_id_70.html': 'h2_detection_probe.html',
    'products_show.aspx_id_83.html': 'mchp_vehicle_h2.html',
    'products_show.aspx_id_79.html': 'ld_h2_detector.html',
    'products_show.aspx_id_81.html': 'mc_hla_fixed_alarm.html',
    'products_show.aspx_id_82.html': 'mc_wd_wearable_alarm.html',
    'products_show.aspx_id_66.html': 'mc_td_leak_detector.html',
    'products_show.aspx_id_116.html': 'portable_gas_test_module.html',
    'products_show.aspx_id_85.html': 'smart_gas_mixing_system.html',
    
    # 生物传感 (biosensing)
    'products_show.aspx_id_51.html': 'carbon_bio_package_chip.html',
    'products_show.aspx_id_74.html': 'mc_bw_bio_workstation.html',
    'products_show.aspx_id_86.html': 'portable_bio_detector.html',
    'products_show.aspx_id_87.html': 'blood_potassium_chip.html',
    'products_show.aspx_id_88.html': 'ion_detector.html',
    'products_show.aspx_id_89.html': 'chlorine_detection_chip.html',
    'products_show.aspx_id_63.html': 'carbon_bio_platform.html',
    'products_show.aspx_id_64.html': 'custom_bio_sensor_chip.html',
    'products_show.aspx_id_118.html': 'respiratory_virus_chip.html',
    'products_show.aspx_id_117.html': 'igzo_device.html',
    
    # 定制服务 (customization)
    'products_show.aspx_id_76.html': 'custom_gas_sensing_module.html',
    'products_show.aspx_id_77.html': 'custom_instrument_dev.html',
    'products_show.aspx_id_78.html': 'micronano_fabrication.html',
}

# 产品列表页面重命名
LIST_PAGE_RENAME = {
    'products.aspx_category_id_0.html': 'index.html',
    'products.aspx_category_id_0_page_2.html': 'index_page_2.html',
    'products.aspx_category_id_0_page_3.html': 'index_page_3.html',
    'products.aspx_category_id_0_page_4.html': 'index_page_4.html',
    'products.aspx_category_id_0_page_5.html': 'index_page_5.html',
    'products.aspx_category_id_37.html': 'gas_sensors.html',
    'products.aspx_category_id_37_page_2.html': 'gas_sensors_page_2.html',
    'products.aspx_category_id_37_page_3.html': 'gas_sensors_page_3.html',
    'products.aspx_category_id_38.html': 'index.html',
    'products.aspx_category_id_38_page_2.html': 'index_page_2.html',
    'products.aspx_category_id_36.html': 'index.html',
}

def get_all_html_files():
    """获取所有HTML文件"""
    html_files = []
    for root, dirs, files in os.walk(ROOT_DIR):
        # 跳过 hnmetachip_site 旧目录
        if 'hnmetachip_site' in root:
            continue
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    return html_files

def rename_files():
    """重命名产品文件"""
    directories = [
        os.path.join(ROOT_DIR, 'pages/gassensing'),
        os.path.join(ROOT_DIR, 'pages/biosensing'),
        os.path.join(ROOT_DIR, 'pages/customization'),
    ]
    
    renamed = []
    
    for directory in directories:
        if not os.path.exists(directory):
            continue
            
        for old_name, new_name in RENAME_MAP.items():
            old_path = os.path.join(directory, old_name)
            new_path = os.path.join(directory, new_name)
            
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed.append((old_path, new_path))
                print(f"重命名: {old_name} -> {new_name}")
        
        # 处理列表页面
        for old_name, new_name in LIST_PAGE_RENAME.items():
            old_path = os.path.join(directory, old_name)
            new_path = os.path.join(directory, new_name)
            
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed.append((old_path, new_path))
                print(f"重命名列表页: {old_name} -> {new_name}")
    
    return renamed

def update_references():
    """更新所有HTML文件中的引用"""
    html_files = get_all_html_files()
    
    # 合并所有重命名映射
    all_renames = {**RENAME_MAP, **LIST_PAGE_RENAME}
    
    updated_count = 0
    
    for file_path in html_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # 替换所有旧文件名引用
            for old_name, new_name in all_renames.items():
                # 匹配各种可能的引用形式
                content = content.replace(old_name, new_name)
            
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                updated_count += 1
                print(f"更新引用: {file_path}")
        
        except Exception as e:
            print(f"处理文件出错 {file_path}: {e}")
    
    return updated_count

def main():
    print("=" * 50)
    print("开始重命名产品文件...")
    print("=" * 50)
    
    # 步骤1: 重命名文件
    renamed = rename_files()
    print(f"\n完成重命名 {len(renamed)} 个文件")
    
    # 步骤2: 更新引用
    print("\n" + "=" * 50)
    print("更新文件引用...")
    print("=" * 50)
    
    updated = update_references()
    print(f"\n完成更新 {updated} 个文件的引用")
    
    print("\n" + "=" * 50)
    print("全部完成!")
    print("=" * 50)

if __name__ == '__main__':
    main()
