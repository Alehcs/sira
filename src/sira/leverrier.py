import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

from . import agents, catalogs, dsl, photometry, scoring
from .fetch import client
from .firewall import as_of, blind
from .live import BANDS, _at, assemble, measure, physics
from .models import fit, phot

LEAPS = {
    "hidden": "a hidden component: something unseen that adds to, magnifies or blocks the light",
    "new": "a new physical model: a mechanism outside the lab's list of hypotheses",
    "instrument": "the instrument: calibration, template or subtraction problems that would mimic this behaviour",
}
TAIL = 0.01  # a PIT this far out counts as a miss
SURPRISE_P = 0.01  # misses this improbable under a calibrated forecast mean the hypotheses are failing
DECISIVE = math.log(20)  # e >= 20 rejects the rival at the 5% level (Ville's inequality); below, the lab abstains
NULL_SHARE = 0.1


def surprised(pits: list[float]) -> dict:
    n, misses = len(pits), sum(p < TAIL or p > 1 - TAIL for p in pits)
    p = float(stats.binom.sf(misses - 1, n, 2 * TAIL)) if n else 1.0
    return {"n": n, "misses": misses, "p_value": p, "surprised": n >= 3 and p < SURPRISE_P}


def _score(parts: list, row: dict) -> float:
    if row["kind"] == "det":
        return scoring.mix_log_score(row["flux"], row["flux_err"], parts)
    return scoring.mix_log_score_limit(photometry.flux(row["mag"], 0)[0], parts)


def verdict(new: callable, old: callable, rows: list[dict]) -> dict:
    # log e-value of the new hypothesis against the old, earned only on data neither saw
    log_e = sum(_score(new(r), r) - _score(old(r), r) for r in rows)
    word = "neptune" if log_e >= DECISIVE else "vulcan" if log_e <= -DECISIVE else "abstain"
    return {"n": len(rows), "log10_e": round(log_e / math.log(10), 2), "verdict": word}


def propose(llm, leap: str, case: dict, failed: dict, misses: list[dict]) -> tuple[dict, dict]:
    task = ("You are Le Verrier. The lab's hypotheses were fitted to this transient and their sealed forecasts "
            "failed on the measurements listed. As Le Verrier found Neptune in the errors of Uranus, propose one "
            f"new explanation of this kind: {LEAPS[leap]}. Build it from these pieces, which the lab's code will fit "
            f"to the data (one to three pieces): {json.dumps(dsl.PRIMITIVES)}. Say what your model predicts that the "
            'failed hypotheses do not. JSON: {"name": "a few words", "idea": "two sentences", '
            '"components": [{"type": "piece"}], "predicts": "one sentence"}')
    payload = {"case": case, "failed_hypotheses": failed, "misses": misses}
    data, event = agents.call(llm, "leverrier", task, payload, case["case"])
    parts = data.get("components") if isinstance(data.get("components"), list) else []
    out = {"leap": leap, "name": str(data.get("name", ""))[:80], "idea": str(data.get("idea", ""))[:400],
           "components": [{"type": str(c.get("type"))} for c in parts if isinstance(c, dict)][: dsl.MAX_PARTS],
           "predicts": str(data.get("predicts", ""))[:300]}
    return out, event | {"leap": leap, "decision": f"proposes {out['name'] or 'nothing'}", "why": out["idea"][:200]}


def _rows(obj: dict, start: float, stop: float) -> list[dict]:
    return [r for r in obj["photometry"] if r["band"] in BANDS and start < r["mjd"] <= stop
            and (r["kind"] != "det" or r["flux"] > 0)]


