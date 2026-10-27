import time
from itertools import product

import numpy as np
from scipy.linalg import block_diag, cho_factor, cho_solve
from scipy.optimize import least_squares, minimize

from .models import Fit, Phot, _cov, _guard

WAVE = {"ztfg": 4746.0, "ztfr": 6366.0, "ztfi": 7829.0}  # effective wavelengths, angstrom
HC_K = 1.43878e8  # h c / k in angstrom kelvin
T_RANGE = (1e4, 6e4)
TAU_RANGE = (1.0, 2000.0)


def _wave(band) -> np.ndarray:
    return np.array([WAVE.get(b, np.nan) for b in np.atleast_1d(band)])


def _tde(p: np.ndarray, t: np.ndarray, lam: np.ndarray) -> np.ndarray:
    t_peak, sigma, t0, amp, temp = p
    # error propagation nudges parameters across their bounds; keep the timescales positive
    sigma, t0 = max(sigma, 1e-3), max(t0, 1e-3)
    dt = t - t_peak
    # Gaussian rise, then the fallback decline; each factor is 1 on the other side of the peak
    shape = np.exp(-0.5 * (np.minimum(dt, 0) / sigma) ** 2) * (1 + np.maximum(dt, 0) / t0) ** (-5 / 3)
    r = WAVE["ztfr"]
    # blackbody f_nu relative to the r band, so amp is the r-band peak flux
    colour = (r / lam) ** 3 * np.expm1(HC_K / (r * temp)) / np.expm1(HC_K / (lam * temp))
    return amp * colour * shape


def fit_tde(ph: Phot) -> Fit | None:
    _guard(ph)
    keep = np.isin(ph.band, list(WAVE))
    t, lam, f, s = ph.t[keep], _wave(ph.band[keep]), ph.flux[keep], ph.sigma[keep]
    if len(t) < 6:
        return None
    start = time.time()
    resid = lambda p: (_tde(p, t, lam) - f) / s
    lo = np.array([t.min() - 100, 1, 1, 0, T_RANGE[0]])
    hi = np.array([t.max() + 100, 150, 1000, 1e7, T_RANGE[1]])
    t_max, best = t[np.argmax(f)], None
    for dt, sigma, t0 in product((-20, -5, 5, 20), (5, 25), (30, 150)):
        p0 = np.clip([t_max + dt, sigma, t0, f.max(), 2.5e4], lo, hi)
        try:
            r = least_squares(resid, p0, bounds=(lo, hi), x_scale="jac")
        except ValueError:
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None:
        return None
    chi2, ndof = float(2 * best.cost), max(len(t) - 5, 1)
    # colour from a single band, for one, stays uncertain rather than breaking the inverse
    cov = _cov(best.jac, lo, hi, max(1.0, chi2 / ndof))
    return Fit("tde", ["t_peak", "sigma", "t0", "amp_r", "T"], best.x, cov,
               lambda p, t, band: _tde(p, t, _wave(band)), chi2, ndof, time.time() - start)


def _drw(a, b: np.ndarray, q: np.ndarray) -> np.ndarray:
    return np.exp(2 * q[0] - np.abs(np.reshape(a, (-1, 1)) - b) / np.exp(q[1]))


def _hessian(f, x: np.ndarray, h: float = 0.02) -> np.ndarray:
    e = h * np.eye(len(x))
    d2 = [[f(x + a + b) - f(x + a - b) - f(x - a + b) + f(x - a - b) for b in e] for a in e]
    return np.array(d2) / (4 * h * h)


def fit_agn(ph: Phot) -> Fit | None:
    _guard(ph)
    if len(ph) < 8:
        return None
    start, bands = time.time(), sorted(set(ph.band))
    y, X = ph.flux, (ph.band[:, None] == np.array(bands)).astype(float)

    def solve(q):
        # Cholesky of the data covariance, then the band means by generalised least squares
        c = cho_factor(_drw(ph.t, ph.t, q) + np.diag(ph.sigma ** 2), lower=True)
        z = cho_solve(c, np.column_stack([y, X]))
        a = X.T @ z[:, 1:]
        beta = np.linalg.solve(a, X.T @ z[:, 0])
        return c, z, a, beta, float((y - X @ beta) @ (z[:, 0] - z[:, 1:] @ beta))

    def nll(q):
        c, *_, chi2 = solve(q)
        return 0.5 * chi2 + np.log(np.diag(c[0])).sum()

    s0 = np.std(y) + np.median(ph.sigma)
    bounds, best = [(np.log(s0) - 7, np.log(s0) + 3), tuple(np.log(TAU_RANGE))], None
    for tau in (10, 100, 1000):
        try:
            r = minimize(nll, [np.log(s0), np.log(tau)], method="L-BFGS-B", bounds=bounds)
        except np.linalg.LinAlgError:
            continue
        if best is None or r.fun < best.fun:
            best = r
    if best is None:
        return None
    q = best.x
    c, z, a, beta, chi2 = solve(q)
    w, v = np.linalg.eigh(_hessian(nll, q))
    # a flat direction of the likelihood gets at most unit variance in log space
    cov = block_diag((v / np.maximum(w, 1.0)) @ v.T, np.linalg.inv(a))

    def flux(p, t, band):
        zp = z if np.array_equal(p[:2], q) else solve(p)[1]
        means = dict(zip(bands, p[2:]))
        mean = np.array([means.get(b, np.nan) for b in np.atleast_1d(band)])
        return mean + _drw(t, ph.t, p) @ (zp[:, 0] - zp[:, 1:] @ p[2:])

    def noise(t, band):
        k = _drw(t, ph.t, q)
        return np.clip(np.exp(2 * q[0]) - np.sum(k * cho_solve(c, k.T).T, axis=1), 0, None)

    names = ["log_sigma", "log_tau"] + [f"mean_{b}" for b in bands]
    extra = {"sigma": float(np.exp(q[0])), "tau": float(np.exp(q[1])),
             "loglike": float(-best.fun - 0.5 * len(ph) * np.log(2 * np.pi))}
    return Fit("agn", names, np.concatenate([q, beta]), cov, flux, chi2, max(len(ph) - len(names), 1),
               time.time() - start, extra, noise)
