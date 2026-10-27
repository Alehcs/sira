import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from astropy.cosmology import Planck18

from . import catalogs
from .fetch import client
from .firewall import as_of
from .models import fit, ia_distance, phot, z_from_mu
from .snapshot import code_version

BANDS = ("ztfg", "ztfr", "ztfi")
DECISIVE = 3.0  # the losing hypothesis must do this many times worse on the future


def _objects(root: Path, category: str) -> list[dict]:
    manifest = json.loads((root / "manifest.json").read_text())
    return [o for o in manifest["objects"] if o["category"] == category]


def _load(root: Path, oid: str) -> dict:
    return json.loads((root / "objects" / f"{oid}.json").read_text())


def _reddening(root: Path, oids: list[str]) -> dict[str, float]:
    out, c = {}, client()
    for oid in oids:
        obj = _load(root, oid)
        try:
            out[oid] = catalogs.mw_ebv(c, obj["ra"], obj["dec"])
        except Exception:
            out[oid] = 0.0
    return out


def _distance(job: tuple) -> tuple[str, dict | None]:
    root, oid, ebv = job
    return oid, ia_distance(phot(as_of(_load(root, oid), float("inf"))), ebv)


def at1(root: Path, workers: int = 6, splits: int = 200, seed: int = 0) -> dict:
    # F7: Ia light curves predict their host redshift; the same recipe on other types must miss badly
    root = Path(root)
    truth = json.loads((root / "truth.json").read_text())
    ia, cc = [o["oid"] for o in _objects(root, "ia")], [o["oid"] for o in _objects(root, "cc")]
    ebv = _reddening(root, ia + cc)
    with ProcessPoolExecutor(workers) as pool:
        dist = dict(pool.map(_distance, [(root, o, ebv[o]) for o in ia + cc]))
    fitted = lambda oids: [o for o in oids if dist[o] and truth[o]["redshift"]]
    good = lambda oids: [o for o in oids if dist[o]["good"]]
    result = {"all": _f7(fitted(ia), fitted(cc), dist, truth, splits, seed),
              "good_fits": _f7(good(fitted(ia)), good(fitted(cc)), dist, truth, splits, seed)}
    # the pass mark uses every fit, so the quality cuts can never be what makes it pass
    result["passes"] = result["all"]["ia"]["median_abs_err"] <= 0.10 and abs(result["all"]["control"]["median_bias"]) >= 0.30
    return result | {"code": code_version()}


def _f7(ia: list[str], cc: list[str], dist: dict, truth: dict, splits: int, seed: int) -> dict:
    mu = np.array([dist[o]["mu_no_m"] for o in ia])
    zt = np.array([truth[o]["redshift"] for o in ia])
    rng, errs = np.random.default_rng(seed), []
    for _ in range(splits):
        # calibrate the absolute magnitude on one half, predict the other half
        idx = rng.permutation(len(ia))
        cal, test = idx[: len(ia) // 2], idx[len(ia) // 2:]
        m = np.median(mu[cal] - Planck18.distmod(zt[cal]).value)
        zp = np.array([z_from_mu(v - m) for v in mu[test]])
        errs.append((zp - zt[test]) / zt[test])
    err = np.abs(np.concatenate(errs))
    m_all = np.median(mu - Planck18.distmod(zt).value)
    bias = np.array([z_from_mu(dist[o]["mu_no_m"] - m_all) / truth[o]["redshift"] - 1 for o in cc])
    return {
        "ia": {"n": len(ia), "median_abs_err": round(float(np.median(err)), 3),
               "within_10": round(float(np.mean(err < 0.1)), 3), "within_20": round(float(np.mean(err < 0.2)), 3),
               "over_30": round(float(np.mean(err > 0.3)), 3)},
        "control": {"n": len(cc), "median_bias": round(float(np.median(bias)), 3) if len(cc) else None,
                    "over_30": round(float(np.mean(np.abs(bias) > 0.3)), 3) if len(cc) else None},
    }


def _verdict(job: tuple) -> dict | None:
    root, oid, truth_kind, cut, ebv = job
    obj = _load(root, oid)
    past = phot(as_of(obj, cut))
    future = [r for r in obj["photometry"]
              if r["kind"] == "det" and r["flux"] > 0 and r["band"] in BANDS and r["mjd"] > cut]
    if len(past) < 5 or len(future) < 5:
        return None
    fits = {"lens": fit("lens", past), "ia": fit("ia", past, ebv)}
    if any(f is None for f in fits.values()):
        return None
    t = np.array([r["mjd"] for r in future])
    band = np.array([r["band"] for r in future])
    flux = np.array([r["flux"] for r in future])
    sigma = np.hypot([r["flux_err"] for r in future], 0.05 * flux)
    chi2 = {k: float(np.mean(((f.flux(f.x, t, band) - flux) / sigma) ** 2)) for k, f in fits.items()}
    winner = min(chi2, key=chi2.get)
    ratio = max(chi2.values()) / max(min(chi2.values()), 1e-9)
    return {"oid": oid, "truth": truth_kind, "winner": winner, "ratio": round(ratio, 2), "chi2": chi2,
            "n_past": len(past), "n_future": len(future), "verdict": winner if ratio >= DECISIVE else "abstain"}


def at2(root: Path, workers: int = 6) -> dict:
    # Neptune or Vulcan: rivals fitted on the past only, judged on the future they never saw
    root = Path(root)
    truth = json.loads((root / "truth.json").read_text())
    jobs = [("lens", o["oid"], truth[o["oid"]]["t0_mjd"]) for o in _objects(root, "microlensing")]
    jobs += [("ia", o["oid"], truth[o["oid"]]["peak_mjd"]) for o in _objects(root, "ia")]
    ebv = _reddening(root, [oid for _, oid, _ in jobs])
    with ProcessPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(_verdict, [(root, oid, kind, cut, ebv[oid]) for kind, oid, cut in jobs]) if r]
    sets = {}
    for kind in ("lens", "ia"):
        rs = [r for r in rows if r["truth"] == kind]
        decisive = [r for r in rs if r["verdict"] != "abstain"]
        sets[kind] = {"n": len(rs), "correct": sum(r["winner"] == kind for r in rs),
                      "decisive_right": sum(r["verdict"] == kind for r in decisive),
                      "decisive_wrong": sum(r["verdict"] != kind for r in decisive),
                      "abstain": len(rs) - len(decisive)}
    right = sum(s["decisive_right"] for s in sets.values())
    decided = right + sum(s["decisive_wrong"] for s in sets.values())
    accuracy = right / decided if decided else 0.0
    return {"sets": sets, "decisive_accuracy": round(accuracy, 3), "abstain_rate": round(1 - decided / len(rows), 3),
            "passes": accuracy >= 0.8, "code": code_version(), "rows": rows}
