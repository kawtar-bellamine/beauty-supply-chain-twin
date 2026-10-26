"""Full study: real flow analysis, forecasting, digital-twin scenarios, Excel model, Power BI exports.

Usage: python experiments/run_all.py           (downloads the data once, about 3 minutes)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bsc import excel_model, flow, forecast, style, twin  # noqa: E402
from bsc.data import build, download  # noqa: E402
from bsc.leadtime import FreightModel, TransitModel  # noqa: E402

OUT = ROOT / "results"
FIG = OUT / "figures"
EXP = ROOT / "exports"
EVAL = ("2017-03-01", "2018-08-15")      # after the warm-up of the twin
BF = ("2017-11-20", "2017-12-20")        # Black Friday window
style.apply()


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def window_kpis(res, start, end, region=None):
    o = res["_orders"]
    d = pd.to_datetime(o["day"])
    m = (d >= start) & (d <= end)
    if region:
        m &= o["region"] == region
    o = o[m]
    w = o["units"]
    return {"fill_rate_pct": 100 * float((w * (o["wait"] == 0)).sum() / w.sum()),
            "otif_pct": 100 * float((w * o["on_time"]).sum() / w.sum()),
            "lead_p50_days": float(o["lead"].median()), "lead_p90_days": float(o["lead"].quantile(0.9)),
            "units": float(w.sum())}


def headline(res, name):
    k = window_kpis(res, *EVAL)
    return {"scenario": name, "dcs": res["dcs"], "z": res["z"], **{kk: round(v, 2) for kk, v in k.items()},
            "days_of_cover": round(res["days_of_cover"], 2), "cost_per_unit_brl": round(float(res["cost_per_unit"]), 3),
            "holding_per_unit": round(float(res["holding_per_unit"]), 3),
            "last_mile_per_unit": round(float(res["last_mile_per_unit"]), 3),
            "dc_fixed_per_unit": round(float(res["dc_fixed_per_unit"]), 3)}


# ------------------------------------------------------------------ figures

def fig_flow(stages, causes, pareto, o):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.3), gridspec_kw={"width_ratios": [1.3, 1, 1]})
    style.title(fig, "Order to delivery on real beauty orders: where the days go",
                f"{causes['orders']:,} delivered health & beauty and perfumery orders, Olist marketplace (Brazil), "
                "2016 to 2018")
    s = stages[stages["stage"] != "Order to delivery"]
    y = np.arange(len(s))[::-1]
    ax[0].barh(y, s["p50_days"], color=[style.SLATE, style.GOLD, style.INK], height=0.55, label="median")
    ax[0].scatter(s["p90_days"], y, marker="|", s=400, color=style.ROSE, lw=2.5, label="90th percentile", zorder=3)
    for yy, (p50, p90, sh) in zip(y, s[["p50_days", "p90_days", "share_of_lead_time_pct"]].to_numpy()):
        ax[0].text(p90 + 0.4, yy, f"{p50:.1f} d median, {sh:.0f} % of lead time", va="center", fontsize=8.5)
    ax[0].set_yticks(y, s["stage"]), ax[0].set_xlabel("days"), ax[0].set_xlim(0, 44)
    ax[0].set_title("Stage times"), ax[0].legend(loc="upper right")
    ax[1].bar(["handed to carrier\nafter the limit", "handed on time"],
              [causes["late_if_shipped_late_pct"], causes["late_if_shipped_on_time_pct"]],
              color=[style.ROSE, style.TEAL], width=0.55)
    for i, v in enumerate([causes["late_if_shipped_late_pct"], causes["late_if_shipped_on_time_pct"]]):
        ax[1].text(i, v + 0.6, f"{v:.1f} %", ha="center", fontsize=10, fontweight="bold")
    ax[1].set_ylabel("orders delivered late (%)"), ax[1].set_title("Seller delay multiplies late deliveries")
    ax[2].plot(pareto["rank_pct"], pareto["cum_share_pct"], color=style.GOLD)
    k = pareto[pareto["cum_share_pct"] >= 50].iloc[0]
    ax[2].axhline(50, color=style.MUTED, lw=0.8, ls="--")
    ax[2].annotate(f"{int((pareto.index <= k.name).sum())} sellers ({k['rank_pct']:.1f} %)\n= half of seller-caused late "
                   "orders", (k["rank_pct"], 50), xytext=(10, -40), textcoords="offset points", fontsize=8.5,
                   arrowprops=dict(arrowstyle="->", color=style.MUTED))
    ax[2].set_xlabel("sellers, ranked (% of all beauty sellers)"), ax[2].set_ylabel("cumulative share (%)")
    ax[2].set_title("Pareto of seller-caused late orders")
    fig.tight_layout(rect=style.rect(fig))
    fig.savefig(FIG / "fig1_flow.png", dpi=150)
    plt.close(fig)


def fig_map(states):
    fig, ax = plt.subplots(1, 2, figsize=(12, 5.4))
    style.title(fig, "Geography is the main driver of lead time",
                "Median order-to-delivery days and share of late orders by customer state (states with at least 30 "
                "beauty orders)")
    st = states[states["orders"] >= 30]
    style.brazil(ax[0], dict(zip(st["customer_state"], st["lead_p50"])), "YlOrBr", "median days")
    ax[0].set_title("Median lead time")
    style.brazil(ax[1], dict(zip(st["customer_state"], st["late_pct"])), "RdPu", "% late")
    ax[1].set_title("Late deliveries")
    fig.tight_layout(rect=style.rect(fig))
    fig.savefig(FIG / "fig2_geography.png", dpi=150)
    plt.close(fig)


def fig_forecast(w, sc, bt):
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    style.title(fig, "Forecasting weekly demand by region",
                "Rolling origins over the last 26 weeks, horizons 1 to 4 weeks, only past data at each origin")
    piv = sc.pivot(index="region", columns="method", values="wape_pct").loc[["Total", "SE", "S", "NE", "CO", "N"]]
    x = np.arange(len(piv))
    for i, (m, colr) in enumerate(zip(piv.columns, [style.SLATE, style.GOLD, style.TEAL, style.ROSE])):
        ax[0].bar(x + (i - 1.5) * 0.2, piv[m], width=0.2, color=colr, label=m)
    ax[0].set_xticks(x, piv.index), ax[0].set_ylabel("WAPE (%)"), ax[0].legend(ncol=2, fontsize=8)
    ax[0].set_title("Error by region (smaller regions are noisier)")
    best = sc[sc["region"] == "Total"].sort_values("wape_pct").iloc[0]["method"]
    b = bt[(bt["region"] == "Total") & (bt["method"] == best) & (bt["h"] == 1)]
    ax[1].plot(w.index, w["Total"], color=style.INK, lw=1.4, label="actual weekly units")
    ax[1].plot(b["origin"], b["forecast"], color=style.GOLD, lw=2, label=f"{best}, one week ahead")
    ax[1].set_title("Total demand and the best forecast"), ax[1].legend()
    import matplotlib.dates as mdates
    ax[1].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout(rect=style.rect(fig))
    fig.savefig(FIG / "fig3_forecast.png", dpi=150)
    plt.close(fig)
    return best


def fig_scenarios(tab, frontier, ne):
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.35, 1, 1]})
    style.title(fig, "Digital twin: what each decision does to service and cost",
                "Simulated March 2017 to August 2018 on the real order stream scaled to a brand-sized flow; plant in "
                "São Paulo; promise per state fixed from the baseline network")
    t = tab.set_index("scenario")
    y = np.arange(len(t))[::-1]
    ax[0].barh(y + 0.18, t["fill_rate_pct"], height=0.34, color=style.GOLD, label="fill rate from stock")
    ax[0].barh(y - 0.18, t["otif_pct"], height=0.34, color=style.INK, label="OTIF (on time, in full)")
    ax[0].set_yticks(y, t.index, fontsize=8.3), ax[0].set_xlim(0, 105), ax[0].set_xlabel("%")
    ax[0].legend(loc="upper center", bbox_to_anchor=(0.4, -0.12), ncol=2, fontsize=8)
    ax[0].set_title("Service by scenario")
    for net_name, colr in [("São Paulo DC", style.INK), ("São Paulo DC + Recife DC", style.GOLD)]:
        g = frontier[frontier["dcs"] == net_name].sort_values("z")
        ax[1].plot(g["z"], g["ne_fill_rate_pct"], "o-", color=colr, label=f"{net_name}: fill")
        ax[1].plot(g["z"], g["ne_otif_pct"], "s--", color=colr, alpha=0.7, label=f"{net_name}: OTIF")
    ax[1].set_xlabel("safety factor z"), ax[1].set_ylabel("North-East customers (%)"), ax[1].legend(fontsize=7.5)
    ax[1].set_title("North-East service vs safety stock")
    for name, colr in [("one DC", style.INK), ("with Recife DC", style.GOLD)]:
        v = ne[ne["network"] == name]["lead"]
        ax[2].hist(v, bins=np.arange(0, 45, 1.5), color=colr, alpha=0.6, label=f"{name}: median {v.median():.1f} d")
    ax[2].set_xlabel("delivery lead time, North-East customers (days)"), ax[2].set_ylabel("orders")
    ax[2].legend(fontsize=8), ax[2].set_title("A regional DC for the North-East")
    fig.tight_layout(rect=style.rect(fig))
    fig.savefig(FIG / "fig4_scenarios.png", dpi=150)
    plt.close(fig)


def fig_stress(heat, bf):
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1, 1.25]})
    style.title(fig, "Stress tests: a plant outage and the Black Friday peak",
                "Fill rate during the event window; capacity planned monthly at 1.3 x the demand level")
    piv = heat.pivot(index="loss_pct", columns="weeks", values="fill_rate_pct")
    im = ax[0].imshow(piv.values, cmap="RdYlGn", vmin=40, vmax=100, aspect="auto", origin="lower")
    ax[0].set_xticks(range(piv.shape[1]), [f"{c} wk" for c in piv.columns])
    ax[0].set_yticks(range(piv.shape[0]), [f"-{r} %" for r in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            ax[0].text(j, i, f"{piv.values[i, j]:.0f}", ha="center", va="center", fontsize=9,
                       color="white" if piv.values[i, j] < 60 else style.INK)
    ax[0].set_xlabel("outage duration"), ax[0].set_ylabel("plant capacity lost"), ax[0].grid(False)
    ax[0].set_title("Fill rate (%) during a plant outage from 5 March 2018")
    plt.colorbar(im, ax=ax[0], fraction=0.04)
    for (name, d), colr in zip(bf.items(), [style.ROSE, style.GOLD, style.TEAL]):
        dd = d[(d["day"] >= "2017-10-01") & (d["day"] <= "2018-01-15")]
        ax[1].plot(dd["day"], dd["stock_units"], color=colr, label=name, lw=1.6)
    ax[1].set_ylabel("units in stock (plant, DCs, in transit)"), ax[1].legend(fontsize=8)
    ax[1].set_title("System stock around Black Friday 2017")
    fig.autofmt_xdate()
    fig.tight_layout(rect=style.rect(fig))
    fig.savefig(FIG / "fig5_stress.png", dpi=150)
    plt.close(fig)


def to_py(o):
    if isinstance(o, dict):
        return {str(k): to_py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_py(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o.item() if hasattr(o, "item") else o


def main():
    t0 = time.time()
    FIG.mkdir(parents=True, exist_ok=True)
    EXP.mkdir(exist_ok=True)
    log(f"data {download()}")
    con = build(OUT / "warehouse.duckdb")
    orders = con.execute("SELECT * FROM fct_orders").df()
    lines = con.execute("SELECT km, freight, is_beauty FROM fct_order_lines").df()
    daily = con.execute("SELECT * FROM daily_beauty_demand").df()
    summ = {}

    log("flow analysis")
    o = flow.beauty(orders)
    stages, causes = flow.stage_summary(o), flow.late_causes(o)
    reg, states, pareto, monthly = flow.by_region(o), flow.by_state(o), flow.seller_pareto(o), flow.monthly(o)
    for name, df in [("stages", stages), ("regions", reg), ("states", states), ("seller_pareto", pareto),
                     ("monthly", monthly)]:
        df.to_csv(OUT / f"flow_{name}.csv", index=False)
    fig_flow(stages, causes, pareto, o)
    fig_map(states)
    half = pareto[pareto["cum_share_pct"] >= 50].iloc[0]
    summ["flow"] = {"beauty_orders": int(len(o)), "stages": stages.round(2).to_dict(orient="records"),
                    **{k: round(v, 2) for k, v in causes.items()},
                    "sellers_for_half_of_seller_late": int((pareto.index <= half.name).sum()),
                    "sellers_total": int(o["seller_id"].nunique()),
                    "regions": reg.round(2).to_dict(orient="records")}

    log("forecasting")
    w = forecast.weekly(daily)
    bt = forecast.backtest(w)
    sc = forecast.scores(bt)
    sc.to_csv(OUT / "forecast_scores.csv", index=False)
    best = fig_forecast(w, sc, bt)
    summ["forecast"] = {"best_total": best, "scores": sc.round(2).to_dict(orient="records")}

    log("digital twin")
    tm, fm = TransitModel.fit(orders), FreightModel.fit(lines)
    real = twin.prepare_orders(orders)
    prom = twin.promise_days(real, tm)
    stream = twin.brand_scale(real, volume=40, seed=0)
    base = twin.run(stream, tm, fm, prom)
    rows = [headline(base, "Baseline: one DC in São Paulo, z 1.65")]
    runs = {"base": base}
    defs = [
        ("Regional DC in Recife", dict(dcs=("São Paulo DC", "Recife DC"))),
        ("Lower safety stock, z 0.84", dict(z=0.84)),
        ("Higher safety stock, z 2.33", dict(z=2.33)),
        ("Plant capacity 1.5 x demand", dict(capacity_ratio=1.5)),
        ("Pre-build 10 days before Black Friday", dict(prebuild=("2017-10-01", "2017-11-22", 10))),
        ("Unplanned +40 % demand, May 2018", dict(surge=("2018-05-01", "2018-05-31", 0.4))),
        ("Plant at 50 % for 4 weeks, March 2018", dict(capacity_cut=("2018-03-05", "2018-04-01", 0.5))),
    ]
    for name, kw in defs:
        r = twin.run(stream, tm, fm, prom, **kw)
        runs[name] = r
        rows.append(headline(r, name))
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "twin_scenarios.csv", index=False)
    log("  frontier")
    fr = []
    for dcs in [("São Paulo DC",), ("São Paulo DC", "Recife DC")]:
        for z in [0.84, 1.28, 1.65, 2.05, 2.33]:
            r = twin.run(stream, tm, fm, prom, dcs=dcs, z=z)
            k = window_kpis(r, *EVAL, region="NE")
            fr.append({**headline(r, f"z {z}"), "ne_fill_rate_pct": round(k["fill_rate_pct"], 2),
                       "ne_otif_pct": round(k["otif_pct"], 2)})
    frontier = pd.DataFrame(fr)
    frontier.to_csv(OUT / "twin_frontier.csv", index=False)
    ne = pd.concat([runs["base"]["_orders"].assign(network="one DC"),
                    runs["Regional DC in Recife"]["_orders"].assign(network="with Recife DC")])
    ne = ne[ne["region"] == "NE"]
    ne_k = {n: window_kpis(r, *EVAL, region="NE") for n, r in
            [("one DC", runs["base"]), ("with Recife DC", runs["Regional DC in Recife"])]}
    log("  stress tests")
    heat = []
    for loss in [20, 35, 50, 65]:
        for weeks in [1, 2, 4, 6]:
            end = (pd.Timestamp("2018-03-05") + pd.Timedelta(days=7 * weeks - 1)).strftime("%Y-%m-%d")
            r = twin.run(stream, tm, fm, prom, capacity_cut=("2018-03-05", end, 1 - loss / 100))
            k = window_kpis(r, "2018-03-05", (pd.Timestamp(end) + pd.Timedelta(days=21)).strftime("%Y-%m-%d"))
            heat.append({"loss_pct": loss, "weeks": weeks, **k})
    heat = pd.DataFrame(heat)
    heat.to_csv(OUT / "twin_stress.csv", index=False)
    bf = {"no pre-build": runs["base"]["_daily"],
          "pre-build 10 days": runs["Pre-build 10 days before Black Friday"]["_daily"],
          "pre-build 20 days": twin.run(stream, tm, fm, prom, prebuild=("2017-10-01", "2017-11-22", 20))["_daily"]}
    bf_k = {}
    for name, kw in [("no pre-build", {}), ("pre-build 10 days", dict(prebuild=("2017-10-01", "2017-11-22", 10))),
                     ("pre-build 20 days", dict(prebuild=("2017-10-01", "2017-11-22", 20)))]:
        bf_k[name] = window_kpis(twin.run(stream, tm, fm, prom, **kw), *BF)
    fig_scenarios(tab, frontier, ne)
    fig_stress(heat, bf)
    ob = base["_orders"]
    dd = pd.to_datetime(ob["day"])
    m = (dd >= EVAL[0]) & ~((dd >= "2017-11-15") & (dd <= "2017-12-31"))
    fill_outside_bf = 100 * float((ob["units"] * (ob["wait"] == 0))[m].sum() / ob["units"][m].sum())
    summ["twin"] = {"volume": 40, "baseline_fill_outside_black_friday_pct": round(fill_outside_bf, 2), "simulated_orders": int(len(stream)), "eval_window": EVAL,
                    "scenarios": tab.to_dict(orient="records"), "frontier": frontier.to_dict(orient="records"),
                    "north_east": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in ne_k.items()},
                    "black_friday": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in bf_k.items()},
                    "stress": heat.round(2).to_dict(orient="records"),
                    "promise_days": prom.to_dict(), "transit_p50_by_band": tm.p50.round(2).tolist(),
                    "freight_per_unit_by_band": fm.per_unit.round(2).tolist()}

    log("Excel model")
    s18 = base["_orders"]
    s18 = s18[pd.to_datetime(s18["day"]) >= "2018-01-01"]
    r2 = runs["Regional DC in Recife"]["_orders"]
    r2 = r2[pd.to_datetime(r2["day"]) >= "2018-01-01"]
    dcs = []
    for name in ["São Paulo DC", "Recife DC"]:
        dd = r2[r2["dc"] == name].groupby("day")["units"].sum()
        km = twin.haversine_km(*twin.PLANT, *twin.DC_SITES[name])
        dcs.append({"name": name, "mean": dd.mean(), "std": dd.std(), "km": km})
    xl = excel_model.build(EXP / "inventory_policy_model.xlsx", dcs, tab.to_dict(orient="records"),
                           {"service": 0.95, "unit_value": 80.0, "holding_rate": 0.25, "kmpd": 650,
                            "dc_fixed": 1500})
    log("Power BI exports")
    o.assign(month=o["purchased"].dt.to_period("M").astype(str))[
        ["order_id", "purchased", "customer_state", "customer_region", "seller_state", "km", "units", "gmv",
         "freight_total", "d_approval", "d_handling", "d_transit", "d_total", "d_promise", "late", "shipped_late",
         "month"]].to_csv(EXP / "fact_beauty_orders.csv", index=False)
    con.execute("SELECT * FROM dim_state").df().to_csv(EXP / "dim_state.csv", index=False)
    days = pd.DataFrame({"date": pd.date_range("2016-09-01", "2018-09-30")})
    days["year"], days["month"], days["week"] = days.date.dt.year, days.date.dt.month, days.date.dt.isocalendar().week
    days["weekday"] = days.date.dt.day_name()
    days.to_csv(EXP / "dim_date.csv", index=False)
    base["_daily"].to_csv(EXP / "fact_twin_daily_baseline.csv", index=False)
    tab.to_csv(EXP / "fact_twin_scenarios.csv", index=False)
    summ["runtime_s"] = round(time.time() - t0, 1)
    (OUT / "summary.json").write_text(json.dumps(to_py(summ), indent=1, default=str))
    log(f"done in {summ['runtime_s']} s")


if __name__ == "__main__":
    main()
