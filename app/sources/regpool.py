"""Registration-pool connector.

Pulls the latest registration export straight from the registration platform so
nobody has to download and upload a spreadsheet. Configure per show with env vars:

    REGPOOL_LEX26_URL    export / API endpoint (returns XLSX, CSV or JSON)
    REGPOOL_LEX26_TOKEN  bearer token or API key (optional)
    REGPOOL_AUTH_HEADER  header name for the token (default: Authorization, sent as "Bearer <token>")

JSON responses may be a list of records, or {"data": [...]} / {"results": [...]};
record keys go through the same data dictionary as spreadsheet columns.
"""
import os

import httpx
import pandas as pd

from .. import ingest


def configured_shows():
    shows = []
    for key in os.environ:
        if key.startswith("REGPOOL_") and key.endswith("_URL"):
            shows.append(key[len("REGPOOL_"):-len("_URL")])
    return sorted(shows)


def fetch(show_code):
    url = os.environ[f"REGPOOL_{show_code}_URL"]
    token = os.environ.get(f"REGPOOL_{show_code}_TOKEN")
    header = os.environ.get("REGPOOL_AUTH_HEADER", "Authorization")
    headers = {}
    if token:
        headers[header] = f"Bearer {token}" if header.lower() == "authorization" else token
    resp = httpx.get(url, headers=headers, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        payload = resp.json()
        if isinstance(payload, dict):
            payload = payload.get("data") or payload.get("results") or payload.get("items") or []
        frame = pd.DataFrame(payload, dtype=object)
    elif "csv" in ctype or url.lower().endswith(".csv"):
        frame = ingest.read_file("export.csv", resp.content)
    else:
        frame = ingest.read_file("export.xlsx", resp.content)
    return ingest.normalise(frame)


def sync(show_code):
    rows = fetch(show_code)
    return ingest.upsert(show_code, rows, "regpool")
