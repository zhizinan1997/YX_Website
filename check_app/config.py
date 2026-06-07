from __future__ import annotations

import os
import secrets
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]

CHECK_DATA_DIR = Path(os.environ.get("CHECK_DATA_DIR", APP_ROOT / "check_data")).resolve()
MAIN_DATA_DIR = Path(os.environ.get("CHECK_MAIN_DATA_DIR", APP_ROOT / "data")).resolve()

DEFAULT_CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "3600"))
DEFAULT_TARGET_TIMEOUT_MS = int(os.environ.get("CHECK_TARGET_TIMEOUT_MS", "25000"))
DATA_RETENTION_DAYS = int(os.environ.get("CHECK_RETENTION_DAYS", "90"))
PUBLIC_WINDOW_HOURS = int(os.environ.get("CHECK_PUBLIC_WINDOW_HOURS", "24"))

AUTH_CODE_EXPIRES_SECONDS = int(os.environ.get("CHECK_AUTH_CODE_EXPIRES_SECONDS", "300"))
AUTH_CODE_RESEND_COOLDOWN_SECONDS = int(os.environ.get("CHECK_AUTH_CODE_RESEND_COOLDOWN_SECONDS", "60"))
AUTH_CODE_MAX_VERIFY_FAILURES = int(os.environ.get("CHECK_AUTH_CODE_MAX_VERIFY_FAILURES", "5"))
SESSION_MAX_AGE_SECONDS = int(os.environ.get("CHECK_SESSION_MAX_AGE_SECONDS", "7200"))

RETRY_DELAYS_SECONDS = (
    int(os.environ.get("CHECK_RETRY_DELAY_1_SECONDS", "60")),
    int(os.environ.get("CHECK_RETRY_DELAY_2_SECONDS", "120")),
)

SECRET_KEY = os.environ.get("CHECK_SECRET_KEY") or secrets.token_urlsafe(48)
SCHEDULER_ENABLED = os.environ.get("CHECK_SCHEDULER_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
DEV_LOGIN_ENABLED = os.environ.get("CHECK_DEV_LOGIN_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
DEV_LOGIN_EMAIL = os.environ.get("CHECK_DEV_LOGIN_EMAIL", "local-admin@check.local").strip().lower()

DEFAULT_TARGETS = [
    ("官网首页", "https://www.hnmetachip.cn/"),
    ("生化传感事业部", "https://www.hnmetachip.cn/pages/biosensing/index.html?filter=sensor"),
    ("先进氢气传感解决方案", "https://www.hnmetachip.cn/pages/gassensing/index.html"),
    ("解决方案", "https://www.hnmetachip.cn/pages/solutions/solutions-index.html"),
    ("洞察与资讯", "https://www.hnmetachip.cn/pages/news/news.html"),
    ("公司简介", "https://www.hnmetachip.cn/pages/about/about.html"),
    ("联系我们", "https://www.hnmetachip.cn/pages/contact/contact.html"),
]
