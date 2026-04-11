"""
鏂伴椈鍐呭绠＄悊璺敱妯″潡銆?

鏈ā鍧楁彁渚涙柊闂昏祫璁殑瀹屾暣绠＄悊鍔熻兘锛屽寘鎷細
1. 鏂伴椈鍒楄〃API
2. 鏂囩珷瑙ｆ瀽鍜屾覆鏌?
3. Markdown鏀寔
4. 灏侀潰鍥剧墖绠＄悊
5. 鍏紑鍐呭杈撳嚭
6. 鍚庡彴缂栬緫鎺ュ彛

涓昏鍔熻兘锛?
1. 鏂伴椈鍒楄〃API
   - 鎸夊垎绫荤瓫閫?
   - 鍒嗛〉鏌ヨ
   - 缃《鏂伴椈澶勭悊
   - 鍙戝竷鏃堕棿鎺掑簭

2. 鏂囩珷瑙ｆ瀽
   - HTML鍐呭瑙ｆ瀽
   - Markdown娓叉煋
   - 鍏冩暟鎹彁鍙栵紙鏍囬銆佹憳瑕併€佸彂甯冩椂闂寸瓑锛?
   - 杩滅▼鍥剧墖澶勭悊

3. 灏侀潰鍥剧墖
   - 鍥剧墖涓婁紶楠岃瘉
   - 鐩稿璺緞杞崲
   - 杩滅▼鍥剧墖鑾峰彇鍜岀紦瀛?

4. HTML瀹夊叏娓呮礂
   - 鐧藉悕鍗曟爣绛捐繃婊?
   - 鍗遍櫓鏍囩绉婚櫎
   - 灞炴€ф竻鐞?
   - XSS闃叉姢

5. 鍚庡彴绠＄悊
   - 鏂伴椈鍒楄〃绠＄悊
   - 鍒嗙被璁剧疆
   - 缃《绠＄悊
   - 鍒犻櫎鍔熻兘

6. 鍏紑杈撳嚭
   - 瀹夊叏鐨勫唴瀹规竻娲?
   - 鐩稿URL澶勭悊
   - 鏃ユ湡鏍煎紡鍖?

瀹夊叏鐗规€э細
- HTML鐧藉悕鍗曟満鍒?
- 鍗遍櫓鏍囩杩囨护锛坰cript銆乮frame銆乫orm绛夛級
- JavaScript浼崗璁睆钄?
- 杩滅▼URL楠岃瘉

浣滆€咃細鍏冭姱浼犳劅鎶€鏈洟闃?
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from flask import jsonify, request, send_from_directory

BEIJING_TZ = timezone(timedelta(hours=8))
FEISHU_HOST_KEYWORDS = ('feishu', 'larksuite', 'larkoffice')
VOID_HTML_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img',
    'input', 'link', 'meta', 'param', 'source', 'track', 'wbr',
}
INLINE_RENDER_TAGS = {
    'strong': 'strong',
    'b': 'strong',
    'em': 'em',
    'i': 'em',
    'u': 'u',
    'code': 'code',
    'span': '',
}
REMOTE_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

def now_beijing():
    """Return the current Beijing time."""
    return datetime.now(BEIJING_TZ)


class RemoteFetchError(Exception):
    """Structured remote fetch error for news import flows."""

    def __init__(self, message: str, *, reason: str = 'download_failed', **details):
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.details = details


def is_http_url(raw_url: str) -> bool:
    value = str(raw_url or '').strip()
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme.lower() in {'http', 'https'} and bool(parsed.netloc)


def is_feishu_like_hostname(hostname: str) -> bool:
    host = str(hostname or '').strip().lower()
    return any(keyword in host for keyword in FEISHU_HOST_KEYWORDS)


def resolve_remote_candidate_url(base_url: str, raw_url: str) -> str:
    value = html.unescape(str(raw_url or '')).strip()
    if not value:
        return ''
    if value.startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
        return ''
    resolved = urljoin(base_url or '', value)
    return resolved if is_http_url(resolved) else ''


def extract_html_title_text(html_text: str) -> str:
    match = re.search(r'<title\b[^>]*>(.*?)</title>', html_text or '', re.I | re.S)
    if not match:
        return ''
    title = normalize_news_plain_text(match.group(1), max_length=200)
    title = re.sub(r'\s*[-|_]\s*(椋炰功|Lark|Feishu).*$', '', title, flags=re.I).strip()
    return title


def is_feishu_login_page_html(html_text: str) -> bool:
    sample = str(html_text or '')[:200000].lower()
    if not sample:
        return False
    markers = (
        'suite/passport/static/login',
        'window.serverinjectres',
        'window.passportsettings',
        'passport_web_did',
        'crossloginurl',
    )
    if 'suite/passport/static/login' in sample:
        return True
    return sum(1 for marker in markers if marker in sample) >= 3


def extract_feishu_client_vars_payload(html_text: str) -> dict | None:
    text = str(html_text or '')
    if not text:
        return None

    match = re.search(r'"type"\s*:\s*"CLIENT_VARS"', text)
    if not match:
        return None

    object_start = text.rfind('Object({', 0, match.start())
    if object_start < 0:
        return None

    start = object_start + len('Object(')
    depth = 0
    in_string = False
    escaped = False
    end = -1

    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = idx + 1
                break

    if end <= start:
        return None

    try:
        payload = json.loads(text[start:end])
    except Exception:
        return None

    data = payload.get('data')
    return data if isinstance(data, dict) else None


def extract_first_html_element_by_attr(html_text: str, *, tag_name: str, attr_name: str, attr_value: str = '') -> str:
    from html.parser import HTMLParser

    class StopExtract(Exception):
        pass

    def build_start_tag(tag: str, attrs: list[tuple[str, str]], *, self_closing: bool = False) -> str:
        attr_text = ''.join(
            f' {str(name or "").lower()}="{html.escape(str(value or ""), quote=True)}"'
            for name, value in attrs
        )
        return f'<{tag}{attr_text}{" /" if self_closing else ""}>'

    target_tag = str(tag_name or '').strip().lower()
    target_attr = str(attr_name or '').strip().lower()
    target_value = str(attr_value or '')

    class ElementExtractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.capture_depth = 0
            self.parts = []
            self.fragment = ''

        def _matches(self, tag: str, attrs: list[tuple[str, str]]) -> bool:
            if str(tag or '').lower() != target_tag:
                return False
            for name, value in attrs:
                if str(name or '').lower() != target_attr:
                    continue
                if target_value == '' or str(value or '') == target_value:
                    return True
            return False

        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text() or build_start_tag(tag, attrs)
            if self.capture_depth == 0:
                if self._matches(tag, attrs):
                    self.capture_depth = 1
                    self.parts = [raw]
            else:
                self.parts.append(raw)
                if str(tag or '').lower() == target_tag:
                    self.capture_depth += 1

        def handle_startendtag(self, tag, attrs):
            raw = self.get_starttag_text() or build_start_tag(tag, attrs, self_closing=True)
            if self.capture_depth == 0:
                if self._matches(tag, attrs):
                    self.fragment = raw
                    raise StopExtract()
                return
            self.parts.append(raw)

        def handle_endtag(self, tag):
            if self.capture_depth == 0:
                return
            self.parts.append(f'</{tag}>')
            if str(tag or '').lower() == target_tag:
                self.capture_depth -= 1
                if self.capture_depth == 0:
                    self.fragment = ''.join(self.parts)
                    raise StopExtract()

        def handle_data(self, data):
            if self.capture_depth > 0 and data:
                self.parts.append(data)

        def handle_entityref(self, name):
            if self.capture_depth > 0:
                self.parts.append(f'&{name};')

        def handle_charref(self, name):
            if self.capture_depth > 0:
                self.parts.append(f'&#{name};')

        def handle_comment(self, data):
            if self.capture_depth > 0:
                self.parts.append(f'<!--{data}-->')

        def handle_decl(self, decl):
            if self.capture_depth > 0:
                self.parts.append(f'<!{decl}>')

    parser = ElementExtractor()
    try:
        parser.feed(html_text or '')
    except StopExtract:
        pass
    finally:
        parser.close()
    return parser.fragment.strip()


def build_simple_html_tree(fragment: str) -> dict:
    from html.parser import HTMLParser

    root = {'type': 'root', 'children': []}
    stack = [root]

    class TreeParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)

        def handle_starttag(self, tag, attrs):
            node = {
                'type': 'tag',
                'tag': str(tag or '').lower(),
                'attrs': {str(name or '').lower(): str(value or '') for name, value in attrs},
                'children': [],
            }
            stack[-1]['children'].append(node)
            if node['tag'] not in VOID_HTML_TAGS:
                stack.append(node)

        def handle_startendtag(self, tag, attrs):
            node = {
                'type': 'tag',
                'tag': str(tag or '').lower(),
                'attrs': {str(name or '').lower(): str(value or '') for name, value in attrs},
                'children': [],
            }
            stack[-1]['children'].append(node)

        def handle_endtag(self, tag):
            target = str(tag or '').lower()
            for idx in range(len(stack) - 1, 0, -1):
                if stack[idx].get('tag') == target:
                    del stack[idx:]
                    break

        def handle_data(self, data):
            if data:
                stack[-1]['children'].append({'type': 'text', 'text': data})

        def handle_entityref(self, name):
            stack[-1]['children'].append({'type': 'text', 'text': html.unescape(f'&{name};')})

        def handle_charref(self, name):
            stack[-1]['children'].append({'type': 'text', 'text': html.unescape(f'&#{name};')})

    parser = TreeParser()
    parser.feed(fragment or '')
    parser.close()
    return root


def extract_text_from_html_node(node) -> str:
    if not node:
        return ''
    if node.get('type') == 'text':
        return str(node.get('text') or '')
    return ''.join(extract_text_from_html_node(child) for child in node.get('children', []))


def decode_feishu_json_attr(raw_value: str):
    value = html.unescape(str(raw_value or '')).strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def decode_feishu_base64_json_attr(raw_value: str):
    value = str(raw_value or '').strip()
    if not value:
        return None
    padding = (-len(value)) % 4
    if padding:
        value += '=' * padding
    try:
        decoded = base64.b64decode(value)
    except (binascii.Error, ValueError):
        return None
    try:
        return json.loads(decoded.decode('utf-8'))
    except Exception:
        return None


def normalize_imported_news_date(raw_text: str) -> str:
    text = normalize_news_plain_text(raw_text, max_length=0)
    if not text:
        return ''
    patterns = [
        re.compile(r'(?P<year>20\d{2})\u5e74(?P<month>\d{1,2})\u6708(?P<day>\d{1,2})\u65e5'),
        re.compile(r'(?P<year>20\d{2})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})'),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        year = int(match.group('year'))
        month = int(match.group('month'))
        day = int(match.group('day'))
        try:
            return datetime(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''

def fetch_remote_url_content(source_url: str, *, allow_redirects: bool = False, timeout: float = 20.0,
                             headers: dict | None = None) -> dict:
    safe_headers = {str(key): str(value) for key, value in (headers or {}).items() if key and value}
    raw_source_url = (source_url or '').strip()
    if not raw_source_url:
        raise RemoteFetchError('缂哄皯杩滅▼鍦板潃', reason='missing_url')

    ok, reason, safe_source_url = _dep('validate_safe_remote_fetch_url')(raw_source_url)
    if not ok:
        raise RemoteFetchError(
            reason or '杩滅▼鍦板潃鏍￠獙澶辫触',
            reason='validate_safe_remote_fetch_url',
            source_url=raw_source_url,
            safe_source_url=safe_source_url,
        )

    try:
        if _dep('requests_support'):
            response = _dep('requests_module').get(
                safe_source_url,
                timeout=timeout,
                allow_redirects=allow_redirects,
                headers=safe_headers or None,
            )
            status_code = int(response.status_code)
            if not allow_redirects and 300 <= status_code < 400:
                raise RemoteFetchError(
                    '閾炬帴鍙戠敓閲嶅畾鍚戯紝璇锋敼鐢ㄦ渶缁堝湴鍧€',
                    reason='redirect_not_supported',
                    source_url=raw_source_url,
                    safe_source_url=safe_source_url,
                    status_code=status_code,
                    location=response.headers.get('Location', ''),
                )
            response.raise_for_status()
            final_url = str(getattr(response, 'url', '') or safe_source_url)
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            return {
                'source_url': raw_source_url,
                'safe_source_url': safe_source_url,
                'final_url': final_url,
                'status_code': status_code,
                'content_type': content_type,
                'content': response.content or b'',
                'text': response.text or '',
            }
        if _dep('httpx_support'):
            response = _dep('httpx_module').get(
                safe_source_url,
                timeout=timeout,
                follow_redirects=allow_redirects,
                headers=safe_headers or None,
            )
            status_code = int(response.status_code)
            if not allow_redirects and 300 <= status_code < 400:
                raise RemoteFetchError(
                    '閾炬帴鍙戠敓閲嶅畾鍚戯紝璇锋敼鐢ㄦ渶缁堝湴鍧€',
                    reason='redirect_not_supported',
                    source_url=raw_source_url,
                    safe_source_url=safe_source_url,
                    status_code=status_code,
                    location=response.headers.get('Location', ''),
                )
            response.raise_for_status()
            final_url = str(getattr(response, 'url', '') or safe_source_url)
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            return {
                'source_url': raw_source_url,
                'safe_source_url': safe_source_url,
                'final_url': final_url,
                'status_code': status_code,
                'content_type': content_type,
                'content': response.content or b'',
                'text': response.text or '',
            }
    except RemoteFetchError:
        raise
    except Exception as exc:
        raise RemoteFetchError(
            '杩滅▼鍐呭涓嬭浇澶辫触锛岃纭閾炬帴鍙叕寮€璁块棶',
            reason='download_failed',
            source_url=raw_source_url,
            safe_source_url=safe_source_url,
            error_type=type(exc).__name__,
            error=str(exc),
        ) from exc

    raise RemoteFetchError(
        '鏈嶅姟绔己灏戜笅杞藉鎴风渚濊禆',
        reason='no_http_client_dependency',
        source_url=raw_source_url,
        safe_source_url=safe_source_url,
    )


def import_news_image_url_to_asset(source_url: str, *, cache: dict | None = None) -> tuple[str, bool]:
    raw_source_url = str(source_url or '').strip()
    if not raw_source_url:
        raise RemoteFetchError('缂哄皯鍥剧墖閾炬帴', reason='missing_url')

    normalized_existing = normalize_legacy_news_asset_url(raw_source_url)
    if normalized_existing.startswith('/cdn_assets/news/'):
        return normalized_existing, False

    if cache is not None and raw_source_url in cache:
        return cache[raw_source_url], False

    fetched = fetch_remote_url_content(raw_source_url, allow_redirects=False, timeout=20.0)
    content = fetched.get('content') or b''
    content_type = str(fetched.get('content_type') or '').strip().lower()
    final_url = str(fetched.get('final_url') or raw_source_url)
    parsed = urlparse(final_url)

    if len(content) == 0:
        raise RemoteFetchError('鍥剧墖鍐呭涓虹┖', reason='empty_content', source_url=raw_source_url)
    if len(content) > 15 * 1024 * 1024:
        raise RemoteFetchError(
            '图片过大（最大 15MB）',
            reason='image_too_large',
            source_url=raw_source_url,
            content_length=len(content),
        )

    ext = _dep('validate_image_bytes')(
        str(parsed.path or ''),
        content_type,
        content,
        allowed_extensions=_dep('allowed_news_image_extensions'),
    )
    if ext not in _dep('allowed_news_image_extensions'):
        raise RemoteFetchError(
            '閾炬帴鍐呭涓嶆槸鍙楁敮鎸佺殑鍥剧墖鏍煎紡',
            reason='unsupported_image_format',
            source_url=raw_source_url,
            content_type=content_type,
            parsed_path=str(parsed.path or ''),
            detected_ext=ext,
        )

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = _dep('news_uploads_dir') / filename
    file_path.write_bytes(content)
    local_url = build_news_asset_url(filename)
    if cache is not None:
        cache[raw_source_url] = local_url
    return local_url, True


def render_inline_text_for_html(raw_text: str, *, preserve_newlines: bool = False) -> str:
    value = str(raw_text or '').replace('\u00a0', ' ')
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    if preserve_newlines:
        escaped = html.escape(value, quote=False)
        return escaped.replace('\n', '<br>')
    value = re.sub(r'\s+', ' ', value)
    if not value.strip():
        return ''
    return html.escape(value, quote=False)


def record_feishu_import_warning(state: dict, message: str) -> None:
    text = normalize_news_plain_text(message, max_length=300)
    if not text:
        return
    warnings = state.setdefault('warnings', [])
    if text not in warnings:
        warnings.append(text)


def merge_remote_candidate_urls(*candidate_groups) -> list[str]:
    merged = []
    seen = set()
    for group in candidate_groups:
        for raw_value in group or []:
            value = str(raw_value or '').strip()
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def collect_feishu_image_candidate_urls(node: dict, *, page_url: str = '', parent_node: dict | None = None) -> list[str]:
    attrs = dict(node.get('attrs') or {})
    parent_attrs = dict((parent_node or {}).get('attrs') or {})
    candidates = []

    def add_candidate(raw_url: str):
        raw_value = str(raw_url or '').strip()
        if not raw_value:
            return
        normalized_local = normalize_legacy_news_asset_url(raw_value)
        if normalized_local.startswith('/cdn_assets/news/'):
            if normalized_local not in candidates:
                candidates.append(normalized_local)
            return
        resolved = resolve_remote_candidate_url(page_url, raw_value)
        if resolved and resolved not in candidates:
            candidates.append(resolved)

    for attr_name in ('src', 'data-src', 'data-origin-src', 'data-raw-src', 'data-original-src'):
        add_candidate(attrs.get(attr_name, ''))

    suite_meta = decode_feishu_base64_json_attr(attrs.get('data-suite', ''))
    if isinstance(suite_meta, dict):
        add_candidate(suite_meta.get('originSrc', ''))

    gallery_sources = [
        parent_attrs.get('data-ace-gallery-json', ''),
        attrs.get('data-ace-gallery-json', ''),
    ]
    for raw_gallery in gallery_sources:
        gallery_meta = decode_feishu_json_attr(raw_gallery)
        items = gallery_meta.get('items') if isinstance(gallery_meta, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_src = str(item.get('src') or '').strip()
            if raw_src:
                add_candidate(unquote(raw_src))

    return candidates


def collect_feishu_page_image_candidate_groups(page_html: str, *, page_url: str = '') -> list[dict]:
    text = str(page_html or '').strip()
    if not text:
        return []

    groups = []
    seen_keys = set()

    def add_group(candidates: list[str], *, alt: str = ''):
        normalized = merge_remote_candidate_urls(candidates)
        if not normalized:
            return
        key = '\n'.join(normalized)
        if key in seen_keys:
            return
        seen_keys.add(key)
        groups.append({
            'candidates': normalized,
            'alt': normalize_news_plain_text(alt, max_length=300),
        })

    try:
        tree = build_simple_html_tree(text)
    except Exception:
        tree = {'type': 'root', 'children': []}

    feishu_meta_attrs = (
        'data-suite',
        'data-ace-gallery-json',
        'data-lark-image-uri',
        'data-origin-src',
        'data-raw-src',
        'data-original-src',
    )

    def walk(node, parent_node: dict | None = None):
        if not isinstance(node, dict):
            return
        if node.get('type') != 'tag':
            for child in node.get('children', []):
                walk(child, parent_node)
            return

        attrs = dict(node.get('attrs') or {})
        parent_attrs = dict((parent_node or {}).get('attrs') or {})
        if node.get('tag') == 'img':
            has_feishu_meta = any(str(attrs.get(name) or '').strip() for name in feishu_meta_attrs)
            has_feishu_meta = has_feishu_meta or any(
                str(parent_attrs.get(name) or '').strip() for name in ('data-ace-gallery-json',)
            )
            candidates = collect_feishu_image_candidate_urls(node, page_url=page_url, parent_node=parent_node)
            if has_feishu_meta or any('/space/api/box/stream/download/' in item for item in candidates):
                add_group(
                    candidates,
                    alt=str(attrs.get('alt') or attrs.get('title') or ''),
                )

        for child in node.get('children', []):
            walk(child, node)

    walk(tree)

    asynccode_matches = re.findall(
        r'https://[^"\'\s<>]+/space/api/box/stream/download/asynccode/\?code=[^"\'\s<>]+',
        text,
        flags=re.I,
    )
    for matched_url in asynccode_matches:
        resolved = resolve_remote_candidate_url(page_url, matched_url)
        if resolved:
            add_group([resolved])

    return groups


def pop_feishu_page_image_candidates(state: dict, *, image_name: str = '') -> list[str]:
    groups = state.get('page_image_candidate_groups') or []
    if not isinstance(groups, list) or not groups:
        return []

    used_indexes = state.setdefault('page_image_candidate_used_indexes', set())
    current_index = int(state.get('page_image_candidate_index') or 0)
    target_name = normalize_news_plain_text(image_name, max_length=300).lower()

    if target_name:
        for idx, group in enumerate(groups):
            if idx in used_indexes or not isinstance(group, dict):
                continue
            alt = normalize_news_plain_text(group.get('alt', ''), max_length=300).lower()
            if alt and (target_name in alt or alt in target_name):
                used_indexes.add(idx)
                state['page_image_candidate_index'] = max(current_index, idx + 1)
                return list(group.get('candidates') or [])

    for idx in range(current_index, len(groups)):
        if idx in used_indexes or not isinstance(groups[idx], dict):
            continue
        used_indexes.add(idx)
        state['page_image_candidate_index'] = idx + 1
        return list(groups[idx].get('candidates') or [])

    for idx, group in enumerate(groups):
        if idx in used_indexes or not isinstance(group, dict):
            continue
        used_indexes.add(idx)
        state['page_image_candidate_index'] = max(current_index, idx + 1)
        return list(group.get('candidates') or [])

    return []


def render_feishu_image_node(node: dict, state: dict, *, parent_node: dict | None = None) -> str:
    state['image_seen_count'] = int(state.get('image_seen_count') or 0) + 1
    candidates = collect_feishu_image_candidate_urls(
        node,
        page_url=state.get('page_url', ''),
        parent_node=parent_node,
    )
    local_url = ''
    last_error = None
    for candidate in candidates:
        if candidate.startswith('/cdn_assets/news/'):
            local_url = candidate
            break
        try:
            local_url, created = import_news_image_url_to_asset(candidate, cache=state.setdefault('image_cache', {}))
            if created:
                state['imported_image_count'] = int(state.get('imported_image_count') or 0) + 1
            break
        except Exception as exc:
            last_error = exc

    if not local_url:
        state['image_failed_count'] = int(state.get('image_failed_count') or 0) + 1
        if last_error:
            message = getattr(last_error, 'message', '') or str(last_error)
            record_feishu_import_warning(state, f'有图片未能转存：{message}')
        return ''

    attrs = dict(node.get('attrs') or {})
    alt = normalize_news_plain_text(
        attrs.get('alt', '') or attrs.get('title', '') or 'news-image',
        max_length=300,
    ) or 'news-image'
    return f'<img src="{html.escape(local_url, quote=True)}" alt="{html.escape(alt, quote=True)}">'


def render_feishu_inline_node(node: dict, state: dict, *, parent_node: dict | None = None,
                              preserve_newlines: bool = False) -> str:
    if not node:
        return ''
    if node.get('type') == 'text':
        return render_inline_text_for_html(node.get('text', ''), preserve_newlines=preserve_newlines)

    tag = str(node.get('tag') or '').lower()
    attrs = dict(node.get('attrs') or {})

    if tag == 'br':
        return '<br>'
    if tag == 'img':
        return render_feishu_image_node(node, state, parent_node=parent_node)
    if tag == 'a':
        raw_href = attrs.get('href', '')
        href = resolve_remote_candidate_url(state.get('page_url', ''), raw_href) or raw_href
        safe_href = sanitize_news_link_url(href)
        inner = ''.join(
            render_feishu_inline_node(child, state, parent_node=node, preserve_newlines=preserve_newlines)
            for child in node.get('children', [])
        ).strip()
        if not inner:
            return ''
        if safe_href:
            return f'<a href="{html.escape(safe_href, quote=True)}">{inner}</a>'
        return inner
    if tag in INLINE_RENDER_TAGS:
        inner = ''.join(
            render_feishu_inline_node(child, state, parent_node=node, preserve_newlines=preserve_newlines)
            for child in node.get('children', [])
        )
        wrap_tag = INLINE_RENDER_TAGS[tag]
        if not wrap_tag:
            return inner
        return f'<{wrap_tag}>{inner}</{wrap_tag}>' if inner else ''

    return ''.join(
        render_feishu_inline_node(child, state, parent_node=node, preserve_newlines=preserve_newlines)
        for child in node.get('children', [])
    )


def render_feishu_list_node(node: dict, state: dict) -> str:
    tag = str(node.get('tag') or '').lower()
    items_html = []
    for child in node.get('children', []):
        if child.get('type') != 'tag' or str(child.get('tag') or '').lower() != 'li':
            continue
        inline_parts = []
        nested_parts = []
        for li_child in child.get('children', []):
            child_tag = str(li_child.get('tag') or '').lower() if li_child.get('type') == 'tag' else ''
            if child_tag in {'ul', 'ol'}:
                nested_parts.append(render_feishu_list_node(li_child, state))
            else:
                inline_parts.append(render_feishu_inline_node(li_child, state, parent_node=child))
        inner_main = ''.join(inline_parts).strip()
        inner = inner_main + ''.join(part for part in nested_parts if part)
        if normalize_news_plain_text(inner, max_length=0):
            items_html.append(f'<li>{inner}</li>')
    if not items_html:
        return ''
    return f'<{tag}>{"".join(items_html)}</{tag}>'


def render_feishu_block_node(node: dict, state: dict, *, parent_node: dict | None = None) -> str:
    if not node:
        return ''
    if node.get('type') == 'text':
        text_html = render_inline_text_for_html(node.get('text', ''))
        return f'<p>{text_html}</p>' if text_html else ''

    tag = str(node.get('tag') or '').lower()
    attrs = dict(node.get('attrs') or {})
    children = list(node.get('children', []))

    if attrs.get('data-lark-html-role') == 'root':
        return ''.join(render_feishu_block_node(child, state, parent_node=node) for child in children)

    if tag == 'h1':
        title_text = normalize_news_plain_text(extract_text_from_html_node(node), max_length=200)
        if title_text and not state.get('title'):
            state['title'] = title_text
            return ''
        inner = ''.join(render_feishu_inline_node(child, state, parent_node=node) for child in children).strip()
        return f'<h2>{inner}</h2>' if inner else ''

    if tag in {'h2', 'h3', 'h4', 'h5', 'h6'}:
        inner = ''.join(render_feishu_inline_node(child, state, parent_node=node) for child in children).strip()
        return f'<{tag}>{inner}</{tag}>' if inner else ''

    if tag in {'ul', 'ol'}:
        return render_feishu_list_node(node, state)

    if tag == 'img':
        image_html = render_feishu_image_node(node, state, parent_node=parent_node)
        return f'<p>{image_html}</p>' if image_html else ''

    if tag == 'hr' or attrs.get('data-type') == 'divider':
        return '<hr>'

    if tag in {'div', 'p', 'blockquote', 'section', 'article'}:
        if attrs.get('data-type') == 'image':
            direct_images = [
                render_feishu_image_node(child, state, parent_node=node)
                for child in children
                if child.get('type') == 'tag' and str(child.get('tag') or '').lower() == 'img'
            ]
            direct_images = [f'<p>{item}</p>' for item in direct_images if item]
            if direct_images:
                return ''.join(direct_images)
            image_html = render_feishu_image_node(node, state, parent_node=parent_node)
            return f'<p>{image_html}</p>' if image_html else ''

        block_children = [
            child for child in children
            if child.get('type') == 'tag'
            and str(child.get('tag') or '').lower() in {'div', 'p', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'section', 'article'}
        ]
        if block_children:
            return ''.join(render_feishu_block_node(child, state, parent_node=node) for child in children)

        preserve_newlines = 'white-space:pre' in str(attrs.get('style') or '').replace(' ', '').lower()
        inner = ''.join(
            render_feishu_inline_node(child, state, parent_node=node, preserve_newlines=preserve_newlines)
            for child in children
        ).strip()
        if not normalize_news_plain_text(inner, max_length=0):
            return ''
        if tag == 'blockquote':
            return f'<blockquote>{inner}</blockquote>'
        return f'<p>{inner}</p>'

    inner = ''.join(render_feishu_inline_node(child, state, parent_node=node) for child in children).strip()
    return f'<p>{inner}</p>' if normalize_news_plain_text(inner, max_length=0) else ''


def convert_feishu_root_fragment_to_news_payload(root_fragment: str, *, page_url: str = '', page_title: str = '') -> dict:
    tree = build_simple_html_tree(root_fragment or '')
    root_node = next(
        (
            child for child in tree.get('children', [])
            if child.get('type') == 'tag' and str(child.get('attrs', {}).get('data-lark-html-role', '')).lower() == 'root'
        ),
        None,
    )
    if not root_node:
        root_node = next((child for child in tree.get('children', []) if child.get('type') == 'tag'), None)
    if not root_node:
        raise ValueError('未能识别飞书正文节点')

    state = {
        'page_url': page_url,
        'page_title': page_title,
        'title': '',
        'warnings': [],
        'image_cache': {},
        'imported_image_count': 0,
        'image_seen_count': 0,
        'image_failed_count': 0,
    }
    content_parts = [
        render_feishu_block_node(child, state, parent_node=root_node)
        for child in root_node.get('children', [])
    ]
    content_html = ''.join(part for part in content_parts if part).strip()
    content_html = sanitize_news_html_fragment(content_html)
    content_html = re.sub(r'(?is)<p>\s*</p>', '', content_html)
    content_html = re.sub(r'\n{3,}', '\n\n', content_html).strip()

    title = state.get('title') or normalize_news_plain_text(page_title, max_length=200)
    date = normalize_imported_news_date(extract_text_from_html_node(root_node))
    if not date:
        date = now_beijing().strftime('%Y-%m-%d')
        record_feishu_import_warning(state, '未识别到发布日期，已使用今天日期，请确认后再发布')
    if not title:
        record_feishu_import_warning(state, '未识别到标题，请检查导入结果后再发布')
    if state.get('image_failed_count'):
        record_feishu_import_warning(
            state,
            f'有 {int(state.get("image_failed_count") or 0)} 张图片未能成功转存，请发布前检查正文图片',
        )

    return {
        'title': title,
        'date': date,
        'content_html': content_html,
        'warnings': state.get('warnings', []),
        'imported_image_count': int(state.get('imported_image_count') or 0),
        'image_failed_count': int(state.get('image_failed_count') or 0),
        'image_seen_count': int(state.get('image_seen_count') or 0),
    }


def extract_feishu_client_vars_block_text(block_data: dict) -> str:
    text_data = (
        ((block_data or {}).get('text') or {}).get('initialAttributedTexts') or {}
    ).get('text')
    if isinstance(text_data, dict):
        parts = []
        for key in sorted(text_data.keys(), key=lambda item: int(str(item)) if str(item).isdigit() else str(item)):
            value = text_data.get(key)
            if value is None:
                continue
            parts.append(str(value))
        return ''.join(parts)
    if isinstance(text_data, list):
        return ''.join(str(item) for item in text_data if item is not None)
    if text_data is None:
        return ''
    return str(text_data)


def collect_feishu_client_vars_image_candidate_urls(block_id: str, block_data: dict) -> list[str]:
    image = dict((block_data or {}).get('image') or {})
    token = str(image.get('token') or '').strip()
    mount_node_token = str(block_id or '').strip()
    if not token or not mount_node_token:
        return []

    return [
        (
            'https://internal-api-drive-stream.feishu.cn/'
            f'space/api/box/stream/download/v2/cover/{token}/'
            f'?fallback_source=1&height=1280&mount_node_token={mount_node_token}'
            '&mount_point=docx_image&policy=equal&width=1280'
        ),
        (
            'https://internal-api-drive-stream.feishu.cn/'
            f'space/api/box/stream/download/all/{token}/'
            f'?mount_node_token={mount_node_token}&mount_point=docx_image'
        ),
        (
            'https://internal-api-drive-stream.feishu.cn/'
            f'space/api/box/stream/download/preview/{token}/?preview_type=16'
        ),
    ]


def render_feishu_client_vars_image_block(block_id: str, block_data: dict, state: dict) -> str:
    state['image_seen_count'] = int(state.get('image_seen_count') or 0) + 1
    image_name = normalize_news_plain_text(((block_data or {}).get('image') or {}).get('name', ''), max_length=120)
    page_candidates = pop_feishu_page_image_candidates(state, image_name=image_name)
    token_candidates = collect_feishu_client_vars_image_candidate_urls(block_id, block_data)
    candidates = merge_remote_candidate_urls(page_candidates, token_candidates)
    local_url = ''
    last_error = None

    for candidate in candidates:
        if candidate.startswith('/cdn_assets/news/'):
            local_url = candidate
            break
        try:
            local_url, created = import_news_image_url_to_asset(candidate, cache=state.setdefault('image_cache', {}))
            if created:
                state['imported_image_count'] = int(state.get('imported_image_count') or 0) + 1
            break
        except Exception as exc:
            last_error = exc

    if not local_url:
        state['image_failed_count'] = int(state.get('image_failed_count') or 0) + 1
        if image_name:
            record_feishu_import_warning(state, f'图片“{image_name}”未能转存：飞书当前未提供可直接下载的公开图片地址，可能仍需登录权限')
        else:
            record_feishu_import_warning(state, '有图片未能转存：飞书当前未提供可直接下载的公开图片地址，可能仍需登录权限')
        return ''

    image_meta = dict((block_data or {}).get('image') or {})
    alt = normalize_news_plain_text(
        image_meta.get('name', '') or 'news-image',
        max_length=300,
    ) or 'news-image'
    align = str((block_data or {}).get('align') or '').strip().lower()
    wrapper_style = 'text-align:center;' if align == 'center' else ''
    return (
        f'<p style="{wrapper_style}"><img src="{html.escape(local_url, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}"></p>'
    )


def convert_feishu_client_vars_payload_to_news_payload(
    client_vars_data: dict,
    *,
    page_url: str = '',
    page_title: str = '',
    page_html: str = '',
) -> dict:
    state = {
        'page_url': page_url,
        'page_title': page_title,
        'title': '',
        'warnings': [],
        'image_cache': {},
        'imported_image_count': 0,
        'image_seen_count': 0,
        'image_failed_count': 0,
        'page_image_candidate_groups': collect_feishu_page_image_candidate_groups(page_html, page_url=page_url),
        'page_image_candidate_index': 0,
    }

    data = dict(client_vars_data or {})
    block_map = dict(data.get('block_map') or {})
    meta_map = dict(data.get('meta_map') or {})
    page_id = str(data.get('id') or '').strip()
    page_block = dict((block_map.get(page_id) or {}).get('data') or {})
    sequence = list(page_block.get('children') or data.get('block_sequence') or [])
    if sequence and page_id and sequence[0] == page_id:
        sequence = sequence[1:]

    content_parts = []
    bullet_items = []
    all_text_parts = []

    def flush_bullets():
        nonlocal bullet_items
        if bullet_items:
            content_parts.append(f"<ul>{''.join(bullet_items)}</ul>")
            bullet_items = []

    for block_id in sequence:
        block = dict((block_map.get(block_id) or {}).get('data') or {})
        if not block or block.get('hidden'):
            continue
        block_type = str(block.get('type') or '').strip().lower()
        text_value = extract_feishu_client_vars_block_text(block)
        normalized_text = normalize_news_plain_text(text_value, max_length=0)
        if normalized_text:
            all_text_parts.append(normalized_text)

        if block_type == 'heading1':
            flush_bullets()
            title_text = normalize_news_plain_text(text_value, max_length=200)
            if title_text and not state.get('title'):
                state['title'] = title_text
            elif title_text:
                content_parts.append(f'<h2>{html.escape(title_text, quote=False)}</h2>')
            continue

        if block_type == 'heading2':
            flush_bullets()
            if normalized_text:
                content_parts.append(f'<h2>{html.escape(normalized_text, quote=False)}</h2>')
            continue

        if block_type == 'bullet':
            if normalized_text:
                bullet_items.append(f'<li>{render_inline_text_for_html(text_value, preserve_newlines=True)}</li>')
            continue

        flush_bullets()

        if block_type == 'text':
            if normalized_text:
                content_parts.append(f'<p>{render_inline_text_for_html(text_value, preserve_newlines=True)}</p>')
            continue

        if block_type == 'image':
            image_html = render_feishu_client_vars_image_block(str(block_id), block, state)
            if image_html:
                content_parts.append(image_html)
            continue

        if block_type == 'divider':
            content_parts.append('<hr>')
            continue

    flush_bullets()

    content_html = ''.join(part for part in content_parts if part).strip()
    content_html = sanitize_news_html_fragment(content_html)
    content_html = re.sub(r'(?is)<p>\s*</p>', '', content_html)
    content_html = re.sub(r'\n{3,}', '\n\n', content_html).strip()

    page_meta = dict(meta_map.get(page_id) or {})
    fallback_title = (
        normalize_news_plain_text(page_meta.get('title', ''), max_length=200)
        or normalize_news_plain_text(page_block.get('text', {}).get('initialAttributedTexts', {}).get('text', {}).get('0', ''), max_length=200)
        or normalize_news_plain_text(page_title, max_length=200)
    )
    title = state.get('title') or fallback_title

    date_source = ' '.join(
        part for part in [
            *all_text_parts,
            str(page_meta.get('update_time') or ''),
            str(page_meta.get('edit_time') or ''),
            str(page_meta.get('create_time') or ''),
        ]
        if str(part or '').strip()
    )
    date = normalize_imported_news_date(date_source)
    if not date:
        date = now_beijing().strftime('%Y-%m-%d')
        record_feishu_import_warning(state, '未识别到发布日期，已使用今天日期，请确认后再发布')
    if not title:
        record_feishu_import_warning(state, '未识别到标题，请检查导入结果后再发布')
    if state.get('image_failed_count'):
        record_feishu_import_warning(
            state,
            f'有 {int(state.get("image_failed_count") or 0)} 张图片未能成功转存，请发布前检查正文图片',
        )

    return {
        'title': title,
        'date': date,
        'content_html': content_html,
        'warnings': state.get('warnings', []),
        'imported_image_count': int(state.get('imported_image_count') or 0),
        'image_failed_count': int(state.get('image_failed_count') or 0),
        'image_seen_count': int(state.get('image_seen_count') or 0),
    }

# 妯″潡绾т緷璧栧鍣紝鍦?configure/register 闃舵涓€娆℃€ф敞鍏ャ€?
_DEPS = {}



# 渚濊禆娉ㄥ叆閰嶇疆鍏ュ彛銆?
def configure_news_content(
    *,
    pages_dir,
    news_featured_file,
    news_visibility_file,
    legacy_news_uploads_dir,
    news_uploads_dir,
    h2_home_file,
    markdown_support,
    markdown_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
    allowed_news_image_extensions,
    news_safe_html_tags,
    news_dropped_html_tags,
    news_void_html_tags,
    validate_uploaded_image_extension,
    validate_image_bytes,
    validate_safe_remote_fetch_url,
    sanitize_public_text,
    sanitize_public_date_text,
    sanitize_public_link_url,
    sanitize_public_media_url,
    get_h2_home_config,
    get_product_settings,
    normalize_related_news_links,
    get_chatbot_config,
    call_openai_api,
):
    """Configure shared dependencies for the news content module."""
    _DEPS.clear()
    _DEPS.update({
        'pages_dir': Path(pages_dir),
        'news_featured_file': Path(news_featured_file),
        'news_visibility_file': Path(news_visibility_file),
        'legacy_news_uploads_dir': Path(legacy_news_uploads_dir),
        'news_uploads_dir': Path(news_uploads_dir),
        'h2_home_file': Path(h2_home_file),
        'markdown_support': bool(markdown_support),
        'markdown_module': markdown_module,
        'requests_support': bool(requests_support),
        'requests_module': requests_module,
        'httpx_support': bool(httpx_support),
        'httpx_module': httpx_module,
        'allowed_news_image_extensions': set(allowed_news_image_extensions or set()),
        'news_safe_html_tags': set(news_safe_html_tags or set()),
        'news_dropped_html_tags': set(news_dropped_html_tags or set()),
        'news_void_html_tags': set(news_void_html_tags or set()),
        'validate_uploaded_image_extension': validate_uploaded_image_extension,
        'validate_image_bytes': validate_image_bytes,
        'validate_safe_remote_fetch_url': validate_safe_remote_fetch_url,
        'sanitize_public_text': sanitize_public_text,
        'sanitize_public_date_text': sanitize_public_date_text,
        'sanitize_public_link_url': sanitize_public_link_url,
        'sanitize_public_media_url': sanitize_public_media_url,
        'get_h2_home_config': get_h2_home_config,
        'get_product_settings': get_product_settings,
        'normalize_related_news_links': normalize_related_news_links,
        'get_chatbot_config': get_chatbot_config,
        'call_openai_api': call_openai_api,
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'News content dependency not configured: {name}')
    return value


def build_news_asset_url(filename: str) -> str:
    safe_name = str(filename or '').strip().lstrip('/')
    if not safe_name:
        return ''
    return f'/cdn_assets/news/{safe_name}'


def resolve_news_asset_file(filename: str) -> Path | None:
    safe_name = str(filename or '').strip().lstrip('/')
    if not safe_name or '..' in safe_name.split('/'):
        return None

    primary_path = _dep('news_uploads_dir') / safe_name
    if primary_path.is_file():
        return primary_path

    legacy_path = _dep('legacy_news_uploads_dir') / safe_name
    if legacy_path.is_file():
        return legacy_path

    return None


def normalize_legacy_news_asset_url(raw_url: str) -> str:
    value = str(raw_url or '').strip()
    if not value:
        return ''
    try:
        parsed = urlparse(value)
    except Exception:
        return value

    path = str(parsed.path or '').strip()
    if not path.startswith('/media/news/'):
        return value

    filename = path.split('/media/news/', 1)[1].lstrip('/')
    normalized_path = build_news_asset_url(filename)
    if not normalized_path:
        return value
    if parsed.query:
        return f'{normalized_path}?{parsed.query}'
    return normalized_path


def _news_dir() -> Path:
    return _dep('pages_dir') / 'news'


def _news_index_path() -> Path:
    return _news_dir() / 'news.html'


def normalize_news_plain_text(value: str, *, max_length: int = 0) -> str:
    text = html.unescape(str(value or '')).replace('\u00a0', ' ')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    if max_length > 0:
        text = text[:max_length].strip()
    return text


def sanitize_news_link_url(raw_url: str) -> str:
    value = str(raw_url or '').strip()
    if not value:
        return ''
    decoded = html.unescape(value).strip()
    lower = decoded.lower()
    if any(lower.startswith(prefix) for prefix in ('javascript:', 'data:', 'vbscript:', 'file:')):
        return ''

    try:
        parsed = urlparse(decoded)
    except Exception:
        return ''

    if parsed.scheme:
        if parsed.scheme.lower() not in {'http', 'https', 'mailto', 'tel'}:
            return ''
        if parsed.scheme.lower() in {'http', 'https'} and not parsed.netloc:
            return ''
        if parsed.username or parsed.password:
            return ''
        return parsed._replace(fragment='').geturl()

    if decoded.startswith('//') or decoded.startswith('\\\\'):
        return ''
    return decoded


def sanitize_news_image_url(raw_url: str) -> str:
    value = str(raw_url or '').strip()
    if not value:
        return ''
    safe_url = sanitize_news_link_url(value)
    if not safe_url:
        return ''
    lower = safe_url.lower()
    if lower.startswith(('mailto:', 'tel:')):
        return ''
    return normalize_legacy_news_asset_url(safe_url)


def sanitize_news_html_fragment(fragment: str) -> str:
    from html.parser import HTMLParser

    news_dropped_html_tags = _dep('news_dropped_html_tags')
    news_safe_html_tags = _dep('news_safe_html_tags')
    news_void_html_tags = _dep('news_void_html_tags')

    class SafeNewsHTMLParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.parts = []
            self.drop_depth = 0

        def _append_start(self, tag: str, attrs: list[tuple[str, str]]):
            if attrs:
                attr_text = ''.join(f' {name}="{html.escape(value, quote=True)}"' for name, value in attrs)
            else:
                attr_text = ''
            if tag in news_void_html_tags:
                self.parts.append(f'<{tag}{attr_text}>')
            else:
                self.parts.append(f'<{tag}{attr_text}>')

        def handle_starttag(self, tag, attrs):
            tag_name = str(tag or '').lower()
            if tag_name in news_dropped_html_tags:
                self.drop_depth += 1
                return
            if self.drop_depth > 0 or tag_name not in news_safe_html_tags:
                return

            cleaned_attrs = []
            if tag_name == 'a':
                href = ''
                rel_tokens = set()
                target_value = ''
                for name, raw_value in attrs:
                    attr_name = str(name or '').lower()
                    if attr_name.startswith('on') or attr_name in {'style', 'srcset'}:
                        continue
                    attr_value = str(raw_value or '')
                    if attr_name == 'href':
                        href = sanitize_news_link_url(attr_value)
                    elif attr_name == 'title':
                        cleaned_attrs.append(('title', normalize_news_plain_text(attr_value, max_length=300)))
                    elif attr_name == 'target':
                        if attr_value in {'_blank', '_self'}:
                            target_value = attr_value
                    elif attr_name == 'rel':
                        rel_tokens.update(
                            token for token in re.split(r'\s+', attr_value.strip().lower())
                            if token in {'noopener', 'noreferrer', 'nofollow'}
                        )
                if href:
                    cleaned_attrs.append(('href', href))
                if target_value:
                    cleaned_attrs.append(('target', target_value))
                    if target_value == '_blank':
                        rel_tokens.update({'noopener', 'noreferrer'})
                if rel_tokens:
                    cleaned_attrs.append(('rel', ' '.join(sorted(rel_tokens))))
            elif tag_name == 'img':
                for name, raw_value in attrs:
                    attr_name = str(name or '').lower()
                    if attr_name.startswith('on') or attr_name in {'style', 'srcset'}:
                        continue
                    attr_value = str(raw_value or '')
                    if attr_name == 'src':
                        safe_src = sanitize_news_image_url(attr_value)
                        if safe_src:
                            cleaned_attrs.append(('src', safe_src))
                    elif attr_name in {'alt', 'title'}:
                        cleaned_attrs.append((attr_name, normalize_news_plain_text(attr_value, max_length=300)))
                    elif attr_name in {'width', 'height'}:
                        digits = re.sub(r'[^0-9]', '', attr_value)
                        if digits:
                            cleaned_attrs.append((attr_name, digits[:4]))
                    elif attr_name == 'loading' and attr_value in {'lazy', 'eager'}:
                        cleaned_attrs.append((attr_name, attr_value))
                if not any(name == 'src' for name, _ in cleaned_attrs):
                    return
            elif tag_name == 'video':
                bool_attrs = set()
                for name, raw_value in attrs:
                    attr_name = str(name or '').lower()
                    if attr_name.startswith('on') or attr_name in {'style', 'srcset', 'class'}:
                        continue
                    attr_value = str(raw_value or '')
                    if attr_name == 'src':
                        safe_src = sanitize_news_image_url(attr_value)
                        if safe_src:
                            cleaned_attrs.append(('src', safe_src))
                    elif attr_name == 'poster':
                        safe_poster = sanitize_news_image_url(attr_value)
                        if safe_poster:
                            cleaned_attrs.append(('poster', safe_poster))
                    elif attr_name == 'preload' and attr_value in {'none', 'metadata', 'auto'}:
                        cleaned_attrs.append(('preload', attr_value))
                    elif attr_name in {'controls', 'muted', 'playsinline', 'loop', 'autoplay'}:
                        bool_attrs.add(attr_name)
                for attr_name in ('controls', 'muted', 'playsinline', 'loop', 'autoplay'):
                    if attr_name in bool_attrs:
                        cleaned_attrs.append((attr_name, attr_name))
            elif tag_name == 'source':
                src_value = ''
                type_value = ''
                for name, raw_value in attrs:
                    attr_name = str(name or '').lower()
                    if attr_name.startswith('on') or attr_name in {'style', 'srcset', 'class'}:
                        continue
                    attr_value = str(raw_value or '')
                    if attr_name == 'src':
                        src_value = sanitize_news_image_url(attr_value)
                    elif attr_name == 'type':
                        type_value = normalize_news_plain_text(attr_value, max_length=100).lower()
                if not src_value:
                    return
                cleaned_attrs.append(('src', src_value))
                if type_value and type_value.startswith(('video/', 'audio/')):
                    cleaned_attrs.append(('type', type_value))
            elif tag_name in {'td', 'th'}:
                for name, raw_value in attrs:
                    attr_name = str(name or '').lower()
                    if attr_name in {'colspan', 'rowspan'}:
                        digits = re.sub(r'[^0-9]', '', str(raw_value or ''))
                        if digits:
                            cleaned_attrs.append((attr_name, digits[:2]))

            self._append_start(tag_name, cleaned_attrs)

        def handle_startendtag(self, tag, attrs):
            tag_name = str(tag or '').lower()
            if tag_name in news_dropped_html_tags or self.drop_depth > 0 or tag_name not in news_safe_html_tags:
                return
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            tag_name = str(tag or '').lower()
            if tag_name in news_dropped_html_tags:
                if self.drop_depth > 0:
                    self.drop_depth -= 1
                return
            if self.drop_depth > 0 or tag_name not in news_safe_html_tags or tag_name in news_void_html_tags:
                return
            self.parts.append(f'</{tag_name}>')

        def handle_data(self, data):
            if self.drop_depth > 0 or not data:
                return
            self.parts.append(html.escape(data))

        def handle_entityref(self, name):
            if self.drop_depth > 0 or not name:
                return
            self.parts.append(f'&{name};')

        def handle_charref(self, name):
            if self.drop_depth > 0 or not name:
                return
            self.parts.append(f'&#{name};')

        def handle_comment(self, data):
            return

    parser = SafeNewsHTMLParser()
    try:
        parser.feed(fragment or '')
        parser.close()
    except Exception:
        return html.escape(fragment or '')
    sanitized = ''.join(parser.parts)
    return sanitized.strip()


def build_news_card_html(
    filename: str,
    category: str,
    division: str,
    image_url: str,
    date: str,
    title: str,
    summary: str,
    *,
    hidden: bool = False,
) -> str:
    safe_filename = Path(filename).name
    safe_category = category if category in {'enterprise', 'industry', 'science'} else 'enterprise'
    safe_division = html.escape(normalize_news_plain_text(division, max_length=80), quote=True)
    safe_image_url = html.escape(sanitize_news_image_url(image_url) or '/assets/images/logo.png', quote=True)
    safe_date = html.escape(normalize_news_plain_text(date, max_length=80), quote=False)
    safe_title = html.escape(normalize_news_plain_text(title, max_length=200), quote=False)
    safe_summary = html.escape(normalize_news_plain_text(summary, max_length=220), quote=False)
    hidden_attr = 'true' if hidden else 'false'
    return f"""
                    <a href="../../pages/news/{safe_filename}" class="vs-card" data-category="{safe_category}" data-division="{safe_division}" data-hidden="{hidden_attr}">
                        <div class="vs-card__img-wrapper">
                            <img src="{safe_image_url}" alt="News Image">
                        </div>
                        <div class="vs-card__content">
                            <div class="vs-news-meta"><i class="far fa-calendar-alt"></i> {safe_date}</div>
                            <h3 class="vs-card__title">{safe_title}</h3>
                            <p class="vs-card__desc">{safe_summary}</p>
                            <span class="vs-link-arrow">鏌ョ湅璇︽儏</span>
                        </div>
                    </a>
