import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import median_abs_deviation

from .models import Fit, Phot, _guard


def fit_null(ph: Phot) -> Fit | None:
    _guard(ph)
    if not len(ph):
        return None
    start, order = time.time(), np.argsort(ph.t, kind="stable")
    last = {ph.band[i]: i for i in order}  # each band keeps its latest point
    pick = lambda band: np.array([last.get(b, order[-1]) for b in np.atleast_1d(band)], dtype=int)
    scale = max(float(median_abs_deviation(ph.flux, scale="normal")), float(np.median(ph.err)))
    flux = lambda p, t, band: ph.flux[pick(np.broadcast_arrays(t, band)[1])]
    noise = lambda t, band: scale ** 2 * (1 + np.abs(t - ph.t[pick(band)]) / 10)
    chi2 = float(np.sum(((ph.flux - flux(None, ph.t, ph.band)) / ph.sigma) ** 2))
    ndof = max(len(ph) - len(last), 1)  # each band's latest point is matched by construction
    return Fit("null", [], np.zeros(0), None, flux, chi2, ndof, time.time() - start, {"scale": scale}, noise)


def fit_instrument(ph: Phot) -> Fit | None:
    _guard(ph)
    if not len(ph):
        return None
    start, sd = time.time(), 2 * float(np.median(ph.err))
    flux = lambda p, t, band: np.zeros(np.broadcast(t, band).shape)
    noise = lambda t, band: np.full(np.broadcast(t, band).shape, sd ** 2)
    chi2 = float(np.sum((ph.flux / ph.sigma) ** 2))
    return Fit("instrument", [], np.zeros(0), None, flux, chi2, len(ph), time.time() - start, {"sd": sd}, noise)


CLIMATE = Path(__file__).parent / "climatology.json"


def climatology(root: Path, bands: tuple = ("ztfg", "ztfr")) -> dict:
    # B0: how supernova fluxes change over one to five days, from the dev half of the snapshot only
    manifest = json.loads((Path(root) / "manifest.json").read_text())
    objs = [o for o in manifest["objects"] if o["category"] in ("ia", "cc") and o["split"] == "dev"]
    out = {"source": f"{len(objs)} dev-split supernovae from the snapshot"}
    for band in bands:
        h, m, s, n = [], [], [], 0
        for days in range(1, 6):
            ratios = []
            for o in objs:
                rows = sorted((r["mjd"], r["flux"]) for r in json.loads((Path(root) / o["file"]).read_text())["photometry"]
                              if r["kind"] == "det" and r["band"] == band and r["flux"] > 0)
                ratios += [np.log(f2 / f1) for i, (t1, f1) in enumerate(rows) for t2, f2 in rows[i + 1:]
                           if abs(t2 - t1 - days) <= 0.5]
            med = float(np.median(ratios))
            h.append(days), m.append(med), s.append(1.4826 * float(np.median(np.abs(np.array(ratios) - med))))
            n += len(ratios)
        h, m, s = np.array(h), np.array(m), np.array(s)
        # drift grows linearly with time, scatter like a random walk
        out[band] = {"drift": round(float(h @ m / (h @ h)), 5), "spread": round(float(np.sqrt(h) @ s / h.sum()), 5),
                     "pairs": n}
    return out


def b0(view: dict, t: np.ndarray, band: np.ndarray, table: dict | None = None) -> list[list]:
    table = table or json.loads(CLIMATE.read_text())
    dets = [r for r in view["photometry"] if r["kind"] == "det" and r["flux"] > 0]
    parts = []
    for when, b in zip(t, band):
        own = [r for r in dets if r["band"] == b] or dets
        last = max(own, key=lambda r: r["mjd"])
        c = table.get(b, table["ztfr"])
        dt = max(float(when) - last["mjd"], 0.1)
        mu, s = np.log(last["flux"]) + c["drift"] * dt, c["spread"] * np.sqrt(dt)
        mean = float(np.exp(mu + s * s / 2))
        parts.append([["b0", 1.0, round(mean, 2), round(mean * float(np.sqrt(np.expm1(s * s))), 2)]])
    return parts
