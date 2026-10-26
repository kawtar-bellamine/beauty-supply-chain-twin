"""Process analysis of the real order-to-delivery flow: stage times, late-delivery causes, bottlenecks."""
from __future__ import annotations

import numpy as np
import pandas as pd

STAGES = [("d_approval", "Payment approval"), ("d_handling", "Seller handling"), ("d_transit", "Carrier transit")]


def beauty(orders: pd.DataFrame) -> pd.DataFrame:
    return orders[orders["has_beauty"]].copy()


def stage_summary(o: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = o["d_total"].median()
    for col, name in STAGES:
        x = o[col].dropna()
        rows.append({"stage": name, "p50_days": x.median(), "p90_days": x.quantile(0.9),
                     "mean_days": x.mean(), "share_of_lead_time_pct": 100 * x.mean() / o["d_total"].mean()})
    rows.append({"stage": "Order to delivery", "p50_days": total, "p90_days": o["d_total"].quantile(0.9),
                 "mean_days": o["d_total"].mean(), "share_of_lead_time_pct": 100.0})
    return pd.DataFrame(rows)


def late_causes(o: pd.DataFrame) -> dict:
    """Each late order is attributed to the seller (handed to the carrier after the shipping limit), the carrier
    (shipped on time but delivered after the promise), or both."""
    late = o[o["late"]]
    seller = late["shipped_late"]
    res = {"orders": len(o), "late_pct": 100 * o["late"].mean(),
           "late_if_shipped_late_pct": 100 * o.loc[o["shipped_late"], "late"].mean(),
           "late_if_shipped_on_time_pct": 100 * o.loc[~o["shipped_late"], "late"].mean(),
           "shipped_late_pct": 100 * o["shipped_late"].mean(),
           "late_caused_by_carrier_only_pct": 100 * (~seller).mean(),
           "late_with_seller_delay_pct": 100 * seller.mean()}
    return res


def by_region(o: pd.DataFrame) -> pd.DataFrame:
    g = o.groupby("customer_region")
    return pd.DataFrame({"orders": g.size(), "share_pct": 100 * g.size() / len(o),
                         "lead_p50": g["d_total"].median(), "lead_p90": g["d_total"].quantile(0.9),
                         "transit_p50": g["d_transit"].median(), "late_pct": 100 * g["late"].mean(),
                         "km_p50": g["km"].median(), "freight_per_order": g["freight_total"].mean()}) \
        .sort_values("orders", ascending=False).reset_index()


def by_state(o: pd.DataFrame) -> pd.DataFrame:
    g = o.groupby("customer_state")
    return pd.DataFrame({"orders": g.size(), "lead_p50": g["d_total"].median(), "transit_p50": g["d_transit"].median(),
                         "late_pct": 100 * g["late"].mean(), "region": g["customer_region"].first()}).reset_index()


def seller_pareto(o: pd.DataFrame) -> pd.DataFrame:
    """Sellers ranked by the number of late orders they shipped late themselves."""
    s = o[o["late"] & o["shipped_late"]].groupby("seller_id").size().sort_values(ascending=False)
    total = o.groupby("seller_id").size()
    df = pd.DataFrame({"late_by_seller": s, "orders": total.reindex(s.index)}).reset_index()
    df["cum_share_pct"] = 100 * df["late_by_seller"].cumsum() / df["late_by_seller"].sum()
    df["rank_pct"] = 100 * (np.arange(len(df)) + 1) / o["seller_id"].nunique()
    return df


def monthly(o: pd.DataFrame) -> pd.DataFrame:
    m = o.assign(month=o["purchased"].dt.to_period("M").dt.to_timestamp())
    g = m.groupby("month")
    return pd.DataFrame({"orders": g.size(), "late_pct": 100 * g["late"].mean(), "lead_p50": g["d_total"].median(),
                         "handling_p50": g["d_handling"].median(), "transit_p50": g["d_transit"].median()}) \
        .reset_index()
