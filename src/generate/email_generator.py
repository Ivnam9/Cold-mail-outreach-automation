# -*- coding: utf-8 -*-
"""Generate a personalized email + subject line for each scraped person, using the
background/projects/domain config in config.yaml.

Usage:
    python email_generator.py --input professors.json --config config.yaml --output emails.json

Input schema (professors.json): a JSON list of
    {"name": str, "email": str | null, "title": str, "bio": str}

Output schema (emails.json): the same records plus
    {"domain_bucket": str, "topic": str, "subject": str, "email_draft": str,
     "resume_path": str}

NEVER fabricate or pattern-guess an email address upstream of this script (e.g.
firstname.lastname@domain). If a scraper couldn't find a real published address, leave
`email: null` — a blank field is honest, a guessed one bounces and looks careless.
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


def salutation(name: str) -> str:
    """Strip any parenthetical disambiguator (e.g. two people sharing a name, tagged
    "Jane Doe (Dept A)" vs "Jane Doe (Dept B)" upstream) before it leaks into the
    greeting — keep it in the spreadsheet's Name column, not in
    "Dear Prof. X (Dept A),".
    """
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    parts = clean.split(" ", 1)
    if len(parts) == 2 and parts[0] in TITLE_PREFIXES:
        return f"Dear {clean},"
    return f"Dear Prof. {clean},"


def build_background(domain_name: str, domain_cfg: dict, cfg: dict) -> str:
    projects = cfg["email_projects"]
    order = domain_cfg.get("lead_order") or list(projects.keys())

    selected = [projects[project_id] for project_id in order[:2]]

    return " and ".join(selected)


def build_subject(domain_name: str, domain_cfg: dict, topic: str) -> str:
    if domain_cfg.get("weak_fit"):
        return f"Research / Project Opportunities in {domain_name} | IIT Bombay"
    return f"Research / Project Opportunities in {topic} | IIT Bombay"


def build_email(name: str, domain_name: str, domain_cfg: dict, topic: str, cfg: dict) -> str:
    s = cfg["sender"]

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
        f"{salutation(name)}\n\n"
        f"I hope you are doing well.\n\n"
        f"{opening}\n\n"
        f"{research_line}\n\n"
        f"{opportunity_line}\n\n"
        f"{closing}"
    )

    # never let an em/en dash slip into generated text
    return body.replace("â€”", ", ").replace("â€“", ", ")

def process(people: list, cfg: dict) -> list:
    domains = cfg["domains"]
    resumes = cfg["resumes"]

    results = []

    for p in people:
        bio = p.get("bio") or ""

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

        results.append({
            **p,
            "domain_bucket": domain_name,
            "topic": topic,
            "subject": build_subject(domain_name, domain_cfg, topic),
            "email_draft": build_email(
                p["name"],
                domain_name,
                domain_cfg,
                topic,
                cfg,
            ),
            "resume_path": resume_path,
        })

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