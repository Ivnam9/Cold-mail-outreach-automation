# -*- coding: utf-8 -*-
"""Tests for Company Mode (src/generate/email_generator.py) and its interaction with
University Mode: default-mode backward compatibility, company-specific salutation/
subject/opening/opportunity wording, remote-evidence verification, and that domain
classification + resume routing stay identical across both modes.

Uses fictional sample data only - no real names, no network calls.

Run with: python -m unittest discover -s tests
"""
import importlib.util as _ilu
import sys
import unittest
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generate.email_generator import process, salutation, build_subject  # noqa: E402


def _load_send_batch():
    """send_batch.py lives in src/send/ as a script, not an importable package
    member — load it directly by path, same approach as tests/test_send_batch.py."""
    spec = _ilu.spec_from_file_location(
        "send_batch",
        Path(__file__).resolve().parent.parent / "src" / "send" / "send_batch.py",
    )
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


send_batch = _load_send_batch()


def make_config():
    """Mirrors the real config.yaml schema (Finance/FinTech/AI_ML domains, the full
    sender field set build_email() always reads, and both `opening`/`company_opening`
    templates) so these tests exercise the actual production shape, not a stripped-down
    fixture."""
    return {
        "sender": {
            "name": "Jordan Rivera",
            "degree": "B.Tech. Computer Science",
            "institution": "Example Institute of Technology",
            "minor": "Dual Minor in Data Science and Statistics",
            "headline_metric": "9.5",
            "natwest": "Example Corp as a Summer Intern in 2027",
            "cfa": "CFA Level I (May 2027)",
            "iitb_email": "jordan.rivera@example.edu",
            "personal_email": "jordan.rivera@example.com",
            "phone": "+1-555-010-0100",
        },
        "flagship_projects": [
            {"id": "project_a", "text": "Flagship project A description."},
            {"id": "project_b", "text": "Flagship project B description."},
        ],
        "email_projects": {
            "project_a": "a quantitative trading project",
            "project_b": "a fixed-income analytics project",
        },
        "secondary_projects": {},
        "templates": {
            "opening": (
                "My name is {name}, a {degree} student at {institution}, pursuing "
                "{minor}, with a CPI of {headline_metric}. I am writing to express my "
                "interest in working with you on research in {topic}. I will also be "
                "joining {natwest} and am preparing for {cfa}."
            ),
            "company_opening": (
                "My name is {name}, a {degree} student at {institution}, pursuing "
                "{minor}, with a CPI of {headline_metric}. I am writing to express my "
                "interest in {company}'s work in {topic}. I will also be joining "
                "{natwest} and am preparing for {cfa}."
            ),
            "closing": "Thanks for your time.",
        },
        "resumes": {
            "Finance": "./resumes/finance_resume.pdf",
            "FinTech": "./resumes/fintech_resume.pdf",
            "AI_ML": "./resumes/ai_ml_resume.pdf",
        },
        "domains": {
            "Finance": {
                "keywords": ["asset pricing", "corporate finance", "portfolio"],
                "lead_order": ["project_a", "project_b"],
                "secondary_project": None,
            },
            "FinTech": {
                "keywords": ["fintech", "blockchain", "payments"],
                "lead_order": ["project_a", "project_b"],
                "secondary_project": None,
            },
            "AI_ML": {
                "keywords": ["machine learning", "deep learning", "neural network"],
                "lead_order": ["project_b", "project_a"],
                "secondary_project": None,
            },
        },
    }


FINANCE_BIO = "Research interests include asset pricing and corporate finance."


def make_university_person(**overrides):
    person = {
        "name": "Taylor Finch",
        "email": "taylor.finch@example.edu",
        "title": "Professor of Finance",
        "bio": FINANCE_BIO,
        "university": "Example School of Business",
        "timezone": "America/New_York",
    }
    person.update(overrides)
    return person


def make_company_person(**overrides):
    person = {
        "name": "Riley Chen",
        "email": "riley.chen@examplecap.test",
        "title": "Portfolio Analyst",
        "bio": FINANCE_BIO,
        "company": "Example Capital",
        "company_url": "https://examplecap.test",
        "timezone": "America/New_York",
        "source_url": "https://examplecap.test/team",
        "mode": "company",
        "remote_evidence": 'Careers page states "all internships are remote."',
        "remote_evidence_url": "https://examplecap.test/careers",
    }
    person.update(overrides)
    return person


