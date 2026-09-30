"""Turn a registration export (XLSX / CSV / list of dicts) into canonical rows and upsert them."""
import io
from datetime import datetime

import pandas as pd
from sqlalchemy import select

from . import dictionary as d
from .db import IngestRun, Registration, SessionLocal, ensure_show

# Workbook tabs that hold the main registration list. Other tabs in the working
# file are per-exhibitor lead lists and are skipped.
PREFERRED_SHEETS = ("visitor data", "registrations", "attendees", "data")


def read_file(filename, content):
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=object)
        for pref in PREFERRED_SHEETS:
            for title, frame in sheets.items():
                if title.strip().lower() == pref:
                    return frame
        return max(sheets.values(), key=len)
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=object)
    raise ValueError("Upload an .xlsx or .csv export")


def normalise(frame):
    """Map raw columns onto the data dictionary. Returns list of dicts."""
    mapping, extras = {}, []
    for col in frame.columns:
        field = d.canonical_column(col)
        if field and field not in mapping.values():
            mapping[col] = field
        else:
            extras.append(col)
    if "source_id" not in mapping.values():
        raise ValueError("No registration ID column found (expected e.g. 'Visitor Code')")

    rows = []
    for rec in frame.to_dict(orient="records"):
        raw = {mapping[c]: rec[c] for c in mapping}
        sid = d.clean(raw.get("source_id"))
        if not sid:
            continue
        created = raw.get("created_at")
        created = pd.to_datetime(created, errors="coerce") if created is not None else None
        created = None if created is None or pd.isna(created) else created.to_pydatetime()
        reg_type = d.clean(raw.get("reg_type_raw"))
        country = d.country(raw.get("country"))
        industry = d.clean(raw.get("industry"))
        email = d.clean(raw.get("email"))
        extra = {c: d.clean(rec[c]) for c in extras if d.clean(rec[c]) is not None}
        rows.append(dict(
            source_id=sid,
            created_at=created,
            reg_type_raw=reg_type,
            category=d.category(reg_type),
            first_name=d.clean(raw.get("first_name")),
            last_name=d.clean(raw.get("last_name")),
            company=d.clean(raw.get("company")),
            email=email.lower() if email else None,
            city=d.clean(raw.get("city")),
            state=d.clean(raw.get("state")),
            country=country,
            world_region=d.world_region(country),
            job_title=d.clean(raw.get("job_title")),
            job_function=d.clean(raw.get("job_function")),
            seniority=d.seniority(raw.get("job_title"), raw.get("job_function")),
            industry=industry,
            industry_group=d.industry_group(industry),
            buyer_supplier=d.buyer_supplier(raw.get("buyer_supplier")),
            budget_responsibility=d.budget_responsibility(raw.get("budget_responsibility")),
            budget_band=d.budget_band(raw.get("budget_band")),
            products=d.clean(raw.get("products")),
            commercial_interest=d.clean(raw.get("commercial_interest")),
            attended=d.yes_no(raw.get("attended")),
            previous_attendee=d.yes_no(raw.get("previous_attendee")),
            source_channel=d.clean(raw.get("source_channel")),
            extra=extra or None,
        ))
    return rows


def upsert(show_code, rows, source):
    """Insert new registrations and update changed ones, keyed on (show, registration ID)."""
    show_code = ensure_show(show_code).code
    run = IngestRun(show_code=show_code, source=source, rows_in=len(rows), inserted=0, updated=0,
                    status="ok", started_at=datetime.utcnow())
    now = datetime.utcnow()
    with SessionLocal() as s:
        existing = {r.source_id: r for r in s.scalars(
            select(Registration).where(Registration.show_code == show_code))}
        seen = set()
        for row in rows:
            if row["source_id"] in seen:
                continue
            seen.add(row["source_id"])
            reg = existing.get(row["source_id"])
            if reg is None:
                s.add(Registration(show_code=show_code, updated_at=now, **row))
                run.inserted += 1
            else:
                changed = False
                for k, v in row.items():
                    # Never blank out a value a later feed (e.g. attendance) already filled
                    if v is None and k in ("attended", "previous_attendee", "source_channel"):
                        continue
                    if getattr(reg, k) != v:
                        setattr(reg, k, v)
                        changed = True
                if changed:
                    reg.updated_at = now
                    run.updated += 1
        s.add(run)
        s.commit()
    return run


def ingest_file(show_code, filename, content, source="upload"):
    frame = read_file(filename, content)
    return upsert(show_code, normalise(frame), f"{source}:{filename}")
