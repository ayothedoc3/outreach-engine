"""Settings loaded from the environment. No secrets are hard-coded."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (ValueError, AttributeError):
        return default


@dataclass
class Mailbox:
    email: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    imap_host: str = ""
    imap_port: int = 993
    daily_cap: int = 30


@dataclass
class Settings:
    database_url: Optional[str]
    anthropic_api_key: Optional[str]
    model: str
    dry_run: bool
    dashboard_secret: str
    sender_name: str
    sender_signature: str
    booking_link: str
    touch_offset_days: list[int]
    daily_cap_per_mailbox: int
    send_window_start: int
    send_window_end: int
    send_timezone: str
    mailboxes: list[Mailbox] = field(default_factory=list)
    lead_engine_url: Optional[str] = None
    lead_engine_secret: Optional[str] = None
    apollo_api_key: Optional[str] = None


def _load_mailboxes() -> list[Mailbox]:
    raw = os.environ.get("MAILBOXES_JSON", "").strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
        out = []
        for it in items:
            out.append(
                Mailbox(
                    email=it["email"],
                    smtp_host=it["smtp_host"],
                    smtp_port=int(it.get("smtp_port", 587)),
                    smtp_user=it.get("smtp_user", it["email"]),
                    smtp_pass=it["smtp_pass"],
                    imap_host=it.get("imap_host", ""),
                    imap_port=int(it.get("imap_port", 993)),
                    daily_cap=int(it.get("daily_cap", 30)),
                )
            )
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[config] could not parse MAILBOXES_JSON: {e}")
        return []


def load_settings() -> Settings:
    offsets = os.environ.get("TOUCH_OFFSET_DAYS", "0,3,6")
    try:
        touch_offsets = [int(x) for x in offsets.split(",") if x.strip() != ""]
    except ValueError:
        touch_offsets = [0, 3, 6]

    return Settings(
        database_url=os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        model=os.environ.get("OUTREACH_MODEL", "claude-opus-4-7"),
        dry_run=_bool("DRY_RUN", True),
        dashboard_secret=os.environ.get("DASHBOARD_SECRET", ""),
        sender_name=os.environ.get("SENDER_NAME", "Ayo"),
        sender_signature=os.environ.get("SENDER_SIGNATURE", "Ayo, ayothedoc.com"),
        booking_link=os.environ.get("BOOKING_LINK", "https://ayothedoc.com/contact"),
        touch_offset_days=touch_offsets,
        daily_cap_per_mailbox=_int("DAILY_CAP_PER_MAILBOX", 30),
        send_window_start=_int("SEND_WINDOW_START_HOUR", 9),
        send_window_end=_int("SEND_WINDOW_END_HOUR", 17),
        send_timezone=os.environ.get("SEND_TIMEZONE", "Europe/Vilnius"),
        mailboxes=_load_mailboxes(),
        lead_engine_url=os.environ.get("LEAD_ENGINE_URL") or None,
        lead_engine_secret=os.environ.get("LEAD_ENGINE_SECRET") or None,
        apollo_api_key=os.environ.get("APOLLO_API_KEY") or None,
    )


settings = load_settings()
