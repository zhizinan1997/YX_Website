#!/usr/bin/env python3
"""
Script to update navigation bars for pages/news, pages/about, pages/contact folders.
Uses the main index.html as the source of truth.
"""
import os
import re
from pathlib import Path

# Base directory
ROOT_DIR = Path(__file__).parent

def get_nav_from_main_index():
    """Extract the navigation section and scripts from main index.html"""
    index_file = ROOT_DIR / 'index.html'
    content = index_file.read_text(encoding='utf-8')
    
    # Extract header section (from <header to </header>)
    header_match = re.search(r'(<header class="vs-header">.*?</header>)', content, re.DOTALL)
    if not header_match:
        print("Could not find header in index.html")
        return None
    
    header = header_match.group(1)
    
    # Extract the script block with showPanel, showPanelContact, showPanelNews functions
    script_match = re.search(
        r'(<script>\s*function showPanel.*?function showPanelNews.*?</script>)',
        content, re.DOTALL
    )
    if script_match:
        script_block = script_match.group(1)
    else:
        script_block = ""
    
    return header, script_block

def adjust_paths_for_depth(content, depth):
    """Adjust relative paths based on folder depth from root.
    depth=1 means file is in pages/news/, pages/about/, or pages/contact/
    """
    if depth == 0:
        # Root level files - no changes needed
        return content
    
    # For depth=1 (files in pages/xxx folders):
    # - Root paths like "assets/..." -> "../assets/..."
    # - "index.html" -> "../index.html"
    # - "pages/xxx/..." -> "../xxx/..."
    
    if depth == 1:
        # Handle asset paths
        content = content.replace('href="assets/', 'href="../../assets/')
        content = content.replace('src="assets/', 'src="../../assets/')
        
        # Handle root-level pages
        content = content.replace('href="index.html"', 'href="../../index.html"')
        content = content.replace('href="index_en.html"', 'href="../../index_en.html"')
        
        # Handle pages/ folder references
        content = content.replace('href="pages/', 'href="../')
        
    return content

def update_nav_in_file(filepath, nav_header, nav_script, depth):
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
        
        # Handle the script block - insert/replace before </body>
        adjusted_script = adjust_paths_for_depth(nav_script, depth)
        
        # Check if showPanel script exists
        existing_script_pattern = r'<script>\s*function showPanel.*?function showPanelNews.*?</script>'
        
        if re.search(existing_script_pattern, content, re.DOTALL):
            # Replace existing script
            content = re.sub(existing_script_pattern, adjusted_script, content, flags=re.DOTALL)
        else:
            # Insert before </body> and other scripts
            # Find the first script before </body> that's one of the common ones
            insert_match = re.search(r'(\s*<!-- 新闻预览|\s*<!-- AI智能客服|\s*<script src=)', content)
            if insert_match:
                insert_pos = insert_match.start()
                content = content[:insert_pos] + '\n\n    ' + adjusted_script + '\n' + content[insert_pos:]
            elif '</body>' in content:
                content = content.replace('</body>', adjusted_script + '\n\n</body>')
        
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
    print("Updating Navigation Bars (Main Site Pages)")
    print("=" * 60)
    print(f"Source: {ROOT_DIR / 'index.html'}")
    print()
    
    # Get navigation from main index.html
    result = get_nav_from_main_index()
    if not result:
        return
    
    nav_header, nav_script = result
    print(f"Extracted header length: {len(nav_header)} chars")
    print(f"Extracted script length: {len(nav_script)} chars")
    print()
    
    updated_count = 0
    
    # Process files in pages/news folder
    news_dir = ROOT_DIR / 'pages' / 'news'
    if news_dir.exists():
        print("Processing files in pages/news/:")
        for filepath in sorted(news_dir.glob('*.html')):
            if update_nav_in_file(filepath, nav_header, nav_script, depth=1):
                updated_count += 1
    
    print()
    
    # Process files in pages/about folder
    about_dir = ROOT_DIR / 'pages' / 'about'
    if about_dir.exists():
        print("Processing files in pages/about/:")
        for filepath in sorted(about_dir.glob('*.html')):
            if update_nav_in_file(filepath, nav_header, nav_script, depth=1):
                updated_count += 1
    
    print()
    
    # Process files in pages/contact folder
    contact_dir = ROOT_DIR / 'pages' / 'contact'
    if contact_dir.exists():
        print("Processing files in pages/contact/:")
        for filepath in sorted(contact_dir.glob('*.html')):
            if update_nav_in_file(filepath, nav_header, nav_script, depth=1):
                updated_count += 1
    
    print()
    print("=" * 60)
    print(f"Complete! Updated {updated_count} files.")
    print("=" * 60)

if __name__ == '__main__':
    main()
