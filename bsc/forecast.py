"""Weekly demand forecasting by region, compared on rolling origins (only past data at each origin)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def weekly(daily: pd.DataFrame, start="2017-01-02", end="2018-08-12") -> pd.DataFrame:
    d = daily.copy()
    d["week"] = pd.to_datetime(d["day"]).dt.to_period("W-SUN").dt.start_time
    w = d.pivot_table(index="week", columns="region", values="units", aggfunc="sum", fill_value=0)
    w = w[(w.index >= start) & (w.index <= end)]
    w["Total"] = w.sum(axis=1)
    return w


def _ses(y, alpha):
    level = y[0]
    for v in y[1:]:
        level = alpha * v + (1 - alpha) * level
    return level


def _holt(y, alpha, beta):
    level, trend = y[0], 0.0
    for v in y[1:]:
        prev = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    return level, trend


METHODS = {
    "Naive (last week)": lambda y, h: np.repeat(y[-1], h),
    "Moving average 4 w": lambda y, h: np.repeat(y[-4:].mean(), h),
    "Exponential smoothing": lambda y, h: np.repeat(_ses(y, 0.3), h),
    "Holt (level + trend)": lambda y, h: (lambda lt: lt[0] + lt[1] * np.arange(1, h + 1))(_holt(y, 0.3, 0.1)),
}


def backtest(w: pd.DataFrame, horizon: int = 4, n_origins: int = 26) -> pd.DataFrame:
    rows = []
    T = len(w)
    for o in range(T - horizon - n_origins + 1, T - horizon + 1):
        for col in w.columns:
            y = w[col].to_numpy(float)[:o]
            actual = w[col].to_numpy(float)[o:o + horizon]
            for name, f in METHODS.items():
                fc = np.maximum(f(y, horizon), 0)
                for h in range(horizon):
                    rows.append({"origin": w.index[o], "region": col, "method": name, "h": h + 1,
                                 "actual": actual[h], "forecast": fc[h]})
    return pd.DataFrame(rows)


def scores(bt: pd.DataFrame) -> pd.DataFrame:
    g = bt.groupby(["region", "method"])
    return pd.DataFrame({"wape_pct": 100 * g.apply(lambda d: np.abs(d["forecast"] - d["actual"]).sum()
                                                   / d["actual"].sum()),
                         "bias_pct": 100 * g.apply(lambda d: (d["forecast"] - d["actual"]).sum() / d["actual"].sum())}) \
        .reset_index()
