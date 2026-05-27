# Ayothedoc Outreach Engine

A custom cold-outreach engine: it personalizes a 3-touch email sequence per prospect with Claude, schedules the touches, sends through your warmed mailboxes with caps and a send window, and stops the sequence the moment a prospect replies (optionally handing the reply to the Lead Engine for an instant booking response).

It ships in **DRY RUN** by default: nothing is sent, every email is rendered for review. You flip to live only after your sending domains finish warmup.

## How it works

```
seed CSV / Apollo  ->  prospects (Postgres)
                         |
                  personalize.py  (fetch site -> Claude writes the opener, no em dashes)
                         |
                  sequencer.prepare  (render touch 1/2/3, schedule day 0 / 3 / 6)
                         |
   worker loop  ->  sequencer.process_due  ->  sender.py (SMTP, rotated mailboxes, caps, window)
                         |
                  replies.py (IMAP)  ->  mark replied, cancel pending touches, hand off to Lead Engine
```

## Files
- `config.py` settings from env (no secrets in code)
- `db.py` Postgres schema + queries (prospects, messages, events)
- `personalize.py` per-prospect opener via Claude, with an em-dash guard
- `sequence.py` the 3-touch templates
- `sequencer.py` prepare + process-due logic (cadence, caps, send window)
- `sender.py` SMTP send + mailbox rotation + threading
- `replies.py` IMAP reply detection + Lead Engine handoff
- `main.py` FastAPI dashboard + trigger endpoints (gated by DASHBOARD_SECRET)
- `worker.py` background loop (the `worker` process)
- `demo_draft.py` generate drafts for the seed list with no database
- `seed_targets.csv` the 12 verified starter agencies

## Run locally (draft mode)
```
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
./.venv/bin/python demo_draft.py        # writes drafts_preview.md, no DB needed
```
With a database set, run the API and use the dashboard buttons:
```
export DATABASE_URL=postgres://...  DASHBOARD_SECRET=...  ANTHROPIC_API_KEY=...
./.venv/bin/uvicorn main:app --port 8080
# open http://localhost:8080/?key=YOUR_DASHBOARD_SECRET
# 1) Import seed targets  2) Personalize + schedule  3) Run due (drafts in dry run)
```

## Going live (the part the software cannot do for you)
Cold email lives or dies on deliverability. Before setting `DRY_RUN=false`:

1. **Buy 2 secondary domains** (never send cold from ayothedoc.com). For example tryayothedoc.com, getayothedoc.com. Set each to forward/redirect to ayothedoc.com.
2. **Create 2 to 3 mailboxes** on those domains (Google Workspace, about $6 per mailbox per month).
3. **Authenticate each domain**: SPF, DKIM, and a DMARC record. Without all three you land in spam.
4. **Warm up the mailboxes for 2 to 3 weeks** before real sends (a warmup tool ramps volume automatically).
5. Put the mailbox SMTP/IMAP details in `MAILBOXES_JSON`, keep `DAILY_CAP_PER_MAILBOX` low (20 to 30), set `DRY_RUN=false`.

## Compliance
Targets are UK/EU/CA/AU, so cold B2B is allowed but regulated (GDPR/PECR, CASL, the Australian Spam Act). Keep volume low, personalize every first line, stay strictly B2B, and give an easy way to opt out. The sequence already offers to stop.

## Env vars
See `.env.example`. Key ones: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `DRY_RUN`, `DASHBOARD_SECRET`, `MAILBOXES_JSON`, `BOOKING_LINK`, `LEAD_ENGINE_URL` + `LEAD_ENGINE_SECRET` (optional reply handoff), `APOLLO_API_KEY` (optional sourcing later).
