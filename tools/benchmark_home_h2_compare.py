#!/usr/bin/env python3
"""
Dependency-free benchmark script for comparing:
1) Initial loading strategy
2) Current loading strategy

Targets:
- Homepage (index)
- H2 homepage (pages/gassensing/index)

Outputs:
- JSON detail report
- Markdown comparison report

No-cache enforcement:
- Adds `Cache-Control: no-cache`, `Pragma: no-cache`
- Appends unique cache-busting query parameter on each HTTP request

Note:
This is network-level simulation of your loading logic.
- "first video starts playing" is approximated by "first playable byte range fetched".
- In addition to strategy-path timing, this script now also reports
  full download timing for all configured hero images/videos.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse, parse_qsl, quote
from urllib.request import Request, urlopen


NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": "YX-Benchmark/1.0",
}


@dataclass
class FetchResult:
    url: str
    status: int
    ok: bool
    elapsed_s: float
    bytes_read: int
    error: str = ""
    body: bytes = b""


@dataclass
class RunRecord:
    strategy: str
    iteration: int
    result: Dict[str, Any]


def add_bust(url: str, run_token: str, label: str) -> str:
    parsed = urlparse(url)
    q = parse_qsl(parsed.query, keep_blank_values=True)
    q.append(("__bench", f"{run_token}-{label}-{uuid.uuid4().hex[:8]}"))
    new_query = urlencode(q)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def to_video_fetch_url(base_url: str, raw_url: str) -> str:
    origin = urlparse(base_url).scheme + "://" + urlparse(base_url).netloc
    absolute = urljoin(origin + "/", raw_url)
    p = urlparse(absolute)
    if (p.scheme + "://" + p.netloc) == origin:
        return absolute
    return f"{origin}/api/video-proxy?url={quote(absolute, safe='')}"


def fetch_bytes(
    url: str,
    timeout_s: int,
    headers: Dict[str, str] | None = None,
    max_read_bytes: int | None = None,
) -> FetchResult:
    merged_headers = dict(NO_CACHE_HEADERS)
    if headers:
        merged_headers.update(headers)

    req = Request(url=url, headers=merged_headers, method="GET")
    started = time.perf_counter()
    status = 0
    total = 0
    body = b""
    err = ""

    try:
        with urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", 200))
            chunks = []
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if max_read_bytes is None:
                    chunks.append(chunk)
                else:
                    remain = max_read_bytes - len(body)
                    if remain > 0:
                        body += chunk[:remain]
                    if total >= max_read_bytes:
                        break
            if max_read_bytes is None:
                body = b"".join(chunks)
    except HTTPError as e:
        status = int(e.code or 0)
        err = f"HTTPError: {e}"
        try:
            body = e.read() or b""
            total = len(body)
        except Exception:
            pass
    except URLError as e:
        err = f"URLError: {e}"
    except Exception as e:
        err = f"Error: {e}"

    elapsed = time.perf_counter() - started
    ok = 200 <= status < 400 and not err
    return FetchResult(url=url, status=status, ok=ok, elapsed_s=elapsed, bytes_read=total, error=err, body=body)


def fetch_json(url: str, timeout_s: int, headers: Dict[str, str] | None = None) -> Tuple[FetchResult, Dict[str, Any]]:
    fr = fetch_bytes(url, timeout_s=timeout_s, headers=headers, max_read_bytes=None)
    if not fr.ok:
        return fr, {}
    try:
        text = fr.body.decode("utf-8", errors="replace")
        data = json.loads(text)
        if not isinstance(data, dict):
            return fr, {}
        return fr, data
    except Exception:
        return fr, {}


def extract_hero_image_urls(hero_payload: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    items = hero_payload.get("items", [])
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).lower() != "image":
            continue
        url = str(item.get("fallback") or item.get("url") or "").strip()
        if url:
            out.append(url)
    return out


def extract_h2_video_urls(h2_payload: Dict[str, Any], base_url: str) -> List[str]:
    out: List[str] = []
    items = h2_payload.get("items", [])
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_url = str(item.get("url") or "").strip()
        if not raw_url:
            continue
        out.append(to_video_fetch_url(base_url, raw_url))
    return out


def _to_abs(base_url: str, raw_url: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))


def download_all_urls_concurrent(
    urls: List[str],
    run_token: str,
    label_prefix: str,
    timeout_s: int,
    max_workers: int,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    reqs: List[Dict[str, Any]] = []
    if not urls:
        return {
            "totalCount": 0,
            "okCount": 0,
            "failedCount": 0,
            "totalBytes": 0,
            "elapsedS": 0.0,
            "requests": reqs,
        }

    worker_n = max(1, min(max_workers, len(urls)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_n) as ex:
        futs = []
        for idx, raw in enumerate(urls):
            u = add_bust(raw, run_token, f"{label_prefix}_{idx}")
            futs.append((idx, ex.submit(fetch_bytes, u, timeout_s, None, None)))

        for idx, fut in futs:
            r = fut.result()
            reqs.append({
                "name": f"{label_prefix}_{idx}",
                "url": r.url,
                "status": r.status,
                "ok": r.ok,
                "elapsed_s": r.elapsed_s,
                "bytes_read": r.bytes_read,
                "error": r.error,
            })

    ok_count = sum(1 for x in reqs if x.get("ok"))
    total_bytes = sum(int(x.get("bytes_read") or 0) for x in reqs)
    elapsed = time.perf_counter() - t0
    return {
        "totalCount": len(reqs),
        "okCount": ok_count,
        "failedCount": len(reqs) - ok_count,
        "totalBytes": total_bytes,
        "elapsedS": elapsed,
        "requests": reqs,
    }


def run_full_media_download(
    base_url: str,
    run_token: str,
    timeout_s: int,
    max_workers: int,
) -> Dict[str, Any]:
    requests: List[Dict[str, Any]] = []
    errors: List[str] = []

    hero_api = add_bust(urljoin(base_url + "/", "api/hero"), run_token, "full_api_hero")
    hero_fr, hero_data = fetch_json(hero_api, timeout_s)
    requests.append({
        "name": "full_api_hero",
        "url": hero_fr.url,
        "status": hero_fr.status,
        "ok": hero_fr.ok,
        "elapsed_s": hero_fr.elapsed_s,
        "bytes_read": hero_fr.bytes_read,
        "error": hero_fr.error,
    })
    if not hero_fr.ok:
        errors.append(f"/api/hero failed: {hero_fr.error or hero_fr.status}")

    h2_api = add_bust(urljoin(base_url + "/", "api/h2-home"), run_token, "full_api_h2")
    h2_fr, h2_data = fetch_json(h2_api, timeout_s)
    requests.append({
        "name": "full_api_h2",
        "url": h2_fr.url,
        "status": h2_fr.status,
        "ok": h2_fr.ok,
        "elapsed_s": h2_fr.elapsed_s,
        "bytes_read": h2_fr.bytes_read,
        "error": h2_fr.error,
    })
    if not h2_fr.ok:
        errors.append(f"/api/h2-home failed: {h2_fr.error or h2_fr.status}")

    hero_images = [_to_abs(base_url, u) for u in extract_hero_image_urls(hero_data)]
    h2_videos = extract_h2_video_urls(h2_data, base_url)

    home_dl = download_all_urls_concurrent(
        urls=hero_images,
        run_token=run_token,
        label_prefix="full_home_img",
        timeout_s=timeout_s,
        max_workers=max_workers,
    )
    h2_dl = download_all_urls_concurrent(
        urls=h2_videos,
        run_token=run_token,
        label_prefix="full_h2_video",
        timeout_s=timeout_s,
        max_workers=max_workers,
    )

    return {
        "homepageAllImages": home_dl,
        "h2AllVideos": h2_dl,
        "errors": errors,
        "requests": requests,
    }


def run_home_initial(
    base_url: str,
    run_token: str,
    timeout_s: int,
    initial_video_prefetch_count: int,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    requests: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []

    hero_url = add_bust(urljoin(base_url + "/", "api/hero"), run_token, "home_initial_api_hero")
    hero_fr, hero_data = fetch_json(hero_url, timeout_s)
    requests.append({
        "name": "home_initial_api_hero",
        "url": hero_fr.url,
        "status": hero_fr.status,
        "ok": hero_fr.ok,
        "elapsed_s": hero_fr.elapsed_s,
        "bytes_read": hero_fr.bytes_read,
        "error": hero_fr.error,
    })
    image_urls = extract_hero_image_urls(hero_data)

    if not image_urls:
        return {
            "error": "No hero images found",
            "firstMediaReadyS": None,
            "allResourcesReadyS": None,
            "steps": steps,
            "requests": requests,
        }

    # Initial behavior: all hero images preloaded concurrently.
    first_ready_s = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(image_urls)))) as ex:
        futs = []
        for idx, raw in enumerate(image_urls):
            u = add_bust(urljoin(base_url + "/", raw.lstrip("/")), run_token, f"home_initial_img_{idx}")
            fut = ex.submit(fetch_bytes, u, timeout_s, None, None)
            futs.append((idx, fut))

        # First slide media ready ~= first image loaded.
        first_idx, first_fut = futs[0]
        first_res = first_fut.result()
        first_ready_s = time.perf_counter() - t0
        requests.append({
            "name": f"home_initial_img_{first_idx}",
            "url": first_res.url,
            "status": first_res.status,
            "ok": first_res.ok,
            "elapsed_s": first_res.elapsed_s,
            "bytes_read": first_res.bytes_read,
            "error": first_res.error,
        })
        steps.append({"name": "home_first_image_ready", "at_s": first_ready_s})

        for idx, fut in futs[1:]:
            r = fut.result()
            requests.append({
                "name": f"home_initial_img_{idx}",
                "url": r.url,
                "status": r.status,
                "ok": r.ok,
                "elapsed_s": r.elapsed_s,
                "bytes_read": r.bytes_read,
                "error": r.error,
            })

    steps.append({"name": "home_all_hero_images_done", "at_s": time.perf_counter() - t0})

    # Initial behavior: prefetch up to N full h2 videos sequentially.
    h2_url = add_bust(urljoin(base_url + "/", "api/h2-home"), run_token, "home_initial_api_h2")
    h2_fr, h2_data = fetch_json(h2_url, timeout_s)
    requests.append({
        "name": "home_initial_api_h2",
        "url": h2_fr.url,
        "status": h2_fr.status,
        "ok": h2_fr.ok,
        "elapsed_s": h2_fr.elapsed_s,
        "bytes_read": h2_fr.bytes_read,
        "error": h2_fr.error,
    })
    video_urls = extract_h2_video_urls(h2_data, base_url)[: max(0, initial_video_prefetch_count)]
    for i, raw in enumerate(video_urls):
        u = add_bust(raw, run_token, f"home_initial_video_full_{i}")
        r = fetch_bytes(u, timeout_s, headers=None, max_read_bytes=None)
        requests.append({
            "name": f"home_initial_video_full_{i}",
            "url": r.url,
            "status": r.status,
            "ok": r.ok,
            "elapsed_s": r.elapsed_s,
            "bytes_read": r.bytes_read,
            "error": r.error,
        })

    all_ready_s = time.perf_counter() - t0
    steps.append({"name": "home_initial_all_resources_done", "at_s": all_ready_s})
    return {
        "firstMediaReadyS": first_ready_s,
        "allResourcesReadyS": all_ready_s,
        "steps": steps,
        "requests": requests,
    }


def run_home_current(
    base_url: str,
    run_token: str,
    timeout_s: int,
    current_range_bytes: int,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    requests: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []

    hero_url = add_bust(urljoin(base_url + "/", "api/hero"), run_token, "home_current_api_hero")
    hero_fr, hero_data = fetch_json(hero_url, timeout_s)
    requests.append({
        "name": "home_current_api_hero",
        "url": hero_fr.url,
        "status": hero_fr.status,
        "ok": hero_fr.ok,
        "elapsed_s": hero_fr.elapsed_s,
        "bytes_read": hero_fr.bytes_read,
        "error": hero_fr.error,
    })
    image_urls = extract_hero_image_urls(hero_data)
    if not image_urls:
        return {
            "error": "No hero images found",
            "firstMediaReadyS": None,
            "allResourcesReadyS": None,
            "steps": steps,
            "requests": requests,
        }

    # Current behavior: first image only (eager)
    first_url = add_bust(urljoin(base_url + "/", image_urls[0].lstrip("/")), run_token, "home_current_first_img")
    first_img = fetch_bytes(first_url, timeout_s, headers={"X-Fetch-Priority": "high"}, max_read_bytes=None)
    first_ready_s = time.perf_counter() - t0
    requests.append({
        "name": "home_current_first_img",
        "url": first_img.url,
        "status": first_img.status,
        "ok": first_img.ok,
        "elapsed_s": first_img.elapsed_s,
        "bytes_read": first_img.bytes_read,
        "error": first_img.error,
    })
    steps.append({"name": "home_first_image_ready", "at_s": first_ready_s})

    # Current behavior: warm only next 2 images sequentially.
    warm_images = image_urls[1:3]
    for i, raw in enumerate(warm_images):
        u = add_bust(urljoin(base_url + "/", raw.lstrip("/")), run_token, f"home_current_warm_img_{i}")
        r = fetch_bytes(u, timeout_s, headers={"X-Fetch-Priority": "low"}, max_read_bytes=None)
        requests.append({
            "name": f"home_current_warm_img_{i}",
            "url": r.url,
            "status": r.status,
            "ok": r.ok,
            "elapsed_s": r.elapsed_s,
            "bytes_read": r.bytes_read,
            "error": r.error,
        })
    steps.append({"name": "home_current_warm_images_done", "at_s": time.perf_counter() - t0})

    # Current behavior: warm only first h2 video with byte range.
    h2_url = add_bust(urljoin(base_url + "/", "api/h2-home"), run_token, "home_current_api_h2")
    h2_fr, h2_data = fetch_json(h2_url, timeout_s)
    requests.append({
        "name": "home_current_api_h2",
        "url": h2_fr.url,
        "status": h2_fr.status,
        "ok": h2_fr.ok,
        "elapsed_s": h2_fr.elapsed_s,
        "bytes_read": h2_fr.bytes_read,
        "error": h2_fr.error,
    })
    video_urls = extract_h2_video_urls(h2_data, base_url)
    if video_urls:
        u = add_bust(video_urls[0], run_token, "home_current_video_range")
        r = fetch_bytes(
            u,
            timeout_s,
            headers={"Range": f"bytes=0-{max(0, current_range_bytes - 1)}"},
            max_read_bytes=None,
        )
        requests.append({
            "name": "home_current_video_range",
            "url": r.url,
            "status": r.status,
            "ok": r.ok,
            "elapsed_s": r.elapsed_s,
            "bytes_read": r.bytes_read,
            "error": r.error,
        })

    all_ready_s = time.perf_counter() - t0
    steps.append({"name": "home_current_all_resources_done", "at_s": all_ready_s})
    return {
        "firstMediaReadyS": first_ready_s,
        "allResourcesReadyS": all_ready_s,
        "steps": steps,
        "requests": requests,
    }


def run_h2_initial(
    base_url: str,
    run_token: str,
    timeout_s: int,
    first_video_range_bytes: int,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    requests: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []

    h2_url = add_bust(urljoin(base_url + "/", "api/h2-home"), run_token, "h2_initial_api")
    h2_fr, h2_data = fetch_json(h2_url, timeout_s)
    requests.append({
        "name": "h2_initial_api",
        "url": h2_fr.url,
        "status": h2_fr.status,
        "ok": h2_fr.ok,
        "elapsed_s": h2_fr.elapsed_s,
        "bytes_read": h2_fr.bytes_read,
        "error": h2_fr.error,
    })
    video_urls = extract_h2_video_urls(h2_data, base_url)
    if not video_urls:
        return {
            "error": "No h2 hero videos found",
            "firstMediaReadyS": None,
            "allResourcesReadyS": None,
            "steps": steps,
            "requests": requests,
        }

    # Approximate "first video starts playing" as first buffered range fetched.
    first_u = add_bust(video_urls[0], run_token, "h2_initial_first_video_range")
    first_r = fetch_bytes(
        first_u,
        timeout_s,
        headers={"Range": f"bytes=0-{max(0, first_video_range_bytes - 1)}"},
        max_read_bytes=None,
    )
    first_ready_s = time.perf_counter() - t0
    requests.append({
        "name": "h2_initial_first_video_range",
        "url": first_r.url,
        "status": first_r.status,
        "ok": first_r.ok,
        "elapsed_s": first_r.elapsed_s,
        "bytes_read": first_r.bytes_read,
        "error": first_r.error,
    })
    steps.append({"name": "h2_first_video_ready", "at_s": first_ready_s})

    # Initial page-load has no additional proactive preloading for next video.
    all_ready_s = first_ready_s
    steps.append({"name": "h2_initial_all_resources_done", "at_s": all_ready_s})
    return {
        "firstMediaReadyS": first_ready_s,
        "allResourcesReadyS": all_ready_s,
        "steps": steps,
        "requests": requests,
    }


def run_h2_current(
    base_url: str,
    run_token: str,
    timeout_s: int,
    first_video_range_bytes: int,
    next_video_metadata_range_bytes: int,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    requests: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []

    h2_url = add_bust(urljoin(base_url + "/", "api/h2-home"), run_token, "h2_current_api")
    h2_fr, h2_data = fetch_json(h2_url, timeout_s)
    requests.append({
        "name": "h2_current_api",
        "url": h2_fr.url,
        "status": h2_fr.status,
        "ok": h2_fr.ok,
        "elapsed_s": h2_fr.elapsed_s,
        "bytes_read": h2_fr.bytes_read,
        "error": h2_fr.error,
    })
    video_urls = extract_h2_video_urls(h2_data, base_url)
    if not video_urls:
        return {
            "error": "No h2 hero videos found",
            "firstMediaReadyS": None,
            "allResourcesReadyS": None,
            "steps": steps,
            "requests": requests,
        }

    first_u = add_bust(video_urls[0], run_token, "h2_current_first_video_range")
    first_r = fetch_bytes(
        first_u,
        timeout_s,
        headers={"Range": f"bytes=0-{max(0, first_video_range_bytes - 1)}"},
        max_read_bytes=None,
    )
    first_ready_s = time.perf_counter() - t0
    requests.append({
        "name": "h2_current_first_video_range",
        "url": first_r.url,
        "status": first_r.status,
        "ok": first_r.ok,
        "elapsed_s": first_r.elapsed_s,
        "bytes_read": first_r.bytes_read,
        "error": first_r.error,
    })
    steps.append({"name": "h2_first_video_ready", "at_s": first_ready_s})

    # Current page-load behavior: preload next video metadata.
    if len(video_urls) > 1:
        next_u = add_bust(video_urls[1], run_token, "h2_current_next_metadata")
        next_r = fetch_bytes(
            next_u,
            timeout_s,
            headers={"Range": f"bytes=0-{max(0, next_video_metadata_range_bytes - 1)}"},
            max_read_bytes=None,
        )
        requests.append({
            "name": "h2_current_next_metadata",
            "url": next_r.url,
            "status": next_r.status,
            "ok": next_r.ok,
            "elapsed_s": next_r.elapsed_s,
            "bytes_read": next_r.bytes_read,
            "error": next_r.error,
        })
        steps.append({"name": "h2_current_next_metadata_ready", "at_s": time.perf_counter() - t0})

    all_ready_s = time.perf_counter() - t0
    steps.append({"name": "h2_current_all_resources_done", "at_s": all_ready_s})
    return {
        "firstMediaReadyS": first_ready_s,
        "allResourcesReadyS": all_ready_s,
        "steps": steps,
        "requests": requests,
    }


def run_strategy(
    strategy: str,
    iteration: int,
    base_url: str,
    timeout_s: int,
    initial_video_prefetch_count: int,
    home_current_range_bytes: int,
    h2_first_video_range_bytes: int,
    h2_next_video_metadata_range_bytes: int,
    full_download_max_workers: int,
) -> RunRecord:
    run_token = f"{int(time.time())}-{strategy}-{iteration}-{uuid.uuid4().hex[:6]}"
    if strategy == "initial":
        homepage = run_home_initial(
            base_url=base_url,
            run_token=run_token,
            timeout_s=timeout_s,
            initial_video_prefetch_count=initial_video_prefetch_count,
        )
        h2page = run_h2_initial(
            base_url=base_url,
            run_token=run_token,
            timeout_s=timeout_s,
            first_video_range_bytes=h2_first_video_range_bytes,
        )
    else:
        homepage = run_home_current(
            base_url=base_url,
            run_token=run_token,
            timeout_s=timeout_s,
            current_range_bytes=home_current_range_bytes,
        )
        h2page = run_h2_current(
            base_url=base_url,
            run_token=run_token,
            timeout_s=timeout_s,
            first_video_range_bytes=h2_first_video_range_bytes,
            next_video_metadata_range_bytes=h2_next_video_metadata_range_bytes,
        )

    full_download = run_full_media_download(
        base_url=base_url,
        run_token=run_token,
        timeout_s=timeout_s,
        max_workers=full_download_max_workers,
    )

    return RunRecord(
        strategy=strategy,
        iteration=iteration,
        result={
            "runToken": run_token,
            "strategy": strategy,
            "homepage": homepage,
            "h2page": h2page,
            "fullDownload": full_download,
        },
    )


def _avg(values: List[float | None]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return float(statistics.mean(nums))


def summarize(records: List[RunRecord]) -> Dict[str, Any]:
    grouped: Dict[str, List[RunRecord]] = {"initial": [], "current": []}
    for r in records:
        grouped.setdefault(r.strategy, []).append(r)

    def metric(strategy: str, page_key: str, field: str) -> float | None:
        values: List[float | None] = []
        for r in grouped.get(strategy, []):
            v = r.result.get(page_key, {}).get(field)
            values.append(v if isinstance(v, (int, float)) else None)
        return _avg(values)

    def metric_path(strategy: str, path: List[str]) -> float | None:
        values: List[float | None] = []
        for r in grouped.get(strategy, []):
            cur: Any = r.result
            for key in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(key)
            values.append(cur if isinstance(cur, (int, float)) else None)
        return _avg(values)

    out = {
        "strategies": {
            "initial": {
                "homepage_first_media_seconds_avg": metric("initial", "homepage", "firstMediaReadyS"),
                "homepage_all_resources_seconds_avg": metric("initial", "homepage", "allResourcesReadyS"),
                "h2_first_media_seconds_avg": metric("initial", "h2page", "firstMediaReadyS"),
                "h2_all_resources_seconds_avg": metric("initial", "h2page", "allResourcesReadyS"),
                "homepage_all_images_full_download_seconds_avg": metric_path(
                    "initial", ["fullDownload", "homepageAllImages", "elapsedS"]
                ),
                "h2_all_videos_full_download_seconds_avg": metric_path(
                    "initial", ["fullDownload", "h2AllVideos", "elapsedS"]
                ),
            },
            "current": {
                "homepage_first_media_seconds_avg": metric("current", "homepage", "firstMediaReadyS"),
                "homepage_all_resources_seconds_avg": metric("current", "homepage", "allResourcesReadyS"),
                "h2_first_media_seconds_avg": metric("current", "h2page", "firstMediaReadyS"),
                "h2_all_resources_seconds_avg": metric("current", "h2page", "allResourcesReadyS"),
                "homepage_all_images_full_download_seconds_avg": metric_path(
                    "current", ["fullDownload", "homepageAllImages", "elapsedS"]
                ),
                "h2_all_videos_full_download_seconds_avg": metric_path(
                    "current", ["fullDownload", "h2AllVideos", "elapsedS"]
                ),
            },
        }
    }
    i = out["strategies"]["initial"]
    c = out["strategies"]["current"]
    out["delta_current_minus_initial"] = {
        "homepage_first_media_seconds": _safe_sub(c["homepage_first_media_seconds_avg"], i["homepage_first_media_seconds_avg"]),
        "homepage_all_resources_seconds": _safe_sub(c["homepage_all_resources_seconds_avg"], i["homepage_all_resources_seconds_avg"]),
        "h2_first_media_seconds": _safe_sub(c["h2_first_media_seconds_avg"], i["h2_first_media_seconds_avg"]),
        "h2_all_resources_seconds": _safe_sub(c["h2_all_resources_seconds_avg"], i["h2_all_resources_seconds_avg"]),
        "homepage_all_images_full_download_seconds": _safe_sub(
            c["homepage_all_images_full_download_seconds_avg"],
            i["homepage_all_images_full_download_seconds_avg"],
        ),
        "h2_all_videos_full_download_seconds": _safe_sub(
            c["h2_all_videos_full_download_seconds_avg"],
            i["h2_all_videos_full_download_seconds_avg"],
        ),
    }
    return out


def _safe_sub(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return float(a - b)


def _fmt(v: float | None) -> str:
    return "N/A" if v is None else f"{v:.3f}s"


def render_markdown(base_url: str, runs: int, summary: Dict[str, Any], records: List[RunRecord]) -> str:
    i = summary["strategies"]["initial"]
    c = summary["strategies"]["current"]
    d = summary["delta_current_minus_initial"]
    lines = [
        "# Homepage & H2 Homepage Benchmark (No Browser Cache)",
        "",
        f"- Base URL: `{base_url}`",
        f"- Runs per strategy: `{runs}`",
        "- No-cache controls: `Cache-Control/Pragma + unique cache-busting query`",
        "",
        "## Strategy Semantics",
        "",
        "- `initial/home`: fetch `/api/hero` -> preload all hero images concurrently -> fetch `/api/h2-home` -> full prefetch first N videos.",
        "- `current/home`: fetch `/api/hero` -> load first hero image -> warm next 2 images -> fetch `/api/h2-home` -> range prefetch first video.",
        "- `initial/h2`: fetch `/api/h2-home` -> range fetch first video (as first-play proxy), no next-video preload.",
        "- `current/h2`: fetch `/api/h2-home` -> range fetch first video -> range preload next video metadata.",
        "",
        "## Average Comparison",
        "",
        "| Metric | Initial | Current | Delta (Current - Initial) |",
        "|---|---:|---:|---:|",
        f"| Homepage first media ready | {_fmt(i['homepage_first_media_seconds_avg'])} | {_fmt(c['homepage_first_media_seconds_avg'])} | {_fmt(d['homepage_first_media_seconds'])} |",
        f"| Homepage all resources done | {_fmt(i['homepage_all_resources_seconds_avg'])} | {_fmt(c['homepage_all_resources_seconds_avg'])} | {_fmt(d['homepage_all_resources_seconds'])} |",
        f"| H2 first media ready | {_fmt(i['h2_first_media_seconds_avg'])} | {_fmt(c['h2_first_media_seconds_avg'])} | {_fmt(d['h2_first_media_seconds'])} |",
        f"| H2 all resources done | {_fmt(i['h2_all_resources_seconds_avg'])} | {_fmt(c['h2_all_resources_seconds_avg'])} | {_fmt(d['h2_all_resources_seconds'])} |",
        f"| Homepage all images full download | {_fmt(i['homepage_all_images_full_download_seconds_avg'])} | {_fmt(c['homepage_all_images_full_download_seconds_avg'])} | {_fmt(d['homepage_all_images_full_download_seconds'])} |",
        f"| H2 all videos full download | {_fmt(i['h2_all_videos_full_download_seconds_avg'])} | {_fmt(c['h2_all_videos_full_download_seconds_avg'])} | {_fmt(d['h2_all_videos_full_download_seconds'])} |",
        "",
        "## Per-Run Detail",
        "",
    ]

    for r in records:
        hp = r.result.get("homepage", {})
        h2 = r.result.get("h2page", {})
        full_dl = r.result.get("fullDownload", {})
        home_full = (full_dl.get("homepageAllImages") or {}).get("elapsedS")
        h2_full = (full_dl.get("h2AllVideos") or {}).get("elapsedS")
        lines.extend([
            f"### {r.strategy} / run {r.iteration}",
            f"- homepage_first_media: {_fmt(hp.get('firstMediaReadyS'))}",
            f"- homepage_all_resources: {_fmt(hp.get('allResourcesReadyS'))}",
            f"- h2_first_media: {_fmt(h2.get('firstMediaReadyS'))}",
            f"- h2_all_resources: {_fmt(h2.get('allResourcesReadyS'))}",
            f"- homepage_all_images_full_download: {_fmt(home_full)}",
            f"- h2_all_videos_full_download: {_fmt(h2_full)}",
        ])
        if hp.get("error"):
            lines.append(f"- homepage_error: `{hp.get('error')}`")
        if h2.get("error"):
            lines.append(f"- h2_error: `{h2.get('error')}`")
        if full_dl.get("errors"):
            lines.append(f"- full_download_errors: `{'; '.join(full_dl.get('errors', []))}`")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare initial vs current resource loading without cache.")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--timeout-s", type=int, default=90)
    p.add_argument("--initial-video-prefetch-count", type=int, default=3)
    p.add_argument("--home-current-range-bytes", type=int, default=524288)
    p.add_argument("--h2-first-video-range-bytes", type=int, default=1048576)
    p.add_argument("--h2-next-video-metadata-range-bytes", type=int, default=262144)
    p.add_argument("--full-download-max-workers", type=int, default=6)
    p.add_argument("--output-json", default="./benchmark_home_h2_compare.json")
    p.add_argument("--output-md", default="./benchmark_home_h2_compare.md")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    records: List[RunRecord] = []

    for strategy in ("initial", "current"):
        for i in range(1, max(1, args.runs) + 1):
            rec = run_strategy(
                strategy=strategy,
                iteration=i,
                base_url=base_url,
                timeout_s=args.timeout_s,
                initial_video_prefetch_count=args.initial_video_prefetch_count,
                home_current_range_bytes=args.home_current_range_bytes,
                h2_first_video_range_bytes=args.h2_first_video_range_bytes,
                h2_next_video_metadata_range_bytes=args.h2_next_video_metadata_range_bytes,
                full_download_max_workers=args.full_download_max_workers,
            )
            records.append(rec)
            print(f"[done] strategy={strategy} run={i}")

    summary = summarize(records)
    payload = {
        "meta": {
            "base_url": base_url,
            "runs_per_strategy": args.runs,
            "timeout_s": args.timeout_s,
            "initial_video_prefetch_count": args.initial_video_prefetch_count,
            "home_current_range_bytes": args.home_current_range_bytes,
            "h2_first_video_range_bytes": args.h2_first_video_range_bytes,
            "h2_next_video_metadata_range_bytes": args.h2_next_video_metadata_range_bytes,
            "full_download_max_workers": args.full_download_max_workers,
            "cache_policy": "no-cache headers + cache-busting query parameter",
            "generated_at_epoch": int(time.time()),
        },
        "summary": summary,
        "records": [
            {"strategy": r.strategy, "iteration": r.iteration, "result": r.result}
            for r in records
        ],
    }

    json_path = Path(args.output_json).resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = Path(args.output_md).resolve()
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(base_url, args.runs, summary, records), encoding="utf-8")

    print(f"JSON report: {json_path}")
    print(f"MD report:   {md_path}")
    print("Summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