"""


def parse_news_from_html():
    """Parse news cards from news.html."""
    news_file = _news_index_path()
    if not news_file.exists():
        return {'enterprise': [], 'industry': [], 'science': []}

    try:
        from html.parser import HTMLParser

        class NewsParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.news_items = {'enterprise': [], 'industry': [], 'science': []}
                self.current_item = None
                self.current_tag = None
                self.in_card = False
                self.in_title = False
                self.in_meta = False
                self.in_desc = False
                self.current_category = None

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)

                if tag == 'a' and 'vs-card' in attrs_dict.get('class', ''):
                    category = attrs_dict.get('data-category', '')
                    if category in self.news_items:
                        self.in_card = True
                        self.current_category = category
                        self.current_item = {
                            'link': attrs_dict.get('href', ''),
                            'title': '',
                            'date': '',
                            'desc': '',
                            'image': '',
                            'division': attrs_dict.get('data-division', '').strip(),
                        }
                elif self.in_card:
                    if tag == 'img' and 'src' in attrs_dict:
                        if not self.current_item['image']:
                            self.current_item['image'] = attrs_dict['src']
                    elif tag == 'h3' and 'vs-card__title' in attrs_dict.get('class', ''):
                        self.in_title = True
                    elif tag == 'div' and 'vs-news-meta' in attrs_dict.get('class', ''):
                        self.in_meta = True
                    elif tag == 'p' and 'vs-card__desc' in attrs_dict.get('class', ''):
                        self.in_desc = True

                self.current_tag = tag

            def handle_endtag(self, tag):
                if tag == 'a' and self.in_card:
                    if self.current_item and self.current_category:
                        link = self.current_item['link']
                        if link.startswith('../../'):
                            link = link[6:]
                        self.current_item['link'] = link
                        self.news_items[self.current_category].append(self.current_item)
                    self.in_card = False
                    self.current_item = None
                    self.current_category = None
                elif tag == 'h3':
                    self.in_title = False
                elif tag == 'div' and self.in_meta:
                    self.in_meta = False
                elif tag == 'p':
                    self.in_desc = False

            def handle_data(self, data):
                if not self.current_item:
                    return
                data = data.strip()
                if not data:
                    return

                if self.in_title:
                    self.current_item['title'] += data
                elif self.in_meta:
                    date_match = re.search(r'\d{4}-\d{2}-\d{2}', data)
                    if date_match:
                        self.current_item['date'] = date_match.group()
                elif self.in_desc:
                    self.current_item['desc'] += data

        html_content = news_file.read_text(encoding='utf-8')
        parser = NewsParser()
        parser.feed(html_content)
        return parser.news_items
    except Exception as exc:
        print(f'Error parsing news: {exc}')
        return {'enterprise': [], 'industry': [], 'science': []}


def get_next_news_id():
    """Return the next available news_show numeric id."""
    news_dir = _news_dir()
    max_id = 0
    if news_dir.exists():
        for file in news_dir.glob('news_show.aspx_id_*.html'):
            match = re.search(r'news_show\.aspx_id_(\d+)\.html', file.name)
            if match:
                try:
                    max_id = max(max_id, int(match.group(1)))
                except ValueError:
                    pass
    return max_id + 1


def build_news_article_html(title, date, image_url, content_html):
    """Render a news article page in the unified template."""
    safe_title_text = normalize_news_plain_text(title, max_length=200)
    safe_title = html.escape(safe_title_text, quote=True)
    hero_title = html.escape(safe_title_text, quote=False)
    safe_date = html.escape(normalize_news_plain_text(date, max_length=80), quote=False)
    safe_image_url = html.escape(sanitize_news_image_url(image_url) or '/assets/images/logo.png', quote=True)
    hero_background_url = sanitize_news_image_url(image_url)
    if not hero_background_url or hero_background_url == '/assets/images/logo.png':
        hero_background_url = '/assets/images/section2_bj.jpg'
    safe_hero_background_url = html.escape(hero_background_url, quote=True)
    safe_content_html = sanitize_news_html_fragment(content_html)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{hero_title} - 湖南元芯传感科技有限责任公司</title>
    
    <!-- YX Style V2.0 -->
    <link rel="stylesheet" href="../../assets/css/yx-style.css">
    
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        .article-hero {{
            position: relative;
            background: linear-gradient(135deg, rgba(0, 31, 63, 0.78) 0%, rgba(0, 31, 63, 0.58) 100%), url('{safe_hero_background_url}') center/cover;
            height: 40vh;
            min-height: 300px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: white !important;
            padding: 0 20px;
        }}
        .article-hero__title {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 16px;
            max-width: 900px;
            line-height: 1.4;
        }}
        .article-hero__meta {{
            font-size: 16px;
            opacity: 0.8;
        }}
        .article-container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }}
        @media (min-width: 1920px) {{
            .article-container {{
                max-width: 1600px;
            }}
            .article-content {{
                font-size: 19px;
            }}
            .article-hero__title {{
                font-size: 48px;
            }}
        }}
        .article-content {{
            font-size: 17px;
            line-height: 1.9;
            color: #333;
        }}
        .article-content p {{
            margin-bottom: 20px;
        }}
        .article-content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 24px auto; display: block;
        }}
        .article-content strong {{
            color: var(--color-primary);
        }}
        .article-content ul, .article-content ol {{
            margin: 20px 0;
            padding-left: 30px;
        }}
        .article-content li {{
            margin-bottom: 10px;
        }}
        .article-nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 40px 0;
            border-top: 1px solid #eee;
            margin-top: 40px;
        }}
        .article-nav a {{
            color: var(--color-primary);
            text-decoration: none;
            font-weight: 500;
        }}
        .article-nav a:hover {{
            text-decoration: underline;
        }}
        .back-btn, a.back-btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: var(--color-primary);
            color: white !important;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
        }}
        .back-btn:hover {{
            background: var(--color-accent-blue);
            transform: translateY(-2px);
        }}
    </style>
  <!-- Site Search -->
  <link rel="stylesheet" href="../../assets/css/search.css">
</head>
<body>
    <!-- Header -->
    <header class="vs-header">
    <div class="vs-container vs-header__inner">
      <div style="display: flex; align-items: center">
        <a href="../../index.html" class="vs-logo">
          <img src="../../assets/images/logo.png" alt="Metachip Logo" style="filter: brightness(0) invert(1)" />
          METACHIP
        </a>
      </div>

      <nav class="vs-nav" style="margin-left: auto; margin-right: 40px;">
        <ul class="vs-nav__list">

          <li class="vs-nav__item">
            <a href="../biosensing/index.html?filter=sensor" class="vs-nav__link">生化传感事业部</a>
          </li>
          <li class="vs-nav__item">
            <a href="../gassensing/index.html" class="vs-nav__link">先进氢气传感解决方案</a>
          </li>
          <li class="vs-nav__item vs-nav__item--has-mega">
            <a href="../news/news.html" class="vs-nav__link">洞察与资讯</a>
          </li>
          <li class="vs-nav__item">
            <a href="../contact/contact.html" class="vs-nav__link">联系我们</a>
          </li>
        </ul>
      </nav>

      <div style="display: flex; gap: 24px; color: white; align-items: center">
        <a href="#" class="vs-search-trigger" title="搜索 (Ctrl+K)"><i class="fas fa-search"></i></a>
        <span style="font-size: 14px; font-weight: 700; color:white;">CN</span> / <a href="../../index_en.html" style="font-size: 14px; font-weight: 500;">EN</a>
      </div>
    </div>
  </header>

    <section class="article-hero" data-cover-image="{safe_image_url}">
        <h1 class="article-hero__title">{hero_title}</h1>
        <div class="article-hero__meta">{safe_date}</div>
    </section>

    <div class="article-container">
        <div class="article-content">
            {safe_content_html}
        </div>

        <div style="margin-top: 40px;">
            <a href="../news/news.html" class="back-btn"><i class="fas fa-arrow-left"></i> 返回资讯列表</a>
        </div>
    </div>

    <script src="../../assets/js/search.js"></script>
</body>
</html>"""


