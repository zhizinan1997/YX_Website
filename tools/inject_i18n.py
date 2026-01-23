import os

root_dir = '/Users/zhizinan/Desktop/YX_Website'
assets_js_path = 'assets/js/i18n.js'

def get_relative_path(html_file_path):
    html_dir = os.path.dirname(html_file_path)
    abs_assets_path = os.path.join(root_dir, assets_js_path)
    return os.path.relpath(abs_assets_path, html_dir)

count = 0
for dirpath, dirnames, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename.endswith('.html'):
            file_path = os.path.join(dirpath, filename)
            
            # Skip irrelevant
            if '.gemini' in file_path or '.git' in file_path:
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'i18n.js' in content:
                    print(f"Skipping {filename}, already has i18n.")
                    continue
                
                rel_script_path = get_relative_path(file_path)
                
                # Check where to insert. After chatbot.js or before </body>
                insert_marker = '</body>'
                
                if insert_marker in content:
                    script_tag = f'\n    <!-- I18N Translation -->\n    <script src="{rel_script_path}"></script>\n'
                    new_content = content.replace(insert_marker, script_tag + insert_marker)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated {filename}")
                    count += 1
                else:
                    print(f"Skipping {filename}, no body tag.")
            except Exception as e:
                print(f"Error {filename}: {e}")

print(f"Total files updated: {count}")
