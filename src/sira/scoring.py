import numpy as np
from numpy.typing import ArrayLike
from scipy import stats


def spread(sigma: ArrayLike, err: ArrayLike) -> np.ndarray:
    return np.hypot(sigma, err)


def log_score(y: ArrayLike, mu: ArrayLike, sigma: ArrayLike) -> np.ndarray:
    return stats.norm.logpdf(y, mu, sigma)


def log_score_limit(f_lim: ArrayLike, mu: ArrayLike, sigma: ArrayLike) -> np.ndarray:
    return stats.norm.logcdf(f_lim, mu, sigma)


def crps(y: ArrayLike, mu: ArrayLike, sigma: ArrayLike) -> np.ndarray:
    z = (np.asarray(y) - mu) / sigma
    # closed form for a Gaussian forecast (Gneiting et al. 2005)
    return sigma * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))


def pit(y: ArrayLike, mu: ArrayLike, sigma: ArrayLike) -> np.ndarray:
    return stats.norm.cdf(y, mu, sigma)


def coverage(y: ArrayLike, mu: ArrayLike, sigma: ArrayLike, level: float = 0.9) -> np.ndarray:
    return np.abs(np.asarray(y) - mu) <= stats.norm.ppf(0.5 + level / 2) * sigma


def uniformity(pits: ArrayLike, bins: int = 10) -> dict:
    counts, _ = np.histogram(pits, bins=bins, range=(0, 1))
    p_value = float(stats.chisquare(counts).pvalue) if counts.sum() else None
    return {"counts": counts.tolist(), "p_value": p_value}


def _col(rows: list[dict], key: str) -> np.ndarray:
    return np.array([r[key] for r in rows], dtype=float)


def _mean(x: np.ndarray) -> float | None:
    return float(x.mean()) if x.size else None


def score(rows: list[dict]) -> dict:
    det = [r for r in rows if r.get("limit") is None]
    lim = [r for r in rows if r.get("limit") is not None]
    y, mu, sd = _col(det, "y"), _col(det, "mu"), spread(_col(det, "sigma"), _col(det, "err"))
    # ZTF limits are 5 sigma, so the measurement behind a limit has noise of a fifth of it
    f_lim = _col(lim, "limit")
    logs = np.concatenate([log_score(y, mu, sd),
                           log_score_limit(f_lim, _col(lim, "mu"), spread(_col(lim, "sigma"), f_lim / 5))])
    pits = pit(y, mu, sd)
    return {
        "n": len(rows), "n_limits": len(lim),
        "log_score": _mean(logs), "crps": _mean(crps(y, mu, sd)), "pit_mean": _mean(pits),
        "coverage_90": _mean(coverage(y, mu, sd, 0.9)),
        "uniformity": uniformity(pits),
    }