def render_markdown(content: str) -> str:
    """Render Markdown content for the news editor."""
    if _dep('markdown_support'):
        return _dep('markdown_module').markdown(content, extensions=['extra', 'tables', 'sane_lists'])

    lines = content.split('\n')
    html_lines = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_lines.append('</ul>')
            in_ul = False
        if in_ol:
            html_lines.append('</ol>')
            in_ol = False

    for raw in lines:
        line = raw.strip()
        if not line:
            close_lists()
            continue

        if line.startswith('### '):
            close_lists()
            html_lines.append(f'<h3>{html.escape(line[4:])}</h3>')
            continue
        if line.startswith('## '):
            close_lists()
            html_lines.append(f'<h2>{html.escape(line[3:])}</h2>')
            continue
        if line.startswith('# '):
            close_lists()
            html_lines.append(f'<h1>{html.escape(line[2:])}</h1>')
            continue

        if line.startswith('- ') or line.startswith('* '):
            if in_ol:
                html_lines.append('</ol>')
                in_ol = False
            if not in_ul:
                html_lines.append('<ul>')
                in_ul = True
            html_lines.append(f'<li>{html.escape(line[2:])}</li>')
            continue

        if re.match(r'^\d+\.\s+', line):
            if in_ul:
                html_lines.append('</ul>')
                in_ul = False
            if not in_ol:
                html_lines.append('<ol>')
                in_ol = True
            item = re.sub(r'^\d+\.\s+', '', line)
            html_lines.append(f'<li>{html.escape(item)}</li>')
            continue

        close_lists()
        escaped = html.escape(line)
        escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
        escaped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', escaped)
        escaped = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1">', escaped)
        escaped = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', escaped)
        html_lines.append(f'<p>{escaped}</p>')

    close_lists()
    return '\n'.join(html_lines)


