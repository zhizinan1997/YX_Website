#!/usr/bin/env python3
"""
Build responsive AVIF/WebP variants for homepage hero images.

Output:
- data/hero/derived/*.avif|*.webp
- data/hero/derived/manifest.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

try:
    from PIL import Image, ImageOps, features as PIL_FEATURES
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"Pillow is required: {exc}")


ROOT = Path(__file__).resolve().parents[1]
HERO_UPLOADS_DIR = ROOT / "data" / "hero" / "uploads"
HERO_DERIVED_DIR = ROOT / "data" / "hero" / "derived"
HERO_DERIVED_MANIFEST_FILE = HERO_DERIVED_DIR / "manifest.json"

SOURCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".avif"}
DERIVED_WIDTHS = (768, 1280, 1920)
DERIVED_FORMATS = ("avif", "webp")


def can_encode_avif() -> bool:
    try:
        return bool(PIL_FEATURES.check("avif"))
    except Exception:
        return False


def load_manifest() -> dict:
    default_manifest = {"version": 1, "items": {}}
    if not HERO_DERIVED_MANIFEST_FILE.exists():
        return default_manifest
    try:
        payload = json.loads(HERO_DERIVED_MANIFEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_manifest
    if not isinstance(payload, dict):
        return default_manifest
    items = payload.get("items")
    if not isinstance(items, dict):
        items = {}
    return {"version": 1, "items": items}


def save_manifest(manifest: dict) -> None:
    HERO_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    HERO_DERIVED_MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def iter_variant_filenames(entry: dict) -> list[str]:
    variants = (entry or {}).get("variants", {})
    if not isinstance(variants, dict):
        return []
    names: list[str] = []
    for group in variants.values():
        if not isinstance(group, list):
            continue
        for row in group:
            if not isinstance(row, dict):
                continue
            filename = str(row.get("filename") or "").strip()
            if filename:
                names.append(filename)
    return names


def build_variants_for_source(source_path: Path) -> dict | None:
    with Image.open(source_path) as raw_img:
        img = ImageOps.exif_transpose(raw_img)
        src_width, src_height = img.size
        if src_width <= 0 or src_height <= 0:
            return None
        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            base_img = img.convert("RGBA")
        else:
            base_img = img.convert("RGB")

    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    widths = sorted({w for w in DERIVED_WIDTHS if isinstance(w, int) and w > 0})
    if src_width not in widths:
        widths.append(src_width)
    widths = sorted({min(src_width, w) for w in widths if w > 0})

    format_map: list[tuple[str, str, dict]] = []
    avif_ok = can_encode_avif()
    for fmt in DERIVED_FORMATS:
        if fmt == "avif" and not avif_ok:
            continue
        if fmt == "webp":
            format_map.append(("webp", "WEBP", {"quality": 80, "method": 6}))
        elif fmt == "avif":
            format_map.append(("avif", "AVIF", {"quality": 50, "speed": 6}))

    if not format_map:
        return None

    base_name = source_path.stem
    variants: dict[str, list[dict]] = {}
    for fmt_name, pil_format, save_options in format_map:
        rows = []
        for width in widths:
            width = int(width)
            if width <= 0:
                continue
            if width == src_width:
                resized = base_img.copy()
                height = src_height
            else:
                height = max(1, int(round(src_height * width / src_width)))
                resized = base_img.resize((width, height), resample)
            out_name = f"{base_name}-w{width}.{fmt_name}"
            out_path = HERO_DERIVED_DIR / out_name
            try:
                resized.save(out_path, pil_format, **save_options)
            except Exception:
                continue
            rows.append({"width": width, "filename": out_name})
        if rows:
            rows.sort(key=lambda x: int(x.get("width", 0)))
            variants[fmt_name] = rows

    if not variants:
        return None

    return {
        "width": int(src_width),
        "height": int(src_height),
        "variants": variants,
        "updated_at": int(time.time()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build hero responsive image variants.")
    parser.add_argument("--force", action="store_true", help="Rebuild all variants.")
    args = parser.parse_args()

    HERO_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    items = manifest.get("items", {})
    if not isinstance(items, dict):
        items = {}

    sources = sorted(
        p for p in HERO_UPLOADS_DIR.glob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_IMAGE_EXTENSIONS
    )
    if not sources:
        print("No hero source images found.")
        return 0

    updated = 0
    skipped = 0
    failed = 0
    seen = set()

    for source in sources:
        seen.add(source.name)
        old_entry = items.get(source.name, {}) if isinstance(items.get(source.name), dict) else {}
        source_mtime = int(source.stat().st_mtime)
        old_mtime = int(old_entry.get("source_mtime", 0) or 0)
        if (not args.force) and old_mtime == source_mtime and old_entry.get("variants"):
            skipped += 1
            continue

        try:
            new_entry = build_variants_for_source(source)
        except Exception:
            new_entry = None

        if not new_entry:
            failed += 1
            continue

        old_files = set(iter_variant_filenames(old_entry))
        new_files = set(iter_variant_filenames(new_entry))
        for stale in old_files - new_files:
            stale_path = HERO_DERIVED_DIR / stale
            if stale_path.exists():
                try:
                    stale_path.unlink()
                except Exception:
                    pass

        new_entry["source_mtime"] = source_mtime
        items[source.name] = new_entry
        updated += 1

    # Cleanup entries for removed source files.
    removed_sources = [name for name in list(items.keys()) if name not in seen]
    for removed in removed_sources:
        old_entry = items.pop(removed, {})
        for stale in iter_variant_filenames(old_entry if isinstance(old_entry, dict) else {}):
            stale_path = HERO_DERIVED_DIR / stale
            if stale_path.exists():
                try:
                    stale_path.unlink()
                except Exception:
                    pass

    manifest["items"] = items
    save_manifest(manifest)
    print(f"Updated: {updated}, skipped: {skipped}, failed: {failed}, removed: {len(removed_sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
