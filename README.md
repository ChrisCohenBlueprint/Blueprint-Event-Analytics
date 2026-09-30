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

## Adding LNA / LME and future years

Shows are rows in the `shows` table (seeded: LEX26, LNA26, LME26). Upload an export against a show
and every tab fills in with the same layout. Column names are matched through the **data dictionary**
(`app/dictionary.py`), so `26_LEM_Annual Budget` and `27_LNA_Annual Budget` both map to *Annual budget*,
and Visitor / Attendee / Delegate all map to *Attendee*. To support a new source column, add its name to
`COLUMN_ALIASES`.

Journey, no-show and returning analysis switch on automatically when an export includes `Attended` or
`Previous attendee` columns (Yes/No).

## Definitions worth knowing

- **Attendee audience** = Visitor + VIP + Speaker. Exhibitors, staff, press and organisers are kept separate.
- **Senior level** = Executive / Owner + Director / VP / Head, classified from job title (`dictionary.seniority`).
  This is broader than the conservative title match in the written review (31.3%), so it reads 37%.
- **Budget bands**: the form labels "$50001 - $10000" and "$10001 - $250000" are typos. They're read as
  $50k–100k and $100k–250k.
- **Companies** are de-duplicated after stripping legal suffixes (GmbH, SE, Ltd…).
- **Registration windows** are relative to the first registration and the show opening date (editable on the Data tab).
