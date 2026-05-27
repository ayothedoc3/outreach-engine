"""Generate personalized draft emails for the seed targets without a database.

Proves the personalization + sequence end to end and writes drafts_preview.md.
Nothing is sent. Run: python demo_draft.py  (set ANTHROPIC_API_KEY to use Claude;
without it, the opener falls back to the researcher's seed hook).
"""
from __future__ import annotations

import csv
import os

import personalize
import sequence
from config import settings

LIMIT = int(os.environ.get("DEMO_LIMIT", "12"))


def main() -> None:
    with open(os.path.join(os.path.dirname(__file__), "seed_targets.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[:LIMIT]

    out = ["# Outreach drafts preview (DRY RUN, nothing sent)\n"]
    out.append(f"Model: {settings.model} | Claude active: {bool(settings.anthropic_api_key)}\n")
    for r in rows:
        opener = personalize.make_opener(r)
        first = (r.get("contact_name") or "there").split()[0]
        out.append(f"\n## {r['company']}  ({r.get('country')})")
        out.append(f"To: {r.get('email') or 'enrich via Apollo'}  |  {r.get('website')}")
        out.append(f"Opener: {opener}\n")
        for t in sequence.TOUCHES:
            subj, body = sequence.render(
                t,
                first_name=first,
                company=r["company"],
                opener=opener,
                signature=settings.sender_signature,
                booking_link=settings.booking_link,
            )
            out.append(f"### Touch {t.number} (subject: {subj})\n```\n{body}\n```")
        print(f"  personalized: {r['company']}")

    text = "\n".join(out)
    with open(os.path.join(os.path.dirname(__file__), "drafts_preview.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nem dashes in output: {text.count(chr(8212))}")
    print(f"wrote drafts_preview.md for {len(rows)} prospects")


if __name__ == "__main__":
    main()