def parse_news_article_html(filepath: Path):
    """Parse a generated news article page and extract fields."""
    def extract_first_div_by_class(html_text: str, class_name: str) -> str:
        start_re = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>',
            re.I,
        )
        start_match = start_re.search(html_text)
        if not start_match:
            return ''

        tag_re = re.compile(r'<div\b[^>]*>|</div\s*>', re.I)
        depth = 1
        content_start = start_match.end()
        for match in tag_re.finditer(html_text, content_start):
            tag = match.group(0)
            if tag.lower().startswith('</div'):
                depth -= 1
                if depth == 0:
                    return html_text[content_start:match.start()]
            else:
                depth += 1
        return ''

    if not filepath.exists():
        return None
    content = filepath.read_text(encoding='utf-8')
    title_match = re.search(r'<h1 class="article-hero__title">(.*?)</h1>', content, re.S)
    date_match = re.search(r'<div class="article-hero__meta">(.*?)</div>', content, re.S)
    cover_match = re.search(r'<section\b[^>]*class="article-hero"[^>]*data-cover-image="([^"]*)"', content, re.I | re.S)
    title = title_match.group(1).strip() if title_match else ''
    date = date_match.group(1).strip() if date_match else ''
    image_url = html.unescape(cover_match.group(1).strip()) if cover_match else ''
    body_html = extract_first_div_by_class(content, 'article-content').strip()
    leading_image_match = re.match(r'^\s*<img\s+[^>]*src="([^"]+)"[^>]*>\s*', body_html, re.I)
    if leading_image_match:
        if not image_url:
            image_url = leading_image_match.group(1)
        body_html = re.sub(r'^\s*<img\s+[^>]*>\s*', '', body_html, count=1, flags=re.I)
    body_text = body_html
    body_text = re.sub(r'(?i)<br\\s*/?>', '\n', body_text)
    body_text = re.sub(r'(?i)</p\\s*>', '\n', body_text)
    body_text = re.sub(r'(?i)</div\\s*>', '\n', body_text)
    body_text = re.sub(r'<[^>]+>', '', body_text)
    body_text = html.unescape(body_text)
    body_text = re.sub(r'\n{3,}', '\n\n', body_text).strip()
    return {
        'title': title,
        'date': date,
        'image_url': image_url,
        'content_html': body_html,
        'content_text': body_text,
    }


