"""Postgres layer for the outreach engine.

Tables:
  prospects  - one row per company/contact, with sequence status
  messages   - one row per (prospect, touch): the rendered email + its state
  events     - replies, bounces, opt-outs, notes (audit trail)

Nothing here sends anything. The worker decides when to send; this module only
records state. Mailbox credentials live in env (config.Mailbox), never in the DB.
"""
from __future__ import annotations

import csv
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

from config import settings

_pool: Optional[SimpleConnectionPool] = None


def _dsn() -> str:
    dsn = settings.database_url or ""
    if not dsn:
        raise RuntimeError("DATABASE_URL is not configured")
    if os.environ.get("POSTGRES_SSL", "").lower() == "true" and "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(1, 5, dsn=_dsn())
    return _pool


@contextmanager
def conn() -> Iterator[Any]:
    pool = _get_pool()
    c = pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        pool.putconn(c)


@contextmanager
def cursor() -> Iterator[Any]:
    with conn() as c:
        cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()


def init_db() -> None:
    with cursor() as cur:
        cur.execute(
            """
            create table if not exists prospects (
              id           bigserial primary key,
              company      text not null,
              website      text,
              country      text,
              niche        text,
              contact_name text,
              email        text,
              linkedin     text,
              seed_hook    text,
              opener       text,
              source       text default 'csv',
              status       text not null default 'new',
              replied_at   timestamptz,
              created_at   timestamptz not null default now(),
              updated_at   timestamptz not null default now(),
              notes        text
            );
            """
        )
        cur.execute(
            """
            create table if not exists messages (
              id            bigserial primary key,
              prospect_id   bigint not null references prospects(id) on delete cascade,
              touch         int not null,
              subject       text not null,
              body          text not null,
              status        text not null default 'scheduled',
              scheduled_at  timestamptz not null,
              sent_at       timestamptz,
              mailbox_email text,
              error         text,
              created_at    timestamptz not null default now(),
              unique (prospect_id, touch)
            );
            """
        )
        cur.execute(
            """
            create table if not exists events (
              id          bigserial primary key,
              prospect_id bigint references prospects(id) on delete cascade,
              kind        text not null,
              detail      text,
              created_at  timestamptz not null default now()
            );
            """
        )
        cur.execute("create index if not exists messages_due_idx on messages (status, scheduled_at);")


# ---------- prospects ----------

def import_csv(path: str) -> int:
    """Insert prospects from a CSV. Dedupes on (company, website). Returns inserted count."""
    inserted = 0
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with cursor() as cur:
        for r in rows:
            cur.execute(
                "select id from prospects where company = %s and coalesce(website,'') = coalesce(%s,'')",
                (r.get("company"), r.get("website")),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                insert into prospects (company, website, country, niche, contact_name, email, linkedin, seed_hook, source)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    r.get("company"),
                    r.get("website") or None,
                    r.get("country") or None,
                    r.get("niche") or None,
                    r.get("contact_name") or None,
                    r.get("email") or None,
                    r.get("linkedin") or None,
                    r.get("seed_hook") or None,
                    "csv",
                ),
            )
            inserted += 1
    return inserted


def add_prospect(data: dict) -> int:
    with cursor() as cur:
        cur.execute(
            """
            insert into prospects (company, website, country, niche, contact_name, email, linkedin, seed_hook, source)
            values (%(company)s,%(website)s,%(country)s,%(niche)s,%(contact_name)s,%(email)s,%(linkedin)s,%(seed_hook)s,%(source)s)
            returning id
            """,
            {
                "company": data.get("company"),
                "website": data.get("website"),
                "country": data.get("country"),
                "niche": data.get("niche"),
                "contact_name": data.get("contact_name"),
                "email": data.get("email"),
                "linkedin": data.get("linkedin"),
                "seed_hook": data.get("seed_hook"),
                "source": data.get("source", "manual"),
            },
        )
        return cur.fetchone()["id"]


def list_prospects() -> list[dict]:
    with cursor() as cur:
        cur.execute("select * from prospects order by id asc")
        return list(cur.fetchall())


