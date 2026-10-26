"""Beauty Supply Chain Twin: control tower and scenario simulator. Run with: streamlit run app/dashboard.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from bsc import flow, style, twin  # noqa: E402
from bsc.data import RAW, TABLES, frames  # noqa: E402
from bsc.leadtime import FreightModel, TransitModel  # noqa: E402

RES = ROOT / "results"
EXP = ROOT / "exports"
style.apply()
st.set_page_config(page_title="Beauty Supply Chain Twin", page_icon="✨", layout="wide")
st.markdown("""
<style>
.stApp { background: #faf7f2; }
.hero { padding: 28px 32px; border-radius: 18px; margin-bottom: 16px; color: #faf7f2;
        background: linear-gradient(120deg, #111 0%, #2a2520 60%, #4a3b28 100%); }
.hero h1 { color: #f3e7d3; font-size: 2.25rem; margin: 0 0 6px; letter-spacing: .4px; font-weight: 600; }
.hero .k { color: #b8925a; letter-spacing: 4px; font-size: .78rem; font-weight: 700; }
.hero p { color: #d9cfc0; margin: 0; max-width: 1000px; font-size: 1.0rem; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; margin: 6px 0 14px; }
.kpi { background: #fff; border: 1px solid #ebe4d8; border-radius: 14px; padding: 14px 16px; }
.kpi b { display: block; font-size: 1.6rem; color: #1a1a1a; line-height: 1.15; font-weight: 600; }
.kpi i { font-style: normal; color: #b8925a; font-size: .85rem; }
.kpi span { color: #6e6a63; font-size: .82rem; display: block; }
.find { background: #fff; border-left: 3px solid #b8925a; border-radius: 8px; padding: 10px 14px; margin: 6px 0; }
</style>""", unsafe_allow_html=True)


@st.cache_data
def summary():
    p = RES / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_resource(show_spinner="Loading the real orders...")
def models():
    sample = not all((RAW / f).exists() for f in TABLES.values()) and not (RES / "warehouse.duckdb").exists()
    orders, lines, daily = frames(sample=sample)
    tm, fm = TransitModel.fit(orders), FreightModel.fit(lines)
    real = twin.prepare_orders(orders)
    prom = twin.promise_days(real, tm)
    volume = int(round(40 * 11_722 / max(1, int(orders["has_beauty"].sum()))))
    stream = twin.brand_scale(real, volume=volume, seed=0)
    return orders, tm, fm, prom, stream, sample


S = summary()


def kpis(items):
    html = "".join(f'<div class="kpi"><b>{v}</b>' + (f'<i>{d}</i>' if d else "") + f'<span>{k}</span></div>'
                   for v, k, d in items)
    st.markdown(f'<div class="kpis">{html}</div>', unsafe_allow_html=True)


def show(fig):
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


st.markdown("""<div class="hero"><div class="k">SUPPLY CHAIN · DATA · SIMULATION</div>
<h1>Beauty Supply Chain Twin</h1>
<p>From sales forecast to customer delivery on 11,722 real beauty orders: where the days go, who causes the delays,
how well demand can be forecast, and a digital twin that tests a regional DC, a Black Friday pre-build, a plant outage
or a safety-stock policy before anyone spends a real.</p></div>""", unsafe_allow_html=True)

tabs = st.tabs(["Control tower", "Order flow", "Forecast", "Scenario simulator", "Stress tests", "Excel & Power BI",
                "Technology watch", "Method"])

# ------------------------------------------------------------------ control tower
with tabs[0]:
    if S is None:
        st.warning("Run `python experiments/run_all.py` first.")
    else:
        f, t = S["flow"], S["twin"]
        st_tr = {r["stage"]: r for r in f["stages"]}
        fc = pd.DataFrame(S["forecast"]["scores"])
        best = fc[(fc["region"] == "Total")].sort_values("wape_pct").iloc[0]
        naive = fc[(fc["region"] == "Total") & (fc["method"] == "Naive (last week)")].iloc[0]
        ne = t["north_east"]
        bfk = t["black_friday"]
        kpis([(f"{st_tr['Order to delivery']['p50_days']:.1f} days", "median order to delivery (real)", ""),
              (f"{st_tr['Carrier transit']['share_of_lead_time_pct']:.0f} %", "of the lead time is carrier transit", ""),
              (f"{f['late_if_shipped_late_pct']:.0f} % vs {f['late_if_shipped_on_time_pct']:.0f} %",
               "late when the seller ships late vs on time", ""),
              (f"{best['wape_pct']:.0f} %", f"weekly forecast error ({best['method']})",
               f"naive: {naive['wape_pct']:.0f} %"),
              (f"{bfk['no pre-build']['fill_rate_pct']:.0f} → {bfk['pre-build 10 days']['fill_rate_pct']:.0f} %",
               "Black Friday fill rate with a 10-day pre-build", ""),
              (f"{ne['one DC']['lead_p50_days']:.0f} → {ne['with Recife DC']['lead_p50_days']:.0f} days",
               "North-East median delivery with a Recife DC", "")])
        st.image(str(RES / "figures" / "fig4_scenarios.png"), use_container_width=True)
        st.markdown("#### Findings")
        for txt in [
            f"Carrier transit is {st_tr['Carrier transit']['share_of_lead_time_pct']:.0f} % of the lead time and "
            f"{f['late_caused_by_carrier_only_pct']:.0f} % of late orders were shipped on time: the first lever is the "
            "carrier and the distance, not the warehouse.",
            f"When a seller hands a parcel over after its shipping limit, {f['late_if_shipped_late_pct']:.0f} % of "
            f"orders arrive late, against {f['late_if_shipped_on_time_pct']:.0f} %; {f['sellers_for_half_of_seller_late']} "
            f"sellers out of {f['sellers_total']} cause half of those delays.",
            f"In the twin, every stock-out outside Black Friday disappears (fill rate "
            f"{t['baseline_fill_outside_black_friday_pct']:.0f} %); at Black Friday the plant cannot follow, and "
            "pre-building 10 to 20 days of stock is what fixes it, not more safety stock in the DC.",
            f"A Recife DC cuts the North-East median delivery from {ne['one DC']['lead_p50_days']:.0f} to "
            f"{ne['with Recife DC']['lead_p50_days']:.0f} days and lifts its OTIF from {ne['one DC']['otif_pct']:.0f} % "
            f"to {ne['with Recife DC']['otif_pct']:.0f} %, for about 0.8 BRL more per unit; it needs its own safety stock "
            "because it is 5 days of line haul from the plant.",
        ]:
            st.markdown(f'<div class="find">{txt}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ order flow
with tabs[1]:
    st.image(str(RES / "figures" / "fig1_flow.png"), use_container_width=True)
    st.image(str(RES / "figures" / "fig2_geography.png"), use_container_width=True)
    reg = pd.read_csv(RES / "flow_regions.csv") if (RES / "flow_regions.csv").exists() else None
    if reg is not None:
        st.markdown("##### By region")
        st.dataframe(reg.round(1), hide_index=True, use_container_width=True)
    mon = pd.read_csv(RES / "flow_monthly.csv", parse_dates=["month"]) if (RES / "flow_monthly.csv").exists() else None
    if mon is not None:
        fig, ax = plt.subplots(figsize=(13, 3.2))
        ax.bar(mon["month"], mon["orders"], width=20, color=style.GRID, label="orders")
        ax2 = ax.twinx()
        ax2.plot(mon["month"], mon["late_pct"], color=style.ROSE, marker="o", label="late %")
        ax.set_ylabel("orders"), ax2.set_ylabel("late (%)"), ax.set_title("Orders and late deliveries by month")
        ax2.grid(False)
        fig.tight_layout()
        show(fig)

# ------------------------------------------------------------------ forecast
with tabs[2]:
    st.image(str(RES / "figures" / "fig3_forecast.png"), use_container_width=True)
    if S:
        sc = pd.DataFrame(S["forecast"]["scores"])
        st.dataframe(sc.pivot(index="region", columns="method", values="wape_pct").round(1), use_container_width=True)

# ------------------------------------------------------------------ simulator
with tabs[3]:
    orders, tm, fm, prom, stream, sample = models()
    if sample:
        st.info("Running on the committed sample of the real data (download the full data with run_all.py).")
    st.markdown("Change the network and the policies; the twin replays March 2017 to August 2018 in about a second.")
    c = st.columns(4)
    extra = c[0].multiselect("Regional DCs (plus the São Paulo DC)", ["Recife DC", "Brasília DC", "Curitiba DC"])
    z = c[1].slider("Safety factor z", 0.0, 3.0, 1.65, 0.05)
    capr = c[2].slider("Plant capacity / demand level", 1.05, 2.0, 1.30, 0.05)
    pre = c[3].slider("Black Friday pre-build (extra days of stock)", 0, 25, 0)
    c = st.columns(4)
    surge = c[0].slider("Unplanned demand surge in May 2018 (%)", 0, 80, 0, 5)
    loss = c[1].slider("Plant outage from 5 March 2018: capacity lost (%)", 0, 90, 0, 5)
    weeks = c[2].slider("Outage duration (weeks)", 1, 8, 4)
    fixed = c[3].number_input("Regional DC fixed cost (BRL/day)", 0, 10_000, 1_500, 250)

    @st.cache_data(show_spinner="Simulating...")
    def sim(extra, z, capr, pre, surge, loss, weeks, fixed):
        kw = dict(dcs=tuple(["São Paulo DC", *extra]), z=z, capacity_ratio=capr,
                  costs=twin.Costs(dc_fixed_per_day=fixed))
        if pre:
            kw["prebuild"] = ("2017-10-01", "2017-11-22", pre)
        if surge:
            kw["surge"] = ("2018-05-01", "2018-05-31", surge / 100)
        if loss:
            end = (pd.Timestamp("2018-03-05") + pd.Timedelta(days=7 * weeks - 1)).strftime("%Y-%m-%d")
            kw["capacity_cut"] = ("2018-03-05", end, 1 - loss / 100)
        r = twin.run(stream, tm, fm, prom, **kw)
        b = twin.run(stream, tm, fm, prom)
        return r, b

    r, b = sim(tuple(extra), z, capr, pre, surge, loss, weeks, fixed)

    def k(res, region=None):
        o = res["_orders"]
        d = pd.to_datetime(o["day"])
        m = d >= "2017-03-01"
        if region:
            m &= o["region"] == region
        o = o[m]
        w = o["units"]
        return {"fill": 100 * (w * (o["wait"] == 0)).sum() / w.sum(), "otif": 100 * (w * o["on_time"]).sum() / w.sum(),
                "lead": o["lead"].median()}

    kr, kb = k(r), k(b)
    kpis([(f"{kr['fill']:.1f} %", "fill rate from stock", f"baseline {kb['fill']:.1f} %"),
          (f"{kr['otif']:.1f} %", "OTIF", f"baseline {kb['otif']:.1f} %"),
          (f"{kr['lead']:.1f} days", "median delivery", f"baseline {kb['lead']:.1f}"),
          (f"{r['days_of_cover']:.1f} days", "system stock cover", f"baseline {b['days_of_cover']:.1f}"),
          (f"{float(r['cost_per_unit']):.2f} BRL", "cost to serve per unit", f"baseline {float(b['cost_per_unit']):.2f}")])
    d = r["_daily"]
    fig, ax = plt.subplots(1, 2, figsize=(15, 3.8), gridspec_kw={"width_ratios": [1.6, 1]})
    ax[0].plot(d["day"], d["demand"].rolling(7, min_periods=1).mean(), color=style.INK, lw=1.4, label="demand (7-day mean)")
    ax[0].plot(d["day"], d["capacity"], color=style.ROSE, lw=1.2, label="plant capacity")
    ax[0].plot(d["day"], d["stock_units"], color=style.GOLD, lw=1.4, label="system stock")
    ax[0].legend(ncol=3, fontsize=8), ax[0].set_title("Demand, capacity and stock")
    reg = pd.DataFrame({n: pd.Series({g: k(res, g)["lead"] for g in ["SE", "S", "CO", "NE", "N"]})
                        for n, res in [("baseline", b), ("scenario", r)]})
    x = np.arange(len(reg))
    ax[1].bar(x - 0.2, reg["baseline"], 0.4, color=style.GRID, label="baseline")
    ax[1].bar(x + 0.2, reg["scenario"], 0.4, color=style.GOLD, label="scenario")
    ax[1].set_xticks(x, reg.index), ax[1].set_ylabel("median delivery (days)"), ax[1].legend(fontsize=8)
    ax[1].set_title("Delivery time by region")
    fig.tight_layout()
    show(fig)
    cost = pd.DataFrame({"baseline": [b[c_] for c_ in ["holding_per_unit", "linehaul_per_unit", "last_mile_per_unit",
                                                        "dc_fixed_per_unit"]],
                         "scenario": [r[c_] for c_ in ["holding_per_unit", "linehaul_per_unit", "last_mile_per_unit",
                                                        "dc_fixed_per_unit"]]},
                        index=["holding", "line haul", "last mile", "regional DC fixed"]).astype(float).round(3)
    st.markdown("##### Cost to serve per unit (BRL)")
    st.dataframe(cost, use_container_width=True)

# ------------------------------------------------------------------ stress tests
with tabs[4]:
    st.image(str(RES / "figures" / "fig5_stress.png"), use_container_width=True)
    if S:
        bf = pd.DataFrame(S["twin"]["black_friday"]).T.round(1)
        st.markdown("##### Black Friday window (20 November to 20 December 2017)")
        st.dataframe(bf, use_container_width=True)

# ------------------------------------------------------------------ excel and power bi
with tabs[5]:
    st.markdown("**Excel inventory-policy model.** Change the blue inputs (service level, demand growth, unit value, "
                "holding rate, truck speed): safety stock, order-up-to levels, days of cover and holding cost "
                "recalculate. The service-level sheet shows the cost of each extra point of service.")
    x = EXP / "inventory_policy_model.xlsx"
    if x.exists():
        st.download_button("Download the Excel model", x.read_bytes(), file_name=x.name)
    st.markdown("**Power BI star schema** in `exports/`: one fact table of real orders with every stage time, the "
                "state and date dimensions, and the twin's daily and scenario facts.")
    for f in sorted(EXP.glob("*.csv")):
        st.download_button(f"Download {f.name}", f.read_bytes(), file_name=f.name, key=f.name)

with tabs[6]:
    st.markdown((ROOT / "docs" / "tech_watch.md").read_text())

with tabs[7]:
    st.markdown((ROOT / "docs" / "method.md").read_text())
