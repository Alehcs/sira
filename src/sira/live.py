import math
from pathlib import Path

import numpy as np
from astropy.time import Time
from scipy import stats

from . import alerce, baselines, catalogs, photometry, scoring
from .decide import decide, eig
from .fetch import client
from .firewall import as_of
from .ledger import Ledger, mjd, upgrade, utcnow
from .models import budget, fit, phot

HYPOTHESES = ("ia", "ii", "ibc", "tde")
# share of each class among bright supernova candidates (Perley et al. 2020, ZTF Bright Transient Survey), rounded
PRIORS = {"ia": 0.70, "ii": 0.20, "ibc": 0.08, "tde": 0.02}
TEMPLATES_WITH_T0 = ("ia", "ii", "ibc", "iin")
NULL_WEIGHT = 0.1  # "none of the above" always keeps this share of every forecast
DAYS = (1, 2, 3, 4, 5)
BANDS = ("ztfg", "ztfr")
RULE = ("Every ZTF g or r measurement taken after this bet was sealed, up to one day past its last forecast, "
        "is scored against the forecast, interpolated linearly between days. The question is settled by the first "
        "r measurement within a day of its time; a limit above the reference leaves it void.")
RECENT = 20 / 24  # an object bet on within this many days waits for the next night
QUESTIONS = ("question", "risky")  # the standard question and the one the director picks


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


def _summary(f, as_of: float) -> dict:
    # what a theorist may see: fit quality and physics, with times relative to now
    keep = {"ia": ("z", "x1", "c"), "ii": ("z",), "ibc": ("z",), "tde": ("T", "t0")}
    out = {"chi2_per_point": round(f.chi2 / max(f.ndof, 1), 2),
           "params": {k: round(v, 4) for k, v in f.params.items() if k in keep.get(f.model, ())}}
    peak = f.params.get("t0") if f.model in TEMPLATES_WITH_T0 else f.params.get("t_peak")
    if peak is not None:
        out["peak_day"] = round(peak - as_of, 1)
    b = budget(f)
    if b:
        out |= {"peak_abs_mag": b["peak_abs_mag"], "nickel_msun": b["nickel"]}
    return out


def physics(view: dict, ebv: float, days: tuple = DAYS) -> dict | None:
    ph = phot(view)
    if len(ph) < 5:
        return None
    t0 = view["as_of"]
    t = np.array([t0 + d for d in days for _ in BANDS])
    band = np.array([b for _ in days for b in BANDS])
    fits, killed, preds = {}, {}, {}
    for kind in HYPOTHESES:
        f = fit(kind, ph, ebv)
        b = budget(f) if f else None
        if b and not b["possible"]:
            killed[kind] = f"needs {b['nickel']} solar masses of nickel in {b['ejecta']} of ejecta"
            continue
        if f is None:
            continue
        mu, sd = f.predict(t, band)
        if np.all(np.isfinite(mu)) and np.all(np.isfinite(sd)):
            fits[kind], preds[kind] = f, (mu, sd)
        else:
            killed[kind] = "its forecast was not finite"
    if not fits:
        return None
    bic = {k: f.chi2 + len(f.x) * math.log(len(ph)) for k, f in fits.items()}
    # the data's verdict times how common each class is among bright transients
    raw = {k: PRIORS[k] * math.exp(-(v - min(bic.values())) / 2) for k, v in bic.items()}
    total = sum(raw.values())
    weights = {k: (1 - NULL_WEIGHT) * v / total for k, v in raw.items() if v / total > 1e-3}
    weights["null"] = NULL_WEIGHT
    preds = {k: preds[k] for k in weights if k != "null"} | {"null": fit("null", ph).predict(t, band)}
    # every hypothesis still standing gets a voice, however small its weight
    return {"ph": ph, "t": t, "band": band, "preds": preds, "weights": weights, "killed": killed,
            "summaries": {k: _summary(f, t0) | {"weight": round((1 - NULL_WEIGHT) * raw[k] / total, 4)}
                          for k, f in fits.items()}}


