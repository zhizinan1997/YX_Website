import os
import glob

NEWS_DIR = "/Users/zhizinan/Desktop/YX_Website/news"

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Target CSS block
    target = """.article-container {
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }"""
        
    # Replacement CSS block with media query
    replacement = """.article-container {
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }
        @media (min-width: 1920px) {
            .article-container {
                max-width: 1600px;
            }
            .article-content {
                font-size: 19px;
            }
            .article-hero__title {
                font-size: 48px;
            }
        }"""
    
    if target in content:
        new_content = content.replace(target, replacement)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated: {os.path.basename(filepath)}")
    else:
        print(f"Skipped (target not found): {os.path.basename(filepath)}")

def main():
    files = glob.glob(os.path.join(NEWS_DIR, "news_show.aspx_id_*.html"))
    for f in files:
        process_file(f)

if __name__ == "__main__":
    main()
