"""WebAuthn/Passkey storage and protocol helpers for the admin console."""

from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


UTC = timezone.utc
_INIT_LOCK = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat(timespec="seconds")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    raw = str(value or "").encode("ascii")
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


@dataclass(frozen=True)
class PasskeyConfig:
    enabled: bool
    rp_id: str
    rp_name: str
    origin: str
    db_path: Path
    challenge_ttl_seconds: int
    max_credentials_per_user: int
    error: str = ""


def load_passkey_config(project_root: Path, public_base_url: str = "", settings=None) -> PasskeyConfig:
    saved = settings if isinstance(settings, dict) else {}
    enabled_source = os.environ.get("PASSKEY_ENABLED")
    if enabled_source is None:
        enabled_source = saved.get("passkey_enabled", False)
    requested = str(enabled_source or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    base_url = str(
        public_base_url
        or os.environ.get("PUBLIC_BASE_URL", "")
        or "https://hnmetachip.cn"
    ).strip().rstrip("/")
    origin = str(os.environ.get("PASSKEY_ORIGIN", "") or "").strip().rstrip("/") or base_url
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower().rstrip(".")
    rp_id = str(os.environ.get("PASSKEY_RP_ID", "") or "").strip().lower().rstrip(".") or host
    rp_name = str(os.environ.get("PASSKEY_RP_NAME", "元芯传感管理后台") or "").strip() or "元芯传感管理后台"
    db_path = Path(os.environ.get("PASSKEY_DB_PATH", "") or (Path(project_root) / "data" / "admin_passkeys.sqlite3"))
    try:
        ttl = max(60, min(900, int(os.environ.get("PASSKEY_CHALLENGE_TTL_SECONDS", "300"))))
    except Exception:
        ttl = 300
    maximum_source = os.environ.get("PASSKEY_MAX_CREDENTIALS_PER_USER")
    if maximum_source is None:
        maximum_source = saved.get("passkey_max_credentials_per_user", 10)
    try:
        maximum = max(1, min(50, int(maximum_source)))
    except Exception:
        maximum = 10

    error = ""
    if requested:
        if not origin or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or not host:
            error = "PASSKEY_ORIGIN 必须是完整且不包含路径的 Origin"
        elif parsed.scheme != "https" and not (parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}):
            error = "Passkey 生产环境必须使用 HTTPS（仅 localhost 可使用 HTTP）"
        elif rp_id != host and not host.endswith("." + rp_id):
            error = "PASSKEY_RP_ID 必须是当前主机名或其父域"
    return PasskeyConfig(
        enabled=bool(requested and not error),
        rp_id=rp_id,
        rp_name=rp_name,
        origin=origin,
        db_path=db_path,
        challenge_ttl_seconds=ttl,
        max_credentials_per_user=maximum,
        error=error,
    )


