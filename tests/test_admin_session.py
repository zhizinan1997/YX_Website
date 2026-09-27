from __future__ import annotations

import unittest

from flask import Flask, request, session

from app.admin_session import (
    ADMIN_SESSION_PERSISTENT_KEY,
    is_admin_session_expired,
    is_persistent_admin_session,
    maybe_refresh_admin_session,
    session_ttls_for,
)
from app.app_config import (
    ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
    ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS as REMEMBER_ME,
)
from app.routes.admin import (
    _clear_admin_session,
    _read_remember_me_flag,
    _set_logged_in_session,
)

DAY_SECONDS = 86400


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


class RememberMeTierTests(unittest.TestCase):
    """登录页「N 天内免登录」档位（admin_session.session_ttls_for）。"""

    LOGIN_AT = 1_000_000

    def _persistent_session(self):
        idle_ttl, absolute_ttl = session_ttls_for(True)
        return {
            "admin_logged_in": True,
            "admin_login_at": self.LOGIN_AT,
            "admin_last_active_at": self.LOGIN_AT,
            "admin_session_ttl": idle_ttl,
            "admin_session_absolute_ttl": absolute_ttl,
            ADMIN_SESSION_PERSISTENT_KEY: True,
        }

    def test_tier_durations(self):
        self.assertEqual(session_ttls_for(True), (REMEMBER_ME, REMEMBER_ME))
        self.assertEqual(
            session_ttls_for(False),
            (ADMIN_SESSION_IDLE_TIMEOUT_SECONDS, ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS),
        )

    def test_remember_me_is_never_shorter_than_default(self):
        # 勾了「免登录」反而比不勾更容易掉线，是最糟的失败形态。
        idle_ttl, absolute_ttl = session_ttls_for(True)
        self.assertGreaterEqual(idle_ttl, ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)
        self.assertGreaterEqual(absolute_ttl, ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS)

    def test_missing_flag_falls_back_to_default_tier(self):
        # 改动之前签发的 cookie 里没有这个键，必须继续按默认档判定，
        # 否则等于强制所有在线用户重新登录一次。
        sess = {
            "admin_logged_in": True,
            "admin_login_at": 1000,
            "admin_last_active_at": 1000,
            "admin_session_ttl": ADMIN_SESSION_IDLE_TIMEOUT_SECONDS,
            "admin_session_absolute_ttl": ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS,
        }
        self.assertFalse(is_persistent_admin_session(sess))

    def test_survives_long_idle_gap(self):
        sess = self._persistent_session()
        gap = min(20 * DAY_SECONDS, REMEMBER_ME - 1)
        # 这个空档远超默认档的绝对上限，默认档下早就掉线了。
        self.assertGreater(gap, ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS)
        self.assertFalse(is_admin_session_expired(sess, now_ts=self.LOGIN_AT + gap))

    def test_expires_once_window_elapses(self):
        sess = self._persistent_session()
        self.assertFalse(is_admin_session_expired(sess, now_ts=self.LOGIN_AT + REMEMBER_ME))
        self.assertTrue(is_admin_session_expired(sess, now_ts=self.LOGIN_AT + REMEMBER_ME + 1))

    def test_refresh_does_not_downgrade_persistent_session(self):
        """回归保护：活跃续期不能把免登录档重置回默认档。

        否则表现是「勾了免登录，但几小时没用就掉线」——功能静默失效。
        """
        app = Flask(__name__)
        sess = self._persistent_session()
        refreshed_at = self.LOGIN_AT + 30 * 60

        with app.test_request_context("/api/admin/example", headers={"X-Admin-User-Active": "1"}):
            self.assertTrue(maybe_refresh_admin_session(sess, request, now_ts=refreshed_at))

        self.assertEqual(sess["admin_last_active_at"], refreshed_at)
        self.assertEqual(sess["admin_session_ttl"], REMEMBER_ME)
        self.assertEqual(sess["admin_session_absolute_ttl"], REMEMBER_ME)


class RememberMeFlagParsingTests(unittest.TestCase):
    """请求体里的勾选状态解析，任何异常输入都必须收敛成「未勾选」。"""

    def test_truthy_forms(self):
        for value in (True, 1, "1", "true", "TRUE", " on ", "yes"):
            self.assertTrue(_read_remember_me_flag({"remember_me": value}), repr(value))

    def test_falsy_forms(self):
        for value in (False, 0, "", None, "0", "false", "off", "no", "maybe", [], {}, [1]):
            self.assertFalse(_read_remember_me_flag({"remember_me": value}), repr(value))

    def test_camel_case_alias(self):
        self.assertTrue(_read_remember_me_flag({"rememberMe": "1"}))

    def test_missing_or_non_dict_payload(self):
        self.assertFalse(_read_remember_me_flag({}))
        self.assertFalse(_read_remember_me_flag(None))
        self.assertFalse(_read_remember_me_flag("remember_me=1"))


class SetLoggedInSessionPersistenceTests(unittest.TestCase):
    """_set_logged_in_session 必须显式写 session.permanent。

    Flask 把它存成会话里的 "_permanent" 键，而 _clear_admin_session 是逐键 pop，
    清不掉它——漏写就会让「这次没勾」的用户继承上一次的长期 cookie。
    """

    def _app(self):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        return app

    def _login(self, persistent):
        _set_logged_in_session(
            session,
            user={"username": "admin"},
            permissions=[],
            is_super_admin=True,
            is_hidden_admin=False,
            persistent=persistent,
        )

    def test_checked_login_issues_persistent_cookie(self):
        with self._app().test_request_context("/"):
            self._login(True)
            self.assertTrue(session.permanent)
            self.assertEqual(session["admin_session_ttl"], REMEMBER_ME)
            self.assertEqual(session["admin_session_absolute_ttl"], REMEMBER_ME)
            self.assertTrue(session[ADMIN_SESSION_PERSISTENT_KEY])

    def test_unchecked_login_issues_session_cookie(self):
        with self._app().test_request_context("/"):
            self._login(False)
            self.assertFalse(session.permanent)
            self.assertEqual(session["admin_session_ttl"], ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)
            self.assertEqual(session["admin_session_absolute_ttl"], ADMIN_SESSION_ABSOLUTE_MAX_AGE_SECONDS)
            self.assertFalse(session[ADMIN_SESSION_PERSISTENT_KEY])

    def test_next_unchecked_login_drops_stale_permanent_flag(self):
        with self._app().test_request_context("/"):
            self._login(True)
            self.assertTrue(session.permanent)
            self._login(False)
            self.assertFalse(session.permanent)
            self.assertFalse(session[ADMIN_SESSION_PERSISTENT_KEY])
            self.assertEqual(session["admin_session_ttl"], ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)


class ClearAdminSessionTests(unittest.TestCase):
    def test_clear_resets_permanent_cookie_flag(self):
        app = Flask(__name__)
        app.secret_key = "test-secret"
        with app.test_request_context("/"):
            session[ADMIN_SESSION_PERSISTENT_KEY] = True
            session.permanent = True
            _clear_admin_session(session)
            self.assertFalse(session.permanent)
            self.assertNotIn(ADMIN_SESSION_PERSISTENT_KEY, session)


if __name__ == "__main__":
    unittest.main()
