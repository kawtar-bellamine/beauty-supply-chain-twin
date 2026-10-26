"""Banner (README) and LinkedIn visual from HTML, with the numbers of results/summary.json."""
import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
S = json.loads((ROOT / "results" / "summary.json").read_text())
t = S["twin"]
img = base64.b64encode((ROOT / "results" / "figures" / "fig2_geography.png").read_bytes()).decode()
carrier = [s for s in S["flow"]["stages"] if s["stage"] == "Carrier transit"][0]["share_of_lead_time_pct"]


def html(w, h, big):
    return f"""<html><head><style>
body {{ margin:0; width:{w}px; height:{h}px; overflow:hidden; font-family:'Inter','Segoe UI',Arial,sans-serif;
  background: linear-gradient(115deg, #0f0f0f 0%, #221d18 55%, #4a3b28 100%); color:#faf7f2; }}
.wrap {{ position:absolute; left:{56 if big else 46}px; top:{50 if big else 40}px; width:{w * 0.52:.0f}px; }}
.kick {{ letter-spacing:4px; font-size:13px; color:#b8925a; font-weight:700; }}
h1 {{ font-size:{58 if big else 50}px; margin:12px 0 10px; color:#f3e7d3; font-weight:600; letter-spacing:.5px; }}
.sub {{ font-size:{20 if big else 18}px; color:#d9cfc0; line-height:1.45; }}
.k {{ position:absolute; left:{56 if big else 46}px; bottom:{46 if big else 34}px; display:flex; gap:14px; }}
.c {{ border:1px solid rgba(184,146,90,.45); border-radius:14px; padding:12px 16px; background:rgba(0,0,0,.25); }}
.c b {{ display:block; font-size:{26 if big else 23}px; color:#f3e7d3; font-weight:600; }}
.c span {{ font-size:12px; color:#b8925a; }}
.fig {{ position:absolute; right:{36 if big else 26}px; top:{36 if big else 120}px; width:{w * 0.40:.0f}px;
  border-radius:14px; box-shadow:0 20px 50px rgba(0,0,0,.45); }}
</style></head><body>
<img class="fig" src="data:image/png;base64,{img}">
<div class="wrap"><div class="kick">SUPPLY CHAIN · DATA · SIMULATION</div>
<h1>Beauty Supply Chain Twin</h1>
<div class="sub">From sales forecast to customer delivery on 11,722 real beauty orders, and a digital twin that tests
a regional DC, a Black Friday pre-build or a plant outage before anyone spends a real.</div></div>
<div class="k">
<div class="c"><b>{carrier:.0f} %</b><span>of lead time is transit</span></div>
<div class="c"><b>{t['black_friday']['no pre-build']['fill_rate_pct']:.0f} → {t['black_friday']['pre-build 10 days']['fill_rate_pct']:.0f} %</b><span>Black Friday fill rate</span></div>
<div class="c"><b>{t['north_east']['one DC']['lead_p50_days']:.0f} → {t['north_east']['with Recife DC']['lead_p50_days']:.0f} days</b><span>North-East delivery</span></div>
</div></body></html>"""


with sync_playwright() as p:
    b = p.chromium.launch()
    for name, (w, h, big) in {"banner": (1600, 540, True), "linkedin": (1200, 627, False)}.items():
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1.5 if name == "banner" else 2)
        pg.set_content(html(w, h, big))
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(ROOT / "docs" / f"{name}.png"))
    b.close()
print("ok")