def derive_news_cover_and_summary(content_html: str, image_url: str = '', summary: str = ''):
    """Derive a cover image and summary from article content."""
    html_body = content_html or ''
    final_image = (image_url or '').strip()
    final_summary = (summary or '').strip()

    if not final_image:
        img_match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html_body, re.I)
        if img_match:
            final_image = img_match.group(1).strip()
    if not final_image:
        final_image = '/assets/images/logo.png'

    if not final_summary:
        para_match = re.search(r'<p\b[^>]*>(.*?)</p>', html_body, re.I | re.S)
        candidate = ''
        if para_match:
            candidate = para_match.group(1)
        else:
            block_match = re.search(r'<(?:div|li|blockquote)\b[^>]*>(.*?)</(?:div|li|blockquote)>', html_body, re.I | re.S)
            if block_match:
                candidate = block_match.group(1)
            else:
                candidate = html_body

        candidate = re.sub(r'(?i)<br\s*/?>', '\n', candidate)
        candidate = re.sub(r'<[^>]+>', '', candidate)
        candidate = html.unescape(candidate).replace('\u00a0', ' ')
        candidate = re.sub(r'\s+', ' ', candidate).strip()
        final_summary = candidate

    return final_image, final_summary


def insert_news_card(news_html_path: Path, card_html: str) -> bool:
    """Insert a news card into news.html after the page marker."""
    if not news_html_path.exists():
        return False
    content = news_html_path.read_text(encoding='utf-8')
    marker = "<!-- Page 1 Items -->"
    idx = content.find(marker)
    if idx != -1:
        insert_pos = idx + len(marker)
        content = content[:insert_pos] + "\n" + card_html + content[insert_pos:]
        news_html_path.write_text(content, encoding='utf-8')
        return True
    fallback = "</div>\n            </div>\n        </section>"
    idx = content.find(fallback)
    if idx != -1:
        content = content[:idx] + card_html + "\n" + content[idx:]
        news_html_path.write_text(content, encoding='utf-8')
        return True
    return False


def build_news_card_regex(filename: str):
    """Build a regex that matches a news card by filename."""
    return re.compile(
        rf'<a\s+[^>]*href\s*=\s*["\'][^"\']*{re.escape(filename)}[^"\']*["\'][^>]*>.*?</a>',
        re.DOTALL | re.IGNORECASE,
    )


def dedupe_news_cards(content: str, filename: str):
    """Remove duplicate news cards for the same filename."""
    pattern = build_news_card_regex(filename)
    matches = list(pattern.finditer(content))
    if len(matches) <= 1:
        return content, 0
    out = []
    last = 0
    removed = 0
    for idx, match in enumerate(matches):
        out.append(content[last:match.start()])
        if idx == 0:
            out.append(match.group(0))
        else:
            removed += 1
        last = match.end()
    out.append(content[last:])
    return ''.join(out), removed


def get_hidden_news_links():
    """Load hidden news links."""
    default_config = {'hidden_links': []}
    news_visibility_file = _dep('news_visibility_file')
    if news_visibility_file.exists():
        try:
            config = json.loads(news_visibility_file.read_text(encoding='utf-8'))
            links = config.get('hidden_links', [])
            if isinstance(links, list):
                return set([link for link in links if isinstance(link, str)])
        except Exception:
            pass
    news_visibility_file.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return set()


def save_hidden_news_links(links):
    """Persist hidden news links."""
    cleaned = []
    for link in links:
        if link and isinstance(link, str):
            cleaned.append(link)
    data = {'hidden_links': cleaned}
    _dep('news_visibility_file').write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return set(cleaned)


def get_featured_news_config():
    """Load featured news links."""
    default_config = {'links': []}
    news_featured_file = _dep('news_featured_file')
    if news_featured_file.exists():
        try:
            config = json.loads(news_featured_file.read_text(encoding='utf-8'))
            if isinstance(config, dict) and isinstance(config.get('links', []), list):
                return config
        except Exception:
            pass
    news_featured_file.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_config