def chance(parts: list, reference: float, direction: str) -> float:
    w = sum(p[1] for p in parts)
    above = sum(p[1] * stats.norm.sf(reference, p[2], max(p[3], 1e-6)) for p in parts) / w
    return min(max(float(above if direction == "above" else 1 - above), 0.001), 0.999)


def assemble(phys: dict, weights: dict, view: dict) -> dict:
    t, band, preds, t0 = phys["t"], phys["band"], phys["preds"], view["as_of"]
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items() if k in preds}
    err = float(np.median(phys["ph"].err))
    forecasts = []
    for i in range(len(t)):
        parts = [[k, round(weights[k], 4), round(float(preds[k][0][i]), 2), round(float(preds[k][1][i]), 2)]
                 for k in weights]
        forecasts.append({"mjd": round(float(t[i]), 4), "band": str(band[i]), "parts": parts,
                          "eig": round(eig(parts, err), 3)})
    # B0, climatology, is sealed beside SIRA and graded by the same rule
    rival = [{"mjd": f["mjd"], "band": f["band"], "parts": p} for f, p in zip(forecasts, baselines.b0(view, t, band))]
    r = [x for x in view["photometry"] if x["kind"] == "det" and x["band"] == "ztfr" and x["flux"] > 0]
    question = None
    if r:
        last = max(r, key=lambda x: x["mjd"])["flux"]
        at = min((f for f in forecasts if f["band"] == "ztfr"), key=lambda f: abs(f["mjd"] - (t0 + 3)))
        question = {"text": "Brighter in r three days from now than at its last r detection?", "band": "ztfr",
                    "mjd": at["mjd"], "reference": round(last, 2), "direction": "above",
                    "p_yes": round(chance(at["parts"], last, "above"), 3)}
    return {"n_points": len(phys["ph"]), "weights": {k: round(v, 4) for k, v in weights.items()},
            "killed": phys["killed"], "forecasts": forecasts, "question": question,
            "decision": decide(forecasts, weights, t0), "baselines": {"b0": rival}}


def forecast(view: dict, ebv: float) -> dict | None:
    phys = physics(view, ebv)
    return assemble(phys, phys["weights"], view) if phys else None


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


def measure(parts: list, kind: str, value: float, err: float = 0.0) -> dict:
    if kind == "det":
        mean, sd = scoring.mix_moments(parts)
        return {"flux": value, "flux_err": err, "log_score": round(scoring.mix_log_score(value, err, parts), 4),
                "pit": round(scoring.mix_pit(value, err, parts), 4),
                "crps": round(float(scoring.crps(value, mean, scoring.spread(sd, err))), 3)}
    return {"limit": value, "log_score": round(scoring.mix_log_score_limit(value, parts), 4)}


def settle(question: dict, outcomes: list[dict]) -> dict:
    near = [o for o in outcomes if o["band"] == question["band"] and abs(o["mjd"] - question["mjd"]) <= 1]
    first = min(near, key=lambda o: o["mjd"]) if near else None
    above = question.get("direction", "above") == "above"
    if first and first["kind"] == "det":
        yes = (first["flux"] > question["reference"]) == above
    elif first and first["limit"] < question["reference"]:
        yes = not above  # a limit below the reference rules out brighter
    else:
        return {"void": True}
    p = question["p_yes"]
    return {"mjd": first["mjd"], "yes": bool(yes), "p_yes": p, "log_score": round(math.log(p if yes else 1 - p), 4)}


