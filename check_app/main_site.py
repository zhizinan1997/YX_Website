from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import MAIN_DATA_DIR

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


@dataclass(frozen=True)
class SmtpSettings:
    configured: bool
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    use_tls: bool = False
    from_name: str = "元芯传感监测站"
    from_email: str = ""


@dataclass(frozen=True)
class TurnstileSettings:
    enabled: bool
    site_key: str = ""
    secret_key: str = ""


def _load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_main_config(main_data_dir: Path | None = None) -> dict:
    data_dir = Path(main_data_dir or MAIN_DATA_DIR)
    return _load_json(data_dir / "config.json")


def load_main_users(main_data_dir: Path | None = None) -> list[dict]:
    data_dir = Path(main_data_dir or MAIN_DATA_DIR)
    payload = _load_json(data_dir / "admin_users.json")
    users = payload.get("users", [])
    return [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []


def bool_from_config(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def get_smtp_settings(main_data_dir: Path | None = None) -> SmtpSettings:
    cfg = load_main_config(main_data_dir)
    host = str(cfg.get("smtp_host") or "").strip()
    username = str(cfg.get("smtp_username") or "").strip()
    password = str(cfg.get("smtp_password_or_app_code") or "").strip()
    from_email = str(cfg.get("smtp_from_email") or "").strip() or username
    from_name = str(cfg.get("smtp_from_name") or "").strip() or "元芯传感监测站"
    try:
        port = int(str(cfg.get("smtp_port") or "465").strip())
    except Exception:
        port = 465
    settings = SmtpSettings(
        configured=bool(host and port > 0 and username and password and from_email),
        host=host,
        port=port,
        username=username,
        password=password,
        use_ssl=bool_from_config(cfg.get("smtp_use_ssl"), True),
        use_tls=bool_from_config(cfg.get("smtp_use_tls"), False),
        from_name=from_name,
        from_email=from_email,
    )
    return settings


def get_turnstile_settings(main_data_dir: Path | None = None) -> TurnstileSettings:
    cfg = load_main_config(main_data_dir)
    site_key = str(cfg.get("turnstile_site_key") or "").strip()
    secret_key = str(cfg.get("turnstile_secret_key") or "").strip()
    enabled = bool_from_config(cfg.get("turnstile_enabled"), False)
    if enabled and (not site_key or not secret_key):
        enabled = False
    return TurnstileSettings(enabled=enabled, site_key=site_key, secret_key=secret_key)


def verify_turnstile_token(secret_key: str, token: str, remote_ip: str = "") -> tuple[bool, str]:
    secret_key = str(secret_key or "").strip()
    token = str(token or "").strip()
    if not secret_key:
        return False, "人机验证密钥缺失"
    if not token:
        return False, "请先完成人机验证"

    payload = {"secret": secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    req = Request(
        TURNSTILE_VERIFY_URL,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        result = json.loads(body) if body else {}
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False, "人机验证服务请求失败，请稍后重试"

    if bool(result.get("success")):
        return True, ""

    codes = result.get("error-codes") or []
    if isinstance(codes, list):
        code_text = ",".join(str(item) for item in codes if item)
    else:
        code_text = str(codes or "").strip()
    if code_text:
        return False, "人机验证校验未通过，请重新验证"
    return False, "人机验证校验未通过"


def get_verified_admins(main_data_dir: Path | None = None) -> list[dict]:
    admins = []
    for user in load_main_users(main_data_dir):
        role = str(user.get("role") or "").strip()
        email = str(user.get("email") or "").strip().lower()
        enabled = bool_from_config(user.get("enabled"), True)
        if role not in {"super_admin", "sub_admin"}:
            continue
        if not enabled or not email or "@" not in email:
            continue
        if not bool_from_config(user.get("email_verified"), False):
            continue
        admins.append(
            {
                "username": str(user.get("username") or "").strip(),
                "role": role,
                "email": email,
                "permissions": user.get("permissions", []) if isinstance(user.get("permissions"), list) else [],
            }
        )
    return admins


def get_verified_admin_emails(main_data_dir: Path | None = None) -> list[str]:
    emails = []
    for user in get_verified_admins(main_data_dir):
        email = user["email"]
        if email not in emails:
            emails.append(email)
    return emails


def find_verified_admin_by_email(email: str, main_data_dir: Path | None = None) -> dict | None:
    normalized = str(email or "").strip().lower()
    if not normalized:
        return None
    for user in get_verified_admins(main_data_dir):
        if user["email"] == normalized:
            return user
    return None