def save_featured_news_config(new_config):
    """Persist featured news links."""
    links = new_config.get('links', [])
    if not isinstance(links, list):
        links = []
    seen = set()
    normalized = []
    for link in links:
        if not link or not isinstance(link, str):
            continue
        if link in seen:
            continue
        seen.add(link)
        normalized.append(link)
    saved = {'links': normalized[:3]}
    _dep('news_featured_file').write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    return saved


def get_all_news_items():
    """Scan all news items and normalize their metadata."""
    news_index = _news_index_path()
    if not news_index.exists():
        return []

    content = news_index.read_text(encoding='utf-8')
    sanitize_public_text = _dep('sanitize_public_text')
    sanitize_public_link_url = _dep('sanitize_public_link_url')
    sanitize_public_media_url = _dep('sanitize_public_media_url')
    sanitize_public_date_text = _dep('sanitize_public_date_text')

    from html.parser import HTMLParser

    class NewsListParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []
            self.current_item = None
            self.current_category = ''
            self.in_card = False
            self.in_title = False
            self.in_meta = False
            self.in_desc = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == 'a' and 'vs-card' in attrs_dict.get('class', ''):
                self.in_card = True
                self.current_category = (attrs_dict.get('data-category', '') or '').strip()
                self.current_item = {
                    'link': (attrs_dict.get('href', '') or '').strip(),
                    'image': '',
                    'date': '',
                    'title': '',
                    'desc': '',
                    'summary': '',
                    'category': self.current_category,
                    'division': (attrs_dict.get('data-division', '') or '').strip(),
                }
                return

            if not self.in_card or not self.current_item:
                return

            if tag == 'img' and not self.current_item['image']:
                self.current_item['image'] = (attrs_dict.get('src', '') or '').strip()
            elif tag == 'h3' and 'vs-card__title' in attrs_dict.get('class', ''):
                self.in_title = True
            elif tag == 'div' and 'vs-news-meta' in attrs_dict.get('class', ''):
                self.in_meta = True
            elif tag == 'p' and 'vs-card__desc' in attrs_dict.get('class', ''):
                self.in_desc = True

        def handle_endtag(self, tag):
            if tag == 'a' and self.in_card:
                if self.current_item:
                    link = self.current_item.get('link', '')
                    if link.startswith('../../pages/news/'):
                        link = '/pages/news/' + link.replace('../../pages/news/', '')
                    desc_text = sanitize_public_text(self.current_item.get('desc', ''), max_length=220)
                    self.current_item['link'] = sanitize_public_link_url(link, default='')
                    self.current_item['image'] = sanitize_public_media_url(self.current_item.get('image', ''), enforce_remote_public=False)
                    self.current_item['date'] = sanitize_public_date_text(self.current_item.get('date', ''))
                    self.current_item['title'] = sanitize_public_text(self.current_item.get('title', ''), max_length=200)
                    self.current_item['desc'] = desc_text
                    self.current_item['summary'] = desc_text
                    self.current_item['category'] = sanitize_public_text(self.current_item.get('category', ''), max_length=32)
                    self.current_item['division'] = sanitize_public_text(self.current_item.get('division', ''), max_length=64)
                    self.items.append(self.current_item)
                self.current_item = None
                self.current_category = ''
                self.in_card = False
                self.in_title = False
                self.in_meta = False
                self.in_desc = False
            elif tag == 'h3':
                self.in_title = False
            elif tag == 'div':
                self.in_meta = False
            elif tag == 'p':
                self.in_desc = False

        def handle_data(self, data):
            if not self.current_item:
                return
            text = (data or '').strip()
            if not text:
                return
            if self.in_title:
                self.current_item['title'] += text
            elif self.in_meta:
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
                if date_match:
                    self.current_item['date'] = date_match.group(0)
            elif self.in_desc:
                self.current_item['desc'] += text

    parser = NewsListParser()
    parser.feed(content)

    hidden_links = get_hidden_news_links()
    for item in parser.items:
        item['hidden'] = item.get('link') in hidden_links
    return parser.items


def normalize_news_link_for_product(link: str) -> str:
    raw = str(link or '').strip()
    if not raw:
        return ''
    if raw.startswith('../../'):
        return '/' + raw.replace('../../', '', 1)
    if raw.startswith('../'):
        return '/' + raw.replace('../', '', 1)
    if raw.startswith('pages/'):
        return '/' + raw
    return raw


def save_h2_home_news(items):
    """Save homepage news configuration with custom fields."""
    if not isinstance(items, list):
        items = []
    cleaned = []
    seen = set()
    sanitize_public_text = _dep('sanitize_public_text')
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get('link')
        if not link or not isinstance(link, str):
            continue
        if link in seen:
            continue
        seen.add(link)
        cleaned.append({
            'link': link,
            'customTag': sanitize_public_text(item.get('customTag', ''), max_length=24),
            'customTitle': sanitize_public_text(item.get('customTitle', ''), max_length=120),
            'customDesc': sanitize_public_text(item.get('customDesc', ''), max_length=220),
        })
    existing = _dep('get_h2_home_config')()
    saved = {
        'items': existing.get('items', []),
        'products': existing.get('products', []),
        'cases': existing.get('cases', []),
        'news': cleaned[:3],
        'measurementProducts': existing.get('measurementProducts', {}),
    }
    _dep('h2_home_file').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    return saved



