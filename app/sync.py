"""Scheduled sync - run by the Render cron job: `python -m app.sync`."""
import sys

from .db import IngestRun, SessionLocal, init_db
from .sources import regpool


def main():
    init_db()
    shows = regpool.configured_shows()
    if not shows:
        print("No REGPOOL_<SHOW>_URL configured - nothing to sync.")
        return 0
    failed = 0
    for code in shows:
        try:
            run = regpool.sync(code)
            print(f"{code}: {run.rows_in} rows, {run.inserted} new, {run.updated} updated")
        except Exception as exc:  # keep syncing the other shows
            failed += 1
            print(f"{code}: FAILED - {exc}", file=sys.stderr)
            with SessionLocal() as s:
                s.add(IngestRun(show_code=code, source="regpool", status="error", message=str(exc)[:2000]))
                s.commit()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
