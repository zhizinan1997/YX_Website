#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIRS = [
    "assets/images",
    "assets/video",
    "pages",
    "data/partners/uploads",
    "data/hero/uploads",
    "data/h2_home_videos",
    "pic",
]

FIXED_OUTPUT_DIRS = [
    "images/common",
    "images/about",
    "images/news",
    "images/products",
    "images/solutions",
    "images/measurement",
    "images/biosensing",
    "images/gassensing",
    "images/services",
    "images/careers",
    "images/honors",
    "images/customization",
    "images/partners",
    "images/external-cache",
    "videos/home",
    "videos/measurement",
    "videos/common",
]

DEFAULT_INCLUDE_EXT = "png,jpg,jpeg,gif,webp,svg,avif,bmp,mp4,webm,mov,m4v"
VIDEO_EXTS = {"mp4", "webm", "mov", "m4v"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "bmp"}


@dataclass
class ManifestRow:
    old_path: str
    new_path: str
    sha1: str
    bytes: int
    category: str
    is_duplicate_of: Optional[str]


def parse_include_ext(raw: str) -> Set[str]:
    out = set()
    for item in (raw or "").split(","):
        ext = item.strip().lower()
        if ext.startswith("."):
            ext = ext[1:]
        if ext:
            out.add(ext)
    return out


