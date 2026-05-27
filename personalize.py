"""Per-prospect personalization.

Fetches the prospect's homepage, then asks Claude for ONE specific opening line
that references something real on the site. Falls back to the seed hook (or a
safe generic line) when Claude or the fetch is unavailable. House rule: the
output never contains an em dash.
"""
from __future__ import annotations

import re

import httpx

from config import settings

try:
    import anthropic

    _client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
except Exception:  # noqa: BLE001
    _client = None


SYSTEM = (
    "You write the opening line of a cold B2B email for Ayothedoc, which builds a system that replies "
    "to a business's new inbound leads in under 60 seconds. The recipient is the owner of a small agency.\n\n"
    "Write ONE sentence, under 30 words, that references something specific and real from the website text "
    "provided (a named service, client, claim, or niche) and ties it to the cost of slow lead follow-up. "
    "It must read like a human who actually looked at their site, not a template.\n\n"
    "Rules: no greeting, no sign-off, output only the sentence. Plain language. "
    "Never use an em dash. Use commas or periods instead. Do not wrap the sentence in quotes."
)


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_site_text(url: str, limit: int = 6000) -> str:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": "AyothedocResearch/1.0"}) as c:
            r = c.get(url)
            r.raise_for_status()
            return _strip_html(r.text)[:limit]
    except Exception:  # noqa: BLE001
        return ""


def _no_em_dash(s: str) -> str:
    # Enforce the house style even if the model slips.
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    return s.strip().strip('"').strip()


def make_opener(prospect: dict) -> str:
    company = prospect.get("company") or "your team"
    niche = prospect.get("niche") or ""
    seed = (prospect.get("seed_hook") or "").strip()
    website = prospect.get("website") or ""

    if not _client:
        return _no_em_dash(seed) if seed else f"I came across {company} and the way you handle inbound enquiries caught my eye."

    site_text = fetch_site_text(website) if website else ""
    context = f"Company: {company}\nNiche: {niche}\nWebsite text (truncated):\n{site_text or '(could not fetch site)'}"
    if seed:
        context += f"\n\nA researcher's note you may draw on: {seed}"

    try:
        resp = _client.messages.create(
            model=settings.model,
            max_tokens=120,
            system=SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
        text = _no_em_dash(text)
        if text:
            return text
    except Exception as e:  # noqa: BLE001
        print(f"[personalize] Claude failed for {company}: {e}")

    return _no_em_dash(seed) if seed else f"I came across {company} and the way you handle inbound enquiries caught my eye."
