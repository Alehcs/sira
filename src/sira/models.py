import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import sncosmo
from astropy.cosmology import Planck18
from astropy.table import Table
from scipy.optimize import least_squares
from scipy.stats import chi2 as chi2_dist

ZP = 23.9  # photometry fluxes are microjansky
FLOOR = 0.05  # model error as a fraction of flux, on every point and every prediction
# Tripp standardisation for F7; M_B only seeds the redshift iteration
ALPHA, BETA, M_B = 0.14, 3.1, -19.3
TEMPLATES = {
    "ia": ("salt3", {"x1": (-3, 3), "c": (-0.3, 0.5)}, (0.005, 0.2)),
    "ii": ("nugent-sn2p", {}, (0.002, 0.15)),
    "ibc": ("nugent-sn1bc", {}, (0.005, 0.2)),
    "iin": ("nugent-sn2n", {}, (0.005, 0.3)),
}
HYPOTHESES = (*TEMPLATES, "lens", "tde", "agn", "null", "instrument")
_Z = np.linspace(0.003, 0.4, 4000)
_MU = Planck18.distmod(_Z).value


class FutureData(RuntimeError):
    pass


@dataclass(frozen=True)
class Phot:
    t: np.ndarray
    band: np.ndarray
    flux: np.ndarray
    err: np.ndarray
    as_of: float
    floor: float = FLOOR

    @property
    def sigma(self) -> np.ndarray:
        return np.hypot(self.err, self.floor * np.abs(self.flux))

    def __len__(self) -> int:
        return len(self.t)


def phot(view: dict, bands: tuple = ("ztfg", "ztfr", "ztfi"), floor: float = FLOOR, signed: bool = False) -> Phot:
    # negative difference fluxes only matter to variable sources, so most hypotheses fit the positive ones
    rows = sorted((r for r in view["photometry"] if r["kind"] == "det" and r["band"] in bands
                   and (signed or r["flux"] > 0)), key=lambda r: r["mjd"])
    col = lambda k: np.array([r[k] for r in rows], dtype=float)
    return Phot(col("mjd"), np.array([r["band"] for r in rows], dtype=str), col("flux"), col("flux_err"),
                view["as_of"], floor)


def _guard(ph: Phot) -> None:
    # every fit takes a view from as_of(t); a point newer than t means the firewall was bypassed
    if len(ph) and ph.t.max() > ph.as_of:
        raise FutureData(f"point at {ph.t.max()} in a view as of {ph.as_of}")


@dataclass
class Fit:
    model: str
    names: list[str]
    x: np.ndarray
    cov: np.ndarray | None
    flux: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]
    chi2: float
    ndof: int
    seconds: float
    extra: dict = field(default_factory=dict)
    # variance a hypothesis adds on top of its parameters, such as a stochastic process
    noise: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None

    @property
    def params(self) -> dict:
        return {n: float(v) for n, v in zip(self.names, self.x)}

    def predict(self, t, band) -> tuple[np.ndarray, np.ndarray]:
        t, band = np.atleast_1d(np.asarray(t, dtype=float)), np.atleast_1d(np.asarray(band, dtype=str))
        mu = self.flux(self.x, t, band)
        var = (FLOOR * mu) ** 2 + (_param_var(self.flux, self.x, self.cov, t, band) if self.cov is not None else 0)
        if self.noise is not None:
            var = var + self.noise(t, band)
        return mu, np.sqrt(var)


def _param_var(flux, x, cov, t, band) -> np.ndarray:
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    grads = []
    for i in range(len(x)):
        # step on the scale of the parameter's own uncertainty, where the linear approximation holds
        h = 0.01 * sd[i] if sd[i] > 0 else 1e-6 * (abs(x[i]) + 1e-8)
        up, down = x.copy(), x.copy()
        up[i] += h
        down[i] -= h
        grads.append((flux(up, t, band) - flux(down, t, band)) / (2 * h))
    flux(x, t, band)  # leave stateful models at the best fit
    g = np.array(grads)
    return np.clip(np.einsum("in,ij,jn->n", g, cov, g), 0, None)