def get_prospect(pid: int) -> Optional[dict]:
    with cursor() as cur:
        cur.execute("select * from prospects where id = %s", (pid,))
        return cur.fetchone()


def set_opener(pid: int, opener: str) -> None:
    with cursor() as cur:
        cur.execute("update prospects set opener = %s, updated_at = now() where id = %s", (opener, pid))


def set_status(pid: int, status: str) -> None:
    with cursor() as cur:
        cur.execute("update prospects set status = %s, updated_at = now() where id = %s", (status, pid))


def mark_replied(pid: int, detail: str = "") -> None:
    with cursor() as cur:
        cur.execute(
            "update prospects set status = 'replied', replied_at = now(), updated_at = now() where id = %s",
            (pid,),
        )
        # cancel anything still queued for this prospect
        cur.execute(
            "update messages set status = 'skipped' where prospect_id = %s and status = 'scheduled'",
            (pid,),
        )
        cur.execute("insert into events (prospect_id, kind, detail) values (%s, 'reply', %s)", (pid, detail))


def add_event(pid: Optional[int], kind: str, detail: str = "") -> None:
    with cursor() as cur:
        cur.execute("insert into events (prospect_id, kind, detail) values (%s, %s, %s)", (pid, kind, detail))


# ---------- messages ----------

def create_message(pid: int, touch: int, subject: str, body: str, scheduled_at: datetime) -> None:
    with cursor() as cur:
        cur.execute(
            """
            insert into messages (prospect_id, touch, subject, body, scheduled_at, status)
            values (%s,%s,%s,%s,%s,'scheduled')
            on conflict (prospect_id, touch) do update
              set subject = excluded.subject, body = excluded.body,
                  scheduled_at = excluded.scheduled_at, status = 'scheduled', error = null
            """,
            (pid, touch, subject, body, scheduled_at),
        )


def due_messages(now: Optional[datetime] = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    with cursor() as cur:
        cur.execute(
            """
            select m.*, p.email as prospect_email, p.company, p.contact_name, p.status as prospect_status
              from messages m
              join prospects p on p.id = m.prospect_id
             where m.status = 'scheduled'
               and m.scheduled_at <= %s
               and p.status not in ('replied','paused','done','bounced')
             order by m.scheduled_at asc
            """,
            (now,),
        )
        return list(cur.fetchall())


def messages_for(pid: int) -> list[dict]:
    with cursor() as cur:
        cur.execute("select * from messages where prospect_id = %s order by touch asc", (pid,))
        return list(cur.fetchall())


def mark_message(mid: int, status: str, mailbox_email: str = "", error: str = "") -> None:
    with cursor() as cur:
        cur.execute(
            "update messages set status = %s, sent_at = case when %s in ('sent','drafted') then now() else sent_at end, "
            "mailbox_email = nullif(%s,''), error = nullif(%s,'') where id = %s",
            (status, status, mailbox_email, error, mid),
        )


def sent_count_today(mailbox_email: str) -> int:
    with cursor() as cur:
        cur.execute(
            "select count(*) as n from messages where mailbox_email = %s and status = 'sent' "
            "and sent_at >= date_trunc('day', now())",
            (mailbox_email,),
        )
        return int(cur.fetchone()["n"])


# ---------- stats ----------

def stats() -> dict:
    with cursor() as cur:
        cur.execute("select status, count(*) as n from prospects group by status")
        by_status = {r["status"]: r["n"] for r in cur.fetchall()}
        cur.execute("select count(*) as n from prospects")
        total = cur.fetchone()["n"]
        cur.execute("select count(*) as n from messages where status = 'sent'")
        sent = cur.fetchone()["n"]
        cur.execute("select count(*) as n from messages where status = 'drafted'")
        drafted = cur.fetchone()["n"]
        cur.execute("select count(*) as n from prospects where status = 'replied'")
        replied = cur.fetchone()["n"]
    return {
        "total_prospects": total,
        "by_status": by_status,
        "messages_sent": sent,
        "messages_drafted": drafted,
        "replies": replied,
    }