class TestUniversityModeBackwardCompatibility(unittest.TestCase):
    """A record with no "mode" key must behave exactly like one with an explicit
    "mode": "university" — and exactly like the pre-Company-Mode code did."""

    def test_missing_mode_defaults_to_university(self):
        no_mode = make_university_person()
        explicit = make_university_person(mode="university")
        r1 = process([no_mode], make_config())[0]
        r2 = process([explicit], make_config())[0]
        self.assertEqual(r1["subject"], r2["subject"])
        self.assertEqual(r1["email_draft"], r2["email_draft"])
        self.assertEqual(r1["domain_bucket"], r2["domain_bucket"])

    def test_university_salutation_unchanged(self):
        self.assertEqual(salutation("Taylor Finch"), "Dear Prof. Taylor Finch,")
        self.assertEqual(salutation("Taylor Finch", mode="university"), "Dear Prof. Taylor Finch,")

    def test_university_subject_unchanged(self):
        cfg = make_config()
        row = process([make_university_person()], cfg)[0]
        self.assertTrue(row["subject"].startswith("Research / Project Opportunities in"))
        self.assertTrue(row["subject"].endswith("| IIT Bombay"))

    def test_university_record_has_no_remote_status_field(self):
        row = process([make_university_person()], make_config())[0]
        self.assertNotIn("remote_status", row)

    def test_university_email_opens_with_dear_prof(self):
        row = process([make_university_person()], make_config())[0]
        self.assertTrue(row["email_draft"].startswith("Dear Prof. Taylor Finch,"))


class TestCompanyModeSalutationAndSubject(unittest.TestCase):
    def test_company_salutation_has_no_prof(self):
        self.assertEqual(salutation("Riley Chen", mode="company"), "Dear Riley Chen,")

    def test_company_salutation_keeps_explicit_title_prefix(self):
        self.assertEqual(salutation("Dr. Riley Chen", mode="company"), "Dear Dr. Riley Chen,")

    def test_company_subject_names_company_and_says_internship(self):
        cfg = make_config()
        row = process([make_company_person()], cfg)[0]
        self.assertEqual(row["subject"], "Remote Internship Inquiry | Example Capital | IIT Bombay")
        self.assertNotIn("Research / Project Opportunities", row["subject"])

    def test_company_email_opens_with_plain_name(self):
        row = process([make_company_person()], make_config())[0]
        self.assertTrue(row["email_draft"].startswith("Dear Riley Chen,"))
        self.assertNotIn("Dear Prof.", row["email_draft"])


class TestRemoteEvidenceVerification(unittest.TestCase):
    def test_verified_when_evidence_and_url_present(self):
        row = process([make_company_person()], make_config())[0]
        self.assertEqual(row["remote_status"], "Verified")
        self.assertIn("supports remote internships", row["email_draft"])

    def test_unverified_when_evidence_missing(self):
        person = make_company_person(remote_evidence=None, remote_evidence_url=None)
        row = process([person], make_config())[0]
        self.assertEqual(row["remote_status"], "Unverified")
        self.assertNotIn("supports remote internships", row["email_draft"])
        self.assertIn("remote or otherwise", row["email_draft"])

    def test_unverified_when_only_evidence_text_present_without_url(self):
        """Never mark "Verified" on partial evidence — both the text AND its source
        URL must be present, or it stays Unverified for manual review."""
        person = make_company_person(remote_evidence_url=None)
        row = process([person], make_config())[0]
        self.assertEqual(row["remote_status"], "Unverified")

    def test_never_claims_remote_without_evidence_even_implicitly(self):
        person = make_company_person(remote_evidence=None, remote_evidence_url=None)
        row = process([person], make_config())[0]
        self.assertNotIn("remote internship", row["email_draft"].split("I wanted to ask")[0])


class TestCompanyModeFieldValidation(unittest.TestCase):
    def test_missing_company_field_raises(self):
        person = make_company_person()
        del person["company"]
        with self.assertRaises(ValueError):
            process([person], make_config())

    def test_unknown_mode_raises(self):
        person = make_university_person(mode="nonsense")
        with self.assertRaises(ValueError):
            process([person], make_config())


class TestDomainClassificationAndResumeRoutingSharedAcrossModes(unittest.TestCase):
    """Requirement: Finance/FinTech/AI_ML classification, topic extraction, and
    resume routing must be identical regardless of mode."""

    def test_same_bio_same_domain_and_resume_university_vs_company(self):
        cfg = make_config()
        uni_row = process([make_university_person()], cfg)[0]
        co_row = process([make_company_person()], cfg)[0]
        self.assertEqual(uni_row["domain_bucket"], co_row["domain_bucket"])
        self.assertEqual(uni_row["resume_path"], co_row["resume_path"])
        self.assertEqual(uni_row["topic"], co_row["topic"])

    def test_fintech_company_gets_fintech_resume(self):
        cfg = make_config()
        person = make_company_person(
            bio="Research interests include fintech and blockchain payments infrastructure.",
        )
        row = process([person], cfg)[0]
        self.assertEqual(row["domain_bucket"], "FinTech")
        self.assertEqual(row["resume_path"], "./resumes/fintech_resume.pdf")

    def test_ai_ml_company_gets_ai_ml_resume(self):
        cfg = make_config()
        person = make_company_person(
            bio="Research interests include machine learning and deep learning for production systems.",
        )
        row = process([person], cfg)[0]
        self.assertEqual(row["domain_bucket"], "AI_ML")
        self.assertEqual(row["resume_path"], "./resumes/ai_ml_resume.pdf")