def _sn_model(source: str, mwebv: float) -> sncosmo.Model:
    model = sncosmo.Model(source=source, effects=[sncosmo.F99Dust()], effect_names=["mw"], effect_frames=["obs"])
    model.set(mwebv=mwebv)
    return model


def fit_template(kind: str, ph: Phot, mwebv: float = 0.0, z: float | None = None) -> Fit | None:
    _guard(ph)
    source, bounds, z_range = TEMPLATES[kind]
    if len(ph) < 4:
        return None
    start, model = time.time(), _sn_model(source, mwebv)
    names = ["t0", "x0" if source.startswith("salt") else "amplitude", *bounds]
    limits = dict(bounds) | {"t0": (ph.t.min() - 60, ph.t.max() + 40)}
    if z is None:
        names, limits["z"] = ["z", *names], z_range
    else:
        model.set(z=z)
    data = Table({"time": ph.t, "band": ph.band, "flux": ph.flux, "fluxerr": ph.sigma,
                  "zp": np.full(len(ph), ZP), "zpsys": np.full(len(ph), "ab")})
    try:
        res, fitted = sncosmo.fit_lc(data, model, names, bounds=limits, warn=False)
    except Exception:
        return None
    x = np.array([fitted[n] for n in names], dtype=float)
    # a poor fit gets wider parameter errors, as in the lens fit
    inflate = max(1.0, float(res.chisq) / max(int(res.ndof), 1))
    cov = np.array(res.covariance) * inflate if res.covariance is not None else None

    def flux(p, t, band):
        fitted.set(**dict(zip(names, p)))
        end, out = fitted.maxtime(), np.zeros(len(t))
        inside = t <= end
        if inside.any():
            out[inside] = fitted.bandflux(band[inside], t[inside], zp=ZP, zpsys="ab")
        if (~inside).any():
            # past the end of the template, keep fading at its last rate, linear in magnitude
            b = band[~inside]
            last = fitted.bandflux(b, np.full(len(b), end - 0.5), zp=ZP, zpsys="ab")
            before = fitted.bandflux(b, np.full(len(b), end - 10.5), zp=ZP, zpsys="ab")
            rate = np.nan_to_num(np.log(np.clip(last, 1e-12, None) / np.clip(before, 1e-12, None)) / 10)
            out[~inside] = last * np.exp(np.minimum(rate, 0) * (t[~inside] - end + 0.5))
        return out

    def noise(t, band):
        # an extrapolated forecast loses 3% of its flux in certainty per day
        beyond = np.clip(t - fitted.maxtime(), 0, None)
        return (0.03 * beyond * flux(x, t, band)) ** 2

    return Fit(kind, names, x, cov, flux, float(res.chisq), int(res.ndof), time.time() - start,
               {"source": source, "mwebv": mwebv, "model": fitted, "inflate": inflate}, noise)


def _cov(jac: np.ndarray, lo: np.ndarray, hi: np.ndarray, inflate: float) -> np.ndarray:
    # bounds act as a weak prior: what the data cannot see stays uncertain instead of breaking the inverse
    _, sv, vt = np.linalg.svd(np.vstack([jac, np.diag(2 / (hi - lo))]), full_matrices=False)
    return (vt.T / sv ** 2) @ vt * inflate


def _magnification(u: np.ndarray) -> np.ndarray:
    return (u * u + 2) / (u * np.sqrt(u * u + 4))


