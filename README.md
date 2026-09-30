# Customer Insights Dashboard

Live audience dashboard for Lubricant Expo Europe (LEX), North America (LNA) and Middle East (LME).
It's a Python web service (FastAPI + Postgres), not a static site, so data can be refreshed
automatically from the registration platform ("reg pool") without rebuilding anything.

**Tabs:** Audience · Behaviour · Geography · Commercial · Journey · Who are we missing? · Compare shows · Data & sources

## Run locally

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/load_local.py LEX26 "Content/LEX26_DNS_Visitor Working File_23092026.xlsx"
.venv/bin/uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

Locally it uses SQLite (`analytics.db`) and has no login. Registration exports contain personal data,
so `.xlsx` / `.csv` files and the database are git-ignored.

## Deploy to Render

1. Push this folder to a private GitHub repo.
2. In Render, go to **New → Blueprint** and pick the repo. `render.yaml` creates:
   - `customer-insights`: the web dashboard (password-protected)
   - `insights-db`: Postgres
   - `customer-insights-sync`: an hourly cron job that pulls from the reg pool
3. Set `DASHBOARD_PASSWORD` when prompted. The username is `blueprint`.
4. Open the site, go to **Data & sources**, and upload the current export to seed it.

## Automating updates from the reg pool

Each show gets its own pair of environment variables on the web service **and** the cron job:

| Variable | Example |
|---|---|
| `REGPOOL_LEX26_URL` | export or API endpoint returning XLSX, CSV or JSON |
| `REGPOOL_LEX26_TOKEN` | API key (sent as `Authorization: Bearer …`) |
| `REGPOOL_AUTH_HEADER` | optional, e.g. `X-Api-Key` if the platform uses a different header |

The cron job (`python -m app.sync`) upserts on registration ID. New people are added and changed
people are updated, with no duplicates. Other systems can push instead of being pulled:

```bash
curl -X POST https://<site>/api/ingest/upload \
  -H "Authorization: Bearer $INGEST_TOKEN" \
  -F show_code=LEX26 -F file=@export.xlsx
```

## Many shows, many years

A show is identified by **brand + two-digit year**: `LEX26`, `LNA27`, `LME28`… Brands are listed in
`dictionary.BRANDS` (add a new one there if the portfolio grows).

- **New editions create themselves.** Upload with a new code on the Data tab, push to the ingest API,
  or add `REGPOOL_LEX27_URL`, and the show is created on first data. Set its dates on the Data tab
  (needed for the registration windows and pacing).
- **Feed the same show as often as you like.** Every load upserts on registration ID, so an hourly sync
  or repeated uploads never duplicate people.
- **Editions link up automatically** by brand and year:
  - *Returning visitors*: registrants whose email appears in any earlier edition of the same brand.
  - *Pacing*: cumulative registrations by days before opening, against the previous edition.
  - *Lapsed audience*: registered last edition but not this one (Who are we missing? tab).
  - *Year over year*: headline measures per edition (Compare shows tab).
- Load **historical exports** (LEX24, LEX25…) the same way to backfill the trend.
- Columns are matched through the **data dictionary** (`app/dictionary.py`), so `26_LEM_Annual Budget`
  and `27_LNA_Annual Budget` both map to *Annual budget*, and Visitor / Attendee / Delegate all map to
  *Attendee*. To support a new source column, add its name to `COLUMN_ALIASES`.
- Journey and no-show analysis switch on when an export includes an `Attended` column (Yes/No).

## Definitions worth knowing

- **Attendee audience** = Visitor + VIP + Speaker. Exhibitors, staff, press and organisers are kept separate.
- **Senior level** = Executive / Owner + Director / VP / Head, classified from job title (`dictionary.seniority`).
  This is broader than the conservative title match in the written review (31.3%), so it reads 37%.
- **Budget bands**: the form labels "$50001 - $10000" and "$10001 - $250000" are typos. They're read as
  $50k–100k and $100k–250k.
- **Companies** are de-duplicated after stripping legal suffixes (GmbH, SE, Ltd…).
- **Registration windows** are relative to the first registration and the show opening date (editable on the Data tab).
