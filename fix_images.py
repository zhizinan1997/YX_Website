"""
修复HTML中的图片路径，将.webp改为.png（当实际文件是.png时）
"""
import re
from pathlib import Path

def find_and_fix_image_references():
    cdn_images = Path('cdn_assets/images')

    # 收集所有实际存在的文件
    webp_files = set()
    png_files = set()
    jpg_files = set()

    for ext in ['*.webp', '*.png', '*.jpg', '*.jpeg']:
        for f in cdn_images.rglob(ext):
            name = f.stem  # 不带扩展名的文件名
            if ext == '*.webp':
                webp_files.add(name)
            elif ext == '*.png':
                png_files.add(name)
            else:
                jpg_files.add(name)

    print(f"实际文件: webp={len(webp_files)}, png={len(png_files)}, jpg={len(jpg_files)}")

    # 查找HTML中的.webp引用
    all_webp_refs = []
    for html_file in list(Path('pages').rglob('*.html')) + list(Path('pages/gassensing').rglob('*.html')):
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')
            for match in re.finditer(r'/cdn_assets/images/([a-f0-9]+)\.webp', content):
                hash_name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                full_match = match.group(0)

                # 检查实际文件是否存在
                actual_ext = None
                if hash_name in png_files:
                    actual_ext = 'png'
                elif hash_name in jpg_files:
                    actual_ext = 'jpg'
                elif hash_name in webp_files:
                    actual_ext = 'webp'

                all_webp_refs.append({
                    'file': str(html_file),
                    'line': line_num,
                    'hash': hash_name,
                    'current': full_match,
                    'actual_ext': actual_ext
                })
        except Exception as e:
            print(f"Error reading {html_file}: {e}")

    # 按文件分组
    files_to_fix = {}
    for ref in all_webp_refs:
        if ref['actual_ext'] and ref['actual_ext'] != 'webp':
            f = ref['file']
            if f not in files_to_fix:
                files_to_fix[f] = []
            files_to_fix[f].append(ref)

    print(f"\n需要修复的文件: {len(files_to_fix)}")
    total_fixes = sum(len(v) for v in files_to_fix.values())
    print(f"总共需要修复的引用: {total_fixes}")

    # 执行修复
    for filepath, refs in files_to_fix.items():
        print(f"\n修复 {filepath}:")
        try:
            content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
            original = content

            for ref in refs:
                old = ref['current']
                new = f"/cdn_assets/images/{ref['hash']}.{ref['actual_ext']}"
                if old in content:
                    content = content.replace(old, new)
                    print(f"  L{ref['line']}: {old} -> {new}")

            if content != original:
                Path(filepath).write_text(content, encoding='utf-8')
                print(f"  ✓ 已保存")
        except Exception as e:
            print(f"  ✗ 错误: {e}")

if __name__ == '__main__':
    find_and_fix_image_references()
