from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PasskeyFrontendTests(unittest.TestCase):
    def test_admin_page_exposes_passkey_login_and_device_management(self):
        html = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="passkeyLoginBtn"', html)
        self.assertIn('id="passkeySecurityCard"', html)
        self.assertIn('id="passkeyAdminSettingsForm"', html)
        self.assertIn('id="passkeyAdminEnabled"', html)
        self.assertIn('/admin/js/passkeys.js', html)

    def test_frontend_only_opens_webauthn_after_user_actions(self):
        script = (ROOT / "admin" / "js" / "passkeys.js").read_text(encoding="utf-8")
        self.assertIn("passkeyLoginBtn')?.addEventListener('click', runPasskeyLogin", script)
        self.assertNotIn("navigator.credentials.get({ publicKey: prepareOptions(start.options) });\n    loadPublicConfig", script)
        self.assertIn("navigator.credentials.create", script)

    def test_security_onboarding_banner_removed(self):
        # 2026-09-15 运营决定：移除后台“完善登录安全设置（可选）”引导横幅，
        # 相关渲染、跳转、focus 轮询与样式一并删除，防止回归。
        script = (ROOT / "admin" / "js" / "passkeys.js").read_text(encoding="utf-8")
        css = (ROOT / "admin" / "styles" / "components.css").read_text(encoding="utf-8")
        self.assertNotIn("securityOnboardingBanner", script)
        self.assertNotIn("renderSecurityOnboarding", script)
        self.assertNotIn("loadSecurityOnboarding", script)
        self.assertNotIn("jumpToSecurityCard", script)
        self.assertNotIn("稍后处理", script)
        self.assertNotIn("security-onboarding", css)


if __name__ == "__main__":
    unittest.main()
