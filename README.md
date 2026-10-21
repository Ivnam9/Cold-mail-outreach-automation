# Cold Mail Outreach Automation

A pipeline for running a personalized, research-fit-aware cold email campaign to professors —
built for reaching out about research opportunities, but the pattern generalizes to any
"find a list of people, learn what each of them actually does, write each of them a
genuinely relevant email, then send in reviewable batches" workflow.

It does **not** try to blast generic mail-merge messages. The whole point is that every email
is written using the recipient's actual, current research description (not a job title, not a
department label), and every batch is meant to be reviewed by a human before anything sends.

## Two outreach modes

Every person record carries an optional `"mode"` field:

- **`"university"`** (the default — any record with no `"mode"` key behaves exactly as before
  Company Mode existed): professors, researchers, labs.
- **`"company"`**: startups/companies, for remote internships and project roles.

Both modes share the *exact same* Finance/FinTech/AI_ML domain classification, topic
extraction, flagship-project ordering, and resume routing (`config.yaml`'s `domains`/
`resumes` blocks) — only the salutation, subject line, opening paragraph and "opportunity"
sentence differ, since "Dear Prof. X, I'd like to work on your research" doesn't make sense
addressed to a company contact. See `src/generate/email_generator.py`'s module docstring for
the exact field-level differences, and `examples/sample_companies.json` /
`examples/sample_company_batch.csv` for a worked example.

**Company-record fields** (superset of the university schema): `mode: "company"`, `company`
(required), `company_url`, `name`, `title`, `email`, `bio`, `source_url`, `timezone`, and
optionally `remote_evidence` / `remote_evidence_url` — a quote and its source URL proving the
company actually offers remote work. **Remote evidence is preferred, not required.** A lead
with no evidence is still kept (never dropped for this reason alone) and the generated record
is marked `remote_status: "Unverified"` rather than ever claiming remote eligibility that
wasn't confirmed; `remote_status: "Verified"` only when both `remote_evidence` and
`remote_evidence_url` are present. The exported review workbook (`src/export/build_workbook.py`)
surfaces `Company` / `Remote Status` / `Remote Evidence` columns, left blank for University
Mode rows, so an `Unverified` lead is easy to spot and resolve by hand before approving it.

Only set `email` when it's actually published somewhere official — the "never fabricate or
pattern-guess an email" rule applies identically to company contacts (no
`firstname.lastname@company.com` guessing) and to `remote_evidence`/`remote_evidence_url`
(never assert a company is remote-friendly without a real source backing it).

Scheduling, sending, and duplicate-protection (`src/schedule/scheduling.py`,
`src/send/send_batch.py`) are completely unmodified and mode-agnostic — they only ever see the
generated CSV's `send/name/email/subject/email_body/resume_path/timezone` columns, the same
Tuesday/Thursday recipient-local send window applies to both modes, and the per-batch sent-log
dedup works identically either way.

## What it does

1. **Scrape** — pull a faculty list plus each person's real research bio, institution, and IANA
   timezone from a university's own site (see `src/scrape/` for worked examples against a few
   common site patterns).
2. **Classify** — bucket each person into a research domain (ML, NLP, Computer Vision, ...)
   based on the *content* of their bio, not just their job title — titles lie more often than
   you'd expect (`src/classify/domain_classifier.py`).
3. **Generate** — write a personalized email per person: an opening that names 1-2 of *their*
   actual topics (never their whole research portfolio — that reads as "I didn't really read
   your bio"), a background paragraph built from your own project blurbs (ordered by relevance
   to their domain), and a consistent closing. Each person's domain also selects which resume
   gets attached later — e.g. Finance / FinTech / AI_ML each route to their own resume PDF, set
   under `resumes:` in `config.yaml` (`src/generate/email_generator.py`).
4. **Export** — a multi-sheet Excel workbook, one sheet per domain, for human review
   (`src/export/build_workbook.py`).
