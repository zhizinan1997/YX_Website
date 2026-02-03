import os

root_dir = '/Users/zhizinan/Desktop/YX_Website'
assets_js_path = 'assets/js/chatbot.js'

def get_relative_path(html_file_path):
    # Calculate relative path from html file to assets/js/chatbot.js
    html_dir = os.path.dirname(html_file_path)
    abs_assets_path = os.path.join(root_dir, assets_js_path)
    return os.path.relpath(abs_assets_path, html_dir)

count = 0
for dirpath, dirnames, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename.endswith('.html') or filename.endswith('.aspx'): # Include aspx just in case, though user said pages are html
            file_path = os.path.join(dirpath, filename)
            
            # Skip if file is in .gemini or other hidden folders
            if '.gemini' in file_path or '.git' in file_path:
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'chatbot.js' in content:
                    print(f"Skipping {filename}, already has chatbot.")
                    continue
                
                # Calculate relative script path
                rel_script_path = get_relative_path(file_path)
                
                # Check where to insert
                if '</body>' in content:
                    # Insert before </body>
                    # Add comment too
                    script_tag = f'\n    <!-- AI智能客服 -->\n    <script src="{rel_script_path}"></script>\n'
                    new_content = content.replace('</body>', script_tag + '</body>')
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated {filename}")
                    count += 1
                else:
                    print(f"Skipping {filename}, no </body> tag.")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

print(f"Total files updated: {count}")
