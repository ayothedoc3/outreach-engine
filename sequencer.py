"""Turns prospects into scheduled, personalized messages and processes what is due.

prepare_*  : personalize + render + schedule the 3 touches for a prospect.
process_due: in DRY_RUN, mark due messages as 'drafted' (review only); live, send
             them through a rotated mailbox, respecting caps, send window, and
             stop-on-reply (already enforced by db.due_messages).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001
    ZoneInfo = None  # type: ignore

import db
import sender
import sequence
from config import settings
import personalize


def _first_name(contact_name: str | None) -> str:
    if not contact_name:
        return "there"
    return contact_name.strip().split()[0]


def prepare_prospect(prospect: dict) -> None:
    pid = prospect["id"]
    opener = personalize.make_opener(prospect)
    db.set_opener(pid, opener)

    base = datetime.now(timezone.utc)
    first = _first_name(prospect.get("contact_name"))
    company = prospect.get("company") or "your team"

    for touch in sequence.TOUCHES:
        idx = touch.number - 1
        offset = settings.touch_offset_days[idx] if idx < len(settings.touch_offset_days) else touch.number * 3
        subject, body = sequence.render(
            touch,
            first_name=first,
            company=company,
            opener=opener,
            signature=settings.sender_signature,
            booking_link=settings.booking_link,
        )
        db.create_message(pid, touch.number, subject, body, base + timedelta(days=offset))

    db.set_status(pid, "active")


def prepare_all() -> int:
    count = 0
    for p in db.list_prospects():
        if p["status"] == "new":
            prepare_prospect(p)
            count += 1
    return count


def in_send_window(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if ZoneInfo is not None:
        try:
            now = now.astimezone(ZoneInfo(settings.send_timezone))
        except Exception:  # noqa: BLE001
            pass
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return settings.send_window_start <= now.hour < settings.send_window_end


def process_due(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    summary = {"processed": 0, "sent": 0, "drafted": 0, "skipped": 0, "failed": 0, "dry_run": settings.dry_run}

    due = db.due_messages(now)
    summary["processed"] = len(due)

    for m in due:
        if settings.dry_run:
            db.mark_message(m["id"], "drafted")
            summary["drafted"] += 1
            continue

        if not in_send_window(now):
            # leave it scheduled; a later run inside the window will pick it up
            continue

        to_addr = m.get("prospect_email")
        if not to_addr:
            db.mark_message(m["id"], "skipped", error="no email on prospect")
            summary["skipped"] += 1
            continue

        mb = sender.pick_mailbox()
        if mb is None:
            # all mailboxes hit their daily cap; stop this run
            break

        try:
            sender.send_email(
                mb,
                to_addr=to_addr,
                subject=m["subject"],
                body=m["body"],
                prospect_id=m["prospect_id"],
                touch=m["touch"],
            )
            db.mark_message(m["id"], "sent", mailbox_email=mb.email)
            summary["sent"] += 1
        except Exception as e:  # noqa: BLE001
            db.mark_message(m["id"], "failed", error=str(e)[:300])
            db.add_event(m["prospect_id"], "send_error", str(e)[:300])
            summary["failed"] += 1

    return summary
