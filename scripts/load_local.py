"""Load a local registration export into the database: python scripts/load_local.py LEX26 path/to/file.xlsx"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.db import init_db  # noqa: E402
from app.ingest import ingest_file  # noqa: E402

init_db()
code, path = sys.argv[1], pathlib.Path(sys.argv[2])
run = ingest_file(code, path.name, path.read_bytes(), source="local")
print(f"{code}: {run.rows_in} rows, {run.inserted} new, {run.updated} updated")
