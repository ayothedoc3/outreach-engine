"""The 3-touch cold sequence. House style: plain text, no em dashes.

Placeholders filled at render time:
  {first_name} {company} {opener} {signature} {booking_link}
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
            "Most agencies I talk to lose deals not on price but on speed: a lead fills out "
            "the form, and by the time someone replies hours later they have booked with whoever "
            "answered first.\n\n"
            "I build a small system that replies to every new lead in under 60 seconds, "
            "personalized, in your voice, with your booking link, and pings you instantly.\n\n"
            "I'll set it up for {company} free, no strings, so you can watch it work on your real "
            "leads. Want me to build it?\n\n"
            "{signature}"
        ),
    ),
    Touch(
        number=2,
        subject="re: leads going cold",
        body=(
            "Quick follow-up, {first_name}. The 60-second reply usually converts more of the leads "
            "you are already getting, without spending a cent more on ads.\n\n"
            "Still glad to build the first one free. Worth 10 minutes to set it up?\n\n"
            "{signature}"
        ),
    ),
    Touch(
        number=3,
        subject="closing the loop",
        body=(
            "I'll stop here so I am not cluttering your inbox, {first_name}.\n\n"
            "If \"every lead answered in 60 seconds\" ever becomes worth 10 minutes, I am around, "
            "and I'll still build the first one free. All the best.\n\n"
            "{signature}"
        ),
    ),
]


def render(touch: Touch, *, first_name: str, company: str, opener: str, signature: str, booking_link: str) -> tuple[str, str]:
    """Return (subject, body) with placeholders filled."""
    ctx = {
        "first_name": first_name or "there",
        "company": company or "your team",
        "opener": opener or "",
        "signature": signature,
        "booking_link": booking_link,
    }
    return touch.subject.format(**ctx), touch.body.format(**ctx)
