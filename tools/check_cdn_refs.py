#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("index.html", "pages", "assets", "data", "admin", "server.py")
TEXT_EXTS = {".html", ".css", ".js", ".json", ".py", ".md", ".txt"}
CDN_PATH_RE = re.compile(r"(?P<path>/cdn_assets/[^\s\"'()<>{}]+)", re.IGNORECASE)


def iter_scan_files():
    for root in SCAN_ROOTS:
        path = ROOT / root
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for fp in path.rglob("*"):
            if not fp.is_file():
                continue
            if fp.suffix.lower() not in TEXT_EXTS:
                continue
            yield fp


def split_suffix(token: str) -> tuple[str, str]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check /cdn_assets references and local file existence.")
    parser.add_argument(
        "--output",
        default="docs/cdn_health_report.json",
        help="Output report path, default: docs/cdn_health_report.json",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=50,
        help="Max number of sample refs/missing refs kept in report.",
    )
    args = parser.parse_args()

    total_files = 0
    files_with_refs = 0
    total_refs = 0
    unique_paths = set()
    missing_paths = set()
    ref_samples = []

    for fp in iter_scan_files():
        total_files += 1
        rel = fp.resolve().relative_to(ROOT.resolve()).as_posix()
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        matches = list(CDN_PATH_RE.finditer(text))
        if not matches:
            continue

        files_with_refs += 1
        for m in matches:
            total_refs += 1
            token = m.group("path")
            base_path, _ = split_suffix(token)
            if "..." in base_path or "*" in base_path:
                continue
            unique_paths.add(base_path)

            fs_path = ROOT / base_path.lstrip("/")
            if not fs_path.exists():
                missing_paths.add(base_path)

            if len(ref_samples) < max(1, args.sample_limit):
                line_no = text.count("\n", 0, m.start()) + 1
                ref_samples.append(
                    {
                        "file": rel,
                        "line": line_no,
                        "ref": token,
                        "exists": fs_path.exists(),
                    }
                )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_roots": list(SCAN_ROOTS),
        "files_scanned": total_files,
        "files_with_cdn_refs": files_with_refs,
        "cdn_ref_total": total_refs,
        "cdn_ref_unique_paths": len(unique_paths),
        "cdn_ref_missing_paths": len(missing_paths),
        "all_cdn_refs_exist": len(missing_paths) == 0,
        "missing_paths_sample": sorted(missing_paths)[: max(1, args.sample_limit)],
        "reference_samples": ref_samples,
    }

    out_path = (ROOT / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
