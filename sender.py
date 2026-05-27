"""SMTP sending + mailbox rotation. In DRY_RUN nothing leaves the machine.

Threading: touch 1 gets a deterministic Message-ID; touches 2 and 3 set
In-Reply-To/References to it so the follow-ups thread under the first email.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from typing import Optional

from config import Mailbox, settings
import db


def thread_message_id(prospect_id: int, mailbox_email: str) -> str:
    domain = mailbox_email.split("@")[-1] if "@" in mailbox_email else "ayothedoc.com"
    return f"<outreach-{prospect_id}-1@{domain}>"


def pick_mailbox() -> Optional[Mailbox]:
    """First mailbox still under its daily cap today."""
    for mb in settings.mailboxes:
        if db.sent_count_today(mb.email) < mb.daily_cap:
            return mb
    return None


def send_email(mailbox: Mailbox, *, to_addr: str, subject: str, body: str, prospect_id: int, touch: int) -> None:
    msg = EmailMessage()
    msg["From"] = f"{settings.sender_name} <{mailbox.email}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    tid = thread_message_id(prospect_id, mailbox.email)
    if touch == 1:
        msg["Message-ID"] = tid
    else:
        msg["In-Reply-To"] = tid
        msg["References"] = tid
    msg.set_content(body)

    with smtplib.SMTP(mailbox.smtp_host, mailbox.smtp_port, timeout=30) as s:
        s.ehlo()
        if mailbox.smtp_port in (587, 25):
            s.starttls()
            s.ehlo()
        s.login(mailbox.smtp_user, mailbox.smtp_pass)
        s.send_message(msg)
