# -*- coding: utf-8 -*-
"""Tests for src/generate/email_generator.py's domain-specific resume routing
(Requirement 3), and that scraped university/timezone fields survive unchanged
through to the generated record (feeding the scheduling gate in send_batch.py).
Uses fictional sample data only - no real names, no network calls.

Run with: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generate.email_generator import process  # noqa: E402


def make_config():
    return {
        "sender": {
            "name": "Jordan Rivera",
            "degree": "B.Tech. Computer Science",
            "institution": "Example Institute of Technology",
            "headline_metric": "CPI of 9.5",
        },
        "flagship_projects": [
            {"id": "project_a", "text": "Flagship project A description."},
            {"id": "project_b", "text": "Flagship project B description."},
        ],
        "secondary_projects": {},
        "templates": {
            "opening": "My name is {name}, a {degree} student at {institution}.",
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


def make_people():
    return [
        {
            "name": "Fictional Finance Prof",
            "email": "finance.prof@example.edu",
            "title": "Professor of Finance",
            "bio": "Research on asset pricing and corporate finance decisions.",
            "university": "Example School of Business, Boston, MA, USA",
            "timezone": "America/New_York",
        },
        {
            "name": "Fictional FinTech Prof",
            "email": "fintech.prof@example.edu",
            "title": "Associate Professor",
            "bio": "Works on fintech payments infrastructure and blockchain systems.",
            "university": "Example Institute, London, UK",
            "timezone": "Europe/London",
        },
        {
            "name": "Fictional AI Prof",
            "email": "ai.prof@example.edu",
            "title": "Assistant Professor",
            "bio": "Focuses on deep learning and neural network architectures.",
            "university": "Example National University, Singapore",
            "timezone": "Asia/Singapore",
        },
    ]


class TestDomainSpecificResumeRouting(unittest.TestCase):
    def test_finance_gets_finance_resume(self):
        results = process(make_people(), make_config())
        row = next(r for r in results if r["name"] == "Fictional Finance Prof")
        self.assertEqual(row["domain_bucket"], "Finance")
        self.assertEqual(row["resume_path"], "./resumes/finance_resume.pdf")

    def test_fintech_gets_fintech_resume(self):
        results = process(make_people(), make_config())
        row = next(r for r in results if r["name"] == "Fictional FinTech Prof")
        self.assertEqual(row["domain_bucket"], "FinTech")
        self.assertEqual(row["resume_path"], "./resumes/fintech_resume.pdf")

    def test_ai_ml_gets_ai_ml_resume(self):
        results = process(make_people(), make_config())
        row = next(r for r in results if r["name"] == "Fictional AI Prof")
        self.assertEqual(row["domain_bucket"], "AI_ML")
        self.assertEqual(row["resume_path"], "./resumes/ai_ml_resume.pdf")

    def test_missing_resume_for_a_domain_raises_rather_than_silently_omitting(self):
        cfg = make_config()
        del cfg["resumes"]["FinTech"]
        with self.assertRaises(ValueError):
            process(make_people(), cfg)


class TestUniversityTimezonePassThrough(unittest.TestCase):
    """University/timezone come from the scraper and must reach the generated
    record unchanged, since send_batch.py's scheduling gate depends on them."""

    def test_timezone_and_university_survive_generation(self):
        results = process(make_people(), make_config())
        row = next(r for r in results if r["name"] == "Fictional FinTech Prof")
        self.assertEqual(row["timezone"], "Europe/London")
        self.assertEqual(row["university"], "Example Institute, London, UK")

    def test_each_person_keeps_their_own_distinct_timezone(self):
        results = process(make_people(), make_config())
        tzs = {r["name"]: r["timezone"] for r in results}
        self.assertEqual(len(set(tzs.values())), 3)  # three distinct timezones


# ---------------------------------------------------------------------------
# Focused fixtures for the real Finance/FinTech/AI_ML content-routing setup:
# a NatWest project shared by every domain (via lead_order), domain-exclusive
# quant/AI-ML projects (also via lead_order), and a Finance-only CFA secondary
# project. Kept separate from make_config()/make_people() above so the
# existing tests are untouched.
# ---------------------------------------------------------------------------

def make_project_routing_config():
    return {
        "sender": {
            "name": "Fictional Student",
            "degree": "B.Tech.",
            "institution": "Example Institute of Technology",
            "headline_metric": "CPI of 9.2",
        },
        "flagship_projects": [
            {
                "id": "natwest_internship",
                "text": (
                    "During the NatWest Group Summer Internship 2027, I worked "
                    "on a fictional risk-analytics project."
                ),
            },
            {
                "id": "quant_project",
                "text": (
                    "I built a fictional quantitative-finance pricing model "
                    "under a faculty advisor."
                ),
            },
            {
                "id": "ai_ml_project",
                "text": "I built a fictional deep-learning model for a classification task.",
            },
        ],
        "secondary_projects": {
            "cfa_note": "I am also pursuing CFA Level I (May 2027) alongside my coursework.",
        },
        "templates": {
            "opening": (
                "My name is {name}, a {degree} student at {institution}, "
                "where I hold a {headline_metric}."
            ),
            "closing": "Thanks for your time.",
        },
        "resumes": {
            "Finance": "./resumes/finance_resume.pdf",
            "FinTech": "./resumes/fintech_resume.pdf",
            "AI_ML": "./resumes/fintech_resume.pdf",
        },
        "domains": {
            "Finance": {
                "keywords": ["asset pricing", "corporate finance", "portfolio"],
                "lead_order": ["natwest_internship", "quant_project"],
                "secondary_project": "cfa_note",
            },
            "FinTech": {
                "keywords": ["fintech", "payments", "blockchain"],
                "lead_order": ["natwest_internship", "quant_project"],
                "secondary_project": None,
            },
            "AI_ML": {
                "keywords": ["machine learning", "deep learning", "neural network"],
                "lead_order": ["natwest_internship", "ai_ml_project"],
                "secondary_project": None,
            },
        },
    }