class PasskeyStore:
    def __init__(self, config: PasskeyConfig):
        self.config = config

    @contextmanager
    def _connect(self):
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.config.db_path), timeout=5.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        if not self.config.enabled:
            return
        with _INIT_LOCK, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS passkey_users (
                    username TEXT PRIMARY KEY,
                    user_handle TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS passkey_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    credential_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    user_handle TEXT NOT NULL,
                    public_key BLOB NOT NULL,
                    sign_count INTEGER NOT NULL DEFAULT 0,
                    transports_json TEXT NOT NULL DEFAULT '[]',
                    backup_eligible INTEGER NOT NULL DEFAULT 0,
                    backup_state INTEGER NOT NULL DEFAULT 0,
                    device_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    last_used_ip TEXT,
                    revoked_at TEXT,
                    revoked_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_passkey_credentials_username
                    ON passkey_credentials(username, revoked_at);
                CREATE TABLE IF NOT EXISTS passkey_challenges (
                    id TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL,
                    challenge TEXT NOT NULL,
                    username TEXT,
                    session_binding TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_passkey_challenges_expiry
                    ON passkey_challenges(expires_at);
                CREATE TABLE IF NOT EXISTS passkey_rate_limits (
                    ip_addr TEXT NOT NULL,
                    bucket INTEGER NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY(ip_addr, bucket)
                );
                """
            )
            try:
                os.chmod(self.config.db_path, 0o600)
            except OSError:
                pass

    def check_rate_limit(self, ip_addr: str, limit: int = 10) -> bool:
        bucket = int(_utc_now().timestamp()) // 60
        with self._connect() as conn:
            conn.execute("DELETE FROM passkey_rate_limits WHERE bucket < ?", (bucket - 2,))
            row = conn.execute(
                "SELECT request_count FROM passkey_rate_limits WHERE ip_addr=? AND bucket=?",
                (ip_addr, bucket),
            ).fetchone()
            count = int(row["request_count"]) if row else 0
            if count >= limit:
                return False
            conn.execute(
                "INSERT INTO passkey_rate_limits(ip_addr,bucket,request_count) VALUES(?,?,1) "
                "ON CONFLICT(ip_addr,bucket) DO UPDATE SET request_count=request_count+1",
                (ip_addr, bucket),
            )
            return True

    def get_or_create_user_handle(self, username: str) -> bytes:
        with self._connect() as conn:
            row = conn.execute("SELECT user_handle FROM passkey_users WHERE username=?", (username,)).fetchone()
            if row:
                return _b64url_decode(row["user_handle"])
            handle = secrets.token_bytes(32)
            conn.execute(
                "INSERT INTO passkey_users(username,user_handle,created_at) VALUES(?,?,?)",
                (username, _b64url(handle), _iso()),
            )
            return handle

    def create_challenge(self, purpose: str, challenge: bytes, session_binding: str, username: str = "") -> str:
        request_id = secrets.token_urlsafe(24)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM passkey_challenges WHERE expires_at < ? OR (consumed_at IS NOT NULL AND consumed_at < ?)",
                (_iso(now - timedelta(hours=24)), _iso(now - timedelta(hours=24))),
            )
            conn.execute(
                "INSERT INTO passkey_challenges(id,purpose,challenge,username,session_binding,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (request_id, purpose, _b64url(challenge), username or None, session_binding, _iso(now),
                 _iso(now + timedelta(seconds=self.config.challenge_ttl_seconds))),
            )
        return request_id

    def load_challenge(self, request_id: str, purpose: str, session_binding: str, username: str = ""):
        now = _iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM passkey_challenges WHERE id=?", (request_id,)).fetchone()
            if not row or row["purpose"] != purpose or row["session_binding"] != session_binding:
                raise ValueError("请求已失效，请重试")
            if username and (row["username"] or "") != username:
                raise ValueError("请求账号不匹配")
            if row["consumed_at"] or row["expires_at"] <= now:
                raise ValueError("请求已过期，请重试")
            attempts = int(row["attempt_count"] or 0) + 1
            conn.execute("UPDATE passkey_challenges SET attempt_count=? WHERE id=?", (attempts, request_id))
            if attempts > 3:
                conn.execute("UPDATE passkey_challenges SET consumed_at=? WHERE id=?", (now, request_id))
                raise ValueError("验证失败次数过多，请重新发起")
            return _b64url_decode(row["challenge"])

    def consume_challenge(self, request_id: str):
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE passkey_challenges SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                (_iso(), request_id),
            ).rowcount
            if changed != 1:
                raise ValueError("请求已被使用")

    def count_credentials(self, username: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM passkey_credentials WHERE username=? AND revoked_at IS NULL", (username,)
            ).fetchone()
            return int(row["n"])

    def list_credentials(self, username: str):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT credential_id,device_name,transports_json,backup_eligible,backup_state,created_at,last_used_at,last_used_ip "
                "FROM passkey_credentials WHERE username=? AND revoked_at IS NULL ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        return [self._public_credential(row) for row in rows]

    @staticmethod
    def _public_credential(row):
        cid = str(row["credential_id"])
        return {
            "credential_id": cid,
            "credential_fingerprint": f"{cid[:8]}…{cid[-6:]}" if len(cid) > 16 else cid,
            "device_name": row["device_name"],
            "transports": json.loads(row["transports_json"] or "[]"),
            "backup_eligible": bool(row["backup_eligible"]),
            "backup_state": bool(row["backup_state"]),
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"] or "",
            "last_used_ip": row["last_used_ip"] or "",
        }

    def credential_ids(self, username: str):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT credential_id FROM passkey_credentials WHERE username=? AND revoked_at IS NULL", (username,)
            ).fetchall()
        return [_b64url_decode(row["credential_id"]) for row in rows]

    def get_credential(self, credential_id: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM passkey_credentials WHERE credential_id=? AND revoked_at IS NULL", (credential_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_credential(self, *, credential_id: bytes, username: str, user_handle: bytes, public_key: bytes,
                       sign_count: int, transports, backup_eligible: bool, backup_state: bool, device_name: str):
        if self.count_credentials(username) >= self.config.max_credentials_per_user:
            raise ValueError(f"每个账号最多绑定 {self.config.max_credentials_per_user} 个 Passkey")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO passkey_credentials(credential_id,username,user_handle,public_key,sign_count,transports_json,"
                "backup_eligible,backup_state,device_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (_b64url(credential_id), username, _b64url(user_handle), sqlite3.Binary(public_key), int(sign_count or 0),
                 json.dumps(list(transports or []), ensure_ascii=False), int(bool(backup_eligible)), int(bool(backup_state)),
                 device_name, _iso()),
            )

    def update_usage(self, credential_id: str, new_sign_count: int, ip_addr: str, backup_state: bool = False):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT sign_count FROM passkey_credentials WHERE credential_id=? AND revoked_at IS NULL", (credential_id,)
            ).fetchone()
            if not row:
                raise ValueError("Passkey 已失效")
            old = int(row["sign_count"] or 0)
            new = int(new_sign_count or 0)
            if old > 0 and new > 0 and new <= old:
                raise ValueError("检测到 Passkey 计数器异常")
            conn.execute(
                "UPDATE passkey_credentials SET sign_count=?,last_used_at=?,last_used_ip=?,backup_state=? WHERE credential_id=?",
                (new, _iso(), ip_addr, int(bool(backup_state)), credential_id),
            )

    def rename_credential(self, username: str, credential_id: str, device_name: str) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "UPDATE passkey_credentials SET device_name=? WHERE username=? AND credential_id=? AND revoked_at IS NULL",
                (device_name, username, credential_id),
            ).rowcount == 1

    def revoke_credential(self, username: str, credential_id: str, revoked_by: str) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "UPDATE passkey_credentials SET revoked_at=?,revoked_by=? WHERE username=? AND credential_id=? AND revoked_at IS NULL",
                (_iso(), revoked_by, username, credential_id),
            ).rowcount == 1

    def revoke_all(self, username: str, revoked_by: str) -> int:
        with self._connect() as conn:
            return conn.execute(
                "UPDATE passkey_credentials SET revoked_at=?,revoked_by=? WHERE username=? AND revoked_at IS NULL",
                (_iso(), revoked_by, username),
            ).rowcount

    def rename_user(self, old_username: str, new_username: str):
        if old_username == new_username:
            return
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE passkey_users SET username=? WHERE username=?", (new_username, old_username))
            conn.execute("UPDATE passkey_credentials SET username=? WHERE username=?", (new_username, old_username))
            conn.execute("UPDATE passkey_challenges SET username=? WHERE username=?", (new_username, old_username))


def require_webauthn():
    try:
        from webauthn import (  # noqa: F401
            generate_authentication_options,
            generate_registration_options,
            options_to_json,
            verify_authentication_response,
            verify_registration_response,
        )
        return True
    except Exception as exc:
        raise RuntimeError("服务器尚未安装 webauthn 依赖") from exc
