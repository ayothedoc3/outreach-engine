"""The 3-touch cold sequence. House style: plain text, no em dashes.

Placeholders filled at render time:
  {first_name} {name_suffix} {company} {opener} {signature} {booking_link}
The {opener} is the per-prospect personalized first line from personalize.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Touch:
    number: int
    subject: str
    body: str


TOUCHES: list[Touch] = [
    Touch(
        number=1,
        subject="leads going cold while you're in meetings?",
        body=(
            "Hi {first_name},\n\n"
            "{opener}\n\n"
            "Most agencies lose deals not on price but on speed: a lead fills out the form, and by "
            "the time someone replies hours later they have booked with whoever answered first.\n\n"
            "I build a small system that replies to every new lead in under 60 seconds, "
            "personalized, in your voice, with your booking link, and pings you instantly. Here it "
            "is running on a real lead: ayothedoc.com/demo\n\n"
            "I'll build the first one free for {company}, on your real leads, no strings. Want me to "
            "set it up, yes or no?\n\n"
            "{signature}"
        ),
    ),
    Touch(
        # Consequence-based, never leaves a "maybe": hold a slot or pass it on.
        number=2,
        subject="re: leads going cold",
        body=(
            "Following up{name_suffix}. I only take a few free builds a month so each one gets done "
            "right, and I'm lining up this month's now.\n\n"
            "Want me to hold a slot for {company}, or should I pass it on? Either way is fine, just "
            "let me know.\n\n"
            "{signature}"
        ),
    ),
    Touch(
        # Clean takeaway close: file closed, door left open, no third "just checking in".
        number=3,
        subject="closing the loop",
        body=(
            "I'll close your file here{name_suffix}, since I have not heard back.\n\n"
            "If answering every lead in 60 seconds ever becomes a priority, the first build is still "
            "free. Just reply to this and I'll set it up. All the best.\n\n"
            "{signature}"
        ),
    ),
]


def render(touch: Touch, *, first_name: str, company: str, opener: str, signature: str, booking_link: str) -> tuple[str, str]:
    """Return (subject, body) with placeholders filled."""
    ctx = {
        "first_name": first_name or "there",
        # ", Jack" when we know the name, "" when we don't (so touches 2/3 read
        # cleanly as "Quick follow-up." instead of "Quick follow-up, there.")
        "name_suffix": f", {first_name}" if first_name else "",
        "company": company or "your team",
        "opener": opener or "",
        "signature": signature,
        "booking_link": booking_link,
    }
    return touch.subject.format(**ctx), touch.body.format(**ctx)
