"""Canonical public URL helpers shared by navigation, SEO and sitemaps."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


LEGACY_PUBLIC_REDIRECTS = {
    '/pages/biosensing/index_page_2.html': '/pages/biosensing/',
    '/pages/careers/job-detail.html': '/pages/careers/jobs.html',
    '/pages/contact/feedback.aspx_attach_id.html': '/pages/contact/feedback.html',
    '/pages/about/history.html': '/pages/about/about.html',
    '/pages/about/culture.html': '/pages/about/values.html',
    '/pages/about/micro-nano.html': '/pages/research/micro-nano.html',
    '/pages/about/research.html': '/pages/research/cooperation.html',
    '/pages/services/service.html': '/pages/research/',
    '/pages/services/core-service.html': '/pages/research/development.html',
    '/pages/honors/honor.html': '/pages/gassensing/service-cases.html',
    '/pages/honors/honor-page2.html': '/pages/gassensing/service-cases.html',
    '/pages/news/news_show.aspx_id_75.html': '/pages/news/news_show.aspx_id_76.html',
    '/pages/news/news_show.aspx_id_50.html': '/pages/news/news_show.aspx_id_47.html',
    '/pages/news/news_show.aspx_id_32.html': '/pages/news/news.html#industry',
    '/pages/products/index.html': '/pages/gassensing/all-products.html',
    '/pages/products/gas_sensors.html': '/pages/gassensing/all-products.html',
    '/pages/gas_sensors.html': '/pages/gassensing/all-products.html',
    '/pages/products/products_mems.html': '/pages/research/micro-nano.html',
    '/pages/products/carbon_bio_platform.html': '/pages/biosensing/carbon_bio_platform.html',
    '/pages/products/respiratory_virus_chip.html': '/pages/biosensing/respiratory_virus_chip.html',
    '/pages/products/igzo_device.html': '/pages/biosensing/igzo_device.html',
    '/pages/solutions/jjfa.html': '/pages/solutions/solutions-index.html',
    '/pages/news/news.aspx_category_id_43.html': '/pages/news/news.html#science',
    '/pages/news/news.aspx_category_id_9.html': '/pages/news/news.html#enterprise',
    '/pages/news/news.aspx_category_id_8.html': '/pages/news/news.html#industry',
    '/pages/news/index.html': '/pages/news/news.html',
    '/pages/honors/honor.aspx@category_id=0&page=2.html': '/pages/gassensing/service-cases.html',
}


def canonicalize_public_path(path_value: str) -> str:
    """Return the final public path for known aliases and directory indexes."""
    path = str(path_value or '').strip()
    if not path.startswith('/') or path.startswith('//'):
        return path

    redirect_target = LEGACY_PUBLIC_REDIRECTS.get(path)
    if redirect_target:
        return urlsplit(redirect_target).path or '/'
    if path == '/index.html':
        return '/'
    if path.startswith('/pages/') and path.endswith('/index.html'):
        return path[:-len('index.html')]
    return path


def canonicalize_public_url(value: str, *, resolve_page_relative: bool = False) -> str:
    """Normalize an internal public URL while preserving query and fragment."""
    raw = str(value or '').strip()
    if not raw or raw.startswith(('#', '//')):
        return raw

    lowered = raw.lower()
    if lowered.startswith(('http://', 'https://', 'mailto:', 'tel:', 'javascript:', 'data:', 'blob:')):
        return raw

    if resolve_page_relative and not raw.startswith('/'):
        clean = raw.replace('\\', '/')
        while clean.startswith('./'):
            clean = clean[2:]
        while clean.startswith('../'):
            clean = clean[3:]
        if clean.startswith('pages/'):
            raw = '/' + clean
        elif clean.startswith(('gassensing/', 'biosensing/', 'measurement/', 'solutions/', 'research/', 'customization/')):
            raw = '/pages/' + clean

    parsed = urlsplit(raw)
    if not parsed.path.startswith('/'):
        return raw

    redirect_target = LEGACY_PUBLIC_REDIRECTS.get(parsed.path)
    if redirect_target:
        target = urlsplit(redirect_target)
        path = target.path or '/'
        fragment = target.fragment or parsed.fragment
    else:
        path = canonicalize_public_path(parsed.path)
        fragment = parsed.fragment

    return urlunsplit(('', '', path, parsed.query, fragment))


def is_legacy_public_path(path_value: str) -> bool:
    return str(path_value or '').strip() in LEGACY_PUBLIC_REDIRECTS


__all__ = [
    'LEGACY_PUBLIC_REDIRECTS',
    'canonicalize_public_path',
    'canonicalize_public_url',
    'is_legacy_public_path',
]
