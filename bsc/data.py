"""Raw data: download the public Olist files, verify checksums, load into DuckDB, build the warehouse."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SAMPLE = ROOT / "data" / "sample"
MANIFEST = ROOT / "data" / "manifest.json"
SQL = ROOT / "sql"
BASE_URL = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"

TABLES = {
    "raw_orders": "olist_orders_dataset.csv",
    "raw_items": "olist_order_items_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_customers": "olist_customers_dataset.csv",
    "raw_sellers": "olist_sellers_dataset.csv",
    "raw_geolocation": "olist_geolocation_dataset.csv",
    "raw_category_translation": "product_category_name_translation.csv",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(force: bool = False, retries: int = 3) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    expected = json.loads(MANIFEST.read_text())["files"]
    status = {}
    for name in TABLES.values():
        path = RAW / name
        if force or not path.exists():
            for attempt in range(retries):
                try:
                    urllib.request.urlretrieve(BASE_URL + name, path)
                    break
                except OSError:
                    if attempt == retries - 1:
                        raise
                    time.sleep(2 ** attempt)
            status[name] = "downloaded"
        else:
            status[name] = "ok"
        if sha256(path) != expected[name]["sha256"]:
            raise ValueError(f"{name}: checksum differs from data/manifest.json, the source has changed")
    return status


def source_dir(sample: bool = False) -> Path:
    if not sample and all((RAW / f).exists() for f in TABLES.values()):
        return RAW
    return SAMPLE


def build(db_path: str | Path = ":memory:", sample: bool = False, folder: Path | None = None):
    """Raw tables (all text), then the staging and mart SQL. Returns the DuckDB connection."""
    folder = folder or source_dir(sample)
    con = duckdb.connect(str(db_path))
    for table, name in TABLES.items():
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv('{(folder / name).as_posix()}', "
                    "header = true, all_varchar = true)")
    for f in sorted(SQL.glob("*.sql")):
        con.execute(f.read_text())
    return con


def frames(sample: bool = False):
    """orders, order lines (distance, freight) and daily beauty demand, from the saved warehouse when present."""
    wh = ROOT / "results" / "warehouse.duckdb"
    if not sample and wh.exists():
        con = duckdb.connect(str(wh), read_only=True)
    else:
        con = build(sample=sample)
    out = (con.execute("SELECT * FROM fct_orders").df(),
           con.execute("SELECT km, freight, is_beauty FROM fct_order_lines").df(),
           con.execute("SELECT * FROM daily_beauty_demand").df())
    con.close()
    return out
