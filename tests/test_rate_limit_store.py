from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.rate_limit_store as rate_limit_store


class RateLimitStoreWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "rate_limits.json"
        patcher = mock.patch.object(rate_limit_store, "RATE_LIMIT_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_short_window_traffic_does_not_prune_long_window_bucket(self):
        # contact 桶（1 小时窗口）先记录一次。
        allowed, _, count = rate_limit_store.check_and_record("contact:1.2.3.4", limit=5, window=3600)
        self.assertTrue(allowed)
        self.assertEqual(count, 1)
        # analytics 桶（60 秒窗口）持续触发全局清理。
        for _ in range(6):
            rate_limit_store.check_and_record("analytics:1.2.3.4", limit=5, window=60)
            # 强制下一次调用重新触发清理分支。
            rate_limit_store._last_cleanup = 0.0
        data = json.loads(self.file.read_text())
        self.assertIn("contact:1.2.3.4", data, "长窗口桶不应被短窗口清理误删")
        snapshot = rate_limit_store.get_snapshot("contact:1.2.3.4", 3600)
        self.assertEqual(snapshot[0], 1)

    def test_limit_is_enforced_per_bucket(self):
        for i in range(3):
            allowed, _, _ = rate_limit_store.check_and_record("preflight:ip", limit=3, window=60)
            self.assertTrue(allowed)
        allowed, retry_after, count = rate_limit_store.check_and_record("preflight:ip", limit=3, window=60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        self.assertEqual(count, 3)

    def test_legacy_list_entries_are_migrated(self):
        import time as time_module

        now = time_module.time()
        self.file.write_text(json.dumps({"legacy:ip": [now - 10]}))
        count, _retry_after = rate_limit_store.get_snapshot("legacy:ip", 60)
        self.assertEqual(count, 1)
        # 触发一次记录后应迁移为 dict 结构。
        rate_limit_store.check_and_record("legacy:ip", limit=10, window=60)
        entry = json.loads(self.file.read_text())["legacy:ip"]
        self.assertIsInstance(entry, dict)
        self.assertIn("w", entry)

    def test_stale_timestamps_within_own_window_are_counted(self):
        import time as time_module

        now = time_module.time()
        # 两个桶各自窗口差异巨大：短窗口的旧记录过期，长窗口的仍然有效。
        self.file.write_text(json.dumps({
            "short:ip": {"w": 60, "ts": [now - 120]},
            "long:ip": {"w": 3600, "ts": [now - 120]},
        }))
        self.assertEqual(rate_limit_store.get_snapshot("short:ip", 60)[0], 0)
        self.assertEqual(rate_limit_store.get_snapshot("long:ip", 3600)[0], 1)


if __name__ == "__main__":
    unittest.main()
