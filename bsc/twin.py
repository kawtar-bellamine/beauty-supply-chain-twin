"""Supply-chain digital twin: plant -> distribution centres -> customers, driven by real daily beauty demand.

Daily discrete-time simulation:
* each customer order (real date, real customer location, real units, scaled by `volume`) goes to its nearest DC;
* each DC reviews its stock every day with an order-up-to policy S = f(L + R) + z * sigma * sqrt(L + R), where the
  forecast f and its error sigma are updated online by exponential smoothing (no look-ahead);
* the plant produces up to its daily capacity and ships what the DCs ask for, after a line-haul lead time;
* orders that find no stock wait (backorder, shipped complete); delivery = ship day + 1 day of handling + a transit
  time drawn from real deliveries of the same distance band.
Everything that is not measured in the data is an explicit assumption in `Network` and `Costs`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .leadtime import FreightModel, TransitModel, haversine_km

PLANT = (-23.55, -46.63)          # São Paulo metropolitan area
DC_SITES = {
    "São Paulo DC": (-23.55, -46.63),
    "Recife DC": (-8.05, -34.88),
    "Brasília DC": (-15.79, -47.88),
    "Curitiba DC": (-25.43, -49.27),
}


@dataclass
class Costs:
    unit_value: float = 80.0          # BRL per unit (median beauty item price in the data, rounded)
    holding_rate: float = 0.25        # per year, on stock at the plant, in DCs and in transit
    linehaul_fixed: float = 0.20      # BRL per unit per shipment
    linehaul_per_km: float = 0.0006   # BRL per unit per km (full-truck line haul)
    dc_fixed_per_day: float = 1_500.0  # BRL per regional DC per day (rent, staff); the central DC is sunk
    lost_margin_late: float = 0.0     # optional penalty per late unit


@dataclass
class Network:
    dcs: tuple = ("São Paulo DC",)
    z: float = 1.65                   # safety factor (95 % cycle service)
    review_days: int = 1
    volume: int = 40                  # kept for reference: the order stream is scaled by brand_scale()
    capacity_ratio: float = 1.30      # plant capacity / demand level, planned monthly
    plant_buffer_days: float = 3.0
    alpha: float = 0.15               # smoothing of the forecast
    linehaul_kmpd: float = 650.0      # line-haul trucks, km per day
    capacity_cut: tuple | None = None  # (start, end, ratio) temporary loss of plant capacity
    surge: tuple | None = None         # (start, end, extra) unforecast demand surge, e.g. +0.3
    prebuild: tuple | None = None      # (start, end, extra days) seasonal stock built at the plant before a peak
    seed: int = 0
    costs: Costs = field(default_factory=Costs)


def linehaul_days(km: float, kmpd: float) -> int:
    return 1 + int(np.ceil(km / kmpd))


def prepare_orders(orders: pd.DataFrame, start="2017-01-01", end="2018-08-15") -> pd.DataFrame:
    o = orders[orders["has_beauty"]].dropna(subset=["customer_lat", "customer_lng"]).copy()
    o["day"] = o["purchased"].dt.normalize()
    o = o[(o["day"] >= start) & (o["day"] <= end)]
    return o[["order_id", "day", "customer_state", "customer_region", "customer_lat", "customer_lng", "units"]] \
        .sort_values(["day", "order_id"]).reset_index(drop=True)


def brand_scale(real: pd.DataFrame, volume: int = 40, seed: int = 0) -> pd.DataFrame:
    """A brand-sized order stream with the real shape: the daily order rate is the real one (7-day centred mean,
    so Black Friday stays visible) times `volume`; each simulated order copies a real order of the same fortnight
    (customer location, state, units). Noise is Poisson at the brand scale, not the marketplace's lumps x volume."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(real["day"].min(), real["day"].max(), freq="D")
    rate = real.groupby("day").size().reindex(days, fill_value=0).rolling(7, center=True, min_periods=1).mean()
    n = rng.poisson(rate.to_numpy() * volume)
    day_of = np.repeat(days.to_numpy(), n)
    pool_t = real["day"].to_numpy()
    pick = np.empty(len(day_of), int)
    order_idx = np.arange(len(real))
    for d, cnt in zip(days, n):
        if cnt == 0:
            continue
        m = np.abs((pool_t - d.to_datetime64()) / np.timedelta64(1, "D")) <= 7
        cand = order_idx[m]
        pick[np.flatnonzero(day_of == d.to_datetime64())] = rng.choice(cand, cnt)
    out = real.iloc[pick][["customer_state", "customer_region", "customer_lat", "customer_lng", "units"]].copy()
    out.insert(0, "day", day_of)
    return out.reset_index(drop=True)