def case(root: Path, oid: str, llm, gap: int = 10, window: int = 40, pool=None) -> dict:
    # replay as the lab lives: bet every few days with the usual hypotheses, call Le Verrier at the first surprise
    root = Path(root)
    obj = json.loads((root / "objects" / f"{oid}.json").read_text())
    ebv = catalogs.mw_ebv(client(), obj["ra"], obj["dec"])
    dets = sorted(r["mjd"] for r in obj["photometry"] if r["kind"] == "det" and r["flux"] > 0)
    report = {"oid": oid, "checks": [], "events": []}
    t = dets[0] + gap
    while t + gap <= dets[-1]:
        first = physics(as_of(obj, t), ebv, days=tuple(range(1, gap + 1)))
        if first:
            sealed = assemble(first, first["weights"], as_of(obj, t))["forecasts"]
            seen = _rows(obj, t, t + gap)
            pits = [measure(_at(sealed, r["mjd"], r["band"]), "det", r["flux"], r["flux_err"])["pit"]
                    for r in seen if r["kind"] == "det"]
            check = {"t": round(t, 2), "weights": first["weights"], "surprise": surprised(pits)}
            report["checks"].append(check)
            if check["surprise"]["surprised"]:
                return report | _leap(obj, ebv, llm, t + gap, first, sealed, seen, window, pool, report)
        t += gap
    return report


def _leap(obj, ebv, llm, now, first, sealed, seen, window, pool, report) -> dict:
    view = as_of(obj, now)
    old = physics(view, ebv, days=tuple(range(1, window + 1)))
    if not old:
        return {"error": "the old hypotheses could not be refitted"}
    old_grid = assemble(old, old["weights"], view)["forecasts"]
    later = _rows(obj, now, now + window)
    misses = []
    for r in seen:
        if r["kind"] == "det":
            mean, spread = scoring.mix_moments(_at(sealed, r["mjd"], r["band"]))
            misses.append({"day": round(r["mjd"] - now, 2), "band": r["band"][-1], "observed": round(r["flux"], 1),
                           "forecast": round(mean, 1), "spread": round(spread, 1)})
    failed = {k: round(v, 3) for k, v in first["weights"].items()}
    mapper = pool.map if pool else map
    blind_case = blind(view)
    results = list(mapper(lambda leap: propose(llm, leap, blind_case, failed, misses), list(LEAPS)))
    ph = phot(view)
    null = fit("null", ph)
    old_at = lambda r: _at(old_grid, r["mjd"], r["band"])
    out = {"now": round(now, 2), "future_points": len(later), "proposals": []}
    for proposal, event in results:
        report["events"].append(event)
        entry = dict(proposal)
        try:
            f = dsl.fit_spec({"components": proposal["components"]}, ph, proposal["name"] or proposal["leap"])
        except ValueError as e:
            out["proposals"].append(entry | {"fit": f"not fitted: {e}"})
            continue
        if f is None:
            out["proposals"].append(entry | {"fit": "not fitted: too little data"})
            continue

        def new_at(r, f=f):
            mu, sd = f.predict([r["mjd"]], [r["band"]])
            nm, ns = null.predict([r["mjd"]], [r["band"]])
            if not (np.isfinite(mu[0]) and np.isfinite(sd[0])):
                return [["null", 1.0, float(nm[0]), float(ns[0])]]
            return [["new", 1 - NULL_SHARE, float(mu[0]), float(sd[0])],
                    ["null", NULL_SHARE, float(nm[0]), float(ns[0])]]

        out["proposals"].append(entry | {
            "fit": {"chi2_per_point": round(f.chi2 / max(f.ndof, 1), 2), "params": {k: round(v, 3) for k, v in f.params.items()}},
            "against_old": verdict(new_at, old_at, later)})
    judged = [p for p in out["proposals"] if "against_old" in p]
    if judged:
        best = max(judged, key=lambda p: p["against_old"]["log10_e"])
        runner = max((p["against_old"]["log10_e"] for p in judged if p is not best), default=None)
        out["best"] = {"leap": best["leap"], "name": best["name"], "verdict": best["against_old"]["verdict"],
                       "log10_e": best["against_old"]["log10_e"],
                       "margin_log10_e": round(best["against_old"]["log10_e"] - runner, 2) if runner is not None else None}
    return out
