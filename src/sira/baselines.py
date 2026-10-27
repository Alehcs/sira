import time

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
