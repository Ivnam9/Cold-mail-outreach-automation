# -*- coding: utf-8 -*-
"""Standalone batch sender — no notebook/IDE dependency, safe to run from `cron` /
Windows Task Scheduler for a scheduled send. All credentials come from environment
variables (see .env.example) — never hardcode a token or address here.

CSV columns expected:
    send (yes/no), name, email, subject, email_body, resume_path, timezone

Rows with send != yes, or a missing subject/email_body/resume_path/timezone, are
skipped. Already-sent rows (tracked in sent_log_<batch>.csv) are skipped
automatically, so re-running never double-sends.

`timezone` is the recipient's own IANA timezone (e.g. "America/New_York" — see
src/scrape/scraping_patterns.py for where it comes from). A row is only ever sent
when, converted into THAT timezone, right now falls on a Tuesday or Thursday between
7:30 and 9:30 AM — never the sender's local time, never a hard-coded "IST" assumption.
See src/schedule/scheduling.py for the window logic.

Because each run only sends whatever is due *right now*, this script needs no
long-running process to "wait" for a future Tue/Thu — just invoke it periodically
(e.g. every 15-30 minutes) from `cron` or Windows Task Scheduler and it will pick up
newly-due rows on its own, indefinitely, without any date ever being hard-coded.

Usage:
    python send_batch.py --batch data/batch_01.csv [--delay 60] [--limit N]

Before raising --delay below 60s on a real institutional mail relay: check your inbox
for bounces after the first 5-10 sends, not just this script's own success/fail count.
SMTP accepting a message only means the relay took it — a bad address still bounces
back to your inbox minutes later as a separate message.
"""
import argparse
import csv
import os
import smtplib
import ssl
import sys
import time
from datetime import date, datetime
from email.charset import QP, Charset
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schedule.scheduling import is_due_now  # noqa: E402

UTF8_QP = Charset("utf-8")
UTF8_QP.body_encoding = QP


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(
            f"Missing required environment variable: {name} "
            "(see .env.example)"
        )
    return val


def build_html(body: str) -> str:
    import html as _h

    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    out = "".join(
        f"<p>{_h.escape(p).replace(chr(10), '<br>')}</p>"
        for p in paras
    )
    return (
        '<div style="font-family:sans-serif;font-size:14px;'
        f'line-height:1.5">{out}</div>'
    )


def build_message(
    row: dict,
    sender_name: str,
    sender_email: str,
    resume_path: Path,
):
    if not resume_path.exists():
        raise FileNotFoundError(
            f"Resume file not found: {resume_path}"
        )

    msg = MIMEMultipart("mixed")
    alt = MIMEMultipart("alternative")

    msg["From"] = formataddr((sender_name, sender_email))
    msg["To"] = row["email"]
    msg["Subject"] = row["subject"]
    msg["Reply-To"] = sender_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    body = row["email_body"]
    if not body.endswith("\n"):
        body += "\n"

    alt.attach(MIMEText(body, "plain", UTF8_QP))
    alt.attach(MIMEText(build_html(body), "html", UTF8_QP))

    msg.attach(alt)

    part = MIMEApplication(
        resume_path.read_bytes(),
        _subtype="pdf",
    )
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=resume_path.name,
    )
    msg.attach(part)

    return msg


def load_already_sent(log_path: Path) -> set:
    """Emails with a logged status of "sent" for this batch — checked before queuing
    so a re-run (e.g. the next scheduled Task Scheduler pass) never double-sends."""
    if not log_path.exists():
        return set()
    with open(log_path, newline="", encoding="utf-8") as f:
        return {
            r["email"]
            for r in csv.DictReader(f)
            if r.get("status") == "sent"
        }