5. **Send** — a batch mailer (Jupyter notebook for supervised runs, or a standalone script for
   scheduled/unattended runs) that sends a reviewed CSV batch over SMTP. Every row only sends on
   a Tuesday or Thursday, between 7:30 and 9:30 AM in *the recipient's own* local timezone —
   never the sender's — with per-send delay and a persistent sent-log so re-running never
   double-sends (`src/send/`, `src/schedule/scheduling.py`).

## Why it's structured this way

This came out of actually running the campaign, not from a design doc. A few of the choices
exist specifically because of mistakes made along the way:

- **Domain classification is checked against bio content, not just trusted from the person's
  title.** Titles like "Professor of Computer Science" tell you nothing about whether someone
  works on vision, security, or theory. Classifying by title alone silently sent the most
  specific, most reusable version of the flagship-project pitch to the wrong bucket for a
  meaningful fraction of people — including, in one run, two of the most prominent researchers
  at the target institution, who ended up with a generic email instead of a personalized one.
- **Every batch is written to a plain-text review file before anything is queued to send.**
  No email goes out without a human reading it first.
- **The mailer never fabricates a recipient's email address.** If it wasn't found published on
  an official page, the field stays blank. Pattern-guessing addresses (`firstname.lastname@...`)
  produces bounces and looks careless.
- **Text-processing helpers that trim or re-case scraped text are the single most bug-prone
  part of this pipeline.** A naive word-by-word regex trim silently dropped internal
  hyphens and duplicated fragments of text (`"Cross-language"` → `"crosslanguage"`,
  `"Tan Lip-Bu"` → `"Lip-Bulipbu"`). If you touch `domain_classifier.py`'s topic-trimming
  logic, re-run it against real scraped text afterward and diff a sample by eye — this class of
  bug doesn't throw an exception, it just quietly corrupts a fraction of your output.
- **Credentials are never hardcoded.** The mailer reads `SENDER_EMAIL` / `SENDER_APP_TOKEN` /
  `SENDER_NAME` from the environment (see `.env.example`). Don't put real values in any tracked
  file.
- **Sends are gated on the recipient's own local time, not the sender's.** Every batch row
  carries a `timezone` column (an IANA name, e.g. `America/New_York`) traced back to the
  scraped record. `send_batch.py` only sends a row when, converted into *that* timezone, right
  now falls on a Tuesday or Thursday between 7:30 and 9:30 AM. Because each run just checks "is
  it due right now?" against the real clock, there's no long-lived scheduler process to keep
  alive — run the script periodically from `cron` or Windows Task Scheduler (every 15-30
  minutes is plenty) and it picks up newly-due rows on its own, including correctly handling
  DST, indefinitely into the future, without any date ever being hard-coded.

## Setup

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # fill in your own background/projects
cp .env.example .env                 # fill in your own SMTP credentials
```

Edit `config.yaml`:
- `sender`: your name, degree, institution — used in the signature and salutation logic.
- `flagship_projects`: 1-3 of your strongest projects, written as ready-to-paste sentences.
  These appear in every email, ordered by relevance to the recipient's domain.
- `secondary_projects`: shorter, domain-specific blurbs (e.g. an NLP project, a CV project) —
  only the one matching the recipient's bucket gets appended.
- `domains`: the keyword lists used to classify bios. Tune these to your field (e.g. Finance /
  FinTech / AI_ML, or the research-area buckets in `config.example.yaml`).
- `resumes`: one resume PDF path per domain name in `domains` (exact key match, e.g.
  `Finance: ./resumes/finance_resume.pdf`). This is what routes each person to the right
  resume — every generated/exported/sent record keeps its own `resume_path`.

## Usage

```bash
# 1. Scrape (site-specific — see src/scrape/ for patterns to adapt). Each record needs
#    name/email/title/bio plus the recipient's university and IANA timezone.
python src/scrape/your_university_scraper.py --out data/professors.json

# 2. Classify + generate emails (also assigns each row's domain-specific resume_path)
python src/generate/email_generator.py \
    --input data/professors.json \
    --config config.yaml \
    --output data/emails.json

# 3. Export for human review (includes University/Timezone/Resume Path columns)
python src/export/build_workbook.py --input data/emails.json --output Professors.xlsx

