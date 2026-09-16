from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LoginCaptchaResetFrontendTests(unittest.TestCase):
    """登录人机验证令牌生命周期回归测试。

    背景：2026-09-15 线上出现“登录成功后换账号立即重登复用已消耗令牌，
    服务端返回 duplicate 并触发延迟保护”。Turnstile 与阿里云 ESA 验证码
    均为一令牌一次有效，前端必须在登录成功/回到登录页时重置。
    """

    def setUp(self):
        self.script = (ROOT / "admin" / "js" / "legacy-admin.js").read_text(encoding="utf-8")

    def test_check_login_status_resets_token_after_login_success(self):
        # 登录成功（showDashboard 前）必须重置验证组件。
        self.assertRegex(
            self.script,
            r"if \(data\.logged_in\) \{[^}]*?setAdminAuthFromCheck\(data\);[^}]*?resetLoginTurnstile\(\);[^}]*?showDashboard\(data\);",
        )

    def test_check_login_status_resets_token_when_back_to_login_page(self):
        # 未登录回到登录页时必须重置验证组件，确保下次拿到全新令牌。
        self.assertRegex(
            self.script,
            r"else \{[^}]*?bindingRequiredState = false;[^}]*?resetLoginTurnstile\(\);",
        )

    def test_aliyun_esa_provider_wiring_present(self):
        # 全量切换 ESA 前确认前端已具备双 provider 能力：
        # ESA 模式走 initAliyunCaptcha + captchaVerifyParam，请求 URL 带验签参数。
        self.assertIn("function renderLoginAliyunCaptcha()", self.script)
        self.assertIn("initAliyunCaptcha", self.script)
        self.assertIn("captchaVerifyParam", self.script)
        self.assertIn("getAdminCaptchaRequestUrl", self.script)
        self.assertIn("aliyunCaptchaInstance.refresh()", self.script)

    def test_turnstile_reset_hook_exposed_for_auth_js(self):
        # auth.js 在鉴权失败时会调用全局 resetLoginTurnstile 钩子。
        auth_js = (ROOT / "admin" / "js" / "auth.js").read_text(encoding="utf-8")
        self.assertIn("window.resetLoginTurnstile", auth_js)


if __name__ == "__main__":
    unittest.main()


class LoginCaptchaResetLoopGuardTests(unittest.TestCase):
    """验证码“完成几秒后被重置重跑”循环的根因修复回归测试。

    根因链：passkeys.js 在 window focus 时请求 email-binding → 未登录 401 →
    api.js 全局 fetch guard 触发 forceRelogin → resetLoginTurnstile →
    人机验证组件被反复重置（公开页无此 guard 故正常）。
    """

    def setUp(self):
        self.api_js = (ROOT / "admin" / "js" / "api.js").read_text(encoding="utf-8")
        self.passkeys_js = (ROOT / "admin" / "js" / "passkeys.js").read_text(encoding="utf-8")

    def test_fetch_guard_skips_force_relogin_when_login_page_visible(self):
        # api.js 的 401 分支必须先判断登录页是否可见。
        self.assertIn("loginPageVisible", self.api_js)
        self.assertIn("getElementById('loginPage')", self.api_js)
        self.assertRegex(
            self.api_js,
            r"if \(!loginPageVisible && window\.Admin2Auth",
        )

    def test_security_onboarding_loop_source_removed(self):
        # 2026-09-15 起整条引导横幅链路已删除（运营决定）：
        # focus → email-binding 401 → forceRelogin → 验证码重置 的循环
        # 源头不复存在；api.js 的登录页豁免仍作为第二道防线保留。
        self.assertNotIn("loadSecurityOnboarding", self.passkeys_js)
        self.assertNotIn("window.addEventListener('focus'", self.passkeys_js)
        self.assertNotIn("email-binding", self.passkeys_js)




class LoginMergedActionButtonTests(unittest.TestCase):
    """登录页按钮合并回归测试：
    单按钮——未发送验证码时为“发送验证码”，发送后变为“验证并登录”。
    """

    def setUp(self):
        self.html = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
        self.script = (ROOT / "admin" / "js" / "legacy-admin.js").read_text(encoding="utf-8")

    def test_send_button_removed_from_html(self):
        self.assertNotIn('id="loginSendCodeBtn"', self.html)
        self.assertIn('id="loginSubmitBtn"', self.html)

    def test_update_action_state_merges_send_and_verify(self):
        # 快捷邮箱模式：未发码 → 发送验证码；进入验证码步骤 → 验证并登录。
        self.assertIn("inCodeStep ? '验证并登录' : '发送验证码'", self.script)
        # 发送期间禁用提交按钮（原 sendBtn 禁用逻辑已迁移）。
        self.assertIn("const submitBtn = document.getElementById('loginSubmitBtn');\n            if (submitBtn) submitBtn.disabled = true;", self.script)
        self.assertNotIn("getElementById('loginSendCodeBtn')", self.script)

    def test_expired_pending_returns_to_send_state(self):
        # 验证码过期/待验证记录失效时清除 pending，按钮回到“发送验证码”。
        self.assertRegex(self.script, r"if \(/过期\|失效\|已用完/\.test\(reason\)\) \{\s*resetPendingLoginState\(\);")


class PasskeyBottomLogoButtonTests(unittest.TestCase):
    """Passkey 登录移至表单下方并呈现为 logo 图标按钮。"""

    def setUp(self):
        self.html = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
        self.css = (ROOT / "admin" / "styles" / "components.css").read_text(encoding="utf-8")

    def test_passkey_wrap_below_login_form(self):
        form_pos = self.html.find('id="loginForm"')
        wrap_pos = self.html.find('id="passkeyLoginWrap"')
        self.assertGreater(wrap_pos, form_pos, "passkeyLoginWrap 必须位于登录表单之后")

    def test_passkey_button_is_icon_only(self):
        self.assertIn("passkey-login-btn passkey-login-btn-icon", self.html)
        self.assertNotIn("使用 Passkey 登录</strong>", self.html)
        self.assertIn('aria-label="使用 Passkey 登录"', self.html)

    def test_icon_button_styles_present(self):
        self.assertIn(".passkey-login-btn-icon", self.css)
        self.assertIn("border-radius:50%", self.css)


class AdminJsSyntaxTests(unittest.TestCase):
    """admin 前端 JS 语法回归测试：任何文件必须能通过 node --check。

    背景：一次编辑在 updateLoginActionState 中重复声明 const codeWrap，
    语法错误导致整个 legacy-admin.js 失效——人机验证不渲染、发送按钮
    无响应、Passkey 登录成功后无法跳转（三个症状同源）。
    """

    def test_all_admin_js_parse_ok(self):
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        root = ROOT / "admin" / "js"
        failures = []
        for js in sorted(root.rglob("*.js")):
            result = subprocess.run(
                [node, "--check", str(js)], capture_output=True, text=True
            )
            if result.returncode != 0:
                failures.append(f"{js.name}: {result.stderr.strip()[:300]}")
        self.assertEqual(failures, [], "存在语法错误的 admin JS 文件")