def resolve(ledger: Ledger, c, now: float) -> list[dict]:
    entries = ledger.entries()
    seals = _seals(entries)
    done = {(e["payload"]["bet"], e["payload"]["mjd"], e["payload"]["band"]) for e in entries if e["kind"] == "outcome"}
    answered = {(e["payload"]["bet"], e["payload"].get("which", "question")) for e in entries if e["kind"] == "answer"}
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
            # rounded first, so anyone can recompute the score from the ledger alone
            if r["kind"] == "det":
                args = ("det", round(r["flux"], 2), round(r["flux_err"], 2))
            else:
                args = ("limit", round(photometry.flux(r["mag"], 0)[0], 2))
            score = measure(parts, *args)
            rivals = {name: measure(_at(grid, r["mjd"], r["band"]), *args)
                      for name, grid in bet.get("baselines", {}).items()}
            if rivals:
                score["baselines"] = rivals
            new.append(ledger.append("outcome", {"bet": bet["bet"], "object": bet["object"], "mjd": r["mjd"],
                                                 "band": r["band"], "kind": r["kind"]} | score))
        for which in QUESTIONS:
            q = bet.get(which)
            if q and (bet["bet"], which) not in answered and now > q["mjd"] + 1.5:
                mine = [e["payload"] for e in ledger.entries()
                        if e["kind"] == "outcome" and e["payload"]["bet"] == bet["bet"]]
                new.append(ledger.append("answer", {"bet": bet["bet"], "object": bet["object"], "which": which}
                                         | settle(q, mine)))
    return new


def run(root: Path, n: int = 15, team: bool = False, night_usd: float = 4.0) -> dict:
    c, ledger, now = client(), Ledger(root), now_mjd()
    resolved = resolve(ledger, c, now)
    recent = {e["payload"]["object"] for e in ledger.entries()
              if e["kind"] == "bet" and e["payload"]["made_at"] > now - RECENT}
    candidates = [o for o in active(c, now, 50) if o not in recent]
    made, skipped, spent = [], [], 0.0
    stamp = utcnow()[:16].replace("-", "").replace(":", "")
    head = {"made_at": round(now, 5), "role": "forecaster", "rule": RULE}
    from .config import KEYS
    if team and not all(KEYS.values()):
        # without keys the night still gets its physics-only bets
        team = False
        skipped.append("team unavailable: no API keys, physics only tonight")
    if not team:
        for oid in candidates[:n]:
            try:
                obj = observe(c, oid, now)
                result = forecast(as_of(obj, now), catalogs.mw_ebv(c, obj["ra"], obj["dec"]))
            except Exception as e:
                skipped.append(f"{oid}: {type(e).__name__}")
                continue
            if result is None:
                skipped.append(f"{oid}: too little data")
                continue
            made.append(ledger.append("bet", {"bet": f"{oid}-{stamp}", "object": oid, "model": "v0", "cost_usd": 0.0}
                                      | head | result))
    else:
        from concurrent.futures import ThreadPoolExecutor

        from . import team as lab
        from .llm import LLM

        llm, views, seniors = LLM(), {}, [lab.SENIOR_PER_NIGHT]
        for oid in candidates[:40]:
            try:
                views[oid] = as_of(observe(c, oid, now), now)
            except Exception as e:
                skipped.append(f"{oid}: {type(e).__name__}")
        with ThreadPoolExecutor(8) as pool:
            readings, events = lab.eyes(llm, c, views, pool)
            picked, more = lab.triage(llm, views, n, pool, readings)
            for e in events + more:
                ledger.append("event", e)
                spent += e["cost_usd"]
            for oid in picked:
                if spent >= night_usd:
                    skipped.append(f"{oid}: night budget spent")
                    continue
                view = views[oid]
                try:
                    result, events = lab.investigate(llm, view, catalogs.mw_ebv(c, view["ra"], view["dec"]), pool, seniors,
                                                     readings.get(oid))
                except Exception as e:
                    skipped.append(f"{oid}: {type(e).__name__}")
                    continue
                for e in events:
                    ledger.append("event", e | {"object": oid})
                    spent += e["cost_usd"]
                if result is None:
                    skipped.append(f"{oid}: the team passed")
                    continue
                made.append(ledger.append("bet", {"bet": f"{oid}-{stamp}", "object": oid, "model": "v1",
                                                  "cost_usd": result["team"]["cost_usd"]} | head | result))
    anchor = ledger.anchor(c)
    upgrade(root)
    return {"resolved": len(resolved), "bets": len(made), "skipped": skipped, "spent_usd": round(spent, 4),
            "anchor": anchor["payload"] if anchor else None}
