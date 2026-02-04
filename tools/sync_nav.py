#!/usr/bin/env python3
"""
导航栏同步脚本 - Navigation Bar Sync Tool
==========================================

功能：
1. 一次性同步：将三个源文件的导航栏同步到所有目标页面
2. 实时监控：监控源文件变化，自动同步到目标页面

源文件：
- index.html (首页导航) -> pages/about/, pages/contact/, pages/news/, pages/careers/
- pages/gassensing/index.html (气体传感导航) -> pages/gassensing/*, pages/solutions/*, 
  pages/measurement/*, pages/research/*, pages/customization/*, pages/gassensing/cases/*
- pages/biosensing/index.html (生物传感导航) -> pages/biosensing/*

用法：
  python3 sync_nav.py          # 一次性同步
  python3 sync_nav.py --watch  # 实时监控模式
  python3 sync_nav.py --dry-run  # 试运行，仅显示将要修改的文件
"""

import os
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.absolute()

# ============================================================================
# 配置：源文件和目标文件夹映射
# ============================================================================

# 源文件配置
NAV_SOURCES = {
    'home': ROOT_DIR / 'index.html',
    'gas': ROOT_DIR / 'pages' / 'gassensing' / 'index.html',
    'bio': ROOT_DIR / 'pages' / 'biosensing' / 'index.html',
}

# 目标文件夹映射（哪些文件夹使用哪个导航源）
TARGET_MAPPING = {
    'home': [
        'pages/about',
        'pages/contact',
        'pages/news',
        'pages/careers',
    ],
    'gas': [
        'pages/gassensing',
        'pages/gassensing/cases',
        'pages/solutions',
        'pages/measurement',
        'pages/research',
        'pages/customization',
    ],
    'bio': [
        'pages/biosensing',
    ],
}

# 排除的文件（源文件本身不需要同步）
EXCLUDE_FILES = {
    str(ROOT_DIR / 'index.html'),
    str(ROOT_DIR / 'pages' / 'gassensing' / 'index.html'),
    str(ROOT_DIR / 'pages' / 'biosensing' / 'index.html'),
}


# ============================================================================
# 导航栏提取和替换
# ============================================================================

def extract_nav_block(html_content: str) -> Optional[Tuple[str, int, int]]:
    """
    提取 <nav class="vs-nav"...>...</nav> 区块
    返回 (nav_html, start_pos, end_pos) 或 None
    """
    # 匹配 <nav class="vs-nav" ...> 开始标签
    nav_start_pattern = r'<nav\s+class="vs-nav[^"]*"[^>]*>'
    match = re.search(nav_start_pattern, html_content)
    if not match:
        return None
    
    start_pos = match.start()
    
    # 从开始位置找到对应的 </nav>
    # 需要处理嵌套的 nav 标签（虽然通常不会有）
    depth = 1
    pos = match.end()
    while depth > 0 and pos < len(html_content):
        next_open = html_content.find('<nav', pos)
        next_close = html_content.find('</nav>', pos)
        
        if next_close == -1:
            return None
        
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                end_pos = next_close + 6  # len('</nav>')
                return (html_content[start_pos:end_pos], start_pos, end_pos)
            pos = next_close + 6
    
    return None


def extract_nav_scripts(html_content: str) -> str:
    """
    提取导航栏相关的 JavaScript 函数
    """
    scripts = []
    
    # 提取 showPanel 相关函数
    patterns = [
        r'function\s+showPanel\s*\([^)]*\)\s*\{[^}]+\}',
        r'function\s+showPanelContact\s*\([^)]*\)\s*\{[^}]+\}',
        r'function\s+showPanelSolutions\s*\([^)]*\)\s*\{[^}]+\}',
        r'function\s+showPanelCases\s*\([^)]*\)\s*\{[^}]+\}',
        r'function\s+showPanelNews\s*\([^)]*\)\s*\{[^}]+\}',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content, re.DOTALL)
        if match:
            scripts.append(match.group(0))
    
    return '\n'.join(scripts)


def calculate_relative_prefix(source_path: Path, target_path: Path) -> Tuple[str, str]:
    """
    计算从目标文件到根目录的相对路径前缀
    返回 (to_root_prefix, from_root_prefix)
    
    例如：
    - target在 pages/about/about.html -> to_root="../../", from_root="pages/about/"
    - target在 pages/gassensing/cases/case-1.html -> to_root="../../../", from_root="pages/gassensing/cases/"
    """
    try:
        rel_path = target_path.relative_to(ROOT_DIR)
        depth = len(rel_path.parts) - 1  # 减去文件名本身
        to_root = '../' * depth if depth > 0 else ''
        from_root = '/'.join(rel_path.parts[:-1]) + '/' if depth > 0 else ''
        return (to_root, from_root)
    except ValueError:
        return ('', '')


