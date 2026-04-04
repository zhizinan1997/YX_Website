"""公开输出内容清洗辅助模块。"""

from __future__ import annotations

import re
import uuid

from app.request_security import validate_safe_remote_fetch_url
from app.routes.news_content import (
    normalize_news_plain_text,
    sanitize_news_image_url,
    sanitize_news_link_url,
)
from app.routes.product_settings import _normalize_related_news_links


def sanitize_public_text(value: str, *, max_length: int = 0) -> str:
    return normalize_news_plain_text(value, max_length=max_length)


def sanitize_public_date_text(value: str, *, max_length: int = 32) -> str:
    return normalize_news_plain_text(value, max_length=max_length)


def sanitize_public_link_url(raw_url: str, *, enforce_remote_public: bool = False, default: str = '') -> str:
    safe_url = sanitize_news_link_url(raw_url)
    if not safe_url:
        return default
    if enforce_remote_public and re.match(r'^https?://', safe_url, re.I):
        ok, _, normalized = validate_safe_remote_fetch_url(safe_url)
        if not ok:
            return default
        return normalized
    return safe_url


def sanitize_public_media_url(raw_url: str, *, enforce_remote_public: bool = False, default: str = '') -> str:
    safe_url = sanitize_news_image_url(raw_url)
    if not safe_url:
        return default
    if enforce_remote_public and re.match(r'^https?://', safe_url, re.I):
        ok, _, normalized = validate_safe_remote_fetch_url(safe_url)
        if not ok:
            return default
        return normalized
    return safe_url


def sanitize_public_product_settings(settings):
    raw = settings if isinstance(settings, dict) else {}
    cleaned = {}
    for product_id, cfg in raw.items():
        pid = str(product_id or '').strip()
        if not pid or not isinstance(cfg, dict):
            continue
        item = {}
        if 'displayName' in cfg:
            item['displayName'] = sanitize_public_text(cfg.get('displayName', ''), max_length=120)
        if 'isNew' in cfg:
            item['isNew'] = bool(cfg.get('isNew', False))
        if 'hidden' in cfg:
            item['hidden'] = bool(cfg.get('hidden', False))
        if 'sortOrder' in cfg:
            try:
                item['sortOrder'] = int(cfg.get('sortOrder', 999))
            except Exception:
                item['sortOrder'] = 999
        if 'cardTitle' in cfg:
            item['cardTitle'] = sanitize_public_text(cfg.get('cardTitle', ''), max_length=120)
        if 'cardImage' in cfg:
            item['cardImage'] = sanitize_public_media_url(
                cfg.get('cardImage', ''),
                enforce_remote_public=False,
            )
        if 'cardSummary' in cfg:
            item['cardSummary'] = sanitize_public_text(cfg.get('cardSummary', ''), max_length=220)
        if 'categories' in cfg:
            values = cfg.get('categories', [])
            if not isinstance(values, list):
                values = [values]
            item['categories'] = [str(v or '').strip() for v in values if str(v or '').strip()]
        if 'industryCategories' in cfg:
            values = cfg.get('industryCategories', [])
            if not isinstance(values, list):
                values = [values]
            item['industryCategories'] = [str(v or '').strip() for v in values if str(v or '').strip()]
        if 'relatedNews' in cfg:
            item['relatedNews'] = _normalize_related_news_links(cfg.get('relatedNews', []))
        cleaned[pid] = item
    return cleaned


def sanitize_public_partner_items(items):
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = sanitize_public_media_url(item.get('url', ''), enforce_remote_public=False)
        if not url:
            continue
        cleaned.append({
            'id': str(item.get('id') or uuid.uuid4().hex),
            'url': url,
            'source': 'upload' if str(item.get('source') or '').lower() == 'upload' else 'url',
        })
    return cleaned
