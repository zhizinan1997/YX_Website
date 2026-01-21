"""
Fix news links in index.html that still point to old news/ path.
"""
from pathlib import Path

ROOT = Path(r"c:\Users\Ryan\Downloads\YX_Website")
index_file = ROOT / "index.html"

content = index_file.read_text(encoding='utf-8')
original = content

# Fix news/ to pages/news/
content = content.replace('href="news/', 'href="pages/news/')
content = content.replace("href='news/", "href='pages/news/")

# Fix news.aspx_category_id_0.html to pages/news/news.html
content = content.replace('href="news.aspx_category_id_0.html', 'href="pages/news/news.html')
content = content.replace("href='news.aspx_category_id_0.html", "href='pages/news/news.html")

if content != original:
    index_file.write_text(content, encoding='utf-8')
    print("Fixed news links in index.html")
else:
    print("No changes needed in index.html")