def adjust_nav_paths(nav_html: str, source_path: Path, target_path: Path) -> str:
    """
    调整导航栏中的相对路径，使其适配目标文件的位置
    """
    # 计算源文件和目标文件到根目录的深度
    try:
        source_rel = source_path.relative_to(ROOT_DIR)
        target_rel = target_path.relative_to(ROOT_DIR)
    except ValueError:
        return nav_html
    
    source_depth = len(source_rel.parts) - 1
    target_depth = len(target_rel.parts) - 1
    
    # 如果深度相同，不需要调整
    if source_depth == target_depth:
        return nav_html
    
    # 计算需要的前缀
    source_prefix = '../' * source_depth if source_depth > 0 else ''
    target_prefix = '../' * target_depth if target_depth > 0 else ''
    
    result = nav_html
    
    # 处理 href 和 src 属性中的路径
    def replace_path(match):
        attr = match.group(1)  # href 或 src
        quote = match.group(2)  # 引号类型
        path = match.group(3)  # 路径值
        
        # 跳过外部链接、锚点、javascript
        if path.startswith(('http://', 'https://', '#', 'javascript:', 'mailto:')):
            return match.group(0)
        
        # 处理 Windows 风格路径 (反斜杠)
        path = path.replace('\\\\', '/').replace('\\', '/')
        
        # 移除源文件的相对前缀，获取相对于根目录的路径
        if source_prefix and path.startswith(source_prefix):
            path = path[len(source_prefix):]
        elif source_prefix:
            # 如果路径不是以预期前缀开始，可能是其他相对路径
            # 尝试解析相对于源文件的路径
            pass
        
        # 添加目标文件的相对前缀
        new_path = target_prefix + path if target_prefix else path
        
        return f'{attr}={quote}{new_path}{quote}'
    
    # 匹配 href="..." 和 src="..."
    result = re.sub(
        r'(href|src)=([\"\'])([^\"\']+)\2',
        replace_path,
        result
    )
    
    return result


def replace_nav_in_file(
    target_path: Path,
    new_nav_html: str,
    new_scripts: str,
    dry_run: bool = False
) -> bool:
    """
    替换目标文件中的导航栏
    返回是否成功
    """
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  [ERROR] 无法读取文件: {e}")
        return False
    
    # 检查是否有 vs-nav
    if '<nav class="vs-nav' not in content:
        print(f"  [SKIP] 无 vs-nav 导航栏")
        return False
    
    # 提取现有导航栏位置
    nav_result = extract_nav_block(content)
    if not nav_result:
        print(f"  [ERROR] 无法解析导航栏结构")
        return False
    
    old_nav, start_pos, end_pos = nav_result
    
    # 构建新内容
    new_content = content[:start_pos] + new_nav_html + content[end_pos:]
    
    if dry_run:
        print(f"  [DRY-RUN] 将替换导航栏 ({end_pos - start_pos} -> {len(new_nav_html)} 字符)")
        return True
    
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  [OK] 已更新导航栏")
        return True
    except Exception as e:
        print(f"  [ERROR] 无法写入文件: {e}")
        return False


# ============================================================================
# 文件扫描和同步
# ============================================================================

def get_target_files(folder: str) -> List[Path]:
    """
    获取指定文件夹中的所有 HTML 文件（不包括排除的文件）
    """
    folder_path = ROOT_DIR / folder
    if not folder_path.exists():
        return []
    
    files = []
    for html_file in folder_path.glob('*.html'):
        if str(html_file) not in EXCLUDE_FILES:
            files.append(html_file)
    
    return sorted(files)


