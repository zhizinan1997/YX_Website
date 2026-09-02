"""Small, explicit repairs for text that was previously mis-decoded."""

from __future__ import annotations


# Keep this list exact. Broad re-encoding heuristics can corrupt legitimate
# Chinese content, so only verified sequences belong here.
KNOWN_MOJIBAKE_REPLACEMENTS = {
    "\u93cc\u30e7\u6e45\u7487\ufe3d\u510f": "查看详情",
}


def repair_known_mojibake(value: str) -> str:
    """Replace known mojibake sequences without altering other text."""
    result = str(value or "")
    for broken, readable in KNOWN_MOJIBAKE_REPLACEMENTS.items():
        result = result.replace(broken, readable)
    return result
