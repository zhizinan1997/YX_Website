from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .time_utils import days_ago, hours_ago, iso_now, now_utc, parse_iso, seconds_from_now


DB_NAME = "check_site.sqlite3"


def db_path(data_dir: Path | None = None) -> Path:
    root = Path(data_dir or config.CHECK_DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / DB_NAME


def connect(data_dir: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(data_dir), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def managed_connection(data_dir: Path | None = None):
    conn = connect(data_dir)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(data_dir: Path | None = None) -> None:
    with managed_connection(data_dir) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                interval_seconds INTEGER NOT NULL DEFAULT 3600,
                timeout_ms INTEGER NOT NULL DEFAULT 25000,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                next_check_at TEXT,
                last_checked_at TEXT,
                last_status TEXT,
                last_latency_ms INTEGER,
                last_error TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                incident_open INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS check_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                target_name TEXT NOT NULL,
                url TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                trigger TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 1,
                http_status INTEGER,
                latency_ms INTEGER,
                dom_content_ms INTEGER,
                load_ms INTEGER,
                resource_total INTEGER NOT NULL DEFAULT 0,
                resource_failed INTEGER NOT NULL DEFAULT 0,
                console_error_count INTEGER NOT NULL DEFAULT 0,
                render_ok INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT,
                alert_sent INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS resource_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                target_id INTEGER,
                url TEXT NOT NULL,
                kind TEXT,
                status TEXT NOT NULL,
                http_status INTEGER,
                latency_ms INTEGER,
                same_origin INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                FOREIGN KEY(run_id) REFERENCES check_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                target_name TEXT NOT NULL,
                url TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_run_id INTEGER,
                last_error TEXT,
                alert_sent_at TEXT,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE SET NULL,
                FOREIGN KEY(last_run_id) REFERENCES check_runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER,
                target_id INTEGER,
                created_at TEXT NOT NULL,
                recipients_json TEXT NOT NULL DEFAULT '[]',
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE SET NULL,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS auth_codes (
                email TEXT PRIMARY KEY,
                salt TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                verify_failures INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_check_runs_target_time ON check_runs(target_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_check_runs_started_at ON check_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_resources_run ON resource_results(run_id);
            CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, target_id);
            """
        )
    seed_default_targets(data_dir)


def normalize_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://www.hnmetachip.cn/{value.lstrip('/')}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def seed_default_targets(data_dir: Path | None = None) -> None:
    with managed_connection(data_dir) as conn:
        count = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        if count:
            return
        now = iso_now()
        next_at = seconds_from_now(15)
        for name, url in config.DEFAULT_TARGETS:
            conn.execute(
                """
                INSERT INTO targets
                    (name, url, enabled, interval_seconds, timeout_ms, created_at, updated_at, next_check_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (name, normalize_url(url), config.DEFAULT_CHECK_INTERVAL_SECONDS, config.DEFAULT_TARGET_TIMEOUT_MS, now, now, next_at),
            )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def list_targets(data_dir: Path | None = None, *, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM targets"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with managed_connection(data_dir) as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def get_target(target_id: int, data_dir: Path | None = None) -> dict | None:
    with managed_connection(data_dir) as conn:
        return row_to_dict(conn.execute("SELECT * FROM targets WHERE id = ?", (int(target_id),)).fetchone())


def create_target(payload: dict, data_dir: Path | None = None) -> dict:
    name = str(payload.get("name") or "").strip()[:120]
    url = normalize_url(payload.get("url") or "")
    if not name:
        raise ValueError("监测目标名称不能为空")
    if not url:
        raise ValueError("监测网址不合法")
    interval = max(60, int(payload.get("interval_seconds") or config.DEFAULT_CHECK_INTERVAL_SECONDS))
    timeout_ms = max(3000, int(payload.get("timeout_ms") or config.DEFAULT_TARGET_TIMEOUT_MS))
    enabled = 1 if bool(payload.get("enabled", True)) else 0
    now = iso_now()
    with managed_connection(data_dir) as conn:
        cur = conn.execute(
            """
            INSERT INTO targets
                (name, url, enabled, interval_seconds, timeout_ms, created_at, updated_at, next_check_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, url, enabled, interval, timeout_ms, now, now, now),
        )
        return get_target(cur.lastrowid, data_dir)


def update_target(target_id: int, payload: dict, data_dir: Path | None = None) -> dict:
    current = get_target(target_id, data_dir)
    if not current:
        raise ValueError("监测目标不存在")
    name = str(payload.get("name", current["name"]) or "").strip()[:120]
    url = normalize_url(payload.get("url", current["url"]))
    interval = max(60, int(payload.get("interval_seconds", current["interval_seconds"]) or config.DEFAULT_CHECK_INTERVAL_SECONDS))
    timeout_ms = max(3000, int(payload.get("timeout_ms", current["timeout_ms"]) or config.DEFAULT_TARGET_TIMEOUT_MS))
    enabled = 1 if bool(payload.get("enabled", bool(current["enabled"]))) else 0
    if not name:
        raise ValueError("监测目标名称不能为空")
    if not url:
        raise ValueError("监测网址不合法")
    with managed_connection(data_dir) as conn:
        conn.execute(
            """
            UPDATE targets
            SET name = ?, url = ?, enabled = ?, interval_seconds = ?, timeout_ms = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, url, enabled, interval, timeout_ms, iso_now(), int(target_id)),
        )
    return get_target(target_id, data_dir)


def delete_target(target_id: int, data_dir: Path | None = None) -> None:
    with managed_connection(data_dir) as conn:
        conn.execute("DELETE FROM targets WHERE id = ?", (int(target_id),))


def due_targets(data_dir: Path | None = None) -> list[dict]:
    now = iso_now()
    with managed_connection(data_dir) as conn:
        rows = conn.execute(
            """
            SELECT * FROM targets
            WHERE enabled = 1 AND (next_check_at IS NULL OR next_check_at <= ?)
            ORDER BY next_check_at ASC, id ASC
            """,
            (now,),
        ).fetchall()
        return [dict(row) for row in rows]


def reserve_next_check(target_id: int, data_dir: Path | None = None) -> None:
    target = get_target(target_id, data_dir)
    if not target:
        return
    next_at = seconds_from_now(int(target.get("interval_seconds") or config.DEFAULT_CHECK_INTERVAL_SECONDS))
    with managed_connection(data_dir) as conn:
        conn.execute("UPDATE targets SET next_check_at = ? WHERE id = ?", (next_at, int(target_id)))


def force_due(target_id: int, data_dir: Path | None = None) -> None:
    with managed_connection(data_dir) as conn:
        conn.execute("UPDATE targets SET next_check_at = ? WHERE id = ?", (iso_now(), int(target_id)))


def _open_incident(conn: sqlite3.Connection, target: dict, run_id: int, error_summary: str) -> int:
    existing = conn.execute(
        "SELECT * FROM incidents WHERE target_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (target.get("id"),),
    ).fetchone()
    if existing:
        failure_count = int(existing["failure_count"] or 0) + 1
        conn.execute(
            """
            UPDATE incidents
            SET failure_count = ?, last_run_id = ?, last_error = ?
            WHERE id = ?
            """,
            (failure_count, run_id, error_summary, existing["id"]),
        )
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO incidents
            (target_id, target_name, url, opened_at, status, failure_count, last_run_id, last_error)
        VALUES (?, ?, ?, ?, 'open', 1, ?, ?)
        """,
        (target.get("id"), target.get("name") or "", target.get("url") or "", iso_now(), run_id, error_summary),
    )
    return int(cur.lastrowid)


def _close_incident(conn: sqlite3.Connection, target_id: int) -> None:
    conn.execute(
        """
        UPDATE incidents
        SET status = 'resolved', closed_at = ?
        WHERE target_id = ? AND status = 'open'
        """,
        (iso_now(), int(target_id)),
    )


def record_run(target: dict, result: dict, *, attempt: int, trigger: str, data_dir: Path | None = None) -> tuple[int, int | None]:
    status = str(result.get("status") or "down")
    resources = result.get("resources") if isinstance(result.get("resources"), list) else []
    error_summary = str(result.get("error_summary") or "").strip()[:1000]
    with managed_connection(data_dir) as conn:
        cur = conn.execute(
            """
            INSERT INTO check_runs
                (target_id, target_name, url, started_at, finished_at, status, trigger, attempt,
                 http_status, latency_ms, dom_content_ms, load_ms, resource_total, resource_failed,
                 console_error_count, render_ok, error_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target.get("id"),
                target.get("name") or "",
                target.get("url") or "",
                result.get("started_at") or iso_now(),
                result.get("finished_at") or iso_now(),
                status,
                trigger,
                int(attempt),
                result.get("http_status"),
                result.get("latency_ms"),
                result.get("dom_content_ms"),
                result.get("load_ms"),
                int(result.get("resource_total") or 0),
                int(result.get("resource_failed") or 0),
                int(result.get("console_error_count") or 0),
                1 if result.get("render_ok") else 0,
                error_summary,
            ),
        )
        run_id = int(cur.lastrowid)
        for item in resources:
            conn.execute(
                """
                INSERT INTO resource_results
                    (run_id, target_id, url, kind, status, http_status, latency_ms, same_origin, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    target.get("id"),
                    str(item.get("url") or "")[:2000],
                    str(item.get("kind") or "")[:40],
                    str(item.get("status") or "unknown")[:20],
                    item.get("http_status"),
                    item.get("latency_ms"),
                    1 if item.get("same_origin") else 0,
                    str(item.get("error") or "")[:500],
                ),
            )

        incident_id = None
        if status == "ok":
            conn.execute(
                """
                UPDATE targets
                SET last_checked_at = ?, last_status = ?, last_latency_ms = ?, last_error = '',
                    consecutive_failures = 0, incident_open = 0
                WHERE id = ?
                """,
                (result.get("finished_at") or iso_now(), status, result.get("latency_ms"), target.get("id")),
            )
            _close_incident(conn, int(target.get("id")))
        else:
            current = conn.execute("SELECT consecutive_failures FROM targets WHERE id = ?", (target.get("id"),)).fetchone()
            failures = int((current or {"consecutive_failures": 0})["consecutive_failures"] or 0) + 1
            conn.execute(
                """
                UPDATE targets
                SET last_checked_at = ?, last_status = ?, last_latency_ms = ?, last_error = ?,
                    consecutive_failures = ?, incident_open = 1
                WHERE id = ?
                """,
                (result.get("finished_at") or iso_now(), status, result.get("latency_ms"), error_summary, failures, target.get("id")),
            )
            incident_id = _open_incident(conn, target, run_id, error_summary)

        return run_id, incident_id


def get_run(run_id: int, data_dir: Path | None = None) -> dict | None:
    with managed_connection(data_dir) as conn:
        row = conn.execute("SELECT * FROM check_runs WHERE id = ?", (int(run_id),)).fetchone()
        return row_to_dict(row)


def get_open_incident(target_id: int, data_dir: Path | None = None) -> dict | None:
    with managed_connection(data_dir) as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM incidents WHERE target_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (int(target_id),),
            ).fetchone()
        )


def record_alert_event(
    *,
    incident_id: int | None,
    target_id: int | None,
    recipients: list[str],
    subject: str,
    status: str,
    error: str = "",
    data_dir: Path | None = None,
) -> int:
    with managed_connection(data_dir) as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_events
                (incident_id, target_id, created_at, recipients_json, subject, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (incident_id, target_id, iso_now(), json.dumps(recipients, ensure_ascii=False), subject, status, error[:1000]),
        )
        if status == "sent" and incident_id:
            conn.execute("UPDATE incidents SET alert_sent_at = ? WHERE id = ?", (iso_now(), int(incident_id)))
        return int(cur.lastrowid)


def mark_run_alert_sent(run_id: int, data_dir: Path | None = None) -> None:
    with managed_connection(data_dir) as conn:
        conn.execute("UPDATE check_runs SET alert_sent = 1 WHERE id = ?", (int(run_id),))


def store_auth_code(email: str, code: str, salt: str, data_dir: Path | None = None) -> None:
    normalized = str(email or "").strip().lower()
    digest = hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()
    now = iso_now()
    expires = seconds_from_now(config.AUTH_CODE_EXPIRES_SECONDS)
    with managed_connection(data_dir) as conn:
        conn.execute(
            """
            INSERT INTO auth_codes (email, salt, code_hash, created_at, sent_at, expires_at, verify_failures)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(email) DO UPDATE SET
                salt = excluded.salt,
                code_hash = excluded.code_hash,
                created_at = excluded.created_at,
                sent_at = excluded.sent_at,
                expires_at = excluded.expires_at,
                verify_failures = 0
            """,
            (normalized, salt, digest, now, now, expires),
        )


def get_auth_code(email: str, data_dir: Path | None = None) -> dict | None:
    normalized = str(email or "").strip().lower()
    with managed_connection(data_dir) as conn:
        return row_to_dict(conn.execute("SELECT * FROM auth_codes WHERE email = ?", (normalized,)).fetchone())


def verify_auth_code(email: str, code: str, data_dir: Path | None = None) -> bool:
    normalized = str(email or "").strip().lower()
    candidate = str(code or "").strip()
    if not normalized or not candidate:
        return False
    with managed_connection(data_dir) as conn:
        row = conn.execute("SELECT * FROM auth_codes WHERE email = ?", (normalized,)).fetchone()
        if not row:
            return False
        if str(row["expires_at"]) < iso_now():
            conn.execute("DELETE FROM auth_codes WHERE email = ?", (normalized,))
            return False
        if int(row["verify_failures"] or 0) >= config.AUTH_CODE_MAX_VERIFY_FAILURES:
            conn.execute("DELETE FROM auth_codes WHERE email = ?", (normalized,))
            return False
        digest = hashlib.sha256(f"{row['salt']}:{candidate}".encode("utf-8")).hexdigest()
        if digest == row["code_hash"]:
            conn.execute("DELETE FROM auth_codes WHERE email = ?", (normalized,))
            return True
        failures = int(row["verify_failures"] or 0) + 1
        if failures >= config.AUTH_CODE_MAX_VERIFY_FAILURES:
            conn.execute("DELETE FROM auth_codes WHERE email = ?", (normalized,))
        else:
            conn.execute("UPDATE auth_codes SET verify_failures = ? WHERE email = ?", (failures, normalized))
        return False


def auth_code_resend_seconds(email: str, data_dir: Path | None = None) -> int:
    row = get_auth_code(email, data_dir)
    if not row:
        return 0
    sent = parse_iso(row.get("sent_at"))
    if not sent:
        return 0
    elapsed = int((now_utc() - sent).total_seconds())
    return max(0, config.AUTH_CODE_RESEND_COOLDOWN_SECONDS - elapsed)


def prune_old_data(data_dir: Path | None = None, *, retention_days: int = config.DATA_RETENTION_DAYS) -> None:
    cutoff = days_ago(retention_days)
    with managed_connection(data_dir) as conn:
        old_run_ids = [row["id"] for row in conn.execute("SELECT id FROM check_runs WHERE started_at < ?", (cutoff,)).fetchall()]
        if old_run_ids:
            placeholders = ",".join("?" for _ in old_run_ids)
            conn.execute(f"DELETE FROM resource_results WHERE run_id IN ({placeholders})", old_run_ids)
            conn.execute(f"DELETE FROM check_runs WHERE id IN ({placeholders})", old_run_ids)
        conn.execute("DELETE FROM alert_events WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM auth_codes WHERE expires_at < ?", (iso_now(),))


def get_public_status(data_dir: Path | None = None, *, window_hours: int = config.PUBLIC_WINDOW_HOURS) -> dict:
    since = hours_ago(window_hours)
    with managed_connection(data_dir) as conn:
        targets = [dict(row) for row in conn.execute("SELECT * FROM targets ORDER BY id ASC").fetchall()]
        runs_by_target: dict[int, list[dict]] = {}
        for row in conn.execute("SELECT * FROM check_runs WHERE started_at >= ? ORDER BY started_at ASC", (since,)).fetchall():
            item = dict(row)
            runs_by_target.setdefault(int(item["target_id"] or 0), []).append(item)
        active_incidents = [dict(row) for row in conn.execute("SELECT * FROM incidents WHERE status = 'open' ORDER BY opened_at DESC").fetchall()]
        recent_incidents = [dict(row) for row in conn.execute("SELECT * FROM incidents ORDER BY opened_at DESC LIMIT 20").fetchall()]

    public_targets = []
    ok_count = degraded_count = down_count = 0
    latencies = []
    for target in targets:
        target_id = int(target["id"])
        runs = runs_by_target.get(target_id, [])
        ok_runs = sum(1 for run in runs if run["status"] == "ok")
        latest_status = target.get("last_status") or "pending"
        if latest_status == "ok":
            ok_count += 1
        elif latest_status == "degraded":
            degraded_count += 1
        elif latest_status in {"down", "error"}:
            down_count += 1
        if target.get("last_latency_ms"):
            latencies.append(int(target["last_latency_ms"]))
        public_targets.append(
            {
                "id": target_id,
                "name": target["name"],
                "url": target["url"],
                "enabled": bool(target["enabled"]),
                "last_status": latest_status,
                "last_latency_ms": target.get("last_latency_ms"),
                "last_checked_at": target.get("last_checked_at"),
                "last_error": target.get("last_error") or "",
                "uptime_percent": round((ok_runs / len(runs) * 100), 1) if runs else None,
                "points": [
                    {
                        "t": run["started_at"],
                        "status": run["status"],
                        "latency_ms": run["latency_ms"],
                        "resource_failed": run["resource_failed"],
                    }
                    for run in runs
                ],
            }
        )
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else None
    return {
        "generated_at": iso_now(),
        "window_hours": window_hours,
        "summary": {
            "target_count": len(targets),
            "ok_count": ok_count,
            "degraded_count": degraded_count,
            "down_count": down_count,
            "avg_latency_ms": avg_latency,
            "active_incidents": len(active_incidents),
        },
        "targets": public_targets,
        "incidents": recent_incidents,
    }


def get_recent_runs(data_dir: Path | None = None, *, limit: int = 50) -> list[dict]:
    with managed_connection(data_dir) as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM check_runs ORDER BY started_at DESC LIMIT ?", (int(limit),)).fetchall()
        ]


def get_recent_incidents(data_dir: Path | None = None, *, limit: int = 50) -> list[dict]:
    with managed_connection(data_dir) as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM incidents ORDER BY opened_at DESC LIMIT ?", (int(limit),)).fetchall()
        ]
