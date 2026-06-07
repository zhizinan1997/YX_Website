from __future__ import annotations

from datetime import datetime, timedelta, timezone


UTC = timezone.utc
BEIJING_TZ = timezone(timedelta(hours=8))


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_from_now(seconds: int) -> str:
    return (now_utc() + timedelta(seconds=int(seconds))).isoformat(timespec="seconds")


def hours_ago(hours: int) -> str:
    return (now_utc() - timedelta(hours=int(hours))).isoformat(timespec="seconds")


def days_ago(days: int) -> str:
    return (now_utc() - timedelta(days=int(days))).isoformat(timespec="seconds")

