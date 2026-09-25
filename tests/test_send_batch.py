# -*- coding: utf-8 -*-
"""Tests for src/send/send_batch.py's row-filtering logic: scheduled/due gating,
duplicate-send prevention, and that domain-specific resume_path rows are preserved
through the queue. These call `build_queue`/`load_already_sent` directly — no SMTP
connection is ever made, and no real email is ever sent, by any test in this file.

Run with: python -m unittest discover -s tests
"""
import csv
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import importlib.util as _ilu  # noqa: E402


def _load_send_batch():
    """send_batch.py isn't a normal importable module name (it lives in src/send/ as
    a script, not a package member), so load it directly by path."""
    spec = _ilu.spec_from_file_location(
        "send_batch",
        Path(__file__).resolve().parent.parent / "src" / "send" / "send_batch.py",
    )
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


send_batch = _load_send_batch()


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# A Tuesday, 8:00 AM America/New_York (EDT, UTC-4) == 12:00 UTC - inside the window.
DUE_NOW = utc(2026, 9, 29, 12, 0)
# Same day, 10am local - outside the window.
NOT_DUE = utc(2026, 9, 29, 14, 0)


def make_row(**overrides) -> dict:
    row = {
        "send": "yes",
        "name": "Alex Morgan",
        "email": "alex.morgan@example.edu",
        "subject": "Interest in your research",
        "email_body": "Dear Prof. Morgan, ...",
        "resume_path": "./resumes/ml_resume.pdf",
        "timezone": "America/New_York",
    }
    row.update(overrides)
    return row


class TestBuildQueueScheduling(unittest.TestCase):
    def test_due_row_is_queued(self):
        queue, skipped = send_batch.build_queue([make_row()], set(), now_utc=DUE_NOW)
        self.assertEqual(len(queue), 1)
        self.assertEqual(skipped, [])

    def test_row_outside_window_is_skipped_not_sent(self):
        queue, skipped = send_batch.build_queue([make_row()], set(), now_utc=NOT_DUE)
        self.assertEqual(queue, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("outside Tue/Thu", skipped[0][1])

    def test_different_recipient_timezones_evaluated_independently(self):
        rows = [
            make_row(email="a@example.edu", timezone="America/New_York"),
            make_row(email="b@example.edu", timezone="Asia/Kolkata"),
        ]
        # DUE_NOW (12:00 UTC) is 8:00am in New York (due) but 5:30pm in Kolkata (not).
        queue, skipped = send_batch.build_queue(rows, set(), now_utc=DUE_NOW)
        queued_emails = {r["email"] for r in queue}
        self.assertEqual(queued_emails, {"a@example.edu"})
        skipped_emails = {r["email"] for r, _ in skipped}
        self.assertEqual(skipped_emails, {"b@example.edu"})

    def test_missing_timezone_is_skipped_not_sent_blind(self):
        row = make_row()
        del row["timezone"]
        queue, skipped = send_batch.build_queue([row], set(), now_utc=DUE_NOW)
        self.assertEqual(queue, [])
        self.assertIn("missing timezone", skipped[0][1])

    def test_invalid_timezone_is_skipped_not_sent_blind(self):
        row = make_row(timezone="Not/ARealZone")
        queue, skipped = send_batch.build_queue([row], set(), now_utc=DUE_NOW)
        self.assertEqual(queue, [])
        self.assertIn("invalid timezone", skipped[0][1])

    def test_send_no_never_queued_regardless_of_window(self):
        row = make_row(send="no")
        queue, skipped = send_batch.build_queue([row], set(), now_utc=DUE_NOW)
        self.assertEqual(queue, [])
        self.assertEqual(skipped[0][1], "send != yes")


class TestBuildQueueDuplicatePrevention(unittest.TestCase):
    def test_already_sent_email_is_never_requeued(self):
        row = make_row()
        already_sent = {row["email"]}
        queue, skipped = send_batch.build_queue([row], already_sent, now_utc=DUE_NOW)
        self.assertEqual(queue, [])
        self.assertEqual(skipped[0][1], "already sent")

    def test_load_already_sent_only_counts_sent_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "sent_log_batch_01.csv"
            with open(log_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "timestamp", "date", "batch", "name", "email",
                        "subject", "status", "error",
                    ],
                )
                w.writeheader()
                w.writerow({
                    "timestamp": "", "date": "", "batch": "batch_01",
                    "name": "Alex Morgan", "email": "alex.morgan@example.edu",
                    "subject": "x", "status": "sent", "error": "",
                })
                w.writerow({
                    "timestamp": "", "date": "", "batch": "batch_01",
                    "name": "Sam Okafor", "email": "sam.okafor@example.edu",
                    "subject": "x", "status": "failed", "error": "boom",
                })

            already = send_batch.load_already_sent(log_path)
            self.assertEqual(already, {"alex.morgan@example.edu"})

    def test_missing_log_file_means_nothing_sent_yet(self):
        already = send_batch.load_already_sent(Path("/nonexistent/sent_log.csv"))
        self.assertEqual(already, set())

    def test_rerunning_a_batch_never_double_sends(self):
        """Simulates a second Task-Scheduler pass after a row was already sent."""
        rows = [make_row(email="a@example.edu"), make_row(email="b@example.edu")]
        first_queue, _ = send_batch.build_queue(rows, set(), now_utc=DUE_NOW)
        self.assertEqual(len(first_queue), 2)

        already_sent_after_first_run = {"a@example.edu"}
        second_queue, skipped = send_batch.build_queue(
            rows, already_sent_after_first_run, now_utc=DUE_NOW
        )
        self.assertEqual([r["email"] for r in second_queue], ["b@example.edu"])
        self.assertIn(("already sent"), [reason for _, reason in skipped])


class TestBuildQueuePreservesResumeRouting(unittest.TestCase):
    """Requirement 3: row-specific (domain-specific) resume_path must survive
    unchanged into the queue that actually gets sent."""

    def test_domain_specific_resume_paths_preserved(self):
        rows = [
            make_row(email="finance@example.edu", resume_path="./resumes/finance_resume.pdf"),
            make_row(email="fintech@example.edu", resume_path="./resumes/fintech_resume.pdf"),
            make_row(email="aiml@example.edu", resume_path="./resumes/ai_ml_resume.pdf"),
        ]
        queue, skipped = send_batch.build_queue(rows, set(), now_utc=DUE_NOW)
        self.assertEqual(skipped, [])
        by_email = {r["email"]: r["resume_path"] for r in queue}
        self.assertEqual(by_email["finance@example.edu"], "./resumes/finance_resume.pdf")
        self.assertEqual(by_email["fintech@example.edu"], "./resumes/fintech_resume.pdf")
        self.assertEqual(by_email["aiml@example.edu"], "./resumes/ai_ml_resume.pdf")

    def test_missing_resume_path_is_skipped(self):
        row = make_row()
        del row["resume_path"]
        queue, skipped = send_batch.build_queue([row], set(), now_utc=DUE_NOW)
        self.assertEqual(queue, [])
        self.assertIn("resume_path", skipped[0][1])


if __name__ == "__main__":
    unittest.main()