def make_project_routing_people():
    return [
        {
            "name": "Fictional Finance Prof",
            "email": "finance.prof@example.edu",
            "title": "Professor of Finance",
            "bio": (
                "Professor's research interests include asset pricing, "
                "corporate finance, and portfolio theory."
            ),
            "university": "Example School of Business",
            "timezone": "America/New_York",
        },
        {
            "name": "Fictional FinTech Prof",
            "email": "fintech.prof@example.edu",
            "title": "Associate Professor",
            "bio": (
                "Professor's research focuses on fintech payments "
                "infrastructure and blockchain systems."
            ),
            "university": "Example Institute, London",
            "timezone": "Europe/London",
        },
        {
            "name": "Fictional AI Prof",
            "email": None,  # no published email - must never be fabricated
            "title": "Assistant Professor",
            "bio": (
                "Professor's research interests include deep learning, "
                "neural network architectures, and machine learning theory."
            ),
            "university": "Example National University",
            "timezone": "Asia/Singapore",
        },
    ]


def _draft_for(name):
    results = process(make_project_routing_people(), make_project_routing_config())
    return next(r for r in results if r["name"] == name)["email_draft"]


class TestLeadOrderFootgun(unittest.TestCase):
    """An explicitly empty lead_order must fail loudly rather than silently
    falling back to whichever flagship projects happen to come first - which
    can belong to a different domain entirely."""

    def test_explicit_empty_lead_order_raises_value_error(self):
        cfg = make_project_routing_config()
        cfg["domains"]["AI_ML"]["lead_order"] = []
        people = [
            p for p in make_project_routing_people()
            if p["name"] == "Fictional AI Prof"
        ]
        with self.assertRaises(ValueError):
            process(people, cfg)

    def test_missing_lead_order_still_falls_back_without_error(self):
        """lead_order being absent (None) must keep the original fallback
        behavior - only an explicitly empty list should raise."""
        cfg = make_project_routing_config()
        del cfg["domains"]["FinTech"]["lead_order"]
        people = [
            p for p in make_project_routing_people()
            if p["name"] == "Fictional FinTech Prof"
        ]
        results = process(people, cfg)
        self.assertEqual(len(results), 1)


class TestDomainSpecificEmailContent(unittest.TestCase):
    def test_finance_email_contains_cfa_and_natwest(self):
        draft = _draft_for("Fictional Finance Prof")
        self.assertIn("CFA Level I (May 2027)", draft)
        self.assertIn("NatWest Group Summer Internship 2027", draft)

    def test_fintech_email_contains_natwest_but_not_cfa(self):
        draft = _draft_for("Fictional FinTech Prof")
        self.assertIn("NatWest Group Summer Internship 2027", draft)
        self.assertNotIn("CFA", draft)

    def test_ai_ml_email_contains_natwest_but_not_cfa(self):
        draft = _draft_for("Fictional AI Prof")
        self.assertIn("NatWest Group Summer Internship 2027", draft)
        self.assertNotIn("CFA", draft)


class TestProjectRouting(unittest.TestCase):
    def test_finance_gets_quant_project_not_ai_ml_project(self):
        draft = _draft_for("Fictional Finance Prof")
        self.assertIn("quantitative-finance pricing model", draft)
        self.assertNotIn("deep-learning model", draft)

    def test_fintech_gets_quant_project_not_ai_ml_project(self):
        draft = _draft_for("Fictional FinTech Prof")
        self.assertIn("quantitative-finance pricing model", draft)
        self.assertNotIn("deep-learning model", draft)

    def test_ai_ml_gets_ai_ml_project_not_quant_project(self):
        draft = _draft_for("Fictional AI Prof")
        self.assertIn("deep-learning model", draft)
        self.assertNotIn("quantitative-finance pricing model", draft)


class TestNoFabricatedEmail(unittest.TestCase):
    def test_missing_email_stays_none_not_fabricated(self):
        results = process(make_project_routing_people(), make_project_routing_config())
        row = next(r for r in results if r["name"] == "Fictional AI Prof")
        self.assertIsNone(row["email"])


class TestRequiredOutputFieldsComplete(unittest.TestCase):
    REQUIRED_FIELDS = [
        "name", "email", "university", "bio", "domain_bucket", "topic",
        "subject", "email_draft", "resume_path",
    ]

    def test_all_nine_required_fields_present_for_every_row(self):
        results = process(make_project_routing_people(), make_project_routing_config())
        self.assertEqual(len(results), 3)
        for row in results:
            for field in self.REQUIRED_FIELDS:
                self.assertIn(field, row, f"missing '{field}' for {row.get('name')}")


class TestSeparatelyPronounCapitalization(unittest.TestCase):
    """Regression test for the follow_text[0].lower() bug: a second project
    blurb starting with the pronoun "I" must not get lowercased into a stray
    "i" when joined after "Separately, "."""

    def test_separately_i_built_stays_capitalized(self):
        draft = _draft_for("Fictional Finance Prof")
        self.assertIn("Separately, I built", draft)
        self.assertNotIn("Separately, i built", draft)


if __name__ == "__main__":
    unittest.main()
