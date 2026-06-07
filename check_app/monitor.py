from __future__ import annotations

import time
import os
from urllib.parse import urlparse

from .time_utils import iso_now


RESOURCE_CAPTURE_GRACE_MS = int(os.environ.get("CHECK_RESOURCE_CAPTURE_GRACE_MS", "1200"))
RENDER_SIGNAL_TIMEOUT_MS = int(os.environ.get("CHECK_RENDER_SIGNAL_TIMEOUT_MS", "3500"))

CRITICAL_SAME_ORIGIN_RESOURCE_TYPES = {
    "document",
    "stylesheet",
    "script",
}


def same_origin(url: str, target_url: str) -> bool:
    try:
        parsed = urlparse(url)
        target = urlparse(target_url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.scheme == target.scheme and parsed.netloc.lower() == target.netloc.lower()


def classify_result(
    *,
    document_failed: bool,
    render_ok: bool,
    same_origin_resource_failed: int,
    console_error_count: int,
) -> str:
    if document_failed:
        return "down"
    if not render_ok or same_origin_resource_failed > 0:
        return "degraded"
    return "ok"


def is_critical_same_origin_failure(item: dict) -> bool:
    return bool(
        item.get("same_origin")
        and item.get("kind") in CRITICAL_SAME_ORIGIN_RESOURCE_TYPES
        and item.get("status") != "ok"
    )


def _safe_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except Exception:
        return None


def choose_display_latency(
    *,
    first_success_latency_ms: int | None,
    main_document_latency_ms: int | None,
    dom_content_ms: int | None,
    fallback_latency_ms: int | None,
) -> int | None:
    for value in (first_success_latency_ms, main_document_latency_ms, dom_content_ms, fallback_latency_ms):
        safe_value = _safe_int(value)
        if safe_value is not None:
            return safe_value
    return None


def _build_failure_result(url: str, started_at: str, error: str) -> dict:
    finished_at = iso_now()
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "down",
        "http_status": None,
        "latency_ms": None,
        "dom_content_ms": None,
        "load_ms": None,
        "resource_total": 0,
        "resource_failed": 0,
        "console_error_count": 0,
        "render_ok": False,
        "error_summary": error,
        "resources": [
            {
                "url": url,
                "kind": "document",
                "status": "failed",
                "http_status": None,
                "latency_ms": None,
                "same_origin": True,
                "error": error,
            }
        ],
    }


