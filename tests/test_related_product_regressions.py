from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_page_uses_shared_related_product_loader():
    page = (ROOT / "pages/gassensing/mc_mgm_01.html").read_text(encoding="utf-8")

    assert "relatedProductIds" not in page
    assert "/assets/js/nav-loader.js" in page