def promise_days(orders: pd.DataFrame, transit: TransitModel) -> pd.Series:
    """Customer promise per state, set once from the baseline network (central DC): p90 transit + 2 days."""
    km = haversine_km(*DC_SITES["São Paulo DC"], orders["customer_lat"], orders["customer_lng"])
    p90 = pd.Series(transit.quantile(km, 0.9), index=orders.index)
    return (p90.groupby(orders["customer_state"]).median() + 2).round()


def simulate(orders: pd.DataFrame, transit: TransitModel, freight: FreightModel, promise: pd.Series,
             net: Network) -> dict:
    rng = np.random.default_rng(net.seed)
    c = net.costs
    days = pd.date_range(orders["day"].min(), orders["day"].max(), freq="D")
    T = len(days)
    dcs = list(net.dcs)
    coords = np.array([DC_SITES[d] for d in dcs])
    # nearest DC for every order
    dist = np.stack([haversine_km(lat, lng, orders["customer_lat"].to_numpy(), orders["customer_lng"].to_numpy())
                     for lat, lng in coords])
    dc_of = dist.argmin(axis=0)
    km = dist[dc_of, np.arange(len(orders))]
    t_idx = ((orders["day"] - days[0]).dt.days).to_numpy()
    units = orders["units"].to_numpy().astype(float)
    if net.surge:
        s0, s1, extra = net.surge
        m = (orders["day"] >= s0) & (orders["day"] <= s1)
        units = np.where(m, units * (1 + extra), units)
    n_dc = len(dcs)
    demand = np.zeros((n_dc, T))
    np.add.at(demand, (dc_of, t_idx), units)
    L = np.array([linehaul_days(haversine_km(*PLANT, *coords[k]), net.linehaul_kmpd) for k in range(n_dc)])
    tot = demand.sum(axis=0)
    mean_d = tot[:28].mean()
    cut = np.ones(T)
    if net.capacity_cut:
        s0, s1, ratio = net.capacity_cut
        cut[(days >= s0) & (days <= s1)] = ratio
    cap = np.zeros(T)
    cap_plan = 0.0
    prebuild_days = np.zeros(T)
    if net.prebuild:
        s0, s1, extra = net.prebuild
        prebuild_days[(days >= s0) & (days <= s1)] = extra
    # state
    f = demand[:, :28].mean(axis=1)                         # warm-up forecast
    var = np.maximum(demand[:, :28].var(axis=1), 1.0)
    on_hand = f * (L + net.review_days) * 1.0
    pipeline = np.zeros((n_dc, T + 40))
    plant = mean_d * net.plant_buffer_days
    plant_backlog = np.zeros(n_dc)
    backlog = np.zeros(n_dc)
    shipped_cum = np.zeros((n_dc, T))
    demand_cum = np.cumsum(demand, axis=1)
    hold_units = np.zeros(T)
    s_level = np.zeros((n_dc, T))
    stockout = np.zeros((n_dc, T), bool)
    linehaul_cost = 0.0
    prod = np.zeros(T)
    for t in range(T):
        on_hand += pipeline[:, t]
        # serve customers FIFO (backlog first)
        need = backlog + demand[:, t]
        ship = np.minimum(on_hand, need)
        on_hand -= ship
        backlog = need - ship
        stockout[:, t] = backlog > 0
        shipped_cum[:, t] = (shipped_cum[:, t - 1] if t else 0) + ship
        # forecast update (online, after observing today's demand)
        err = demand[:, t] - f
        f = f + net.alpha * err
        var = (1 - net.alpha) * var + net.alpha * err ** 2
        # order-up-to review
        protect = L + net.review_days
        S = f * protect + net.z * np.sqrt(var * protect)
        s_level[:, t] = S
        in_transit = pipeline[:, t + 1:].sum(axis=1)
        position = on_hand + in_transit - backlog - 0.0
        req = np.maximum(0.0, S - position - plant_backlog)
        plant_backlog += req
        # plant capacity is planned on the first day of each month: capacity_ratio x the current forecast
        if t == 0 or days[t].day == 1:
            # monthly capacity plan: ratio x the demand level, never cut by more than 5 % a month (a plant does
            # not shed capacity because of one quiet week)
            recent = tot[max(0, t - 27):t + 1].mean()
            cap_plan = max(net.capacity_ratio * max(f.sum(), recent), 0.95 * cap_plan)
        cap[t] = cap_plan * cut[t]
        # plant: produce, then ship to DCs (proportional allocation if short)
        buf = net.plant_buffer_days + (prebuild_days[t] if net.prebuild else 0.0)
        target = f.sum() * buf + plant_backlog.sum()
        p = min(cap[t], max(0.0, target - plant))
        prod[t] = p
        plant += p
        total = plant_backlog.sum()
        if total > 0:
            send = plant_backlog * min(1.0, plant / total)
            plant -= send.sum()
            plant_backlog -= send
            for k in range(n_dc):
                if send[k] > 0:
                    pipeline[k, t + L[k]] += send[k]
                    linehaul_cost += send[k] * (c.linehaul_fixed + c.linehaul_per_km *
                                                haversine_km(*PLANT, *coords[k]))
        hold_units[t] = on_hand.sum() + plant + pipeline[:, t + 1:].sum()
    # ship day of each order: first day the cumulative shipments cover the cumulative demand of its day
    ship_day = np.empty(len(orders), int)
    for k in range(n_dc):
        m = dc_of == k
        need_cum = demand_cum[k, t_idx[m]]
        sd = np.searchsorted(shipped_cum[k], need_cum - 1e-9, side="left")
        ship_day[m] = np.where(sd >= T, T + 30, sd)
    wait = ship_day - t_idx
    tr = transit.sample(km, rng)
    lead = wait + 1 + tr
    prom = orders["customer_state"].map(promise).to_numpy()
    on_time = lead <= prom
    w = units
    last_mile = freight.cost(km)
    holding = hold_units.sum() * c.unit_value * c.holding_rate / 365
    regional = sum(1 for d in dcs if d != "São Paulo DC")
    fixed = regional * c.dc_fixed_per_day * T
    lm = float(np.sum(last_mile * w))
    total_units = float(w.sum())
    cost = holding + linehaul_cost + lm + fixed
    res = {
        "dcs": " + ".join(dcs), "z": net.z, "otif_pct": 100 * float(np.sum(on_time * w) / total_units),
        "fill_rate_pct": 100 * float(np.sum((wait == 0) * w) / total_units),
        "lead_p50_days": float(np.median(lead)), "lead_p90_days": float(np.quantile(lead, 0.9)),
        "days_of_cover": float(hold_units.mean() / (demand.sum() / T)),
        "stockout_days_pct": 100 * float(stockout.any(axis=0).mean()),
        "cost_per_unit": cost / total_units, "holding_per_unit": holding / total_units,
        "linehaul_per_unit": linehaul_cost / total_units, "last_mile_per_unit": lm / total_units,
        "dc_fixed_per_unit": fixed / total_units, "units": total_units,
    }
    res["_daily"] = pd.DataFrame({"day": days, "demand": demand.sum(axis=0), "production": prod,
                                  "capacity": cap, "stock_units": hold_units,
                                  "backlog": np.array([0.0] * T)})
    res["_orders"] = pd.DataFrame({"day": orders["day"], "state": orders["customer_state"],
                                   "region": orders["customer_region"], "dc": np.array(dcs)[dc_of], "km": km,
                                   "units": w, "wait": wait, "lead": lead, "promise": prom, "on_time": on_time})
    return res


def run(orders, transit, freight, promise, **kw) -> dict:
    return simulate(orders, transit, freight, promise, replace(Network(), **kw))