def check_url(url: str, *, timeout_ms: int = 25000) -> dict:
    started_at = iso_now()
    start_perf = time.perf_counter()
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _build_failure_result(url, started_at, "浏览器检测组件不可用")

    resources: list[dict] = []
    request_starts: dict[str, float] = {}
    document_failed = False
    document_error = ""
    navigation_timed_out = False
    http_status = None
    dom_content_ms = None
    load_ms = None
    render_ok = False
    first_success_latency_ms = None
    main_document_latency_ms = None
    collecting_requests = True

    def request_key(request) -> str:
        return f"{id(request)}:{getattr(request, 'url', '')}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (compatible; MetachipCheck/1.0; +https://check.hnmetachip.cn) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                ),
            )
            page = context.new_page()

            def on_request(request):
                request_starts[request_key(request)] = time.perf_counter()

            def on_response(response):
                nonlocal document_failed, document_error, http_status, first_success_latency_ms, main_document_latency_ms
                if not collecting_requests:
                    return
                req = response.request
                key = request_key(req)
                elapsed = _safe_int((time.perf_counter() - request_starts.get(key, time.perf_counter())) * 1000)
                item_url = response.url
                is_same = same_origin(item_url, url)
                kind = req.resource_type
                status_code = response.status
                try:
                    is_main_document = bool(kind == "document" and req.is_navigation_request() and req.frame == page.main_frame)
                except Exception:
                    is_main_document = False
                if is_same and status_code < 400 and first_success_latency_ms is None:
                    first_success_latency_ms = elapsed
                if is_main_document:
                    http_status = status_code
                    main_document_latency_ms = elapsed
                    if status_code >= 400:
                        document_failed = True
                        document_error = f"主文档响应状态码 {status_code}"
                item_status = "ok" if status_code < 400 else "failed"
                resources.append(
                    {
                        "url": item_url,
                        "kind": kind,
                        "status": item_status,
                        "http_status": status_code,
                        "latency_ms": elapsed,
                        "same_origin": is_same,
                        "error": "" if item_status == "ok" else f"响应状态码 {status_code}",
                    }
                )

            def on_request_failed(request):
                if not collecting_requests:
                    return
                key = request_key(request)
                elapsed = _safe_int((time.perf_counter() - request_starts.get(key, time.perf_counter())) * 1000)
                failure = request.failure or {}
                resources.append(
                    {
                        "url": request.url,
                        "kind": request.resource_type,
                        "status": "failed",
                        "http_status": None,
                        "latency_ms": elapsed,
                        "same_origin": same_origin(request.url, url),
                        "error": "请求失败",
                    }
                )

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_request_failed)

            try:
                try:
                    response = page.goto(url, wait_until="commit", timeout=timeout_ms)
                except PlaywrightError as exc:
                    if "commit" not in str(exc):
                        raise
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response is not None:
                    http_status = response.status
                    document_failed = http_status >= 400
                    if main_document_latency_ms is None:
                        main_document_latency_ms = _safe_int((time.perf_counter() - start_perf) * 1000)
                    if document_failed:
                        document_error = f"主文档响应状态码 {http_status}"
                post_response_start = time.perf_counter()
                try:
                    page.wait_for_function(
                        """() => {
                            const bodyText = (document.body && document.body.innerText || '').trim();
                            return Boolean(document.title || bodyText.length > 80);
                        }""",
                        timeout=min(RENDER_SIGNAL_TIMEOUT_MS, timeout_ms),
                    )
                except PlaywrightTimeoutError:
                    pass
                elapsed_after_response = _safe_int((time.perf_counter() - post_response_start) * 1000) or 0
                remaining_capture_ms = min(RESOURCE_CAPTURE_GRACE_MS, timeout_ms) - elapsed_after_response
                if remaining_capture_ms > 0:
                    page.wait_for_timeout(remaining_capture_ms)
            except PlaywrightTimeoutError:
                navigation_timed_out = True
                document_error = f"页面初始加载超时（{timeout_ms} 毫秒）"
            except PlaywrightError as exc:
                document_failed = True
                document_error = "页面访问失败"

            try:
                metrics = page.evaluate(
                    """() => {
                        const nav = performance.getEntriesByType('navigation')[0];
                        const bodyText = (document.body && document.body.innerText || '').trim();
                        return {
                          title: document.title || '',
                          bodyLength: bodyText.length,
                          domContentMs: nav && nav.domContentLoadedEventEnd > 0 ? nav.domContentLoadedEventEnd : null,
                          loadMs: nav && nav.loadEventEnd > 0 ? nav.loadEventEnd : null
                        };
                    }"""
                )
                render_ok = bool(metrics.get("title") or int(metrics.get("bodyLength") or 0) > 80)
                dom_content_ms = _safe_int(metrics.get("domContentMs"))
                load_ms = _safe_int(metrics.get("loadMs"))
            except Exception:
                render_ok = False
            if navigation_timed_out and (render_ok or (http_status is not None and http_status < 400)):
                document_failed = False
                document_error = ""

            collecting_requests = False
            context.close()
            browser.close()
    except Exception as exc:
        return _build_failure_result(url, started_at, "浏览器检测进程异常")

    fallback_latency_ms = _safe_int((time.perf_counter() - start_perf) * 1000)
    latency_ms = choose_display_latency(
        first_success_latency_ms=first_success_latency_ms,
        main_document_latency_ms=main_document_latency_ms,
        dom_content_ms=dom_content_ms,
        fallback_latency_ms=fallback_latency_ms,
    )
    same_origin_failures = [item for item in resources if is_critical_same_origin_failure(item)]
    resource_failed = len(same_origin_failures)
    status = classify_result(
        document_failed=document_failed,
        render_ok=render_ok,
        same_origin_resource_failed=resource_failed,
        console_error_count=0,
    )
    error_parts = []
    if document_error:
        error_parts.append(document_error)
    if not render_ok:
        error_parts.append("页面未检测到有效标题或正文渲染")
    if resource_failed:
        error_parts.append(f"同域关键资源失败 {resource_failed} 个")

    return {
        "started_at": started_at,
        "finished_at": iso_now(),
        "status": status,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "dom_content_ms": dom_content_ms,
        "load_ms": load_ms,
        "resource_total": len([item for item in resources if item.get("same_origin")]),
        "resource_failed": resource_failed,
        "console_error_count": 0,
        "render_ok": render_ok,
        "error_summary": "；".join(error_parts),
        "resources": resources[:400],
    }
