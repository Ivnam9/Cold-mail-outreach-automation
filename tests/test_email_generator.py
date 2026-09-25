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


if __name__ == "__main__":
    unittest.main()
