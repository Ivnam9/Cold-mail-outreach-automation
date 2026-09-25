# -*- coding: utf-8 -*-
"""Timezone-aware Tuesday/Thursday, 7:30-9:30 AM send-window logic.

Emails in this pipeline may only go out on a Tuesday or Thursday, between 7:30 AM
and 9:30 AM in the RECIPIENT's own university/lab local time — never the sender's,
and never a hard-coded "IST" or similar assumption.

This module intentionally has no notion of a long-running scheduler process: it just
answers "is right now, in this recipient's timezone, inside the allowed window?" and
"when's the next one?". `src/send/send_batch.py` calls `is_due_now()` once per row on
each invocation, which is what makes it safe to run from `cron` / Windows Task
Scheduler every N minutes instead of keeping a Python process alive for days — each
run is a stateless check against the current wall-clock time, so future Tue/Thu
windows are picked up automatically without ever hard-coding a date.

Timezone handling uses the stdlib `zoneinfo` module (IANA tz database), which
correctly accounts for DST transitions. On Windows, `zoneinfo` needs the `tzdata`
PyPI package (see requirements.txt) since Windows doesn't ship its own IANA database;
Linux/macOS normally already have one installed system-wide.
"""
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# datetime.weekday(): Monday=0 ... Sunday=6
TUESDAY = 1
THURSDAY = 3
ALLOWED_WEEKDAYS = (TUESDAY, THURSDAY)

WINDOW_START = time(7, 30)
WINDOW_END = time(9, 30)

MAX_LOOKAHEAD_DAYS = 14  # more than enough to find the next Tue/Thu


def resolve_zone(tz_name: str) -> ZoneInfo:
    """Validate and return a ZoneInfo for an IANA timezone name (e.g.
    "America/New_York"). Raises ValueError with a clear message on anything else —
    never guess/normalize a bad or missing timezone, since a wrong zone here means
    silently sending outside the allowed window."""
    if not tz_name or not tz_name.strip():
        raise ValueError("Missing IANA timezone name")
    try:
        return ZoneInfo(tz_name.strip())
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"Unknown IANA timezone: {tz_name!r}") from e


def is_allowed_local_time(local_dt: datetime) -> bool:
    """True if a (timezone-aware) local datetime falls on a Tuesday or Thursday,
    between 7:30 and 9:30 AM inclusive, in whatever timezone it's already expressed
    in. Does not do any timezone conversion itself — see `is_due_now` for that."""
    if local_dt.weekday() not in ALLOWED_WEEKDAYS:
        return False
    return WINDOW_START <= local_dt.time() <= WINDOW_END


def is_due_now(tz_name: str, now_utc: datetime = None) -> bool:
    """True if, right now, converted into the recipient's own IANA timezone, we're
    inside the Tue/Thu 7:30-9:30 AM send window.

    `now_utc` defaults to the real current time; a test can pass a fixed aware (or
    naive-treated-as-UTC) datetime instead to check a specific moment without waiting
    for it or mocking the clock.
    """
    if now_utc is None:
        now_utc = datetime.now(dt_timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt_timezone.utc)

    zone = resolve_zone(tz_name)
    local_dt = now_utc.astimezone(zone)
    return is_allowed_local_time(local_dt)


def next_send_window_start(tz_name: str, after: datetime = None) -> datetime:
    """Dynamically compute the next upcoming Tue/Thu 7:30 AM window start, in the
    recipient's own local timezone, strictly after `after` (defaults to now).

    Never hard-codes a date — walks forward day by day from the reference moment and
    stops at the first allowed weekday whose window start is still ahead of it. Useful
    for showing a human reviewer roughly when a row will go out, and for tests.
    """
    zone = resolve_zone(tz_name)
    if after is None:
        after = datetime.now(dt_timezone.utc)
    elif after.tzinfo is None:
        after = after.replace(tzinfo=dt_timezone.utc)

    ref = after.astimezone(zone)
    candidate_date = ref.date()

    for _ in range(MAX_LOOKAHEAD_DAYS):
        if candidate_date.weekday() in ALLOWED_WEEKDAYS:
            candidate = datetime.combine(candidate_date, WINDOW_START, tzinfo=zone)
            if candidate > ref:
                return candidate
        candidate_date += timedelta(days=1)

    raise RuntimeError(
        f"Could not find a Tue/Thu send window within {MAX_LOOKAHEAD_DAYS} days "
        f"of {after!r} in timezone {tz_name!r} (this should never happen)."
    )


def describe_due_status(tz_name: str, now_utc: datetime = None) -> str:
    """Human-readable one-liner for logging/console output: whether a row is due
    right now, and if not, when its next window opens."""
    if is_due_now(tz_name, now_utc=now_utc):
        return f"due now ({tz_name})"
    nxt = next_send_window_start(tz_name, after=now_utc)
    return f"not due — next window {nxt.isoformat()} ({tz_name})"
