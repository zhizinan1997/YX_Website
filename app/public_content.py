"""
公开输出内容清洗辅助模块。

本模块负责对公开显示的内容进行安全清洗，防止XSS攻击和恶意内容注入。
所有面向用户的内容输出都必须经过本模块处理。

主要功能：
1. 文本清洗（sanitize_public_text）
   - 纯文本内容的安全处理
   - 可选的最大长度限制
   - 移除所有HTML标签和特殊字符

2. 日期文本清洗（sanitize_public_date_text）
   - 日期显示内容的安全处理
   - 限制最大长度（默认32字符）
   - 防止恶意内容注入

3. 链接URL清洗（sanitize_public_link_url）
   - 验证链接URL的合法性
   - 可选强制远程公网地址验证
   - 防止javascript:伪协议攻击
   - 空链接返回默认值

4. 媒体URL清洗（sanitize_public_media_url）
   - 图片、视频等媒体URL的安全处理
   - 可选强制远程公网地址验证
   - 支持相对路径和绝对路径

5. 产品设置清洗（sanitize_public_product_settings）
   - 产品展示配置的全面清洗
   - 支持的配置项：
     * displayName: 显示名称
     * isNew: 新品标识
     * hidden: 隐藏标识
     * sortOrder: 排序权重
     * cardTitle: 卡片标题
     * cardImage: 卡片图片
     * cardSummary: 卡片摘要
     * categories: 产品分类
     * industryCategories: 行业分类
     * relatedNews: 相关新闻

6. 合作伙伴数据清洗（sanitize_public_partner_items）
   - 合作伙伴Logo的URL清洗
   - 生成唯一标识符
   - 标记图片来源（上传或URL）

安全特性：
- 默认拒绝所有javascript:伪协议
- 强制验证远程URL的公网可达性
- 移除潜在的危险字符和标签
- 长度限制防止缓冲区溢出

使用场景：
- 首页展示内容
- 产品详情页
- 新闻文章
- 合作伙伴展示

作者：元芯传感技术团队
"""

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
        for field, max_length in {
            'seoTitle': 180,
            'seoDescription': 320,
            'sku': 120,
            'brand': 120,
            'manufacturer': 180,
            'seoCategory': 120,
            'imageAlt': 220,
            'imageTitle': 220,
            'imageCaption': 320,
        }.items():
            if field in cfg:
                item[field] = sanitize_public_text(cfg.get(field, ''), max_length=max_length)
        if 'indexable' in cfg:
            item['indexable'] = bool(cfg.get('indexable', True))
        if 'technicalProperties' in cfg:
            properties = []
            for prop in cfg.get('technicalProperties', []) if isinstance(cfg.get('technicalProperties'), list) else []:
                if not isinstance(prop, dict):
                    continue
                name = sanitize_public_text(prop.get('name', ''), max_length=120)
                value = sanitize_public_text(prop.get('value', ''), max_length=220)
                if name and value:
                    properties.append({'name': name, 'value': value})
                if len(properties) >= 40:
                    break
            item['technicalProperties'] = properties
        cleaned[pid] = item
    if 'consultButton' in raw:
        cleaned['consultButton'] = raw['consultButton']
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