def build_queue(
    rows: list,
    already_sent: set,
    now_utc: datetime = None,
) -> tuple:
    """Filter batch rows down to the ones actually eligible to send right now.

    Returns (queue, skipped) where `skipped` is a list of (row, reason) pairs, purely
    for reporting — skipped rows are never logged (they were never attempted), so a
    row missing its timezone or outside the send window today is picked up again
    automatically on a later run, with no state to reset.

    `now_utc` lets tests check a specific moment instead of the real current time;
    left as None (the default) for real sends, which always use "now".
    """
    queue = []
    skipped = []

    for row in rows:
        if row.get("send", "").strip().lower() != "yes":
            skipped.append((row, "send != yes"))
            continue

        if row.get("email") in already_sent:
            skipped.append((row, "already sent"))
            continue

        if not (
            row.get("subject")
            and row.get("email_body")
            and row.get("resume_path")
        ):
            skipped.append((row, "missing subject/email_body/resume_path"))
            continue

        tz_name = (row.get("timezone") or "").strip()
        if not tz_name:
            skipped.append((row, "missing timezone - cannot verify send window"))
            continue

        try:
            due = is_due_now(tz_name, now_utc=now_utc)
        except ValueError as e:
            skipped.append((row, f"invalid timezone: {e}"))
            continue

        if not due:
            skipped.append(
                (row, f"outside Tue/Thu 7:30-9:30 AM local window ({tz_name})")
            )
            continue

        queue.append(row)

    return queue, skipped


def log_send(
    log_path: Path,
    row: dict,
    batch: str,
    status: str,
    error: str = "",
) -> None:
    exists = log_path.exists()

    fields = [
        "timestamp",
        "date",
        "batch",
        "name",
        "email",
        "subject",
        "status",
        "error",
    ]

    with open(
        log_path,
        "a",
        newline="",
        encoding="utf-8",
    ) as f:
        w = csv.DictWriter(f, fieldnames=fields)

        if not exists:
            w.writeheader()

        w.writerow({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": date.today().isoformat(),
            "batch": batch,
            "name": row.get("name", ""),
            "email": row["email"],
            "subject": row["subject"],
            "status": status,
            "error": error,
        })


def main():
    ap = argparse.ArgumentParser(description=__doc__)

    ap.add_argument(
        "--batch",
        required=True,
        help="path to the batch CSV",
    )

    ap.add_argument(
        "--delay",
        type=int,
        default=60,
        help="seconds between sends (default 60)",
    )

    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="send only the first N queued rows",
    )

    args = ap.parse_args()

    sender_name = require_env("SENDER_NAME")
    sender_email = require_env("SENDER_EMAIL")
    sender_token = require_env("SENDER_APP_TOKEN")
    smtp_server = require_env("SMTP_SERVER")

    smtp_port = int(
        os.environ.get("SMTP_PORT", "587")
    )

    batch_path = Path(args.batch)
    batch_name = batch_path.stem
    log_path = (
        batch_path.parent
        / f"sent_log_{batch_name}.csv"
    )

    already_sent = load_already_sent(log_path)

    with open(
        batch_path,
        newline="",
        encoding="utf-8",
    ) as f:
        rows = list(csv.DictReader(f))

    queue, skipped = build_queue(rows, already_sent)

    if args.limit:
        queue = queue[: args.limit]

    print(f"Queued: {len(queue)}")

    if skipped:
        reason_counts = {}
        for _, reason in skipped:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        print(f"Skipped: {len(skipped)}")
        for reason, count in reason_counts.items():
            print(f"  {count}x {reason}")

    if not queue:
        return

    ctx = ssl.create_default_context()

    smtp = smtplib.SMTP(
        smtp_server,
        smtp_port,
        timeout=30,
    )

    smtp.ehlo()
    smtp.starttls(context=ctx)
    smtp.ehlo()
    smtp.login(
        sender_email,
        sender_token,
    )

    print(f"Connected as {sender_email}.")

    ok = fail = 0

    for i, row in enumerate(queue, 1):

        print(
            f"[{i}/{len(queue)}] "
            f"{row.get('name', ''):<32} "
            f"{row['email']}"
        )

        try:
            resume_path = Path(
                row["resume_path"].strip()
            )

            msg = build_message(
                row,
                sender_name,
                sender_email,
                resume_path,
            )

            smtp.send_message(msg)

            ok += 1
            print(
                f"  sent with {resume_path.name}"
            )

            log_send(
                log_path,
                row,
                batch_name,
                "sent",
            )

        except smtplib.SMTPRecipientsRefused as e:
            fail += 1
            print(f"  refused: {e.recipients}")

            log_send(
                log_path,
                row,
                batch_name,
                "refused",
                str(e.recipients),
            )

        except Exception as e:
            fail += 1
            print(
                f"  failed: {type(e).__name__}: {e}"
            )

            log_send(
                log_path,
                row,
                batch_name,
                "failed",
                str(e),
            )

        if i < len(queue):
            time.sleep(args.delay)

    smtp.quit()

    print(
        f"Done. sent={ok} failed={fail}"
    )


if __name__ == "__main__":
    main()