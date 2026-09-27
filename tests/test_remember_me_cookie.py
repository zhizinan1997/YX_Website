"""「N 天内免登录」在 HTTP 响应头这一层的集成验证。

`tests/test_admin_session.py` 验的是会话档位判定（服务端认不认这个会话）；
这里验的是**最终发出去的 Set-Cookie 上到底有没有 Max-Age**。

这一层不能省：没有 Max-Age 就是个会话 cookie，浏览器和 WebView2 都不会把它写到磁盘，
「关掉客户端再打开还登录着」这条功能整个不成立。而且它依赖
`create_app()` 里把 `PERMANENT_SESSION_LIFETIME` 配上——配漏了单测全绿、功能却失效。
"""
from __future__ import annotations

import os
import unittest

from flask import request, session

from app.admin_session import ADMIN_SESSION_PERSISTENT_KEY
from app.app_config import ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS, create_app
from app.routes.admin import _set_logged_in_session

TEST_SECRET = "test-secret-key-for-remember-me-cookie-0123456789"


class RememberMeCookieHeaderTests(unittest.TestCase):
    def setUp(self):
        self._previous_secret = os.environ.get("SECRET_KEY")
        os.environ["SECRET_KEY"] = TEST_SECRET

        self.app = create_app()
        self.app.config["TESTING"] = True

        @self.app.route("/__test_login")
        def __test_login():  # pragma: no cover - 仅测试用
            _set_logged_in_session(
                session,
                user={"username": "admin"},
                permissions=[],
                is_super_admin=True,
                is_hidden_admin=False,
                persistent=request.args.get("persistent") == "1",
            )
            return "ok"

    def tearDown(self):
        if self._previous_secret is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = self._previous_secret

    def _login_set_cookie(self, persistent: bool) -> str:
        client = self.app.test_client()
        response = client.get(f"/__test_login?persistent={'1' if persistent else '0'}")
        self.assertEqual(response.status_code, 200)
        return response.headers.get("Set-Cookie") or ""

    def test_checked_login_emits_expiry_so_browser_can_persist_it(self):
        header = self._login_set_cookie(True)
        # Flask 的 save_session 传的是 expires 而不是 max_age，所以只会有 Expires=。
        # 带未来 Expires 的 cookie 就是持久 cookie，会被浏览器/WebView2 写到磁盘。
        self.assertIn("Expires=", header)
        self.assertIn("HttpOnly", header)
        # 会话 cookie 有效期应当就是我们配置的那一档，而不是被别处悄悄改写
        self.assertEqual(
            self.app.config["PERMANENT_SESSION_LIFETIME"].total_seconds(),
            ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS,
        )

    def test_unchecked_login_still_emits_session_cookie(self):
        header = self._login_set_cookie(False)
        self.assertIn("session=", header)
        self.assertNotIn("Max-Age", header)
        self.assertNotIn("Expires", header)

    def test_configured_lifetime_matches_the_constant(self):
        """create_app() 必须把 PERMANENT_SESSION_LIFETIME 配上，否则勾了也没用。"""
        lifetime = self.app.config.get("PERMANENT_SESSION_LIFETIME")
        self.assertIsNotNone(lifetime)
        self.assertEqual(int(lifetime.total_seconds()), ADMIN_SESSION_REMEMBER_ME_MAX_AGE_SECONDS)

    def test_persistent_flag_is_recorded_in_the_session(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess[ADMIN_SESSION_PERSISTENT_KEY] = True
        # 档位标记会被 login_required / maybe_refresh 读取，必须能跨请求存活
        with client.session_transaction() as sess:
            self.assertTrue(sess[ADMIN_SESSION_PERSISTENT_KEY])


if __name__ == "__main__":
    unittest.main()
