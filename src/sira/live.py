import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from astropy.time import Time
from scipy import stats

from . import alerce, catalogs, photometry, scoring
from .fetch import client
from .firewall import as_of
from .ledger import Ledger, mjd, upgrade
from .models import budget, fit, phot

HYPOTHESES = ("ia", "ii", "ibc", "tde")
NULL_WEIGHT = 0.1  # "none of the above" always keeps this share of every forecast
DAYS = (1, 2, 3, 4, 5)
BANDS = ("ztfg", "ztfr")
RULE = ("Every ZTF g or r measurement taken after this bet was sealed, up to one day past its last forecast, "
        "is scored against the forecast, interpolated linearly between days. The question is settled by the first "
        "r measurement within a day of its time.")


def now_mjd() -> float:
    return float(Time.now().mjd)


def active(c, now: float, n: int = 15) -> list[str]:
    # young transients the stamp classifier calls supernovae, detected in the last three nights
    params = [("classifier", "stamp_classifier"), ("class", "SN"), ("probability", 0.5),
              ("firstmjd", now - 30), ("firstmjd", now), ("lastmjd", now - 3), ("lastmjd", now),
              ("ndet", 5), ("ndet", 1000), ("page_size", 50), ("order_by", "lastmjd"), ("order_mode", "DESC")]
    items = sorted(alerce.objects(c, params, fresh=True), key=lambda i: -i["ndet"])
    return [i["oid"] for i in items[:n]]


def observe(c, oid: str, now: float) -> dict:
    lc = alerce.lightcurve(c, oid, fresh=True)
    rows = photometry.from_alerce(lc)
    for r in rows:
        # it is in hand now, so it was available now at the latest
        r["available_at"] = min(r["available_at"], now)
    dets = [d for d in lc.get("detections", []) if d.get("ra") is not None]
    ra = float(np.mean([d["ra"] for d in dets])) if dets else None
    dec = float(np.mean([d["dec"] for d in dets])) if dets else None
    return {"oid": oid, "survey": "ztf", "ra": ra, "dec": dec, "photometry": rows}


def forecast(view: dict, ebv: float) -> dict | None:
    ph = phot(view)
    if len(ph) < 5:
        return None
    fits, killed = {}, {}
    for kind in HYPOTHESES:
        f = fit(kind, ph, ebv)
        b = budget(f) if f else None
        if b and not b["possible"]:
            killed[kind] = f"needs {b['nickel']} solar masses of nickel in {b['ejecta']} of ejecta"
        elif f:
            fits[kind] = f
    if not fits:
        return None
    bic = {k: f.chi2 + len(f.x) * math.log(len(ph)) for k, f in fits.items()}
    raw = {k: math.exp(-(v - min(bic.values())) / 2) for k, v in bic.items()}
    weights = {k: (1 - NULL_WEIGHT) * v / sum(raw.values()) for k, v in raw.items() if v / sum(raw.values()) > 1e-3}
    weights["null"] = NULL_WEIGHT
    parts = {k: fits[k] if k in fits else fit("null", ph) for k in weights}
    t0 = view["as_of"]
    t = np.array([t0 + d for d in DAYS for _ in BANDS])
    band = np.array([b for _ in DAYS for b in BANDS])
    preds = {k: f.predict(t, band) for k, f in parts.items()}
    forecasts = [{"mjd": round(float(t[i]), 4), "band": str(band[i]),
                  "parts": [[k, round(weights[k], 4), round(float(mu[i]), 2), round(float(sd[i]), 2)]
                            for k, (mu, sd) in preds.items()]} for i in range(len(t))]
    r = [x for x in view["photometry"] if x["kind"] == "det" and x["band"] == "ztfr" and x["flux"] > 0]
    question = None
    if r:
        last = max(r, key=lambda x: x["mjd"])["flux"]
        at = min((f for f in forecasts if f["band"] == "ztfr"), key=lambda f: abs(f["mjd"] - (t0 + 3)))
        p = sum(w * stats.norm.sf(last, mu, max(sd, 1e-6)) for _, w, mu, sd in at["parts"]) / sum(weights.values())
        question = {"text": "Brighter in r three days from now than at its last r detection?", "band": "ztfr",
                    "mjd": at["mjd"], "reference": round(last, 2), "p_yes": round(float(p), 3)}
    return {"n_points": len(ph), "weights": {k: round(v, 4) for k, v in weights.items()},
            "killed": killed, "forecasts": forecasts, "question": question}