# 4. Review the .xlsx, then build a send batch (CSV) for whichever rows you approve —
#    columns: send, name, email, subject, email_body, resume_path, timezone.

# 5. Send. Interactively via the notebook, or unattended via the standalone script —
#    both only send a row inside its OWN Tue/Thu 7:30-9:30 AM recipient-local window.
#    Run send_batch.py periodically (cron / Windows Task Scheduler); it exits after
#    each pass and picks up newly-due rows on the next scheduled run, indefinitely.
python src/send/send_batch.py --batch data/batch_01.csv
```

### Selecting University vs Company Mode

There's no separate command or flag — the mode is a per-record field in your input JSON (see
"Two outreach modes" above). Steps 2-5 are identical either way:

```bash
# University Mode input: records with no "mode" field (or "mode": "university").
python src/generate/email_generator.py \
    --input data/professors.json --config config.yaml --output data/emails.json

# Company Mode input: records with "mode": "company" and a "company" field.
# See examples/sample_companies.json for the full fictional schema reference.
python src/generate/email_generator.py \
    --input data/companies.json --config config.yaml --output data/emails.json

# A single input file may even mix both kinds of records — each is classified and
# generated independently, and build_workbook.py groups by domain_bucket regardless
# of mode (Company/Remote Status/Remote Evidence columns stay blank for university rows).
```

## Repo layout

```
config.example.yaml        # background/projects/domain/resume config template
.env.example                # required environment variables for sending mail
src/
  scrape/                   # example scrapers for common site patterns (WordPress REST API,
                             # embedded JSON-LD, generic HTML directory listing) — also attach
                             # each record's university + IANA timezone
  classify/
    domain_classifier.py    # keyword-based bio -> domain-bucket classifier
  generate/
    email_generator.py      # config-driven personalized email + subject + resume_path generator
  export/
    build_workbook.py       # multi-sheet Excel builder (one sheet per domain)
  schedule/
    scheduling.py           # timezone-aware Tue/Thu 7:30-9:30 AM recipient-local send window
  send/
    mailer_notebook.ipynb   # interactive, supervised batch sender (dry-run + send + dashboard)
    send_batch.py           # standalone unattended sender (for scheduled/cron/Task Scheduler runs)
tests/
  test_scheduling.py        # timezone/DST/window/duplicate-day unit tests (fictional data only)
  test_send_batch.py        # scheduled/due filtering + duplicate-send-prevention tests
  test_email_generator.py   # domain-specific resume routing tests (University Mode)
  test_company_mode.py      # Company Mode generation, remote-evidence verification,
                             # University Mode backward-compatibility regression
  test_build_workbook.py    # review workbook's Company/Remote Status/Remote Evidence columns
examples/
  sample_professors.json    # a handful of fictional University Mode example records
  sample_batch.csv          # a fictional University Mode example send-batch
  sample_companies.json     # a handful of fictional Company Mode example records
  sample_company_batch.csv  # a fictional Company Mode example send-batch
docs/
  PIPELINE.md                # longer write-up of the methodology and lessons learned
```

## Testing

```bash
python -m unittest discover -s tests -v
```

Covers timezone conversion (including DST transitions), the Tuesday/Thursday + 7:30-9:30 AM
local-time window across several different recipient timezones, which rows count as "due"
right now, duplicate-send prevention across re-runs, domain-specific resume routing, Company
Mode email generation (salutation/subject/opening/opportunity wording, remote-evidence
verification, missing-`company`-field/unknown-`mode` validation), the review workbook's new
columns, and that University Mode output is byte-identical whether a record's `mode` field is
absent or explicitly `"university"`. Everything runs against fictional sample data and never
opens a network connection or SMTP session — no real email is ever sent by the test suite.

## What's *not* in this repo

No real scraped data, no real email addresses, no credentials, no resume, no identifying
information about who originally built this. `examples/` uses entirely fictional names. If
you use this, your own scraped data and your own `config.yaml`/`.env` should stay local
(both are gitignored).

## License

MIT — see `LICENSE`.
