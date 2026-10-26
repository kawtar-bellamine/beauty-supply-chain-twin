"""Committed sample of the real data (tests and CI): 2,500 beauty orders and 2,500 other orders, all their rows."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402

from bsc.data import RAW, SAMPLE, TABLES  # noqa: E402

SAMPLE.mkdir(parents=True, exist_ok=True)
rd = {k: pd.read_csv(RAW / v, dtype=str) for k, v in TABLES.items()}
items = rd["raw_items"].merge(rd["raw_products"][["product_id", "product_category_name"]], on="product_id")
beauty = set(items.loc[items["product_category_name"].isin(["beleza_saude", "perfumaria"]), "order_id"])
orders = rd["raw_orders"]
b = orders[orders["order_id"].isin(beauty)].sort_values("order_id").iloc[::4][:2500]
o = orders[~orders["order_id"].isin(beauty)].sort_values("order_id").iloc[::30][:2500]
keep = pd.concat([b, o])
it = rd["raw_items"][rd["raw_items"]["order_id"].isin(keep["order_id"])]
pr = rd["raw_products"][rd["raw_products"]["product_id"].isin(it["product_id"])]
cu = rd["raw_customers"][rd["raw_customers"]["customer_id"].isin(keep["customer_id"])]
se = rd["raw_sellers"][rd["raw_sellers"]["seller_id"].isin(it["seller_id"])]
zips = set(cu["customer_zip_code_prefix"].str.zfill(5)) | set(se["seller_zip_code_prefix"].str.zfill(5))
geo = rd["raw_geolocation"]
geo = geo[geo["geolocation_zip_code_prefix"].str.zfill(5).isin(zips)]
geo = geo.groupby("geolocation_zip_code_prefix").head(3)
for k, df in {"raw_orders": keep, "raw_items": it, "raw_products": pr, "raw_customers": cu, "raw_sellers": se,
              "raw_geolocation": geo, "raw_category_translation": rd["raw_category_translation"]}.items():
    df.to_csv(SAMPLE / TABLES[k], index=False)
print({k: len(v) for k, v in [("orders", keep), ("items", it), ("geo", geo)]})
