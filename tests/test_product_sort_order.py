from __future__ import annotations

import unittest

from app.routes.product_settings import _apply_sort_order


class ProductSortOrderTests(unittest.TestCase):
    def test_applies_contiguous_sort_order(self):
        settings = {
            "product-a": {"sortOrder": 8},
            "product-b": {"sortOrder": 2},
            "product-c": {},
        }

        updated, error = _apply_sort_order(settings, ["product-c", "product-a", "product-b"])

        self.assertIsNone(error)
        self.assertEqual(updated["product-c"]["sortOrder"], 0)
        self.assertEqual(updated["product-a"]["sortOrder"], 1)
        self.assertEqual(updated["product-b"]["sortOrder"], 2)

    def test_rejects_duplicate_product_ids(self):
        updated, error = _apply_sort_order({}, ["product-a", "product-a"])

        self.assertIsNone(updated)
        self.assertEqual(error, ("排序数据包含重复产品", 400))

    def test_rejects_empty_product_ids(self):
        updated, error = _apply_sort_order({}, ["product-a", ""])

        self.assertIsNone(updated)
        self.assertEqual(error, ("排序数据包含无效产品", 400))


if __name__ == "__main__":
    unittest.main()