def sync_navigation(dry_run: bool = False) -> Tuple[int, int, int]:
    """
    执行一次性同步
    返回 (成功数, 跳过数, 失败数)
    """
    success_count = 0
    skip_count = 0
    error_count = 0
    
    # 读取所有源文件的导航栏
    nav_cache: Dict[str, Tuple[str, str, Path]] = {}  # key -> (nav_html, scripts, source_path)
    
    for key, source_path in NAV_SOURCES.items():
        if not source_path.exists():
            print(f"[ERROR] 源文件不存在: {source_path}")
            continue
        
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"[ERROR] 无法读取源文件 {source_path}: {e}")
            continue
        
        nav_result = extract_nav_block(content)
        if not nav_result:
            print(f"[ERROR] 无法从 {source_path} 提取导航栏")
            continue
        
        nav_html, _, _ = nav_result
        scripts = extract_nav_scripts(content)
        nav_cache[key] = (nav_html, scripts, source_path)
        print(f"[INFO] 已加载导航栏源: {key} ({len(nav_html)} 字符)")
    
    # 遍历每个映射组
    for nav_key, folders in TARGET_MAPPING.items():
        if nav_key not in nav_cache:
            print(f"[WARN] 跳过 {nav_key} 组，源文件未加载")
            continue
        
        source_nav, source_scripts, source_path = nav_cache[nav_key]
        
        print(f"\n=== 同步组: {nav_key} ===")
        print(f"源文件: {source_path}")
        
        for folder in folders:
            target_files = get_target_files(folder)
            if not target_files:
                continue
            
            print(f"\n文件夹: {folder} ({len(target_files)} 个文件)")
            
            for target_path in target_files:
                print(f"  处理: {target_path.name}")
                
                # 调整路径
                adjusted_nav = adjust_nav_paths(source_nav, source_path, target_path)
                
                # 替换导航栏
                result = replace_nav_in_file(
                    target_path,
                    adjusted_nav,
                    source_scripts,
                    dry_run=dry_run
                )
                
                if result:
                    success_count += 1
                elif result is None:
                    skip_count += 1
                else:
                    error_count += 1
    
    return (success_count, skip_count, error_count)


# ============================================================================
# 文件监控模式
# ============================================================================

def watch_mode():
    """
    监控源文件变化，自动同步
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[ERROR] 监控模式需要 watchdog 库")
        print("请运行: pip3 install watchdog")
        sys.exit(1)
    
    class NavSyncHandler(FileSystemEventHandler):
        def __init__(self):
            self.last_sync = {}
        
        def on_modified(self, event):
            if event.is_directory:
                return
            
            source_path = Path(event.src_path)
            
            # 检查是否是源文件
            nav_key = None
            for key, path in NAV_SOURCES.items():
                if source_path.samefile(path):
                    nav_key = key
                    break
            
            if not nav_key:
                return
            
            # 防抖：1秒内不重复同步
            now = time.time()
            if nav_key in self.last_sync and now - self.last_sync[nav_key] < 1:
                return
            self.last_sync[nav_key] = now
            
            print(f"\n[WATCH] 检测到变化: {source_path.name}")
            print(f"[WATCH] 开始同步 {nav_key} 组...")
            
            # 执行同步
            sync_navigation(dry_run=False)
    
    handler = NavSyncHandler()
    observer = Observer()
    
    # 监控所有源文件所在的目录
    watched_dirs = set()
    for path in NAV_SOURCES.values():
        watched_dirs.add(str(path.parent))
    
    for dir_path in watched_dirs:
        observer.schedule(handler, dir_path, recursive=False)
        print(f"[WATCH] 监控目录: {dir_path}")
    
    observer.start()
    print("\n[WATCH] 监控模式已启动，按 Ctrl+C 停止...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[WATCH] 监控已停止")
    
    observer.join()


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='导航栏同步工具 - 同步网站导航栏到所有页面',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python3 sync_nav.py              # 一次性同步所有页面
  python3 sync_nav.py --dry-run    # 试运行，显示将要修改的文件
  python3 sync_nav.py --watch      # 监控模式，源文件变化时自动同步
        '''
    )
    parser.add_argument(
        '--watch', '-w',
        action='store_true',
        help='启用监控模式，实时同步源文件变化'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='试运行模式，仅显示将要修改的文件，不实际修改'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("导航栏同步工具 - Navigation Bar Sync Tool")
    print("=" * 60)
    print(f"项目根目录: {ROOT_DIR}")
    print()
    
    if args.watch:
        # 先执行一次同步
        print("执行初始同步...")
        sync_navigation(dry_run=args.dry_run)
        print()
        
        # 然后进入监控模式
        watch_mode()
    else:
        # 一次性同步
        success, skip, error = sync_navigation(dry_run=args.dry_run)
        
        print()
        print("=" * 60)
        print(f"同步完成!")
        print(f"  成功: {success}")
        print(f"  跳过: {skip}")
        print(f"  失败: {error}")
        print("=" * 60)


if __name__ == '__main__':
    main()
