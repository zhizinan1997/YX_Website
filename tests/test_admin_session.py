from __future__ import annotations

import unittest

from flask import Flask, request

from app.admin_session import is_admin_session_expired, maybe_refresh_admin_session
from app.app_config import (
    ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
)


class AdminSessionTests(unittest.TestCase):
    def test_idle_timeout_uses_last_active_time(self):
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1200,
            "admin_session_ttl": 100,
            "admin_session_absolute_ttl": 1000,
        }

        self.assertFalse(is_admin_session_expired(sess, now_ts=1299))
        self.assertTrue(is_admin_session_expired(sess, now_ts=1301))

    def test_absolute_timeout_does_not_slide(self):
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1290,
            "admin_session_ttl": 500,
            "admin_session_absolute_ttl": 300,
        }

        self.assertTrue(is_admin_session_expired(sess, now_ts=1301))

    def test_refresh_requires_activity_header(self):
        app = Flask(__name__)
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1100,
            "admin_session_ttl": 500,
            "admin_session_absolute_ttl": 1000,
        }

        with app.test_request_context("/api/admin/example"):
            self.assertFalse(maybe_refresh_admin_session(sess, request, now_ts=1200))
        self.assertEqual(sess["admin_last_active_at"], 1100)

    def test_refresh_updates_last_active_and_ttls(self):
        app = Flask(__name__)
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1100,
            "admin_session_ttl": 500,
            "admin_session_absolute_ttl": 1000,
        }

        with app.test_request_context("/api/admin/example", headers={"X-Admin-User-Active": "1"}):
            self.assertTrue(maybe_refresh_admin_session(sess, request, now_ts=1200))

        self.assertEqual(sess["admin_last_active_at"], 1200)
        self.assertEqual(sess["admin_session_ttl"], ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)
        self.assertEqual(sess["admin_session_absolute_ttl"], ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS)

    def test_refresh_is_throttled(self):
        app = Flask(__name__)
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1190,
            "admin_session_ttl": 500,
            "admin_session_absolute_ttl": 1000,
        }

        with app.test_request_context("/api/admin/example", headers={"X-Admin-User-Active": "1"}):
            self.assertFalse(maybe_refresh_admin_session(sess, request, now_ts=1200))

        self.assertEqual(sess["admin_last_active_at"], 1190)


if __name__ == "__main__":
    unittest.main()
