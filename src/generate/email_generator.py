# -*- coding: utf-8 -*-
"""Generate a personalized email + subject line for each scraped person, using the
background/projects/domain config in config.yaml.

Usage:
    python email_generator.py --input professors.json --config config.yaml --output emails.json

Input schema (professors.json): a JSON list of
    {"name": str, "email": str | null, "title": str, "bio": str}

Two outreach modes, selected per-record via an optional "mode" field:
    "university" (default when "mode" is absent) — unchanged professor/researcher/lab
        outreach. Every existing record without a "mode" key behaves exactly as before.
    "company" — startup/company outreach. Requires an additional "company" field (the
        company name); optional "company_url", "remote_evidence", "remote_evidence_url".
        Uses a name-based salutation (no "Prof." default), company-aware subject line
        and opening, and never states an opportunity is remote unless both
        "remote_evidence" and "remote_evidence_url" are present on the record — see
        `process()`'s `remote_status` ("Verified"/"Unverified") below.

Output schema (emails.json): the same records plus
    {"domain_bucket": str, "topic": str, "subject": str, "email_draft": str,
     "resume_path": str}
and, for "company" mode records only, additionally:
    {"remote_status": "Verified" | "Unverified"}

Domain classification, topic extraction, flagship-project lead_order and resume
routing are identical for both modes — only the salutation/subject/opening/opportunity
wording differs.

NEVER fabricate or pattern-guess an email address upstream of this script (e.g.
firstname.lastname@domain). If a scraper couldn't find a real published address, leave
`email: null` — a blank field is honest, a guessed one bounces and looks careless. The
same rule applies to `remote_evidence`/`remote_evidence_url`: never assert a company
offers remote work without a real source backing it.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classify.domain_classifier import classify, extract_topic

TITLE_PREFIXES = ("Sir", "Dame", "Dr.", "Dr", "Lord", "Prince")


def salutation(name: str, mode: str = "university") -> str:
    """Strip any parenthetical disambiguator (e.g. two people sharing a name, tagged
    "Jane Doe (Dept A)" vs "Jane Doe (Dept B)" upstream) before it leaks into the
    greeting — keep it in the spreadsheet's Name column, not in
    "Dear Prof. X (Dept A),".

    University mode defaults to "Dear Prof. {name}," (unless the name already carries
    its own title, e.g. "Dr."/"Sir" — see TITLE_PREFIXES). Company mode never assumes
    "Prof." — a company contact is addressed by their plain name, keeping whatever
    title prefix they already have, if any.
    """
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    parts = clean.split(" ", 1)
    has_title_prefix = len(parts) == 2 and parts[0] in TITLE_PREFIXES

    if mode == "company" or has_title_prefix:
        return f"Dear {clean},"
    return f"Dear Prof. {clean},"


def build_background(domain_name: str, domain_cfg: dict, cfg: dict) -> str:
    projects = cfg["email_projects"]
    order = domain_cfg.get("lead_order") or list(projects.keys())

    selected = [projects[project_id] for project_id in order[:2]]

    return " and ".join(selected)


def build_subject(
    domain_name: str,
    domain_cfg: dict,
    topic: str,
    mode: str = "university",
    company: str = None,
) -> str:
    if mode == "company":
        label = domain_name if domain_cfg.get("weak_fit") else topic
        return f"Internship / Project Opportunities in {label} at {company} | IIT Bombay"
    if domain_cfg.get("weak_fit"):
        return f"Research / Project Opportunities in {domain_name} | IIT Bombay"
    return f"Research / Project Opportunities in {topic} | IIT Bombay"


def build_email(
    name: str,
    domain_name: str,
    domain_cfg: dict,
    topic: str,
    cfg: dict,
    mode: str = "university",
    company: str = None,
    remote_evidence: str = None,
) -> str:
    s = cfg["sender"]

    if mode == "company":
        opening = cfg["templates"]["company_opening"].format(
            name=s["name"],
            degree=s["degree"],
            institution=s["institution"],
            minor=s["minor"],
            headline_metric=s["headline_metric"],
            topic=topic,
            company=company,
            natwest=s["natwest"],
            cfa=s["cfa"],
        ).strip()

        research_line = (
            f"I have worked on related projects including "
            f"{build_background(domain_name, domain_cfg, cfg)}, "
            f"which I believe are directly relevant to the work your team is doing."
        )

        # Only state remote work as a known fact when it's actually backed by evidence
        # (remote_evidence + remote_evidence_url) — otherwise ask, don't assume.
        if remote_evidence:
            opportunity_line = (
                f"I understand {company} supports remote internships, and I wanted to "
                "ask if there might be a remote internship or project opportunity where "
                "I could contribute and learn."
            )
        else:
            opportunity_line = (
                f"I wanted to ask if {company} might have any internship or project "
                "opportunities, remote or otherwise, where I could contribute and learn."
            )
    else:
        opening = cfg["templates"]["opening"].format(
            name=s["name"],
            degree=s["degree"],
            institution=s["institution"],
            minor=s["minor"],
            headline_metric=s["headline_metric"],
            topic=topic,
            natwest=s["natwest"],
            cfa=s["cfa"],
        ).strip()

        research_line = (
            f"I have explored related areas through projects including "
            f"{build_background(domain_name, domain_cfg, cfg)}, "
            f"which have further strengthened my curiosity about research in this field."
        )

        opportunity_line = (
            "I wanted to ask if you might have any ongoing or upcoming "
            "research/project opportunities or internships where I could contribute and learn. "
            "I would be very keen to work on a project aligned with your research."
        )

    closing = cfg["templates"]["closing"].format(
        name=s["name"],
        degree=s["degree"],
        institution=s["institution"],
        minor=s["minor"],
        iitb_email=s["iitb_email"],
        personal_email=s["personal_email"],
        phone=s["phone"],
    ).strip()

    body = (
        f"{salutation(name, mode)}\n\n"
        f"I hope you are doing well.\n\n"
        f"{opening}\n\n"
        f"{research_line}\n\n"
        f"{opportunity_line}\n\n"
        f"{closing}"
    )

    # never let an em/en dash slip into generated text
    return body.replace("â€”", ", ").replace("â€“", ", ")


VALID_MODES = ("university", "company")


def process(people: list, cfg: dict) -> list:
    domains = cfg["domains"]
    resumes = cfg["resumes"]

    results = []

    for p in people:
        bio = p.get("bio") or ""

        mode = p.get("mode", "university")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Unknown mode {mode!r} for {p.get('name')!r}; "
                f"expected one of {VALID_MODES}."
            )

        company = p.get("company")
        if mode == "company" and not company:
            raise ValueError(
                f"Company-mode record {p.get('name')!r} is missing the required "
                f"'company' field."
            )

        # Domain classification, topic extraction, lead_order and resume routing are
        # identical for both modes — only the salutation/subject/opening/opportunity
        # wording differs below.
        domain_name = (
            classify(bio, domains, default=next(iter(domains)))
            if bio
            else next(iter(domains))
        )

        domain_cfg = domains[domain_name]

        fallback = f"{domain_name.lower()} research"
        topic = (
            fallback
            if domain_cfg.get("weak_fit")
            else extract_topic(bio, fallback)
        )

        resume_path = resumes.get(domain_name)

        if not resume_path:
            raise ValueError(
                f"No resume configured for domain '{domain_name}'. "
                f"Add it under 'resumes' in config.yaml."
            )

        record = {
            **p,
            "domain_bucket": domain_name,
            "topic": topic,
            "subject": build_subject(
                domain_name, domain_cfg, topic, mode=mode, company=company
            ),
            "email_draft": build_email(
                p["name"],
                domain_name,
                domain_cfg,
                topic,
                cfg,
                mode=mode,
                company=company,
                remote_evidence=p.get("remote_evidence"),
            ),
            "resume_path": resume_path,
        }

        if mode == "company":
            # "Verified" only when both the evidence text and its source URL are
            # present — never claim remote eligibility on a hunch. Reviewers see this
            # in the workbook (src/export/build_workbook.py) and can keep an
            # "Unverified" lead for manual follow-up rather than dropping it outright.
            record["remote_status"] = (
                "Verified"
                if p.get("remote_evidence") and p.get("remote_evidence_url")
                else "Unverified"
            )

        results.append(record)

    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="scraped professors JSON")
    ap.add_argument("--config", required=True, help="config.yaml")
    ap.add_argument("--output", required=True, help="output emails JSON")
    args = ap.parse_args()

    people = json.loads(
        Path(args.input).read_text(encoding="utf-8-sig")
    )

    cfg = yaml.safe_load(
        Path(args.config).read_text(encoding="utf-8")
    )

    results = process(people, cfg)

    Path(args.output).write_text(
        json.dumps(results, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    with_email = sum(1 for r in results if r.get("email"))
    print(
        f"Processed {len(results)} people "
        f"({with_email} with a verified email)."
    )


if __name__ == "__main__":
    main()