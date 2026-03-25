#!/usr/bin/env python3
import json
import hashlib
import html
import re
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

WORKERS = 20  # parallel download threads

ROOT = Path('/Users/zhizinan/Desktop/YX_Website')
SEARCH_ROOTS = [ROOT / 'index.html', ROOT / 'pages', ROOT / 'pages_en', ROOT / 'assets']
TEXT_EXTS = {'.html', '.css', '.js', '.json'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tif', '.tiff', '.avif'}
EXCLUDE_HOSTS = {
    'pic.hnmetachip.cn',
    'storage.hnmetachip.cn',
    'test.hnmetachip.cn',
    'localhost',
    '127.0.0.1',
    '121.40.30.236',
}
CACHE_ROOT = ROOT / 'assets' / 'images' / 'external-cache'
REPORT_PATH = ROOT / 'assets' / 'images' / 'external-cache' / '_download_report.json'

# Keep URLs bounded so we don't absorb trailing punctuation.
URL_RE = re.compile(r'https?://[^\s"\'<>)]+' )


def iter_text_files():
    files = []
    for p in SEARCH_ROOTS:
        if p.is_file() and p.suffix.lower() in TEXT_EXTS:
            if CACHE_ROOT in p.parents:
                continue
            files.append(p)
        elif p.is_dir():
            for fp in p.rglob('*'):
                if fp.is_file() and fp.suffix.lower() in TEXT_EXTS:
                    if CACHE_ROOT in fp.parents:
                        continue
                    files.append(fp)
    return files


def parse_image_url(raw_url: str):
    decoded = html.unescape(raw_url)
    parsed = urlparse(decoded)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    host = parsed.hostname.lower() if parsed.hostname else ''
    if host in EXCLUDE_HOSTS:
        return None
    ext = Path(parsed.path).suffix.lower()
    if ext not in IMAGE_EXTS:
        return None
    return decoded, parsed, host


def sanitize_filename(name: str):
    safe = []
    for ch in name:
        if ch.isalnum() or ch in '._-':
            safe.append(ch)
        else:
            safe.append('_')
    out = ''.join(safe).strip('._')
    if not out:
        out = 'image'
    if '.' not in out:
        out += '.bin'
    return out


def build_local_path(url: str, parsed, host: str, used_names: set):
    host_dir = CACHE_ROOT / host
    host_dir.mkdir(parents=True, exist_ok=True)

    base_name = Path(parsed.path).name or 'image'
    base_name = sanitize_filename(base_name)
    stem = Path(base_name).stem
    ext = Path(base_name).suffix

    # Avoid collisions across different URLs with same filename.
    if parsed.query:
        short = hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]
        base_name = f'{stem}_{short}{ext}'

    final_name = base_name
    if final_name in used_names:
        short = hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]
        final_name = f'{stem}_{short}{ext}'
    used_names.add(final_name)

    abs_path = host_dir / final_name
    rel_path = f'/assets/images/external-cache/{host}/{final_name}'
    return abs_path, rel_path


def alt_scheme(url: str):
    p = urlparse(url)
    if p.scheme == 'http':
        return urlunparse(('https', p.netloc, p.path, p.params, p.query, p.fragment))
    if p.scheme == 'https':
        return urlunparse(('http', p.netloc, p.path, p.params, p.query, p.fragment))
    return None


# Map of hostname patterns -> Referer to use (to bypass hotlink protection)
HOTLINK_REFERERS = {
    'wstx.web.vleader.net.cn': 'https://www.hnmetachip.cn/',
    'vleader.net.cn': 'https://www.hnmetachip.cn/',
}


def get_referer_for(p) -> str:
    """Return a suitable Referer header for the given parsed URL."""
    host = (p.hostname or '').lower()
    for pattern, referer in HOTLINK_REFERERS.items():
        if host == pattern or host.endswith('.' + pattern):
            return referer
    return f'{p.scheme}://{p.netloc}/'


