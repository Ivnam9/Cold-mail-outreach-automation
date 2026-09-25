# -*- coding: utf-8 -*-
"""Tests for src/schedule/scheduling.py: the Tue/Thu 7:30-9:30 AM recipient-local send
window. Covers timezone conversion (including DST), the day/time boundary, several
different recipient timezones, and that "next window" is computed dynamically rather
than reading a hard-coded date.

Run with: python -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from schedule.scheduling import (  # noqa: E402
    is_allowed_local_time,
    is_due_now,
    next_send_window_start,
    resolve_zone,
)


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestResolveZone(unittest.TestCase):
    def test_valid_iana_name(self):
        zone = resolve_zone("America/New_York")
        self.assertEqual(str(zone), "America/New_York")

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError):
            resolve_zone("")

    def test_none_like_raises(self):
        with self.assertRaises(ValueError):
            resolve_zone("   ")

    def test_bogus_name_raises(self):
        with self.assertRaises(ValueError):
            resolve_zone("Not/ARealZone")

    def test_never_silently_falls_back_to_ist(self):
        # a bad timezone must fail loudly, never silently resolve to some default
        with self.assertRaises(ValueError):
            resolve_zone("garbage")


class TestIsAllowedLocalTime(unittest.TestCase):
    """Weekday + 7:30-9:30 AM boundary checks, independent of timezone conversion."""

    def test_tuesday_inside_window(self):
        # 2026-09-29 is a Tuesday
        self.assertTrue(is_allowed_local_time(datetime(2026, 9, 29, 8, 0)))

    def test_thursday_inside_window(self):
        # 2026-10-01 is a Thursday
        self.assertTrue(is_allowed_local_time(datetime(2026, 10, 1, 8, 0)))

    def test_window_start_inclusive(self):
        self.assertTrue(is_allowed_local_time(datetime(2026, 9, 29, 7, 30)))

    def test_window_end_inclusive(self):
        self.assertTrue(is_allowed_local_time(datetime(2026, 9, 29, 9, 30)))

    def test_just_before_window(self):
        self.assertFalse(is_allowed_local_time(datetime(2026, 9, 29, 7, 29)))

    def test_just_after_window(self):
        self.assertFalse(is_allowed_local_time(datetime(2026, 9, 29, 9, 31)))

    def test_monday_rejected(self):
        # 2026-09-28 is a Monday
        self.assertFalse(is_allowed_local_time(datetime(2026, 9, 28, 8, 0)))

    def test_wednesday_rejected(self):
        # 2026-09-30 is a Wednesday
        self.assertFalse(is_allowed_local_time(datetime(2026, 9, 30, 8, 0)))

    def test_friday_rejected(self):
        self.assertFalse(is_allowed_local_time(datetime(2026, 10, 2, 8, 0)))

    def test_saturday_rejected(self):
        self.assertFalse(is_allowed_local_time(datetime(2026, 10, 3, 8, 0)))

    def test_sunday_rejected(self):
        self.assertFalse(is_allowed_local_time(datetime(2026, 10, 4, 8, 0)))


class TestIsDueNowAcrossTimezones(unittest.TestCase):
    """The whole point: the same instant is due or not due depending entirely on the
    RECIPIENT's own timezone, never the sender's, never IST by default."""

    def test_new_york_tuesday_8am_is_due(self):
        # 2026-09-29 08:00 America/New_York (EDT, UTC-4) == 2026-09-29 12:00 UTC
        self.assertTrue(is_due_now("America/New_York", now_utc=utc(2026, 9, 29, 12, 0)))

    def test_same_instant_not_due_in_kolkata(self):
        # The exact same UTC instant as above lands at 17:30 IST - outside the window.
        self.assertFalse(is_due_now("Asia/Kolkata", now_utc=utc(2026, 9, 29, 12, 0)))

    def test_kolkata_tuesday_8am_is_due(self):
        # 2026-09-29 08:00 Asia/Kolkata (UTC+5:30, no DST) == 2026-09-29 02:30 UTC
        self.assertTrue(is_due_now("Asia/Kolkata", now_utc=utc(2026, 9, 29, 2, 30)))

    def test_sydney_thursday_8am_is_due(self):
        # 2026-10-01 08:00 Australia/Sydney (AEST, UTC+10 in early Oct) == 2026-09-30 22:00 UTC
        self.assertTrue(is_due_now("Australia/Sydney", now_utc=utc(2026, 9, 30, 22, 0)))

    def test_london_tuesday_8am_is_due(self):
        # 2026-09-29 08:00 Europe/London (BST, UTC+1) == 2026-09-29 07:00 UTC
        self.assertTrue(is_due_now("Europe/London", now_utc=utc(2026, 9, 29, 7, 0)))

    def test_new_york_tuesday_10am_not_due(self):
        # Past 9:30 AM local - outside the window even though it's still Tuesday.
        self.assertFalse(is_due_now("America/New_York", now_utc=utc(2026, 9, 29, 14, 0)))

    def test_new_york_wednesday_8am_not_due(self):
        # 2026-09-30 08:00 America/New_York (EDT) == 2026-09-30 12:00 UTC, a Wednesday.
        self.assertFalse(is_due_now("America/New_York", now_utc=utc(2026, 9, 30, 12, 0)))

    def test_naive_now_treated_as_utc(self):
        self.assertTrue(is_due_now("America/New_York", now_utc=datetime(2026, 9, 29, 12, 0)))

    def test_invalid_timezone_raises_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            is_due_now("Definitely/NotAZone", now_utc=utc(2026, 9, 29, 12, 0))


class TestDST(unittest.TestCase):
    """The same recipient-local wall-clock time must map to different UTC instants
    depending on whether DST is in effect - proof zoneinfo (not a fixed UTC offset)
    is doing the conversion."""

    def test_new_york_dst_summer_boundaries(self):
        # 2026-07-07 is a Tuesday during EDT (UTC-4): the 7:30-9:30 local window is
        # 11:30-13:30 UTC.
        self.assertTrue(is_due_now("America/New_York", now_utc=utc(2026, 7, 7, 11, 30)))
        self.assertTrue(is_due_now("America/New_York", now_utc=utc(2026, 7, 7, 13, 30)))
        self.assertFalse(is_due_now("America/New_York", now_utc=utc(2026, 7, 7, 13, 31)))

    def test_new_york_dst_winter_boundaries(self):
        # 2026-01-06 is a Tuesday during EST (UTC-5): the SAME recipient-local window
        # (7:30-9:30 AM) is 12:30-14:30 UTC - a full hour later than the summer case
        # above, proving the offset is resolved per-date via zoneinfo, not fixed.
        self.assertTrue(is_due_now("America/New_York", now_utc=utc(2026, 1, 6, 12, 30)))
        self.assertTrue(is_due_now("America/New_York", now_utc=utc(2026, 1, 6, 14, 30)))
        self.assertFalse(is_due_now("America/New_York", now_utc=utc(2026, 1, 6, 14, 31)))
        # The UTC instant that opened the window in summer is too early in winter.
        self.assertFalse(is_due_now("America/New_York", now_utc=utc(2026, 1, 6, 11, 30)))


class TestNextSendWindowStart(unittest.TestCase):
    """`next_send_window_start` walks forward day-by-day from the reference moment -
    it never reads a hard-coded date, so it works for any starting point."""

    def test_from_sunday_finds_tuesday(self):
        # 2026-10-04 is a Sunday in New York.
        result = next_send_window_start(
            "America/New_York", after=utc(2026, 10, 4, 12, 0)
        )
        self.assertEqual(result.date(), date(2026, 10, 6))  # the following Tuesday
        self.assertEqual(result.weekday(), 1)
        self.assertEqual((result.hour, result.minute), (7, 30))

    def test_from_tuesday_after_window_finds_thursday(self):
        # Tuesday 2026-09-29, 10am local (window already passed) -> next is Thursday.
        result = next_send_window_start(
            "America/New_York", after=utc(2026, 9, 29, 14, 0)
        )
        self.assertEqual(result.date(), date(2026, 10, 1))
        self.assertEqual(result.weekday(), 3)

    def test_from_tuesday_before_window_finds_same_day(self):
        # Tuesday 2026-09-29, 6am local (before window opens) -> same day's window.
        result = next_send_window_start(
            "America/New_York", after=utc(2026, 9, 29, 10, 0)
        )
        self.assertEqual(result.date(), date(2026, 9, 29))

    def test_result_is_timezone_aware_in_requested_zone(self):
        result = next_send_window_start(
            "Asia/Kolkata", after=utc(2026, 9, 29, 12, 0)
        )
        self.assertEqual(str(result.tzinfo), "Asia/Kolkata")

    def test_never_hard_codes_a_date_two_different_references_two_different_results(self):
        r1 = next_send_window_start("America/New_York", after=utc(2026, 9, 29, 14, 0))
        r2 = next_send_window_start("America/New_York", after=utc(2027, 1, 1, 0, 0))
        self.assertNotEqual(r1.date(), r2.date())


if __name__ == "__main__":
    unittest.main()
