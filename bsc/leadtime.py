"""Transit time and last-mile cost models learnt from 96,000 real deliveries (distance -> empirical distribution)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


@dataclass
class TransitModel:
    edges: np.ndarray            # distance bin edges, km
    samples: list                # real transit days observed in each bin
    p50: np.ndarray
    p90: np.ndarray

    @classmethod
    def fit(cls, orders: pd.DataFrame, n_bins: int = 24) -> "TransitModel":
        d = orders.dropna(subset=["km", "d_transit"])
        d = d[(d["d_transit"] >= 0) & (d["d_transit"] < 120)]
        edges = np.unique(np.quantile(d["km"], np.linspace(0, 1, n_bins + 1)))
        edges[0], edges[-1] = 0.0, max(edges[-1], 5000.0)
        idx = np.clip(np.searchsorted(edges, d["km"].to_numpy(), side="right") - 1, 0, len(edges) - 2)
        samples = [np.sort(d["d_transit"].to_numpy()[idx == k]) for k in range(len(edges) - 1)]
        p50 = np.array([np.median(s) for s in samples])
        p90 = np.array([np.quantile(s, 0.9) for s in samples])
        return cls(edges, samples, p50, p90)

    def bin(self, km):
        return np.clip(np.searchsorted(self.edges, np.asarray(km), side="right") - 1, 0, len(self.edges) - 2)

    def sample(self, km, rng) -> np.ndarray:
        """Bootstrap: one real transit time drawn from the deliveries of the same distance band."""
        b = self.bin(km)
        out = np.empty(len(b))
        for k in np.unique(b):
            m = b == k
            out[m] = rng.choice(self.samples[k], m.sum())
        return out

    def quantile(self, km, q=0.9):
        b = self.bin(km)
        return np.array([np.quantile(self.samples[k], q) for k in np.atleast_1d(b)])


@dataclass
class FreightModel:
    edges: np.ndarray
    per_unit: np.ndarray          # median real freight per item (BRL) in each distance band

    @classmethod
    def fit(cls, lines: pd.DataFrame) -> "FreightModel":
        d = lines.dropna(subset=["km", "freight"])
        d = d[d["is_beauty"]]
        edges = np.array([0, 100, 300, 600, 1000, 1500, 2000, 2500, 3000, 5000.0])
        idx = np.clip(np.searchsorted(edges, d["km"].to_numpy(), side="right") - 1, 0, len(edges) - 2)
        med = np.array([np.median(d["freight"].to_numpy()[idx == k]) if np.any(idx == k) else np.nan
                        for k in range(len(edges) - 1)])
        med = pd.Series(med).ffill().bfill().to_numpy()
        return cls(edges, med)

    def cost(self, km) -> np.ndarray:
        b = np.clip(np.searchsorted(self.edges, np.asarray(km), side="right") - 1, 0, len(self.edges) - 2)
        return self.per_unit[b]
