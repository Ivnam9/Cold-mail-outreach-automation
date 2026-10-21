# -*- coding: utf-8 -*-
"""Tests for src/export/build_workbook.py's Company/Remote Status/Remote Evidence
columns (added for Company Mode): present in the header row, populated for Company
Mode records, and left blank for University Mode records that never carry those
fields. Uses fictional sample data only - no real names, no network calls.

Run with: python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from export.build_workbook import build, HEADERS  # noqa: E402


def make_university_record():
    return {
        "name": "Taylor Finch",
        "email": "taylor.finch@example.edu",
        "title": "Professor of Finance",
        "bio": "Research interests include asset pricing.",
        "university": "Example School of Business",
        "timezone": "America/New_York",
        "domain_bucket": "Finance",
        "subject": "Research / Project Opportunities in asset pricing | IIT Bombay",
        "email_draft": "Dear Prof. Taylor Finch, ...",
        "resume_path": "./resumes/finance_resume.pdf",
    }


def make_company_record():
    return {
        "name": "Riley Chen",
        "email": "riley.chen@examplecap.test",
        "title": "Portfolio Analyst",
        "bio": "Research interests include asset pricing.",
        "company": "Example Capital",
        "timezone": "America/New_York",
        "domain_bucket": "Finance",
        "subject": "Internship / Project Opportunities in asset pricing at Example Capital | IIT Bombay",
        "email_draft": "Dear Riley Chen, ...",
        "resume_path": "./resumes/finance_resume.pdf",
        "remote_status": "Verified",
        "remote_evidence": 'Careers page states "all internships are remote."',
        "remote_evidence_url": "https://examplecap.test/careers",
    }


class TestWorkbookHeaders(unittest.TestCase):
    def test_headers_include_company_and_remote_columns(self):
        self.assertIn("Company", HEADERS)
        self.assertIn("Remote Status", HEADERS)
        self.assertIn("Remote Evidence", HEADERS)
        # existing columns must still all be present, in their original relative order
        for col in ("Name", "Email", "Designation", "Research Description",
                    "University", "Timezone", "Subject", "Personalized Email",
                    "Resume Path"):
            self.assertIn(col, HEADERS)


class TestWorkbookRowContent(unittest.TestCase):
    def _build_and_load(self, records):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.xlsx"
            build(records, str(out_path))
            wb = load_workbook(str(out_path))
            return wb

    def _row_by_header(self, ws):
        headers = [c.value for c in ws[1]]
        row = [c.value for c in ws[2]]
        return dict(zip(headers, row))

    def test_university_row_leaves_company_columns_blank(self):
        wb = self._build_and_load([make_university_record()])
        ws = wb["Finance"]
        row = self._row_by_header(ws)
        self.assertIn(row["Company"], (None, ""))
        self.assertIn(row["Remote Status"], (None, ""))
        self.assertIn(row["Remote Evidence"], (None, ""))
        self.assertEqual(row["University"], "Example School of Business")

    def test_company_row_populates_company_columns(self):
        wb = self._build_and_load([make_company_record()])
        ws = wb["Finance"]
        row = self._row_by_header(ws)
        self.assertEqual(row["Company"], "Example Capital")
        self.assertEqual(row["Remote Status"], "Verified")
        self.assertIn("all internships are remote", row["Remote Evidence"])
        self.assertIn("https://examplecap.test/careers", row["Remote Evidence"])

    def test_company_row_without_evidence_has_blank_remote_evidence(self):
        record = make_company_record()
        record["remote_status"] = "Unverified"
        del record["remote_evidence"]
        del record["remote_evidence_url"]
        wb = self._build_and_load([record])
        ws = wb["Finance"]
        row = self._row_by_header(ws)
        self.assertEqual(row["Remote Status"], "Unverified")
        self.assertIn(row["Remote Evidence"], (None, ""))

    def test_mixed_batch_both_modes_same_sheet(self):
        wb = self._build_and_load([make_university_record(), make_company_record()])
        ws = wb["Finance"]
        self.assertEqual(ws.max_row, 3)  # header + 2 rows, both Finance


if __name__ == "__main__":
    unittest.main()
