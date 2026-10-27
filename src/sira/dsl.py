import time

import numpy as np
from scipy.optimize import least_squares

from .models import Fit, Phot, _cov, _guard, _magnification

# the pieces a Le Verrier may combine; code compiles and fits them, so no model-written code ever runs
PRIMITIVES = {
    "lens": "an unseen point lens magnifying a background source; the same time profile in every band (t0, u0, tE)",
    "rise_fall": "a smooth rise and fall, like the light curve of an explosion (t0, rise, fall)",
    "power_law": "a decline as a power of the time since onset, like fallback accretion (t0, tau, index)",
    "decay": "an exponential fade from an onset, like radioactive heating (t0, tau)",
    "flare": "a short symmetric flare (t0, width)",
    "constant": "a steady level in each band, like unmodelled host light or a calibration offset",
    "trend": "a slow linear drift in each band, like a variable host or a drifting calibration",
}
SHARED = {"lens": ("t0", "u0", "tE"), "rise_fall": ("t0", "rise", "fall"), "power_law": ("t0", "tau", "index"),
          "decay": ("t0", "tau"), "flare": ("t0", "width"), "constant": (), "trend": ()}
SHARED_PARAMS = {p for ps in SHARED.values() for p in ps}
LIMITS = {"u0": (1e-3, 2.0), "tE": (1.0, 600.0), "rise": (0.5, 50.0), "fall": (1.0, 300.0), "tau": (1.0, 500.0),
          "index": (0.1, 5.0), "width": (0.5, 100.0)}
SIGNED = ("constant", "trend")  # these may push flux below the template's level
MAX_PARTS = 3


def _shape(kind: str, q: np.ndarray, t: np.ndarray, ref: float) -> np.ndarray:
    if kind == "constant":
        return np.ones_like(t)
    if kind == "trend":
        return (t - ref) / 100
    if kind == "lens":
        return _magnification(np.hypot(q[1], (t - q[0]) / q[2])) - 1
    if kind == "rise_fall":
        return np.exp(-np.clip((t - q[0]) / q[2], -50, 50)) / (1 + np.exp(-np.clip((t - q[0]) / q[1], -50, 50)))
    after = np.clip(t - q[0], 0, None)
    if kind == "power_law":
        return np.where(t > q[0], (1 + after / q[1]) ** -q[2], 0.0)
    if kind == "decay":
        return np.where(t > q[0], np.exp(-after / q[1]), 0.0)
    return np.exp(-0.5 * ((t - q[0]) / q[1]) ** 2)


def compile_spec(spec: dict, ph: Phot) -> tuple[list[str], np.ndarray, np.ndarray, callable]:
    parts = [c.get("type") for c in spec.get("components", []) if isinstance(c, dict)]
    if not parts or len(parts) > MAX_PARTS or any(p not in PRIMITIVES for p in parts):
        raise ValueError(f"components must be 1 to {MAX_PARTS} of {sorted(PRIMITIVES)}")
    bands, top = sorted(set(ph.band)), float(np.max(np.abs(ph.flux)))
    names, lo, hi, layout = [], [], [], []
    for i, kind in enumerate(parts):
        shared = list(range(len(names), len(names) + len(SHARED[kind])))
        for p in SHARED[kind]:
            names.append(f"{kind}{i}.{p}")
            low, high = (ph.t.min() - 100, ph.t.max() + 100) if p == "t0" else LIMITS[p]
            lo.append(low), hi.append(high)
        amps = list(range(len(names), len(names) + len(bands)))
        for b in bands:
            names.append(f"{kind}{i}.{b}")
            lo.append(-top if kind in SIGNED else 0.0), hi.append(top if kind in SIGNED else 10 * top)
        layout.append((kind, shared, amps))
    ref = float(np.median(ph.t))

    def flux(p, t, band):
        out = np.zeros(len(t))
        index = np.array([bands.index(b) if b in bands else -1 for b in band])
        for kind, shared, amps in layout:
            a = np.append(p[amps], np.nan)[index]  # an unseen band has no amplitude to forecast with
            out = out + a * _shape(kind, p[shared], t, ref)
        return out

    return names, np.array(lo, dtype=float), np.array(hi, dtype=float), flux


def fit_spec(spec: dict, ph: Phot, name: str = "proposal", starts: int = 16, seed: int = 0) -> Fit | None:
    _guard(ph)
    names, lo, hi, flux = compile_spec(spec, ph)
    if len(ph) < len(names) + 2:
        return None
    start, rng, best = time.time(), np.random.default_rng(seed), None
    resid = lambda p: (flux(p, ph.t, ph.band) - ph.flux) / ph.sigma
    t_max = ph.t[np.argmax(ph.flux)]
    for k in range(starts):
        p0 = lo + rng.uniform(0.05, 0.95, len(lo)) * (hi - lo)
        for i, n in enumerate(names):
            if n.endswith(".t0"):
                p0[i] = t_max + rng.normal(0, 15) if k else t_max  # onsets and peaks start near the brightest point
            elif not any(n.endswith(f".{x}") for x in SHARED_PARAMS):
                p0[i] = rng.uniform(0, 1) * ph.flux.max() if lo[i] >= 0 else 0.0
        try:
            r = least_squares(resid, np.clip(p0, lo, hi), bounds=(lo, hi))
        except ValueError:
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None:
        return None
    chi2, ndof = float(2 * best.cost), max(len(ph) - len(names), 1)
    return Fit(name, names, best.x, _cov(best.jac, lo, hi, max(1.0, chi2 / ndof)), flux, chi2, ndof,
               time.time() - start, {"spec": spec})

