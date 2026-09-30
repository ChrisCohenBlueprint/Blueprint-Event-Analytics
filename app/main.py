import base64
import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from . import analytics
from . import dictionary as d
from .db import IngestRun, Registration, SessionLocal, Show, ensure_show, init_db
from .ingest import ingest_file
from .sources import regpool

BASE = Path(__file__).parent
app = FastAPI(title="Customer Insights Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

USER = os.environ.get("DASHBOARD_USER", "")
PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
INGEST_TOKEN = os.environ.get("INGEST_TOKEN", "")


@app.on_event("startup")
def _startup():
    init_db()


# The data is personal (names, emails), so the whole site sits behind a login
# whenever DASHBOARD_PASSWORD is set. /healthz stays open for Render's checks;
# /api/ingest/* accepts the INGEST_TOKEN bearer instead, for automation.
@app.middleware("http")
async def basic_auth(request: Request, call_next):
    path = request.url.path
    if path == "/healthz" or not PASSWORD:
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if path.startswith("/api/ingest/") and INGEST_TOKEN and secrets.compare_digest(auth, f"Bearer {INGEST_TOKEN}"):
        return await call_next(request)
    if auth.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
            if secrets.compare_digest(user, USER) and secrets.compare_digest(pw, PASSWORD):
                return await call_next(request)
        except Exception:
            pass
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Insights"'})


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/shows")
def shows():
    with SessionLocal() as s:
        counts = dict(s.execute(select(Registration.show_code, func.count())
                                .group_by(Registration.show_code)).all())
        rows = list(s.scalars(select(Show)))
    rows.sort(key=lambda r: (d.REGION_ORDER.get(r.region, 9), -r.year))
    return [{"code": r.code, "brand": r.brand, "name": r.name, "region": r.region, "year": r.year,
             "start_date": r.start_date.isoformat() if r.start_date else None,
             "end_date": r.end_date.isoformat() if r.end_date else None,
             "records": counts.get(r.code, 0)} for r in rows]


@app.get("/api/shows/{code}/summary")
def show_summary(code: str, segment: str = "attendees"):
    if segment not in analytics.SEGMENTS:
        raise HTTPException(400, "unknown segment")
    try:
        return JSONResponse(analytics.summary(code, segment))
    except KeyError:
        raise HTTPException(404, "unknown show")


@app.get("/api/compare")
def compare(segment: str = "attendees"):
    return analytics.compare(segment)


@app.get("/api/history")
def history(segment: str = "attendees"):
    return analytics.history(segment)


@app.get("/api/dictionary")
def dictionary():
    return {
        "fields": [{"field": f, "label": l, "definition": x} for f, l, x in d.FIELDS],
        "aliases": d.COLUMN_ALIASES,
        "sources": [{"name": n, "provides": p, "status": s} for n, p, s in d.DATA_SOURCES],
        "seniority_levels": d.SENIORITY_ORDER,
        "budget_bands": d.BUDGET_ORDER,
        "automated_shows": regpool.configured_shows(),
        "brands": [{"code": k, "name": v[0], "region": v[1]} for k, v in d.BRANDS.items()],
    }


@app.get("/api/ingest/runs")
def runs():
    with SessionLocal() as s:
        items = list(s.scalars(select(IngestRun).order_by(IngestRun.started_at.desc()).limit(25)))
    return [{"show": r.show_code, "source": r.source, "at": r.started_at.isoformat() + "Z",
             "rows": r.rows_in, "inserted": r.inserted, "updated": r.updated,
             "status": r.status, "message": r.message} for r in items]


@app.post("/api/ingest/upload")
async def upload(show_code: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    try:
        run = ingest_file(show_code.strip().upper(), file.filename or "upload.xlsx", content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    analytics.invalidate()
    return {"show": run.show_code, "rows": run.rows_in, "inserted": run.inserted, "updated": run.updated}


@app.post("/api/ingest/sync/{code}")
def sync_now(code: str):
    if code not in regpool.configured_shows():
        raise HTTPException(400, f"No REGPOOL_{code}_URL configured")
    run = regpool.sync(code)
    analytics.invalidate()
    return {"rows": run.rows_in, "inserted": run.inserted, "updated": run.updated}


@app.post("/admin/show")
def edit_show(code: str = Form(...), start_date: str = Form(""), end_date: str = Form("")):
    try:
        code = ensure_show(code).code  # also creates a new edition, e.g. LEX27
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    with SessionLocal() as s:
        show = s.get(Show, code)
        show.start_date = date.fromisoformat(start_date) if start_date else None
        show.end_date = date.fromisoformat(end_date) if end_date else None
        s.commit()
    analytics.invalidate()
    return RedirectResponse("/#sources", status_code=303)
