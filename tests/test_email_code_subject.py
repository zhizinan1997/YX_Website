from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.routes.admin import _build_login_email_subject_v2


class EmailCodeSubjectTests(unittest.TestCase):
    """验证码邮件主题回归测试：主题中必须带【验证码】，无需打开邮件即可见。"""

    def test_subject_contains_code(self):
        self.assertEqual(_build_login_email_subject_v2('483920'), '元芯验证码：【483920】')

    def test_subject_without_code_falls_back(self):
        self.assertEqual(_build_login_email_subject_v2(), '元芯验证码')
        self.assertEqual(_build_login_email_subject_v2(''), '元芯验证码')

    def test_login_and_binding_send_sites_pass_code(self):
        script = (REPO_ROOT / "app" / "routes" / "admin.py").read_text(encoding="utf-8")
        self.assertIn("subject=_build_login_email_subject_v2(code_to_send)", script)
        self.assertIn("subject=_build_login_email_subject_v2(code)", script)
        # 不再存在不带验证码的固定“元芯验证码”发码主题
        self.assertNotIn("subject='元芯验证码'", script)


if __name__ == '__main__':
    unittest.main()
