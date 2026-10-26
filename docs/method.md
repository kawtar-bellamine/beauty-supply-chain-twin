## Method

**Data.** Public Olist marketplace extract (Brazil, 2016 to 2018, MIT licence): orders, items, products, customers,
sellers and the zip-code geolocation table, checksummed. The beauty scope is the health & beauty and perfumery
categories: 11,722 delivered orders. Customer and seller coordinates come from the median of each zip prefix
(coordinates outside Brazil discarded); 99.5 % of orders get a distance.

**Flow analysis.** Each delivered order is split into payment approval, seller handling (approval to carrier) and carrier
transit (carrier to customer). An order is late when it arrives after the end of its promised day. A late order is
attributed to the seller when it was handed to the carrier after the shipping limit, to the carrier otherwise.

**Forecasting.** Weekly units by macro-region (N, NE, CO, SE, S) and in total; naive, 4-week moving average,
exponential smoothing and Holt compared on 26 rolling origins, horizons 1 to 4 weeks. WAPE and bias.

**Digital twin.**
* *Demand:* the real daily beauty order rate (7-day centred mean) times 40, Poisson at that scale; each simulated order
  copies a real order of the same fortnight (customer location, state, units). About 450,000 orders.
* *Transit:* drawn from the 96,000 real deliveries in the same distance band (24 bands); last-mile cost from the
  median real freight per beauty item in the same band.
* *Policy:* each DC reviews daily with an order-up-to level `S = f (L + R) + z σ √(L + R)`; `f` and `σ` are updated
  online by exponential smoothing. The plant capacity is planned on the 1st of each month at 1.3 × the demand level
  (never cut by more than 5 % a month) and the plant keeps 3 days of finished goods.
* *Line haul:* 1 day plus distance at 650 km a day (São Paulo DC 1 day, Recife DC 5 days).
* *Promise:* per state, the 90th percentile of transit from São Paulo plus 2 days, fixed for every scenario.
* *Costs (assumptions):* unit value 80 BRL, holding 25 % a year, line haul 0.20 BRL + 0.0006 BRL per unit-km, a
  regional DC 1,500 BRL a day.

**Excel model.** `exports/inventory_policy_model.xlsx`: the same order-up-to policy written as Excel formulas
(NORMSINV, ROUNDUP, SQRT), with the inputs in blue, a service-level trade-off table and chart, and the twin's scenario
results as values.

**Power BI.** `exports/` holds a star schema: `fact_beauty_orders`, `dim_state`, `dim_date`, `fact_twin_daily_baseline`,
`fact_twin_scenarios`.

## Limits

* The data is a Brazilian marketplace, not a brand's own network: the twin uses its demand pattern, geography and
  transit times, with a hypothetical plant and DCs.
* Volumes are scaled ×40 to a brand-sized flow; costs are assumptions written in one place (`bsc/twin.py`).
* Transit times are those of marketplace parcel carriers; a brand with contracted carriers would have its own.
* One product family, no product mix, no production changeovers; the plant is a single capacity.