def safe_rel_path(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


def iter_media_files(include_ext: Set[str]) -> Iterable[Tuple[str, Path, str]]:
    for src in SOURCE_DIRS:
        base_dir = ROOT / src
        if not base_dir.exists() or not base_dir.is_dir():
            continue
        for walk_root, _, files in os.walk(base_dir):
            walk_root_path = Path(walk_root)
            for name in files:
                fp = walk_root_path / name
                ext = fp.suffix.lower().lstrip(".")
                if ext in include_ext:
                    rel = safe_rel_path(fp, ROOT)
                    yield src, fp, rel


def classify_category(rel_path: str, ext: str) -> str:
    rel = rel_path.replace("\\", "/")
    is_video = ext in VIDEO_EXTS

    if rel.startswith("assets/images/external-cache/"):
        remainder = rel[len("assets/images/external-cache/") :]
        host = remainder.split("/", 1)[0].strip() if remainder else ""
        host = host or "unknown-host"
        return f"images/external-cache/{host}"

    if rel.startswith("assets/images/about/") or rel.startswith("pages/about/"):
        return "images/about"
    if rel.startswith("pages/news/"):
        return "images/news"
    if rel.startswith("assets/images/products/"):
        return "images/products"
    if rel.startswith("assets/images/solutions/") or rel.startswith("pages/solutions/"):
        return "images/solutions"
    if rel.startswith("assets/images/measurement/") or rel.startswith("pages/measurement/"):
        return "images/measurement"
    if rel.startswith("pages/biosensing/"):
        return "images/biosensing"
    if rel.startswith("pages/gassensing/") or rel.startswith("pages/gassensing_test/"):
        return "images/gassensing"
    if rel.startswith("pages/services/"):
        return "images/services"
    if rel.startswith("pages/careers/"):
        return "images/careers"
    if rel.startswith("pages/honors/"):
        return "images/honors"
    if rel.startswith("pages/customization/"):
        return "images/customization"
    if rel.startswith("data/partners/uploads/"):
        return "images/partners"
    if rel.startswith("assets/video/") or rel.startswith("data/h2_home_videos/"):
        return "videos/home"

    if is_video and rel.startswith("pages/measurement/"):
        return "videos/measurement"
    if is_video:
        return "videos/common"
    return "images/common"


def sha1_and_size(path: Path) -> Tuple[str, int]:
    h = hashlib.sha1()
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def ensure_output_clean(output_dir: Path) -> None:
    output_resolved = output_dir.resolve()
    root_resolved = ROOT.resolve()
    if output_resolved == root_resolved or output_resolved == root_resolved.parent:
        raise ValueError("Refusing to use unsafe output directory.")
    if output_resolved.exists():
        shutil.rmtree(output_resolved)
    output_resolved.mkdir(parents=True, exist_ok=True)
    for rel in FIXED_OUTPUT_DIRS:
        (output_resolved / rel).mkdir(parents=True, exist_ok=True)


def materialize_file(src: Path, dst: Path, mode: str) -> Tuple[str, bool]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        try:
            os.link(src, dst)
            return "hardlink", False
        except OSError:
            shutil.copy2(src, dst)
            return "copy", True
    shutil.copy2(src, dst)
    return "copy", False


def collision_safe_path(dst_dir: Path, sha1: str, ext: str) -> Path:
    candidate = dst_dir / f"{sha1[:12]}.{ext}"
    if not candidate.exists():
        return candidate
    idx = 1
    while True:
        alt = dst_dir / f"{sha1[:12]}_{idx}.{ext}"
        if not alt.exists():
            return alt
        idx += 1


def build_cdn_assets(output_dir: Path, mode: str, include_ext: Set[str]) -> Dict[str, object]:
    started_at = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at))

    ensure_output_clean(output_dir)

    manifest: List[ManifestRow] = []
    failures: List[Dict[str, str]] = []
    hardlink_fallback_copies = 0

    dedupe_index: Dict[str, Dict[str, object]] = {}
    group_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"count": 0, "bytes": 0, "size_each": 0, "sha1": ""}
    )
    by_category: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total_files": 0, "total_bytes": 0, "unique_files": 0, "unique_bytes": 0}
    )
    by_source_root: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total_files": 0, "total_bytes": 0}
    )

    all_files = sorted(iter_media_files(include_ext), key=lambda x: x[2])

    for source_root, file_path, old_rel in all_files:
        ext = file_path.suffix.lower().lstrip(".")
        category = classify_category(old_rel, ext)
        by_source_root[source_root]["total_files"] += 1

        try:
            sha1, size = sha1_and_size(file_path)
        except Exception as e:  # noqa: BLE001
            failures.append({"old_path": old_rel, "error": f"hash_failed: {e}"})
            continue

        by_source_root[source_root]["total_bytes"] += size

        dedupe_key = f"{sha1}:{size}"
        canonical = dedupe_index.get(dedupe_key)
        if canonical is None:
            dst_dir = output_dir / category
            dst_path = collision_safe_path(dst_dir, sha1, ext)
            try:
                _, fallback = materialize_file(file_path, dst_path, mode)
                if fallback:
                    hardlink_fallback_copies += 1
            except Exception as e:  # noqa: BLE001
                failures.append({"old_path": old_rel, "error": f"write_failed: {e}"})
                continue

            new_rel = safe_rel_path(dst_path, output_dir)
            canonical = {
                "old_path": old_rel,
                "new_path": new_rel,
                "sha1": sha1,
                "bytes": size,
                "category": category,
            }
            dedupe_index[dedupe_key] = canonical
            by_category[category]["unique_files"] += 1
            by_category[category]["unique_bytes"] += size
            is_duplicate_of = None
        else:
            new_rel = str(canonical["new_path"])
            is_duplicate_of = str(canonical["old_path"])
            category = str(canonical["category"])

        by_category[category]["total_files"] += 1
        by_category[category]["total_bytes"] += size

        group = group_stats[dedupe_key]
        group["count"] = int(group["count"]) + 1
        group["bytes"] = int(group["bytes"]) + size
        group["size_each"] = size
        group["sha1"] = sha1

        manifest.append(
            ManifestRow(
                old_path=old_rel,
                new_path=new_rel,
                sha1=sha1,
                bytes=size,
                category=category,
                is_duplicate_of=is_duplicate_of,
            )
        )

    duplicate_groups = 0
    duplicate_files = 0
    reclaimable_bytes = 0
    for info in group_stats.values():
        count = int(info["count"])
        size_each = int(info["size_each"])
        if count > 1:
            duplicate_groups += 1
            duplicate_files += count
            reclaimable_bytes += (count - 1) * size_each

    manifest_payload = [
        {
            "old_path": row.old_path,
            "new_path": row.new_path,
            "sha1": row.sha1,
            "bytes": row.bytes,
            "category": row.category,
            "is_duplicate_of": row.is_duplicate_of,
        }
        for row in manifest
    ]
    manifest_payload.sort(key=lambda x: x["old_path"])

    dedupe_report = {
        "total_files": len(manifest_payload),
        "unique_files": len(dedupe_index),
        "duplicate_groups": duplicate_groups,
        "duplicate_files": duplicate_files,
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable_mb": round(reclaimable_bytes / 1024 / 1024, 2),
        "by_category": {k: v for k, v in sorted(by_category.items(), key=lambda x: x[0])},
        "by_source_root": {k: v for k, v in sorted(by_source_root.items(), key=lambda x: x[0])},
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "dedupe_report.json").write_text(
        json.dumps(dedupe_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    finished_at = time.time()
    finished_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(finished_at))

    build_report = {
        "started_at": started_iso,
        "finished_at": finished_iso,
        "elapsed_seconds": round(finished_at - started_at, 3),
        "repo_root": str(ROOT),
        "output_dir": str(output_dir),
        "mode": mode,
        "include_ext": sorted(include_ext),
        "scan_scope": SOURCE_DIRS,
        "files_scanned": len(all_files),
        "files_processed": len(manifest_payload),
        "unique_files_written": len(dedupe_index),
        "hardlink_fallback_copies": hardlink_fallback_copies,
        "failures_count": len(failures),
        "failures": failures,
        "validations": {},
    }

    (output_dir / "build_report.json").write_text(
        json.dumps(build_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    build_report["validations"] = run_validations(output_dir, manifest_payload)
    (output_dir / "build_report.json").write_text(
        json.dumps(build_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return build_report


def run_validations(output_dir: Path, manifest_payload: List[Dict[str, object]]) -> Dict[str, object]:
    old_exists = True
    new_exists = True
    sha1_to_new: Dict[str, str] = {}
    sha1_unique_new = True

    for row in manifest_payload:
        old_path = ROOT / str(row["old_path"])
        new_path = output_dir / str(row["new_path"])
        sha1 = str(row["sha1"])

        if not old_path.exists():
            old_exists = False
        if not new_path.exists():
            new_exists = False

        existing = sha1_to_new.get(sha1)
        if existing is None:
            sha1_to_new[sha1] = str(row["new_path"])
        elif existing != str(row["new_path"]):
            sha1_unique_new = False

    allowed_top_level = {"images", "videos", "manifest.json", "dedupe_report.json", "build_report.json"}
    actual_top_level = {p.name for p in output_dir.iterdir()}
    top_level_only_allowed = actual_top_level.issubset(allowed_top_level)

    return {
        "manifest_old_path_exists_all": old_exists,
        "manifest_new_path_exists_all": new_exists,
        "single_new_path_per_sha1": sha1_unique_new,
        "top_level_only_allowed_entries": top_level_only_allowed,
        "top_level_entries": sorted(actual_top_level),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deduplicated CDN assets package from local media files."
    )
    parser.add_argument(
        "--output",
        default="cdn_assets",
        help="Output directory, relative to repo root or absolute path.",
    )
    parser.add_argument(
        "--mode",
        default="copy",
        choices=["copy", "hardlink"],
        help="Materialization mode. hardlink falls back to copy on failure.",
    )
    parser.add_argument(
        "--include-ext",
        default=DEFAULT_INCLUDE_EXT,
        help="Comma-separated file extensions without dots.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    include_ext = parse_include_ext(args.include_ext)
    if not include_ext:
        print("No valid extensions provided.", file=sys.stderr)
        return 2

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    try:
        report = build_cdn_assets(output_dir=output_dir, mode=args.mode, include_ext=include_ext)
    except Exception as e:  # noqa: BLE001
        print(f"Build failed: {e}", file=sys.stderr)
        return 1

    print(json.dumps({
        "output_dir": report["output_dir"],
        "files_processed": report["files_processed"],
        "unique_files_written": report["unique_files_written"],
        "failures_count": report["failures_count"],
        "elapsed_seconds": report["elapsed_seconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
