#!/usr/bin/env python3
"""Initialize SEO fields for existing product settings without overwriting edits."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANY = '湖南元芯传感科技有限责任公司'
BRAND = '元芯传感'


def clean_markup(value: str) -> str:
    value = re.sub(r'(?is)<(script|style|svg).*?>.*?</\1>', ' ', str(value or ''))
    value = re.sub(r'(?is)<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()


def first_match(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.I | re.S)
    return clean_markup(match.group(1)) if match else ''


def truncate(value: str, limit: int) -> str:
    value = re.sub(r'\s+', ' ', str(value or '')).strip(' ，。；;')
    return value if len(value) <= limit else value[:limit].rstrip(' ，。；;')


def infer_sku(name: str, stem: str, source: str) -> str:
    model_value = first_match(source, r'(?is)(?:产品型号|型号)\s*</(?:th|td)>\s*<td\b[^>]*>(.*?)</td>')
    if model_value:
        return re.sub(r'[_ ]+', '-', model_value.upper()).replace('–', '-').replace('—', '-')
    candidates = re.findall(r'(?i)\b(?:MC|MCS|YX)[-–—_ ]?[A-Z0-9]+(?:[-–—_./][A-Z0-9]+)*(?![A-Za-z0-9])', name)
    if candidates:
        return re.sub(r'[_ ]+', '-', candidates[0].upper()).replace('–', '-').replace('—', '-')
    if re.match(r'(?i)^(?:mc|mcs|yx)[_-]', stem):
        return stem.replace('_', '-').upper()
    return stem.replace('_', '-').upper()


def category_label(name: str, fallback: str) -> str:
    for token, label in (
        ('芯片', '生物传感芯片'), ('工作站', '生物传感工作站'), ('平台', '传感平台'),
        ('报警器', '气体报警器'), ('检漏仪', '气体检漏仪'), ('检测仪', '气体检测仪'),
        ('分析仪', '气体分析仪'), ('配气', '动态配气系统'), ('模块', '传感检测模块'),
        ('探头', '气体检测探头'), ('传感器', '传感器'), ('器件', '半导体器件'),
    ):
        if token in name:
            return label
    return {'detector': '气体检测仪', 'alarm': '气体报警器', 'sensor': '传感器', 'system': '检测系统', 'service': '定制服务'}.get(fallback, '传感产品')


def extract_description(source: str, name: str, category: str) -> str:
    existing = first_match(source, r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)')
    candidates = [existing]
    for match in re.finditer(r'(?is)<p\b[^>]*>(.*?)</p>', source):
        text = clean_markup(match.group(1))
        if len(text) >= 28 and not any(x in text for x in ('版权所有', '联系我们', 'ICP备')):
            candidates.append(text)
    base = next((text for text in candidates if len(text) >= 28), '')
    if not base:
        base = f'{name}面向工业检测、科研与安全监测场景，提供可靠的{category}能力和产品技术支持。'
    if name not in base:
        base = f'{name}，{base}'
    return truncate(base, 155).rstrip('。') + '。'


def extract_properties(source: str) -> list[dict]:
    properties = []
    patterns = (
        r'(?is)<tr\b[^>]*>\s*<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>\s*<td\b[^>]*>(.*?)</td>',
        r'(?is)<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>',
    )
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            name, value = clean_markup(match.group(1)), clean_markup(match.group(2))
            if not name or not value or len(name) > 50 or len(value) > 180:
                continue
            key = (name, value)
            if key in seen:
                continue
            seen.add(key)
            properties.append({'name': name, 'value': value})
            if len(properties) >= 20:
                return properties
    return properties


def build_item(path: Path, product_id: str) -> dict:
    source = path.read_text(encoding='utf-8', errors='ignore')
    title = first_match(source, r'<title\b[^>]*>(.*?)</title>')
    name = first_match(source, r'<h1\b[^>]*>(.*?)</h1>') or re.sub(r'\s*[-_|].*$', '', title).strip()
    sku = infer_sku(name, path.stem, source)
    if name.upper().startswith('WC-') and sku.upper().startswith('MC-'):
        name = 'MC-' + name[3:]
    category_key = first_match(source, r'<meta[^>]+name=["\']product-category["\'][^>]+content=["\']([^"\']+)')
    category = category_label(name, category_key)
    keyword = ''
    for candidate in ('氢气泄漏检测', '氢气检测', '气体检测', '生物传感', '工业安全监测', '科研检测'):
        if candidate in clean_markup(source):
            keyword = candidate
            break
    seo_title = f'{name}｜{keyword or category} - {BRAND}'
    if len(seo_title) > 70:
        seo_title = f'{name} - {BRAND}'
    description = extract_description(source, name, category)
    alt = f'{name}{category}' if category not in name else name
    return {
        'seoTitle': truncate(seo_title, 70),
        'seoDescription': description,
        'sku': sku,
        'brand': BRAND,
        'manufacturer': COMPANY,
        'seoCategory': category,
        'imageAlt': truncate(alt, 120),
        'imageTitle': truncate(name, 120),
        'imageCaption': truncate(description, 220),
        'indexable': True,
        'technicalProperties': extract_properties(source),
    }


def collect() -> tuple[dict, dict]:
    gas = {}
    for directory, prefix, excluded in (
        (ROOT / 'pages/gassensing', '', {'index.html', 'all-products.html', 'online-store.html', 'service-cases.html', 'mc_mgm_01_new.html'}),
        (ROOT / 'pages/customization', '../customization/', {'index.html'}),
    ):
        for path in sorted(directory.glob('*.html')):
            if path.name in excluded:
                continue
            gas[f'{prefix}{path.stem}'] = build_item(path, f'{prefix}{path.stem}')
    bio = {}
    for path in sorted((ROOT / 'pages/biosensing').glob('*.html')):
        if path.name in {'index.html', 'index_page_2.html'}:
            continue
        product_id = f'../biosensing/{path.stem}'
        bio[product_id] = build_item(path, product_id)
    return gas, bio


def merge_file(path: Path, generated: dict, *, write: bool, force: bool = False) -> dict:
    current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    initialized = 0
    preserved = 0
    for product_id, fields in generated.items():
        config = current.setdefault(product_id, {})
        for field, value in fields.items():
            if not force and field in config and config[field] not in ('', None, []):
                preserved += 1
                continue
            config[field] = value
            initialized += 1
    if write:
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'products': len(generated), 'initialized_fields': initialized, 'preserved_fields': preserved}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='write generated values to data files')
    parser.add_argument('--force', action='store_true', help='replace SEO fields for scanned products')
    args = parser.parse_args()
    gas, bio = collect()
    report = {
        'gas': merge_file(ROOT / 'data/product_settings.json', gas, write=args.write, force=args.force),
        'bio': merge_file(ROOT / 'data/bio_product_settings.json', bio, write=args.write, force=args.force),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
