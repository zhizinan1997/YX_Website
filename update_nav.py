#!/usr/bin/env python3
"""
Script to update navigation bars across all HTML files in gassensing and solutions folders.
Uses index.html as the source of truth for navigation.
Also includes the dynamic loading scripts for product menu, recommendations, and categories.
"""
import os
import re
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent / 'pages' / 'gassensing'

def get_nav_from_index():
    """Extract the navigation section and dynamic scripts from index.html"""
    index_file = BASE_DIR / 'index.html'
    content = index_file.read_text(encoding='utf-8')
    
    # Extract header section (from <header to </header>)
    header_match = re.search(r'(<header class="vs-header">.*?</header>)', content, re.DOTALL)
    if not header_match:
        print("Could not find header in index.html")
        return None
    
    header = header_match.group(1)
    
    # Extract the script block that follows the header (showPanel functions)
    script_match = re.search(r'(</header>\s*<script>.*?function showPanelCases.*?</script>)', content, re.DOTALL)
    if script_match:
        script_block = script_match.group(1).replace('</header>', '').strip()
    else:
        script_block = ""
    
    # Extract the dynamic loading scripts (product list, recommendations, categories)
    # These are located near the end of the body
    dynamic_scripts_match = re.search(
        r'(<!-- 动态产品菜单.*?</script>\s*<!-- 动态加载新品推荐.*?</script>\s*<!-- 动态加载产品种类.*?</script>)',
        content, re.DOTALL
    )
    if dynamic_scripts_match:
        dynamic_scripts = dynamic_scripts_match.group(1)
    else:
        dynamic_scripts = ""
    
    return header, script_block, dynamic_scripts

def adjust_paths_for_depth(content, depth):
    """Adjust relative paths based on folder depth from gassensing folder.
    depth=0 means file is in gassensing folder directly
    depth=1 means file is in gassensing/cases/ subfolder
    """
    if depth == 0:
        # Files directly in gassensing folder - no changes needed
        return content
    
    # Files in subdirectories need to go up one more level
    # ../../ becomes ../../../
    # ../ becomes ../../
    # For relative links without ../ (like all-products.html), add ../
    
    # First handle ../../ -> ../../../
    content = content.replace('href="../../', 'href="../../../')
    content = content.replace('src="../../', 'src="../../../')
    
    # Handle relative links that don't start with ../ or http
    # Like all-products.html -> ../all-products.html
    patterns = [
        (r'href="(all-products\.html)"', r'href="../\1"'),
        (r'href="(index\.html)"', r'href="../\1"'),
        (r'href="(service-cases\.html)"', r'href="../\1"'),
        (r'href="(cases/)', r'href="../\1'),
        (r'href="(../about/)', r'href="../../about/'),
        (r'href="(../research/)', r'href="../../research/'),
        (r'href="(../gassensing/)', r'href="../../gassensing/'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content

def update_nav_in_file(filepath, nav_header, nav_script, dynamic_scripts, depth):
    """Update the navigation in a single file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        
        # Find and replace the existing header
        header_pattern = r'<header class="vs-header">.*?</header>'
        header_match = re.search(header_pattern, content, re.DOTALL)
        
        if not header_match:
            print(f"  Skipping {filepath.name}: No header found")
            return False
        
        # Adjust paths for this file's depth
        adjusted_header = adjust_paths_for_depth(nav_header, depth)
        
        # Replace the header
        content = re.sub(header_pattern, adjusted_header, content, flags=re.DOTALL)
        
        # Find and replace the script block after header
        # Look for the showPanel functions
        script_pattern = r'</header>\s*<script>\s*function showPanel.*?function showPanelCases.*?</script>'
        adjusted_script = adjust_paths_for_depth(nav_script, depth)
        
        if re.search(script_pattern, content, re.DOTALL):
            content = re.sub(script_pattern, '</header>\n\n    ' + adjusted_script, content, flags=re.DOTALL)
        elif nav_script:
            # If no script block exists, add it after header
            content = content.replace('</header>', '</header>\n\n    ' + adjusted_script)
        
        # Handle dynamic scripts - inject before </body> if not already present
        if dynamic_scripts:
            adjusted_dynamic = adjust_paths_for_depth(dynamic_scripts, depth)
            
            # Check if already has dynamic product menu script
            if '<!-- 动态产品菜单' not in content:
                # Find </body> and inject before it
                if '</body>' in content:
                    content = content.replace('</body>', '\n    ' + adjusted_dynamic + '\n\n</body>')
            else:
                # Replace existing dynamic scripts
                old_dynamic_pattern = r'<!-- 动态产品菜单.*?</script>\s*<!-- 动态加载新品推荐.*?</script>\s*<!-- 动态加载产品种类.*?</script>'
                if re.search(old_dynamic_pattern, content, re.DOTALL):
                    content = re.sub(old_dynamic_pattern, adjusted_dynamic, content, flags=re.DOTALL)
        
        # Only write if content changed
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            print(f"  Updated: {filepath.name}")
            return True
        else:
            print(f"  No changes: {filepath.name}")
            return False
            
    except Exception as e:
        print(f"  Error updating {filepath.name}: {e}")
        return False

def main():
    print("=" * 60)
    print("Updating Navigation Bars")
    print("=" * 60)
    print(f"Source: {BASE_DIR / 'index.html'}")
    print()
    
    # Get navigation from index.html
    result = get_nav_from_index()
    if not result:
        return
    
    nav_header, nav_script, dynamic_scripts = result
    print(f"Extracted header length: {len(nav_header)} chars")
    print(f"Extracted script length: {len(nav_script)} chars")
    print(f"Extracted dynamic scripts length: {len(dynamic_scripts)} chars")
    print()
    
    # Find all HTML files
    updated_count = 0
    
    # Process files in gassensing folder (depth=0)
    print("Processing files in gassensing/:")
    for filepath in sorted(BASE_DIR.glob('*.html')):
        if filepath.name != 'index.html':  # Skip source file
            if update_nav_in_file(filepath, nav_header, nav_script, dynamic_scripts, depth=0):
                updated_count += 1
    
    print()
    
    # Process files in cases subfolder (depth=1)
    cases_dir = BASE_DIR / 'cases'
    if cases_dir.exists():
        print("Processing files in gassensing/cases/:")
        for filepath in sorted(cases_dir.glob('*.html')):
            if update_nav_in_file(filepath, nav_header, nav_script, dynamic_scripts, depth=1):
                updated_count += 1
    
    print()
    
    # Process files in solutions folder (same level as gassensing, depth=0)
    solutions_dir = Path(__file__).parent / 'pages' / 'solutions'
    if solutions_dir.exists():
        print("Processing files in solutions/:")
        for filepath in sorted(solutions_dir.glob('*.html')):
            if update_nav_in_file(filepath, nav_header, nav_script, dynamic_scripts, depth=0):
                updated_count += 1
    
    print()
    print("=" * 60)
    print(f"Complete! Updated {updated_count} files.")
    print("=" * 60)

if __name__ == '__main__':
    main()