def fit_lens(ph: Phot) -> Fit | None:
    _guard(ph)
    if len(ph) < 5:
        return None
    start, bands = time.time(), sorted(set(ph.band))

    def flux(p, t, band):
        # difference flux of a point-source point-lens event: the template already holds the unlensed source
        fs = np.array([p[3 + bands.index(b)] if b in bands else np.nan for b in band])
        return fs * (_magnification(np.hypot(p[1], (t - p[0]) / p[2])) - 1)

    resid = lambda p: (flux(p, ph.t, ph.band) - ph.flux) / ph.sigma
    lo = np.array([ph.t.min() - 100, 1e-3, 3] + [0] * len(bands))
    hi = np.array([ph.t.max() + 200, 2.0, 600] + [1e7] * len(bands))
    t_max, best = ph.t[np.argmax(ph.flux)], None
    for dt in (-5, 5, 20):
        for u0 in (0.1, 0.5):
            for te in (20, 60, 150):
                p0 = np.clip([t_max + dt, u0, te] + [ph.flux.max()] * len(bands), lo, hi)
                try:
                    r = least_squares(resid, p0, bounds=(lo, hi))
                except ValueError:
                    continue
                if best is None or r.cost < best.cost:
                    best = r
    if best is None:
        return None
    chi2, ndof = float(2 * best.cost), max(len(ph) - len(best.x), 1)
    cov = _cov(best.jac, lo, hi, max(1.0, chi2 / ndof))
    names = ["t0", "u0", "tE"] + [f"fs_{b}" for b in bands]
    return Fit("lens", names, best.x, cov, flux, chi2, ndof, time.time() - start)


def fit(kind: str, ph: Phot, mwebv: float = 0.0) -> Fit | None:
    from . import baselines, nuclear

    others = {"lens": fit_lens, "tde": nuclear.fit_tde, "agn": nuclear.fit_agn,
              "null": baselines.fit_null, "instrument": baselines.fit_instrument}
    if kind in TEMPLATES:
        return fit_template(kind, ph, mwebv)
    if kind in others:
        return others[kind](ph)
    raise KeyError(f"unknown hypothesis {kind}")


def z_from_mu(mu: float) -> float:
    return float(np.interp(mu, _MU, _Z))


def ia_distance(ph: Phot, mwebv: float = 0.0, rounds: int = 3) -> dict | None:
    # F7: a type Ia light curve alone gives a distance, hence a host redshift to check against the galaxy
    z = 0.05
    for _ in range(rounds):
        f = fit_template("ia", ph, mwebv, z=z)
        if f is None:
            return None
        p = f.params
        mu_no_m = f.extra["model"].source_peakmag("bessellb", "ab") + ALPHA * p["x1"] - BETA * p["c"]
        z = z_from_mu(mu_no_m - M_B)
    sd = dict(zip(f.names, np.sqrt(np.diag(f.cov) / f.extra["inflate"]))) if f.cov is not None else {}
    prob = float(chi2_dist.sf(f.chi2, max(f.ndof, 1)))
    # standard SN Ia cosmology cuts, as in Pantheon+: F7 only bets on a well-measured Ia
    good = bool(sd and abs(p["x1"]) < 3 and abs(p["c"]) < 0.3 and sd["x1"] < 1.5 and sd["t0"] < 2
                and mwebv < 0.2 and prob > 0.001)
    return {"mu_no_m": float(mu_no_m), "z": z, "x1": p["x1"], "c": p["c"], "chi2": f.chi2, "ndof": f.ndof,
            "fit_prob": prob, "sd_t0": float(sd.get("t0", np.inf)), "sd_x1": float(sd.get("x1", np.inf)), "good": good}


def budget(f: Fit) -> dict | None:
    # Arnett's rule: peak light is powered by Ni56, which cannot outweigh the ejecta (nor a Chandrasekhar mass for an Ia)
    if f.model not in ("ia", "ibc"):
        return None
    peak = f.extra["model"].source_peakabsmag("bessellr", "ab", cosmo=Planck18)
    lum = 3.828e33 * 10 ** (-0.4 * (peak - 4.74))
    rise = 18.0 * (0.98 + 0.091 * f.params.get("x1", 0.0)) if f.model == "ia" else 15.0
    # Ni56 and Co56 heating per solar mass (Nadyozhin 1994)
    nickel = lum / (6.45e43 * np.exp(-rise / 8.8) + 1.45e43 * np.exp(-rise / 111.3))
    kappa = 0.1 if f.model == "ia" else 0.07
    ejecta = (rise * 86400) ** 2 * 13.8 * 3e10 * 1e9 / (2 * kappa) / 1.989e33
    limit = min(ejecta, 1.4) if f.model == "ia" else ejecta
    return {"peak_abs_mag": round(float(peak), 2), "nickel": round(float(nickel), 3), "ejecta": round(float(ejecta), 2),
            "possible": bool(nickel <= limit)}