class TestBuildSubjectDirectly(unittest.TestCase):
    """build_subject() in isolation (no process()/classify() involved)."""

    def test_company_subject_fixed_format_regardless_of_weak_fit(self):
        """Unlike University Mode, the company subject never varies with domain fit,
        topic, or weak_fit — it's a fixed inquiry format naming only the company."""
        weak_fit_cfg = {"weak_fit": True}
        strong_fit_cfg = {"weak_fit": False}
        subject_weak = build_subject("AI_ML", weak_fit_cfg, "some topic", mode="company", company="Acme")
        subject_strong = build_subject("AI_ML", strong_fit_cfg, "some topic", mode="company", company="Acme")
        expected = "Remote Internship Inquiry | Acme | IIT Bombay"
        self.assertEqual(subject_weak, expected)
        self.assertEqual(subject_strong, expected)
        self.assertNotIn("AI_ML", subject_weak)
        self.assertNotIn("some topic", subject_weak)

    def test_default_mode_is_university(self):
        subject = build_subject("AI_ML", {}, "neural networks")
        self.assertEqual(subject, "Research / Project Opportunities in neural networks | IIT Bombay")


class TestMixedBatchProcessing(unittest.TestCase):
    """process() must handle a single input list containing both University and
    Company Mode records correctly and independently — guards against any state
    leaking between iterations of the per-person loop."""

    def test_single_process_call_with_both_modes_in_one_list(self):
        cfg = make_config()
        uni = make_university_person(name="Taylor Finch")
        co = make_company_person(name="Riley Chen")
        results = process([uni, co], cfg)
        self.assertEqual(len(results), 2)

        uni_row = next(r for r in results if r["name"] == "Taylor Finch")
        co_row = next(r for r in results if r["name"] == "Riley Chen")

        self.assertTrue(uni_row["email_draft"].startswith("Dear Prof. Taylor Finch,"))
        self.assertNotIn("remote_status", uni_row)

        self.assertTrue(co_row["email_draft"].startswith("Dear Riley Chen,"))
        self.assertEqual(co_row["remote_status"], "Verified")

        # same bio -> same domain/resume regardless of the other record's mode
        self.assertEqual(uni_row["domain_bucket"], co_row["domain_bucket"])
        self.assertEqual(uni_row["resume_path"], co_row["resume_path"])

    def test_company_mode_in_first_position_does_not_leak_into_university_record(self):
        """Order shouldn't matter - try company-first too."""
        cfg = make_config()
        co = make_company_person(name="Riley Chen")
        uni = make_university_person(name="Taylor Finch")
        results = process([co, uni], cfg)

        uni_row = next(r for r in results if r["name"] == "Taylor Finch")
        self.assertNotIn("remote_status", uni_row)
        self.assertNotIn("company", uni_row)
        self.assertTrue(uni_row["email_draft"].startswith("Dear Prof. Taylor Finch,"))


class TestCompanyModeUsesUnchangedSendingInfrastructure(unittest.TestCase):
    """send_batch.py has no notion of "mode" at all — it only ever sees CSV columns
    (send/name/email/subject/email_body/resume_path/timezone). This proves a
    Company-Mode-generated row flows through the exact same, unmodified Tue/Thu
    7:30-9:30 AM recipient-local scheduling gate as a University-Mode row."""

    def _to_csv_row(self, record):
        return {
            "send": "yes",
            "name": record["name"],
            "email": record["email"],
            "subject": record["subject"],
            "email_body": record["email_draft"],
            "resume_path": record["resume_path"],
            "timezone": record["timezone"],
        }

    def test_company_row_due_inside_window(self):
        record = process([make_company_person()], make_config())[0]
        row = self._to_csv_row(record)
        # Tuesday, 8:00 AM America/New_York (EDT, UTC-4) == 12:00 UTC - inside window.
        due_now = datetime(2026, 9, 29, 12, 0, tzinfo=dt_timezone.utc)
        queue, skipped = send_batch.build_queue([row], set(), now_utc=due_now)
        self.assertEqual(len(queue), 1)
        self.assertEqual(skipped, [])

    def test_company_row_skipped_outside_window(self):
        record = process([make_company_person()], make_config())[0]
        row = self._to_csv_row(record)
        # Same day, 10am local - outside the 7:30-9:30 window.
        not_due = datetime(2026, 9, 29, 14, 0, tzinfo=dt_timezone.utc)
        queue, skipped = send_batch.build_queue([row], set(), now_utc=not_due)
        self.assertEqual(queue, [])
        self.assertIn("outside Tue/Thu", skipped[0][1])


if __name__ == "__main__":
    unittest.main()
