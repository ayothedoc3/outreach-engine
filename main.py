"""Outreach engine API + dashboard.

Every state-changing route and the dashboard are gated by DASHBOARD_SECRET
(passed as ?key= or the X-Engine-Secret header). The engine never sends in
DRY_RUN; it renders every email for review instead.
"""
from __future__ import annotations

import hmac
import html
import os

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

import db
import sequencer
import replies
from config import settings

app = FastAPI(title="Ayothedoc Outreach Engine")

SEED_CSV = os.path.join(os.path.dirname(__file__), "seed_targets.csv")


@app.on_event("startup")
def _startup() -> None:
    if settings.database_url:
        try:
            db.init_db()
        except Exception as e:  # noqa: BLE001
            print(f"[startup] init_db failed: {e}")


def _check(key: str | None, header_key: str | None) -> None:
    presented = key or header_key or ""
    if not settings.dashboard_secret or not hmac.compare_digest(presented, settings.dashboard_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "dry_run": settings.dry_run,
            "mailboxes": len(settings.mailboxes),
            "model": settings.model,
            "db": bool(settings.database_url),
        }
    )


@app.post("/import")
def do_import(key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)):
    _check(key, x_engine_secret)
    n = db.import_csv(SEED_CSV)
    return {"imported": n}


@app.post("/prepare")
def do_prepare(key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)):
    _check(key, x_engine_secret)
    n = sequencer.prepare_all()
    return {"prepared": n}


@app.post("/run")
def do_run(key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)):
    _check(key, x_engine_secret)
    return sequencer.process_due()


@app.post("/poll-replies")
def do_poll(key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)):
    _check(key, x_engine_secret)
    return replies.poll_replies()


@app.post("/prospects")
async def add_prospect(request: Request, key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)):
    _check(key, x_engine_secret)
    body = await request.json()
    if not body.get("company"):
        raise HTTPException(status_code=400, detail="company is required")
    pid = db.add_prospect(body)
    return {"id": pid}


# ---------- dashboard ----------

def _esc(s) -> str:
    return html.escape(str(s or ""))


@app.get("/", response_class=HTMLResponse)
def dashboard(key: str | None = Query(default=None), x_engine_secret: str | None = Header(default=None)) -> HTMLResponse:
    _check(key, x_engine_secret)
    st = db.stats() if settings.database_url else {}
    prospects = db.list_prospects() if settings.database_url else []

    banner = (
        "<div style='background:#fef9c3;border:1px solid #eab308;padding:10px 14px;border-radius:8px;margin-bottom:16px'>"
        "DRY RUN is ON. Nothing is sent. Emails below are rendered for review. Set DRY_RUN=false (after warmup) to send."
        "</div>"
        if settings.dry_run
        else "<div style='background:#dcfce7;border:1px solid #22c55e;padding:10px 14px;border-radius:8px;margin-bottom:16px'>"
        "LIVE sending is ON.</div>"
    )

    rows = []
    for p in prospects:
        msgs = db.messages_for(p["id"]) if settings.database_url else []
        msg_html = ""
        for m in msgs:
            msg_html += (
                f"<details style='margin:6px 0'><summary><b>Touch {m['touch']}</b> "
                f"<span style='color:#64748b'>[{_esc(m['status'])}]</span> "
                f"<span style='color:#94a3b8'>{_esc(m['subject'])}</span></summary>"
                f"<pre style='white-space:pre-wrap;background:#f8fafc;padding:10px;border-radius:6px;margin-top:6px'>"
                f"{_esc(m['body'])}</pre></details>"
            )
        rows.append(
            "<tr style='border-top:1px solid #e2e8f0'>"
            f"<td style='padding:8px;vertical-align:top'>{p['id']}</td>"
            f"<td style='padding:8px;vertical-align:top'><b>{_esc(p['company'])}</b><br>"
            f"<span style='color:#64748b;font-size:12px'>{_esc(p.get('niche'))}</span><br>"
            f"<a href='{_esc(p.get('website'))}' style='font-size:12px'>{_esc(p.get('website'))}</a></td>"
            f"<td style='padding:8px;vertical-align:top'>{_esc(p.get('contact_name'))}<br>"
            f"<span style='font-size:12px;color:#64748b'>{_esc(p.get('email') or 'enrich via Apollo')}</span></td>"
            f"<td style='padding:8px;vertical-align:top'><span style='font-weight:600'>{_esc(p['status'])}</span></td>"
            f"<td style='padding:8px;vertical-align:top'>{_esc(p.get('opener'))}<br>{msg_html}</td>"
            "</tr>"
        )

    by_status = st.get("by_status", {})
    stat_line = (
        f"Prospects: {st.get('total_prospects', 0)} &nbsp;|&nbsp; "
        f"Sent: {st.get('messages_sent', 0)} &nbsp;|&nbsp; "
        f"Drafted: {st.get('messages_drafted', 0)} &nbsp;|&nbsp; "
        f"Replies: {st.get('replies', 0)} &nbsp;|&nbsp; "
        f"By status: {_esc(by_status)}"
    )

    page = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Ayothedoc Outreach Engine</title>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<style>body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#0f172a}}
button{{background:#84cc16;color:#0f172a;border:0;padding:8px 14px;border-radius:8px;font-weight:600;cursor:pointer;margin-right:8px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th{{text-align:left;padding:8px;color:#64748b}}</style>
</head><body>
<h1>Outreach Engine</h1>
{banner}
<p>{stat_line}</p>
<p>
<button onclick="act('/import')">1. Import seed targets</button>
<button onclick="act('/prepare')">2. Personalize + schedule</button>
<button onclick="act('/run')">3. Run due (draft/send)</button>
<button onclick="act('/poll-replies')">Poll replies</button>
<span id="msg" style="margin-left:10px;color:#475569"></span>
</p>
<table><thead><tr><th>#</th><th>Company</th><th>Contact</th><th>Status</th><th>Opener + emails</th></tr></thead>
<tbody>{''.join(rows) or "<tr><td colspan=5 style='padding:12px;color:#64748b'>No prospects yet. Click Import seed targets.</td></tr>"}</tbody></table>
<script>
const key = new URLSearchParams(location.search).get('key') || '';
async function act(path){{
  document.getElementById('msg').textContent = 'working...';
  const r = await fetch(path + '?key=' + encodeURIComponent(key), {{method:'POST'}});
  const d = await r.json();
  document.getElementById('msg').textContent = JSON.stringify(d);
  if (r.ok) setTimeout(()=>location.reload(), 800);
}}
</script>
</body></html>"""
    return HTMLResponse(page)