def try_download(url: str, target: Path):
    ctx = ssl._create_unverified_context()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    }

    last_err = 'no candidates'
    for candidate in [url, alt_scheme(url)]:
        if not candidate:
            continue
        try:
            p = urlparse(candidate)
            referer = get_referer_for(p)
            req = Request(
                candidate,
                headers={**headers, 'Referer': referer},
            )
            with urlopen(req, timeout=10, context=ctx) as resp:
                status = getattr(resp, 'status', 200)
                if status and int(status) >= 400:
                    raise RuntimeError(f'HTTP {status}')
                data = resp.read()
                if not data:
                    raise RuntimeError('empty body')
            target.write_bytes(data)
            return True, ''
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    return False, last_err


def main():
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    files = iter_text_files()

    # raw_url -> metadata
    urls = {}
    refs = {}
    used_names_per_host = {}

    for fp in files:
        content = fp.read_text(encoding='utf-8', errors='ignore')
        for raw in URL_RE.findall(content):
            parsed_info = parse_image_url(raw)
            if not parsed_info:
                continue
            decoded, parsed, host = parsed_info
            if raw not in urls:
                used = used_names_per_host.setdefault(host, set())
                abs_path, rel_path = build_local_path(decoded, parsed, host, used)
                urls[raw] = {
                    'decoded': decoded,
                    'host': host,
                    'abs_path': abs_path,
                    'rel_path': rel_path,
                }
            refs.setdefault(raw, set()).add(str(fp.relative_to(ROOT)))

    ok = 0
    skipped = 0
    failed = []
    replace_map = {}
    total = len(urls)
    lock = threading.Lock()
    counter = [0]  # mutable counter for threads

    # Separate already-cached URLs from ones that need downloading
    to_download = {}
    for raw_url, info in urls.items():
        target = info['abs_path']
        if target.exists() and target.stat().st_size > 0:
            with lock:
                skipped += 1
                replace_map[raw_url] = info['rel_path']
        else:
            to_download[raw_url] = info

    need = len(to_download)
    print(f'Skipped {skipped} already cached. Downloading {need} images with {WORKERS} threads...', flush=True)

    def download_one(raw_url, info):
        success, err = try_download(info['decoded'], info['abs_path'])
        with lock:
            counter[0] += 1
            n = counter[0]
            if success:
                replace_map[raw_url] = info['rel_path']
                print(f'[{n}/{need}] ✓ {raw_url[:90]}', flush=True)
            else:
                print(f'[{n}/{need}] ✗ {raw_url[:80]} | {err}', flush=True)
                failed.append({
                    'url': raw_url,
                    'error': err,
                    'target': str(info['abs_path'].relative_to(ROOT)),
                    'refs': sorted(refs.get(raw_url, []))[:8],
                })
        return success

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(download_one, raw, info): raw
                   for raw, info in to_download.items()}
        for fut in as_completed(futures):
            if fut.result():
                ok += 1

    changed_files = 0
    replaced_tokens = 0
    for fp in files:
        src = fp.read_text(encoding='utf-8', errors='ignore')
        dst = src
        for raw_url, rel in replace_map.items():
            if raw_url in dst:
                count = dst.count(raw_url)
                if count:
                    dst = dst.replace(raw_url, rel)
                    replaced_tokens += count
        if dst != src:
            fp.write_text(dst, encoding='utf-8')
            changed_files += 1

    report = {
        'total_unique_external_image_urls': len(urls),
        'downloaded_ok': ok,
        'download_skipped_existing': skipped,
        'download_failed': len(failed),
        'changed_files': changed_files,
        'replaced_tokens': replaced_tokens,
        'failed': failed,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'failed'}, ensure_ascii=False))
    if failed:
        print('failed_sample:')
        for item in failed[:15]:
            print('-', item['url'], '|', item['error'])


if __name__ == '__main__':
    main()
