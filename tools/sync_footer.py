#!/usr/bin/env python3
import argparse
import os
import re
import sys


FOOTER_MARKER_RE = re.compile(
    r"<!-- FOOTER_START -->(?P<footer>.*)<!-- FOOTER_END -->",
    re.DOTALL | re.IGNORECASE,
)
FOOTER_TAG_RE = re.compile(
    r"<footer\\s+class=\"vs-footer-new\"[^>]*>.*?</footer>",
    re.DOTALL | re.IGNORECASE,
)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_footer_block(index_html: str) -> str:
    match = FOOTER_MARKER_RE.search(index_html)
    if match:
        return "<!-- FOOTER_START -->" + match.group("footer") + "<!-- FOOTER_END -->"

    match = FOOTER_TAG_RE.search(index_html)
    if match:
        return match.group(0)

    raise ValueError("在 index.html 中找不到页尾块。")


def iter_html_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common heavy or irrelevant dirs
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", "extracted_images"}
        ]
        for name in filenames:
            if name.lower().endswith(".html"):
                yield os.path.join(dirpath, name)


def replace_footer(content: str, footer_block: str) -> str:
    if FOOTER_MARKER_RE.search(content):
        return FOOTER_MARKER_RE.sub(footer_block, content, count=1)
    if FOOTER_TAG_RE.search(content):
        return FOOTER_TAG_RE.sub(footer_block, content, count=1)
    if "</body>" in content:
        return content.replace("</body>", footer_block + "\n\n</body>", 1)
    if "</html>" in content:
        return content.replace("</html>", footer_block + "\n\n</html>", 1)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 index.html 页尾到所有 HTML 页面")
    parser.add_argument("--print-updated", action="store_true", help="仅打印被更新的文件路径")
    args = parser.parse_args()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    index_path = os.path.join(root, "index.html")

    index_html = read_file(index_path)
    footer_block = extract_footer_block(index_html)

    updated = []
    for path in iter_html_files(root):
        # Always skip index.html itself (source of truth)
        if os.path.abspath(path) == os.path.abspath(index_path):
            continue
        original = read_file(path)
        replaced = replace_footer(original, footer_block)
        if replaced != original:
            write_file(path, replaced)
            updated.append(path)

    if args.print_updated:
        for path in updated:
            print(path)
    else:
        print(f"[sync_footer] 已更新 {len(updated)} 个文件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