# 璺敱娉ㄥ唽鍏ュ彛銆?
def register_news_content_routes(
    app,
    *,
    login_required,
    pages_dir,
    news_featured_file,
    news_visibility_file,
    legacy_news_uploads_dir,
    news_uploads_dir,
    h2_home_file,
    markdown_support,
    markdown_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
    allowed_news_image_extensions,
    news_safe_html_tags,
    news_dropped_html_tags,
    news_void_html_tags,
    validate_uploaded_image_extension,
    validate_image_bytes,
    validate_safe_remote_fetch_url,
    sanitize_public_text,
    sanitize_public_date_text,
    sanitize_public_link_url,
    sanitize_public_media_url,
    get_h2_home_config,
    get_product_settings,
    normalize_related_news_links,
    get_chatbot_config,
    call_openai_api,
):
    """Register news-content routes and inject shared dependencies."""
    configure_news_content(
        pages_dir=pages_dir,
        news_featured_file=news_featured_file,
        news_visibility_file=news_visibility_file,
        legacy_news_uploads_dir=legacy_news_uploads_dir,
        news_uploads_dir=news_uploads_dir,
        h2_home_file=h2_home_file,
        markdown_support=markdown_support,
        markdown_module=markdown_module,
        requests_support=requests_support,
        requests_module=requests_module,
        httpx_support=httpx_support,
        httpx_module=httpx_module,
        allowed_news_image_extensions=allowed_news_image_extensions,
        news_safe_html_tags=news_safe_html_tags,
        news_dropped_html_tags=news_dropped_html_tags,
        news_void_html_tags=news_void_html_tags,
        validate_uploaded_image_extension=validate_uploaded_image_extension,
        validate_image_bytes=validate_image_bytes,
        validate_safe_remote_fetch_url=validate_safe_remote_fetch_url,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_date_text=sanitize_public_date_text,
        sanitize_public_link_url=sanitize_public_link_url,
        sanitize_public_media_url=sanitize_public_media_url,
        get_h2_home_config=get_h2_home_config,
        get_product_settings=get_product_settings,
        normalize_related_news_links=normalize_related_news_links,
        get_chatbot_config=get_chatbot_config,
        call_openai_api=call_openai_api,
    )

    @app.route('/api/news')
    def get_news():
        count = request.args.get('count', 2, type=int)
        category = request.args.get('category', None)
        news_data = parse_news_from_html()

        result = {}
        for cat, items in news_data.items():
            if category and cat != category:
                continue
            result[cat] = items[:count]
        return jsonify(result)

    @app.route('/api/news/all')
    @login_required
    def get_all_news():
        return jsonify({'items': get_all_news_items()})

    @app.route('/api/news/featured')
    def get_featured_news():
        config = get_featured_news_config()
        links = config.get('links', [])
        items = get_all_news_items()
        hidden_links = get_hidden_news_links()
        item_map = {item.get('link'): item for item in items if item.get('link') and item.get('link') not in hidden_links}
        featured = [item_map.get(link) for link in links if item_map.get(link)]

        if len(featured) < 3:
            for item in items:
                if item.get('link') in hidden_links:
                    continue
                if item in featured:
                    continue
                featured.append(item)
                if len(featured) >= 3:
                    break

        output = []
        for item in featured[:3]:
            if not item:
                continue
            output.append({
                'link': sanitize_public_link_url(item.get('link', ''), default='#'),
                'image': sanitize_public_media_url(item.get('image', ''), enforce_remote_public=False),
                'date': sanitize_public_date_text(item.get('date', '')),
                'title': sanitize_public_text(item.get('title', ''), max_length=200),
                'desc': sanitize_public_text(item.get('desc', ''), max_length=220),
                'summary': sanitize_public_text(item.get('summary', ''), max_length=220),
                'category': sanitize_public_text(item.get('category', ''), max_length=32),
                'division': sanitize_public_text(item.get('division', ''), max_length=64),
            })
        return jsonify({'items': output})

    @app.route('/api/news/featured', methods=['POST'])
    @login_required
    def update_featured_news():
        data = request.json or {}
        config = save_featured_news_config(data)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/news/list')
    @login_required
    def get_news_list():
        items = get_all_news_items()
        return jsonify({'items': items, 'count': len(items)})

    @app.route('/api/products/related-news')
    def get_product_related_news():
        product_id = (request.args.get('id') or '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': '缂哄皯浜у搧ID'}), 400

        all_items = [item for item in get_all_news_items() if not item.get('hidden')]
        normalized_items = []
        for item in all_items:
            normalized_link = normalize_news_link_for_product(item.get('link', ''))
            if not normalized_link:
                continue
            normalized_items.append({
                'link': sanitize_public_link_url(normalized_link, default='#'),
                'title': sanitize_public_text(item.get('title', ''), max_length=200),
                'image': sanitize_public_media_url(item.get('image', ''), enforce_remote_public=False) or '/assets/images/logo.png',
                'desc': sanitize_public_text(item.get('summary') or item.get('desc') or '', max_length=220),
                '_date': sanitize_public_date_text(item.get('date', '')),
            })

        item_map = {item['link']: item for item in normalized_items}
        settings = _dep('get_product_settings')()
        selected_links = _dep('normalize_related_news_links')((settings.get(product_id) or {}).get('relatedNews', []))

        selected_items = []
        for link in selected_links:
            normalized = normalize_news_link_for_product(link)
            if normalized in item_map:
                selected_items.append(item_map[normalized])

        if selected_items:
            selected_links_set = {item.get('link') for item in selected_items}

            def sort_key(item):
                date_str = str(item.get('_date') or '').strip()
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except Exception:
                    return datetime.min

            latest_pool = sorted(normalized_items, key=sort_key, reverse=True)
            for item in latest_pool:
                if len(selected_items) >= 2:
                    break
                if item.get('link') in selected_links_set:
                    continue
                selected_items.append(item)
                selected_links_set.add(item.get('link'))
            for item in selected_items[:2]:
                item.pop('_date', None)
            return jsonify({'success': True, 'items': selected_items[:2]})

        def sort_key(item):
            date_str = str(item.get('_date') or '').strip()
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except Exception:
                return datetime.min

        latest = sorted(normalized_items, key=sort_key, reverse=True)[:2]
        for item in latest:
            item.pop('_date', None)
        return jsonify({'success': True, 'items': latest})

    @app.route('/api/h2-home/news', methods=['GET'])
    def get_h2_home_news():
        config = _dep('get_h2_home_config')()
        news_configs = config.get('news', [])
        items = get_all_news_items()
        item_map = {item.get('link'): item for item in items if item.get('link')}

        output = []
        used_links = set()
        for news_cfg in news_configs:
            if isinstance(news_cfg, dict):
                link = news_cfg.get('link')
                custom_tag = sanitize_public_text(news_cfg.get('customTag', ''), max_length=24)
                custom_title = sanitize_public_text(news_cfg.get('customTitle', ''), max_length=120)
                custom_desc = sanitize_public_text(news_cfg.get('customDesc', ''), max_length=220)
            else:
                continue

            item = item_map.get(link)
            if not item:
                continue
            used_links.add(link)
            output.append({
                'link': sanitize_public_link_url(item.get('link', ''), default='#'),
                'title': sanitize_public_text(item.get('title', ''), max_length=200),
                'image': sanitize_public_media_url(item.get('image', ''), enforce_remote_public=False),
                'date': sanitize_public_date_text(item.get('date', '')),
                'summary': sanitize_public_text(item.get('summary', ''), max_length=220),
                'customTag': custom_tag,
                'customTitle': custom_title,
                'customDesc': custom_desc,
            })

        if len(output) < 3:
            for item in items:
                if item.get('link') in used_links:
                    continue
                output.append({
                    'link': sanitize_public_link_url(item.get('link', ''), default='#'),
                    'title': sanitize_public_text(item.get('title', ''), max_length=200),
                    'image': sanitize_public_media_url(item.get('image', ''), enforce_remote_public=False),
                    'date': sanitize_public_date_text(item.get('date', '')),
                    'summary': sanitize_public_text(item.get('summary', ''), max_length=220),
                    'customTag': '',
                    'customTitle': '',
                    'customDesc': '',
                })
                if len(output) >= 3:
                    break

        return jsonify({'items': output[:3]})

    @app.route('/api/h2-home/news', methods=['POST'])
    @login_required
    def update_h2_home_news():
        data = request.json or {}
        items = data.get('items', [])
        config = save_h2_home_news(items)
        return jsonify({'success': True, 'config': config})

    @app.route('/api/news/create', methods=['POST'])
    @login_required
    def create_news():
        data = request.json or {}
        title = normalize_news_plain_text(data.get('title', ''), max_length=200)
        date = normalize_news_plain_text(data.get('date', ''), max_length=80)
        category = (data.get('category') or '').strip()
        division = normalize_news_plain_text(data.get('division', ''), max_length=80)
        image_url = sanitize_news_image_url(data.get('image_url', ''))
        summary = normalize_news_plain_text(data.get('summary', ''), max_length=220)
        content = (data.get('content') or '').strip()
        content_is_html = bool(data.get('content_is_html', False))

        if not title or not date or not category or not division or not content:
            return jsonify({'success': False, 'message': '请填写标题、日期、分类、归属事业部和正文'}), 400
        if category not in {'enterprise', 'industry', 'science'}:
            return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

        content_html = content if content_is_html else render_markdown(content)
        content_html = sanitize_news_html_fragment(content_html)
        image_url, summary = derive_news_cover_and_summary(content_html, image_url, summary)
        image_url = sanitize_news_image_url(image_url) or '/assets/images/logo.png'
        summary = normalize_news_plain_text(summary, max_length=220)

        news_dir = _news_dir()
        news_dir.mkdir(parents=True, exist_ok=True)
        news_id = get_next_news_id()
        filename = f'news_show.aspx_id_{news_id}.html'
        filepath = news_dir / filename
        article_html = build_news_article_html(title, date, image_url, content_html)
        filepath.write_text(article_html, encoding='utf-8')

        card_html = build_news_card_html(filename, category, division, image_url, date, title, summary, hidden=False)
        news_index = news_dir / 'news.html'
        inserted = insert_news_card(news_index, card_html)
        if not inserted:
            return jsonify({'success': False, 'message': '宸插垱寤鸿祫璁紝浣嗘湭鑳芥洿鏂?news.html'}), 500

        return jsonify({'success': True, 'filename': filename, 'link': f'/pages/news/{filename}'})

    @app.route('/api/news/visibility', methods=['POST'])
    @login_required
    def update_news_visibility():
        data = request.json or {}
        link = (data.get('link') or '').strip()
        hidden = bool(data.get('hidden'))
        if not link:
            return jsonify({'success': False, 'message': '缂哄皯璧勮閾炬帴'}), 400

        hidden_links = get_hidden_news_links()
        if hidden:
            hidden_links.add(link)
        else:
            hidden_links.discard(link)
        save_hidden_news_links(hidden_links)

        news_index = _news_index_path()
        if news_index.exists():
            content = news_index.read_text(encoding='utf-8')
            filename = Path(link).name
            card_pattern = build_news_card_regex(filename)
            card_match = card_pattern.search(content)
            if card_match:
                card_html = card_match.group(0)
                open_tag_match = re.search(r'<a\b[^>]*>', card_html, re.IGNORECASE)
                if open_tag_match:
                    open_tag = open_tag_match.group(0)
                    if 'data-hidden=' in open_tag:
                        open_tag = re.sub(
                            r'data-hidden\s*=\s*["\'](true|false)["\']',
                            f'data-hidden="{str(hidden).lower()}"',
                            open_tag,
                            flags=re.IGNORECASE,
                        )
                    else:
                        open_tag = open_tag[:-1] + f' data-hidden="{str(hidden).lower()}">'
                    card_html = card_html[:open_tag_match.start()] + open_tag + card_html[open_tag_match.end():]
                    content = content[:card_match.start()] + card_html + content[card_match.end():]
            news_index.write_text(content, encoding='utf-8')

        return jsonify({'success': True})

    @app.route('/api/news/category', methods=['POST'])
    @login_required
    def update_news_category():
        data = request.json or {}
        link = (data.get('link') or '').strip()
        category = (data.get('category') or '').strip()

        if not link:
            return jsonify({'success': False, 'message': '缂哄皯璧勮閾炬帴'}), 400
        if category not in {'enterprise', 'industry', 'science'}:
            return jsonify({'success': False, 'message': '分类不合法'}), 400

        filename = Path(link).name
        news_index = _news_index_path()
        if not news_index.exists():
            return jsonify({'success': False, 'message': 'news.html 不存在'}), 404

        content = news_index.read_text(encoding='utf-8')
        card_pattern = build_news_card_regex(filename)
        card_match = card_pattern.search(content)
        if not card_match:
            return jsonify({'success': False, 'message': '未找到对应资讯卡片'}), 404

        card_html = card_match.group(0)
        open_tag_match = re.search(r'<a\b[^>]*>', card_html, re.IGNORECASE)
        if not open_tag_match:
            return jsonify({'success': False, 'message': '鍗＄墖鏍煎紡寮傚父'}), 500

        open_tag = open_tag_match.group(0)
        if 'data-category=' in open_tag:
            open_tag = re.sub(
                r'data-category\s*=\s*["\'][^"\']*["\']',
                f'data-category="{category}"',
                open_tag,
                flags=re.IGNORECASE,
            )
        else:
            open_tag = open_tag[:-1] + f' data-category="{category}">'

        card_html = card_html[:open_tag_match.start()] + open_tag + card_html[open_tag_match.end():]
        content = content[:card_match.start()] + card_html + content[card_match.end():]
        news_index.write_text(content, encoding='utf-8')
        return jsonify({'success': True})

    @app.route('/api/news/delete', methods=['POST'])
    @login_required
    def delete_news():
        data = request.json or {}
        link = (data.get('link') or '').strip()
        if not link:
            return jsonify({'success': False, 'message': '缂哄皯璧勮閾炬帴'}), 400

        filename = Path(link).name
        news_dir = _news_dir()
        filepath = news_dir / filename
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass

        news_index = news_dir / 'news.html'
        if news_index.exists():
            content = news_index.read_text(encoding='utf-8')
            pattern = build_news_card_regex(filename)
            content, _ = pattern.subn('', content)
            news_index.write_text(content, encoding='utf-8')

        hidden_links = get_hidden_news_links()
        if link in hidden_links:
            hidden_links.discard(link)
            save_hidden_news_links(hidden_links)

        return jsonify({'success': True})

    @app.route('/api/news/update', methods=['POST'])
    @login_required
    def update_news():
        data = request.json or {}
        link = (data.get('link') or '').strip()
        title = normalize_news_plain_text(data.get('title', ''), max_length=200)
        date = normalize_news_plain_text(data.get('date', ''), max_length=80)
        category = (data.get('category') or '').strip()
        division = normalize_news_plain_text(data.get('division', ''), max_length=80)
        image_url = sanitize_news_image_url(data.get('image_url', ''))
        summary = normalize_news_plain_text(data.get('summary', ''), max_length=220)
        content = (data.get('content') or '').strip()
        content_is_html = bool(data.get('content_is_html', False))

        if not link:
            return jsonify({'success': False, 'message': '缂哄皯璧勮閾炬帴'}), 400
        if not title or not date or not category or not division or not content:
            return jsonify({'success': False, 'message': '请填写标题、日期、分类、归属事业部和正文'}), 400
        if category not in {'enterprise', 'industry', 'science'}:
            return jsonify({'success': False, 'message': '请选择正确的资讯分类'}), 400

        content_html = content if content_is_html else render_markdown(content)
        content_html = sanitize_news_html_fragment(content_html)
        image_url, summary = derive_news_cover_and_summary(content_html, image_url, summary)
        image_url = sanitize_news_image_url(image_url) or '/assets/images/logo.png'
        summary = normalize_news_plain_text(summary, max_length=220)

        filename = Path(link).name
        news_dir = _news_dir()
        filepath = news_dir / filename
        if not filepath.exists():
            return jsonify({'success': False, 'message': '资讯文件不存在'}), 404

        article_html = build_news_article_html(title, date, image_url, content_html)
        filepath.write_text(article_html, encoding='utf-8')

        news_index = news_dir / 'news.html'
        if news_index.exists():
            content_text = news_index.read_text(encoding='utf-8')
            card_html = build_news_card_html(filename, category, division, image_url, date, title, summary, hidden=False)
            pattern = build_news_card_regex(filename)
            content_text, count = pattern.subn(card_html, content_text, count=1)
            if count:
                content_text, _ = dedupe_news_cards(content_text, filename)
                news_index.write_text(content_text, encoding='utf-8')
            else:
                insert_news_card(news_index, card_html)

        return jsonify({'success': True, 'link': link})

    @app.route('/api/news/detail')
    @login_required
    def get_news_detail():
        link = request.args.get('link', '').strip()
        if not link:
            return jsonify({'success': False, 'message': '缂哄皯璧勮閾炬帴'}), 400
        filename = Path(link).name
        filepath = _news_dir() / filename
        detail = parse_news_article_html(filepath)
        if not detail:
            return jsonify({'success': False, 'message': '资讯不存在'}), 404
        return jsonify({'success': True, 'detail': detail})

    @app.route('/api/news/preview', methods=['POST'])
    @login_required
    def preview_news_content():
        data = request.json or {}
        content = (data.get('content') or '').strip()
        is_html = bool(data.get('content_is_html', False))
        html_body = content if is_html else render_markdown(content)
        return jsonify({'success': True, 'html': sanitize_news_html_fragment(html_body)})

    @app.route('/api/news/preview-page', methods=['POST'])
    @login_required
    def preview_news_page():
        data = request.json or {}
        title = normalize_news_plain_text(data.get('title', ''), max_length=200) or '标题预览'
        date = normalize_news_plain_text(data.get('date', ''), max_length=80) or now_beijing().strftime('%Y-%m-%d')
        image_url = sanitize_news_image_url(data.get('image_url', ''))
        content = (data.get('content') or '').strip()
        is_html = bool(data.get('content_is_html', False))

        content_html = content if is_html else render_markdown(content)
        content_html = sanitize_news_html_fragment(content_html)
        image_url, _ = derive_news_cover_and_summary(content_html, image_url, '')
        page_html = build_news_article_html(title, date, image_url, content_html)
        resize_bridge = """
<style>
/* Preview-only guard: prevent vh-based feedback loops in iframe auto-height */
html, body {
  min-height: 0 !important;
  height: auto !important;
}
body {
  overflow-x: hidden !important;
}
.article-hero {
  height: clamp(260px, 32vw, 420px) !important;
  min-height: 260px !important;
}
</style>
<div id="__preview_end_marker__" style="height:1px;width:100%;"></div>
<script>
(function () {
  function sendHeight() {
    var marker = document.getElementById('__preview_end_marker__');
    var h = 0;
    if (marker) {
      var rect = marker.getBoundingClientRect();
      h = Math.ceil((window.scrollY || window.pageYOffset || 0) + rect.top + rect.height);
    } else {
      var d = document.documentElement;
      var b = document.body;
      h = Math.max(
        d ? d.scrollHeight : 0,
        b ? b.scrollHeight : 0,
        d ? d.offsetHeight : 0,
        b ? b.offsetHeight : 0
      );
    }
    try { parent.postMessage({ type: 'news-preview-height', height: h }, '*'); } catch (e) {}
  }
  window.addEventListener('load', sendHeight);
  document.addEventListener('DOMContentLoaded', sendHeight);
  window.addEventListener('resize', sendHeight);
  setTimeout(sendHeight, 100);
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1200);
  if (document.images) {
    Array.prototype.forEach.call(document.images, function (img) {
      if (!img.complete) {
        img.addEventListener('load', sendHeight, { once: true });
        img.addEventListener('error', sendHeight, { once: true });
      }
    });
  }
  var mo = new MutationObserver(function () { sendHeight(); });
  mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
})();
</script>
"""
        if '</body>' in page_html:
            page_html = page_html.replace('</body>', resize_bridge + '\n</body>')
        else:
            page_html += resize_bridge
        return jsonify({'success': True, 'page_html': page_html})

    @app.route('/api/news/ai-polish', methods=['POST'])
    @login_required
    def ai_polish_news():
        def extract_visible_text(text: str, is_html: bool, collapse_whitespace: bool) -> str:
            value = text or ''
            if is_html:
                value = re.sub(r'(?is)<script.*?>.*?</script>', '', value)
                value = re.sub(r'(?is)<style.*?>.*?</style>', '', value)
                value = re.sub(r'(?i)<br\\s*/?>', '\n', value)
                value = re.sub(r'(?is)<[^>]+>', '', value)
            value = html.unescape(value)
            value = value.replace('\u00a0', ' ')
            if collapse_whitespace:
                value = re.sub(r'\s+', '', value)
            else:
                value = re.sub(r'\s+', ' ', value).strip()
            return value

        def get_first_diff_hint(before_text: str, after_text: str, window: int = 18):
            n = min(len(before_text), len(after_text))
            idx = 0
            while idx < n and before_text[idx] == after_text[idx]:
                idx += 1
            if idx >= n and len(before_text) == len(after_text):
                return 0, before_text[:window], after_text[:window]
            start = max(0, idx - window)
            end_before = min(len(before_text), idx + window)
            end_after = min(len(after_text), idx + window)
            return idx, before_text[start:end_before], after_text[start:end_after]

        def sanitize_ai_typeset_output(text: str, is_html: bool) -> str:
            value = (text or '').strip()
            if not value:
                return value
            value = re.sub(r'^\s*```(?:html|markdown)?\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'\s*```\s*$', '', value)
            value = re.sub(r'^\s*(?:鏂伴椈鏍囬|鏍囬)\s*[锛?].*?(?:\n|<br\s*/?>)+', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^\s*鎽樿\s*[锛?].*?(?:\n|<br\s*/?>)+', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^\s*姝ｆ枃\s*[锛?]\s*', '', value, flags=re.IGNORECASE)

            if is_html:
                value = re.sub(r'^\s*<p>\s*(?:鏂伴椈鏍囬|鏍囬)\s*[锛?].*?</p>\s*', '', value, flags=re.IGNORECASE | re.DOTALL)
                value = re.sub(r'^\s*<p>\s*鎽樿\s*[锛?].*?</p>\s*', '', value, flags=re.IGNORECASE | re.DOTALL)
                value = re.sub(r'^\s*<p>\s*姝ｆ枃\s*[锛?]\s*</p>\s*', '', value, flags=re.IGNORECASE | re.DOTALL)
            return value.strip()

        config = _dep('get_chatbot_config')()
        if not config.get('enabled', True):
            return jsonify({'success': False, 'message': 'AI 客服暂时不可用'}), 503
        if not config.get('api_key'):
            return jsonify({'success': False, 'message': 'AI 客服未配置'}), 400

        data = request.json or {}
        title = (data.get('title') or '').strip()
        summary = (data.get('summary') or '').strip()
        content = (data.get('content') or '').strip()
        content_is_html = bool(data.get('content_is_html', True))
        if not content:
            return jsonify({'success': False, 'message': '请输入正文内容'}), 400

        output_mode = 'HTML' if content_is_html else 'Markdown'
        system_prompt = (
            "你是一名企业资讯排版助手。你的任务只允许“排版”，不允许“改写”。"
            "必须严格保持输入正文的可见文字完全一致（不得增删改任何字、数字、标点、顺序）。"
            "可以调整段落结构、换行、列表、标题层级、强调样式。"
            f"输出格式必须是 {output_mode}。只输出排版后的正文片段本身。"
            "禁止输出“标题：”“摘要：”“正文：”等前缀，禁止输出解释。"
        )
        user_prompt = (
            f"上下文（仅供理解，不得输出）：标题={title}；摘要={summary}\n"
            f"待排版正文（仅此内容可输出）：\n{content}\n\n"
            f"请仅做排版并输出正文片段（{output_mode}）。"
        )
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        response, error = _dep('call_openai_api')(messages, stream=False)
        if error:
            return jsonify({'success': False, 'message': error}), 500

        response = sanitize_ai_typeset_output(response or '', content_is_html)
        if content_is_html:
            response = sanitize_news_html_fragment(response or '')

        before_norm = extract_visible_text(content, content_is_html, collapse_whitespace=True)
        after_norm = extract_visible_text(response or '', content_is_html, collapse_whitespace=True)
        if before_norm != after_norm:
            before_human = extract_visible_text(content, content_is_html, collapse_whitespace=False)
            after_human = extract_visible_text(response or '', content_is_html, collapse_whitespace=False)
            diff_index, before_excerpt, after_excerpt = get_first_diff_hint(before_human, after_human)
            return jsonify({
                'success': True,
                'content': response or content,
                'changed_text': True,
                'warning': '检测到 AI 可能改写了部分正文，已直接替换。你可以使用“撤销替换”恢复。',
                'diff_index': diff_index,
                'before_excerpt': before_excerpt,
                'after_excerpt': after_excerpt,
            })

        return jsonify({'success': True, 'content': response, 'changed_text': False})

    @app.route('/api/news/import/feishu', methods=['POST'])
    @login_required
    def import_news_from_feishu_share():
        def log_import_failure(reason: str, **details):
            parts = [f"reason={reason}"]
            for key, value in details.items():
                if value in (None, '', b''):
                    continue
                parts.append(f"{key}={value!r}")
            app.logger.warning("news feishu import failed | %s", ' | '.join(parts))

        data = request.json or {}
        source_url = (data.get('url') or '').strip()
        if not source_url:
            log_import_failure('missing_url')
            return jsonify({'success': False, 'message': '请输入飞书分享链接'}), 400

        try:
            parsed = urlparse(source_url)
        except Exception:
            parsed = None
        hostname = str((parsed.hostname if parsed else '') or '').strip().lower()
        if not is_feishu_like_hostname(hostname):
            log_import_failure('unsupported_host', source_url=source_url, hostname=hostname)
            return jsonify({'success': False, 'message': '目前仅支持飞书分享链接导入'}), 400

        try:
            fetched = fetch_remote_url_content(
                source_url,
                allow_redirects=True,
                timeout=25.0,
                headers=REMOTE_BROWSER_HEADERS,
            )
        except RemoteFetchError as exc:
            log_import_failure(exc.reason, source_url=source_url, **exc.details)
            status_code = 500 if exc.reason == 'no_http_client_dependency' else 400
            return jsonify({'success': False, 'message': exc.message}), status_code

        final_url = str(fetched.get('final_url') or source_url).strip()
        ok, reason, _safe_final_url = _dep('validate_safe_remote_fetch_url')(final_url)
        final_hostname = str(urlparse(final_url).hostname or '').strip().lower()
        if not ok or not is_feishu_like_hostname(final_hostname):
            log_import_failure(
                'unsafe_final_url',
                source_url=source_url,
                final_url=final_url,
                message=reason,
            )
            return jsonify({'success': False, 'message': '分享链接重定向到了不受支持的地址'}), 400

        page_html = str(fetched.get('text') or '')
        if not page_html.strip():
            page_html = (fetched.get('content') or b'').decode('utf-8', errors='replace')
        if not page_html.strip():
            log_import_failure('empty_page', source_url=source_url, final_url=final_url)
            return jsonify({'success': False, 'message': '飞书分享页内容为空'}), 400
        if is_feishu_login_page_html(page_html):
            log_import_failure(
                'login_page_returned',
                source_url=source_url,
                final_url=final_url,
                page_title=extract_html_title_text(page_html),
            )
            return jsonify({
                'success': False,
                'message': '该飞书链接当前返回的是登录页，不是文档正文。通常是未开启公开分享，或必须登录飞书后才能访问；请把分享权限改为可直接访问后重试。',
            }), 400

        root_fragment = extract_first_html_element_by_attr(
            page_html,
            tag_name='div',
            attr_name='data-lark-html-role',
            attr_value='root',
        )
        if not root_fragment:
            root_fragment = extract_first_html_element_by_attr(
                page_html,
                tag_name='div',
                attr_name='data-docx-has-block-data',
                attr_value='true',
            )
        client_vars_payload = extract_feishu_client_vars_payload(page_html)
        if not root_fragment and not client_vars_payload:
            log_import_failure('root_fragment_not_found', source_url=source_url, final_url=final_url)
            return jsonify({
                'success': False,
                'message': '未在分享页中解析到正文，请确认该飞书链接已开启分享且页面可直接访问',
            }), 400

        try:
            if root_fragment:
                imported = convert_feishu_root_fragment_to_news_payload(
                    root_fragment,
                    page_url=final_url,
                    page_title=extract_html_title_text(page_html),
                )
            else:
                imported = convert_feishu_client_vars_payload_to_news_payload(
                    client_vars_payload or {},
                    page_url=final_url,
                    page_title=extract_html_title_text(page_html),
                    page_html=page_html,
                )
        except Exception as exc:
            log_import_failure(
                'parse_failed',
                source_url=source_url,
                final_url=final_url,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return jsonify({'success': False, 'message': '飞书正文解析失败，请检查链接后重试'}), 400

        content_html = str(imported.get('content_html') or '').strip()
        if not content_html:
            log_import_failure('empty_content_html', source_url=source_url, final_url=final_url)
            return jsonify({'success': False, 'message': '未解析到可用正文内容'}), 400

        image_url, summary = derive_news_cover_and_summary(content_html, '', '')
        image_url = sanitize_news_image_url(image_url) or '/assets/images/logo.png'
        summary = normalize_news_plain_text(summary, max_length=220)

        imported_image_count = int(imported.get('imported_image_count') or 0)
        image_failed_count = int(imported.get('image_failed_count') or 0)
        image_seen_count = int(imported.get('image_seen_count') or 0)
        warnings = [str(item) for item in (imported.get('warnings') or []) if str(item).strip()]

        if image_seen_count > 0:
            message = f'导入完成，成功转存 {imported_image_count} 张图片'
        else:
            message = '导入完成'
        if image_failed_count > 0:
            message += f'，另有 {image_failed_count} 张图片未成功转存'

        return jsonify({
            'success': True,
            'message': message,
            'source_url': final_url,
            'title': normalize_news_plain_text(imported.get('title', ''), max_length=200),
            'date': normalize_news_plain_text(imported.get('date', ''), max_length=80),
            'category': 'enterprise',
            'image_url': image_url,
            'summary': summary,
            'content_html': content_html,
            'imported_image_count': imported_image_count,
            'image_failed_count': image_failed_count,
            'image_seen_count': image_seen_count,
            'warnings': warnings,
        })

    @app.route('/api/news/image/import', methods=['POST'])
    @login_required
    def import_news_image_from_url():
        def log_import_failure(reason: str, **details):
            parts = [f"reason={reason}"]
            for key, value in details.items():
                if value in (None, '', b''):
                    continue
                parts.append(f"{key}={value!r}")
            app.logger.warning("news image import failed | %s", ' | '.join(parts))

        data = request.json or {}
        source_url = (data.get('url') or '').strip()
        if not source_url:
            log_import_failure('missing_url')
            return jsonify({'success': False, 'message': '缂哄皯鍥剧墖閾炬帴'}), 400
        ok, reason, safe_source_url = _dep('validate_safe_remote_fetch_url')(source_url)
        if not ok:
            log_import_failure(
                'validate_safe_remote_fetch_url',
                source_url=source_url,
                safe_source_url=safe_source_url,
                message=reason,
            )
            return jsonify({'success': False, 'message': reason}), 400

        parsed = urlparse(safe_source_url)
        content_type = ''
        content = b''

        try:
            if _dep('requests_support'):
                resp = _dep('requests_module').get(safe_source_url, timeout=20, allow_redirects=False)
                if 300 <= resp.status_code < 400:
                    log_import_failure(
                        'redirect_not_supported',
                        source_url=source_url,
                        safe_source_url=safe_source_url,
                        status_code=resp.status_code,
                        location=resp.headers.get('Location', ''),
                    )
                    return jsonify({'success': False, 'message': '鍥剧墖閾炬帴涓嶆敮鎸侀噸瀹氬悜锛岃浣跨敤鏈€缁堝湴鍧€'}), 400
                resp.raise_for_status()
                content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                content = resp.content or b''
            elif _dep('httpx_support'):
                resp = _dep('httpx_module').get(safe_source_url, timeout=20.0, follow_redirects=False)
                if 300 <= resp.status_code < 400:
                    log_import_failure(
                        'redirect_not_supported',
                        source_url=source_url,
                        safe_source_url=safe_source_url,
                        status_code=resp.status_code,
                        location=resp.headers.get('Location', ''),
                    )
                    return jsonify({'success': False, 'message': '鍥剧墖閾炬帴涓嶆敮鎸侀噸瀹氬悜锛岃浣跨敤鏈€缁堝湴鍧€'}), 400
                resp.raise_for_status()
                content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                content = resp.content or b''
            else:
                log_import_failure(
                    'no_http_client_dependency',
                    source_url=source_url,
                    safe_source_url=safe_source_url,
                )
                return jsonify({'success': False, 'message': '鏈嶅姟绔己灏戜笅杞藉鎴风渚濊禆'}), 500
        except Exception as exc:
            log_import_failure(
                'download_failed',
                source_url=source_url,
                safe_source_url=safe_source_url,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return jsonify({'success': False, 'message': '鍥剧墖涓嬭浇澶辫触锛岃妫€鏌ラ摼鎺ユ槸鍚﹀彲璁块棶'}), 400

        if len(content) == 0:
            log_import_failure(
                'empty_content',
                source_url=source_url,
                safe_source_url=safe_source_url,
                content_type=content_type,
            )
            return jsonify({'success': False, 'message': '鍥剧墖鍐呭涓虹┖'}), 400
        if len(content) > 15 * 1024 * 1024:
            log_import_failure(
                'image_too_large',
                source_url=source_url,
                safe_source_url=safe_source_url,
                content_type=content_type,
                content_length=len(content),
            )
            return jsonify({'success': False, 'message': '图片过大（最大 15MB）'}), 400

        ext = _dep('validate_image_bytes')(
            str(parsed.path or ''),
            content_type,
            content,
            allowed_extensions=_dep('allowed_news_image_extensions'),
        )
        if ext not in _dep('allowed_news_image_extensions'):
            log_import_failure(
                'unsupported_image_format',
                source_url=source_url,
                safe_source_url=safe_source_url,
                content_type=content_type,
                content_length=len(content),
                parsed_path=str(parsed.path or ''),
                detected_ext=ext,
            )
            return jsonify({'success': False, 'message': '閾炬帴鍐呭涓嶆槸鍙楁敮鎸佺殑鍥剧墖鏍煎紡'}), 400

        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = _dep('news_uploads_dir') / filename
        file_path.write_bytes(content)
        return jsonify({'success': True, 'url': build_news_asset_url(filename)})

    @app.route('/api/news/image/upload', methods=['POST'])
    @login_required
    def upload_news_image_file():
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '娌℃湁涓婁紶鏂囦欢'}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        ext = _dep('validate_uploaded_image_extension')(file, allowed_extensions=_dep('allowed_news_image_extensions'))
        if not ext:
            return jsonify({'success': False, 'message': '浠呮敮鎸?PNG/JPG/JPEG/WEBP/GIF'}), 400

        saved_name = f"{uuid.uuid4().hex}{ext}"
        save_path = _dep('news_uploads_dir') / saved_name
        file.save(str(save_path))

        if save_path.stat().st_size > 15 * 1024 * 1024:
            try:
                save_path.unlink()
            except Exception:
                pass
            return jsonify({'success': False, 'message': '图片过大（最大 15MB）'}), 400

        return jsonify({'success': True, 'url': build_news_asset_url(saved_name)})

    @app.route('/media/news/<path:filename>')
    def serve_news_media(filename):
        resolved = resolve_news_asset_file(filename)
        if resolved is None:
            return jsonify({'success': False, 'message': '图片不存在'}), 404
        response = send_from_directory(str(resolved.parent), resolved.name)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

