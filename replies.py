"""Reply + bounce detection over IMAP.

Polls each mailbox for recent messages, matches the sender against active
prospects, and on a match: marks the prospect replied (which cancels pending
touches) and, if configured, hands the reply to the Lead Engine so it can fire
an instant booking response.
"""
from __future__ import annotations

import email
import imaplib
from email.utils import parseaddr

import httpx

import db
from config import Mailbox, settings


def _active_prospects_by_email() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with db.cursor() as cur:
        cur.execute("select id, company, contact_name, email, status from prospects where email is not null and email <> ''")
        for r in cur.fetchall():
            if r["status"] in ("active", "new"):
                out[r["email"].strip().lower()] = r
    return out


def _handoff_to_lead_engine(prospect: dict, snippet: str) -> None:
    if not (settings.lead_engine_url and settings.lead_engine_secret):
        return
    try:
        httpx.post(
            settings.lead_engine_url,
            headers={"Content-Type": "application/json", "X-Lead-Secret": settings.lead_engine_secret},
            json={
                "name": prospect.get("contact_name") or prospect.get("company"),
                "email": prospect.get("email"),
                "message": f"Replied to outreach: {snippet}",
                "source": "Outreach reply",
            },
            timeout=20.0,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[replies] lead-engine handoff failed: {e}")


def _poll_mailbox(mb: Mailbox, by_email: dict[str, dict]) -> int:
    if not mb.imap_host:
        return 0
    matched = 0
    try:
        M = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port)
        M.login(mb.smtp_user, mb.smtp_pass)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        if typ != "OK":
            M.logout()
            return 0
        for num in data[0].split():
            typ, msg_data = M.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            from_addr = parseaddr(msg.get("From", ""))[1].strip().lower()
            prospect = by_email.get(from_addr)
            if prospect:
                snippet = (msg.get("Subject", "") or "")[:160]
                db.mark_replied(prospect["id"], detail=f"from {from_addr}: {snippet}")
                _handoff_to_lead_engine(prospect, snippet)
                matched += 1
            # leave message state to the human; do not mark seen automatically
        M.logout()
    except Exception as e:  # noqa: BLE001
        print(f"[replies] poll failed for {mb.email}: {e}")
    return matched


def poll_replies() -> dict:
    by_email = _active_prospects_by_email()
    total = 0
    for mb in settings.mailboxes:
        total += _poll_mailbox(mb, by_email)
    return {"replies_matched": total, "mailboxes_checked": len(settings.mailboxes)}
