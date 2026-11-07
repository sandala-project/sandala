from __future__ import annotations

from datetime import datetime, timezone


def iso_utc(value: datetime) -> str:
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return iso_utc(datetime.now(timezone.utc))


def parse_iso_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("ISO datetime must be a non-empty string")
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
