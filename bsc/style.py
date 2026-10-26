"""Figure style: ivory, black and gold."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

BG, PANEL, GRID = "#faf7f2", "#ffffff", "#ebe4d8"
INK, MUTED = "#1a1a1a", "#6e6a63"
GOLD, ROSE, TEAL, SLATE, PLUM = "#b8925a", "#c46b6b", "#2f7d79", "#5b6b7a", "#7b4f8a"
SERIES = [INK, GOLD, TEAL, ROSE, SLATE, PLUM]
GEO = Path(__file__).resolve().parent.parent / "data" / "geo" / "brazil_states.geojson"


def apply():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": PANEL, "savefig.facecolor": BG, "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
        "axes.titlecolor": INK, "grid.color": GRID, "axes.grid": True, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 9.5, "axes.titlesize": 10.5,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False, "legend.fontsize": 8.5,
        "lines.linewidth": 2.0, "font.family": "DejaVu Sans",
    })


def title(fig, text, sub=None):
    h = fig.get_figheight()
    fig.suptitle(text, x=0.012, y=1 - 0.12 / h, ha="left", va="top", fontsize=13.5, fontweight="bold", color=INK)
    if sub:
        fig.text(0.012, 1 - 0.46 / h, sub, ha="left", va="top", fontsize=9, color=MUTED)


def rect(fig):
    return (0, 0, 1, 1 - 0.66 / fig.get_figheight())


def brazil(ax, values: dict, cmap="YlOrBr", label="", vmin=None, vmax=None, fmt="{:.0f}"):
    """Choropleth of the 27 states from the simplified GeoJSON."""
    g = json.loads(GEO.read_text())
    patches, vals = [], []
    for feat in g["features"]:
        st = feat["properties"]["state"]
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            patches.append(Polygon(poly[0], closed=True))
            vals.append(values.get(st, float("nan")))
    pc = PatchCollection(patches, cmap=cmap, edgecolor="white", linewidth=0.6)
    pc.set_array(vals)
    if vmin is not None:
        pc.set_clim(vmin, vmax)
    ax.add_collection(pc)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    cb = plt.colorbar(pc, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(label, color=MUTED)
    cb.outline.set_visible(False)
    return pc
