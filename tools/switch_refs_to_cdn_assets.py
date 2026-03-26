#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import posixpath
import re
from pathlib import Path
from typing import Dict, Tuple


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "cdn_assets" / "manifest.json"
TEXT_EXTS = {".html", ".js", ".css", ".json"}
MEDIA_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "bmp", "mp4", "webm", "mov", "m4v")
SCAN_ROOTS = ["index.html", "pages", "assets", "data"]

# Lightweight path matcher to avoid catastrophic backtracking on long lines.
PATH_RE = re.compile(
    r"(?P<raw>[^\"'\)\(\s]+\.(?:"
    + "|".join(MEDIA_EXTS)
    + r")(?:\?[^\"'\)\s#]*)?(?:#[^\"'\)\s]+)?)",
    re.IGNORECASE,
)


def load_mapping() -> Dict[str, str]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    mapping: Dict[str, str] = {}
    for row in payload:
        old_path = str(row["old_path"]).strip().replace("\\", "/")
        new_path = str(row["new_path"]).strip().replace("\\", "/")
        if old_path and new_path:
            mapping[old_path] = "/cdn_assets/" + new_path
    return mapping


def split_path_query_fragment(token: str) -> Tuple[str, str]:
    q_idx = token.find("?")
    f_idx = token.find("#")
    cut = -1
    if q_idx >= 0 and f_idx >= 0:
        cut = min(q_idx, f_idx)
    elif q_idx >= 0:
        cut = q_idx
    elif f_idx >= 0:
        cut = f_idx
    if cut < 0:
        return token, ""
    return token[:cut], token[cut:]


def is_remote_or_data(path_token: str) -> bool:
    p = path_token.lower()
    return (
        p.startswith("http://")
        or p.startswith("https://")
        or p.startswith("//")
        or p.startswith("data:")
        or p.startswith("blob:")
        or p.startswith("javascript:")
    )


def resolve_to_repo_rel(file_rel: str, local_path: str) -> str:
    normalized = local_path.replace("\\", "/")
    if normalized.startswith("/"):
        return normalized.lstrip("/")
    for root_prefix in ("assets/", "pages/", "data/", "pic/"):
        if normalized.startswith(root_prefix):
            return normalized
    base_dir = posixpath.dirname(file_rel)
    combined = posixpath.normpath(posixpath.join(base_dir, normalized))
    # Prevent escaping the repo root in normalization logic.
    while combined.startswith("../"):
        combined = combined[3:]
    if combined == ".":
        return ""
    return combined


def iter_text_files():
    for root in SCAN_ROOTS:
        p = ROOT / root
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() in TEXT_EXTS:
                rel = p.resolve().relative_to(ROOT.resolve()).as_posix()
                yield p, rel
            continue
        for fp in p.rglob("*"):
            if not fp.is_file():
                continue
            if fp.suffix.lower() not in TEXT_EXTS:
                continue
            rel = fp.resolve().relative_to(ROOT.resolve()).as_posix()
            if rel.startswith("cdn_assets/"):
                continue
            yield fp, rel


def rewrite_text(content: str, file_rel: str, mapping: Dict[str, str]) -> Tuple[str, int]:
    changed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal changed
        raw = match.group("raw")
        if is_remote_or_data(raw):
            return raw
        path_only, suffix = split_path_query_fragment(raw)
        old_rel = resolve_to_repo_rel(file_rel, path_only)
        if not old_rel:
            return raw
        new_abs = mapping.get(old_rel)
        if not new_abs:
            return raw
        changed += 1
        return new_abs + suffix

    return PATH_RE.sub(_replace, content), changed


def main() -> int:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest not found: {MANIFEST_PATH}")

    mapping = load_mapping()
    if not mapping:
        raise SystemExit("Empty mapping from manifest.")

    changed_files = 0
    replaced_tokens = 0

    for fp, rel in iter_text_files():
        try:
            src = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        dst, changed = rewrite_text(src, rel, mapping)
        if changed > 0 and dst != src:
            fp.write_text(dst, encoding="utf-8")
            changed_files += 1
            replaced_tokens += changed

    summary = {
        "changed_files": changed_files,
        "replaced_tokens": replaced_tokens,
        "manifest_mappings": len(mapping),
    }
    ensure_legacy_cdn_placeholders()
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def ensure_legacy_cdn_placeholders() -> None:
    """
    Ensure old-style legacy decorative assets exist in CDN output.
    These files are referenced by historical CSS and were not present in source media.
    """
    out_dir = ROOT / "cdn_assets" / "images" / "external-cache" / "www.hnmetachip.cn"
    out_dir.mkdir(parents=True, exist_ok=True)

    transparent_gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")
    white_jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBUQEBAVFhUVFRUVFRUVFRUVFRUVFRUWFhUVFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0fHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/xAAXAAEBAQEAAAAAAAAAAAAAAAABAgAD/8QAFhEBAQEAAAAAAAAAAAAAAAAAAQAC/9oADAMBAAIQAxAAAAHjA//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCcf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8BJ//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8BJ//Z"
    )

    for name in ("bar.gif", "invbar.gif", "newstitle.gif", "jiantou.gif", "icon_onload.gif"):
        target = out_dir / name
        if not target.exists():
            target.write_bytes(transparent_gif)

    for name in ("case_ban.jpg", "yy_jishu.jpg"):
        target = out_dir / name
        if not target.exists():
            target.write_bytes(white_jpeg)


if __name__ == "__main__":
    raise SystemExit(main())