def _at(forecasts: list[dict], t: float, band: str) -> list | None:
    grid = [f for f in forecasts if f["band"] == band]
    if not grid:
        return None
    times = np.array([f["mjd"] for f in grid])
    i = int(np.clip(np.searchsorted(times, t), 1, len(grid) - 1))
    a, b = grid[i - 1], grid[i]
    x = float(np.clip((t - a["mjd"]) / (b["mjd"] - a["mjd"]), 0, 1))
    return [[pa[0], pa[1], pa[2] + x * (pb[2] - pa[2]), pa[3] + x * (pb[3] - pa[3])] for pa, pb in zip(a["parts"], b["parts"])]


def _seals(entries: list[dict]) -> dict[str, float]:
    anchors = [(e["payload"]["seq"], mjd(e["payload"]["tsa_time"])) for e in entries if e["kind"] == "anchor"]
    out = {}
    for e in entries:
        if e["kind"] == "bet":
            times = [when for seq, when in anchors if seq >= e["seq"]]
            if times:
                out[e["payload"]["bet"]] = min(times)
    return out


def resolve(ledger: Ledger, c, now: float) -> list[dict]:
    entries = ledger.entries()
    seals = _seals(entries)
    done = {(e["payload"]["bet"], e["payload"]["mjd"], e["payload"]["band"]) for e in entries if e["kind"] == "outcome"}
    answered = {e["payload"]["bet"] for e in entries if e["kind"] == "answer"}
    new = []
    for bet in (e["payload"] for e in entries if e["kind"] == "bet"):
        last_day = max(f["mjd"] for f in bet["forecasts"])
        sealed = seals.get(bet["bet"])
        # never score a bet that was not sealed, and stop once its window has closed
        if sealed is None or now > last_day + 3:
            continue
        rows = [r for r in observe(c, bet["object"], now)["photometry"]
                if r["band"] in BANDS and sealed < r["mjd"] <= last_day + 1]
        for r in rows:
            if (bet["bet"], r["mjd"], r["band"]) in done:
                continue
            parts = _at(bet["forecasts"], r["mjd"], r["band"])
            if r["kind"] == "det":
                mean, sd = scoring.mix_moments(parts)
                score = {"flux": round(r["flux"], 2), "flux_err": round(r["flux_err"], 2),
                         "log_score": round(scoring.mix_log_score(r["flux"], r["flux_err"], parts), 4),
                         "pit": round(scoring.mix_pit(r["flux"], r["flux_err"], parts), 4),
                         "crps": round(float(scoring.crps(r["flux"], mean, scoring.spread(sd, r["flux_err"]))), 3)}
            else:
                f_lim = photometry.flux(r["mag"], 0)[0]
                score = {"limit": round(f_lim, 2), "log_score": round(scoring.mix_log_score_limit(f_lim, parts), 4)}
            new.append(ledger.append("outcome", {"bet": bet["bet"], "object": bet["object"], "mjd": r["mjd"],
                                                 "band": r["band"], "kind": r["kind"]} | score))
        q = bet.get("question")
        if q and bet["bet"] not in answered:
            near = [r for r in rows if r["band"] == q["band"] and abs(r["mjd"] - q["mjd"]) <= 1]
            first = min(near, key=lambda r: r["mjd"]) if near else None
            if first and first["kind"] == "det":
                answer = first["flux"] > q["reference"]
            elif first and photometry.flux(first["mag"], 0)[0] < q["reference"]:
                answer = False  # a limit below the reference rules out brighter
            else:
                continue
            new.append(ledger.append("answer", {"bet": bet["bet"], "object": bet["object"], "mjd": first["mjd"],
                                                "yes": bool(answer), "p_yes": q["p_yes"],
                                                "log_score": round(math.log(q["p_yes"] if answer else 1 - q["p_yes"]), 4)}))
    return new


def run(root: Path, n: int = 15) -> dict:
    c, ledger, now = client(), Ledger(root), now_mjd()
    resolved = resolve(ledger, c, now)
    made, skipped = [], []
    day = (date(1858, 11, 17) + timedelta(days=now)).isoformat()
    for oid in active(c, now, n):
        try:
            obj = observe(c, oid, now)
            result = forecast(as_of(obj, now), catalogs.mw_ebv(c, obj["ra"], obj["dec"]))
        except Exception as e:
            skipped.append(f"{oid}: {type(e).__name__}")
            continue
        if result is None:
            skipped.append(f"{oid}: too little data")
            continue
        made.append(ledger.append("bet", {"bet": f"{oid}-{day}", "object": oid, "made_at": round(now, 5),
                                          "model": "v0", "role": "forecaster", "cost_usd": 0.0, "rule": RULE}
                                  | result))
    anchor = ledger.anchor(c)
    upgrade(root)
    return {"resolved": len(resolved), "bets": len(made), "skipped": skipped,
            "anchor": anchor["payload"] if anchor else None}
