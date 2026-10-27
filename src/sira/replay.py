import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from astropy.time import Time

from . import agents, catalogs, photometry
from . import team as lab
from .fetch import client
from .firewall import as_of
from .ledger import Ledger
from .leverrier import judge, watch
from .live import BANDS, DAYS, assemble, physics, resolve, seen
from .probe import coarse
from .snapshot import code_version

CHECKS = 6  # checkpoints per case
CLASSES = ("ia", "ii", "ibc", "tde", "other")


def iso(mjd: float) -> str:
    return Time(mjd, format="mjd").to_datetime().replace(microsecond=0).isoformat() + "+00:00"


def checkpoints(obj: dict, gap: int = len(DAYS), n: int = CHECKS) -> list[float]:
    # the lab meets an object once it has five points, as a lookout would, and bets every few days
    dets = sorted(r["mjd"] for r in obj["photometry"] if r["kind"] == "det" and r["flux"] > 0 and r["band"] in BANDS)
    if len(dets) < 6:
        return []
    start = dets[4] + photometry.LATENCY  # when the fifth point is actually in hand
    return [round(start + k * gap, 4) for k in range(n) if start + (k + 1) * gap <= dets[-1]]


def klass(truth_type: str) -> str:
    return {"ia": "ia", "ii": "ii", "stripped": "ibc", "tde": "tde"}.get(coarse(truth_type), "other")


def pick(root: Path, split: str, per: int) -> list[str]:
    manifest = json.loads((Path(root) / "manifest.json").read_text())
    out = []
    for category in ("ia", "cc", "rare", "microlensing"):
        rows = sorted((o for o in manifest["objects"] if o["category"] == category and o["split"] == split),
                      key=lambda o: hashlib.sha256(o["oid"].encode()).hexdigest())
        out += [o["oid"] for o in rows if checkpoints(json.loads((Path(root) / o["file"]).read_text()))][:per]
    return out


def _b2_grid(points: dict, view: dict, t: np.ndarray, band: np.ndarray) -> list[dict]:
    dets = [r for r in view["photometry"] if r["kind"] == "det" and r["flux"] > 0]
    grid = []
    for when, b in zip(t, band):
        day = int(round(when - view["as_of"]))
        if (b, day) in points:
            mu, sd = points[(b, day)]
        else:
            # a point the model left out falls back on persistence, with wide doubt
            own = [r for r in dets if r["band"] == b] or dets
            mu = max(own, key=lambda r: r["mjd"])["flux"]
            sd = 0.5 * abs(mu) + 1
        grid.append({"mjd": round(float(when), 4), "band": str(b), "parts": [["llm", 1.0, round(mu, 2), round(sd, 2)]]})
    return grid


def case(root: Path, oid: str, out: Path, llm, gap: int = len(DAYS), n: int = CHECKS) -> dict:
    root, c = Path(root), client()
    obj = json.loads((root / "objects" / f"{oid}.json").read_text())
    look = lambda o, t: as_of(obj, t)
    book = Ledger(Path(out) / oid)
    times = checkpoints(obj, gap, n)
    ebv = catalogs.mw_ebv(c, obj["ra"], obj["dec"])
    with ThreadPoolExecutor(6) as pool:
        readings, events = lab.eyes(llm, c, {oid: look(oid, times[0])}, pool) if times else ({}, [])
        for e in events:
            book.append("event", e, now=iso(times[0]))
        for t in times:
            when = iso(t)
            seals = {e["payload"]["bet"]: e["payload"]["made_at"] for e in book.entries() if e["kind"] == "bet"}
            resolve(book, c, t, look=look, seals=seals, when=when)
            judge(book, t, when=when)
            watch(book, c, llm, t, pool, f"{t:.2f}", look=look, when=when)
            view = look(oid, t)
            sira, events = lab.investigate(llm, view, ebv, pool, [lab.SENIOR_PER_NIGHT], readings.get(oid))
            for e in events:
                book.append("event", e | {"object": oid}, now=when)
            b2, event = agents.llm_only(llm, lab.case_of(view), DAYS, BANDS)
            book.append("event", event | {"object": oid}, now=when)
            if sira is None:
                # the team dropped it; the physics bet stands in, so every forecaster faces the same data
                phys = physics(view, ebv)
                if phys is None:
                    continue
                sira = assemble(phys, phys["weights"], view)
                sira["baselines"]["b1"] = sira["forecasts"]
                sira["dropped"] = True
            t_grid = np.array([f["mjd"] for f in sira["forecasts"]])
            b_grid = np.array([f["band"] for f in sira["forecasts"]])
            sira["baselines"]["b2"] = _b2_grid(b2["points"], view, t_grid, b_grid)
            book.append("bet", {"bet": f"{oid}-{t:.2f}", "object": oid, "model": "v1", "made_at": t,
                                "b2_classes": b2["classes"], "seen": seen(view)} | sira, now=when)
        if times:
            end = times[-1] + gap + 1
            seals = {e["payload"]["bet"]: e["payload"]["made_at"] for e in book.entries() if e["kind"] == "bet"}
            resolve(book, c, end, look=look, seals=seals, when=iso(end))
            judge(book, end + 10, when=iso(end))
    return {"oid": oid, "checkpoints": len(times), "entries": len(book.entries())}


def run(root: Path, oids: list[str], out: Path, llm, workers: int = 4) -> list[dict]:
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda oid: case(root, oid, out, llm), oids))


def _boot(diffs: dict[str, list[float]], seed: int = 0, draws: int = 2000) -> list[float]:
    # resample whole bets, since the scores within one bet move together
    groups = [np.array(v) for v in diffs.values() if v]
    rng, means = np.random.default_rng(seed), []
    for _ in range(draws):
        pick_ = rng.integers(0, len(groups), len(groups))
        means.append(np.concatenate([groups[i] for i in pick_]).mean())
    return [round(float(x), 3) for x in np.percentile(means, [2.5, 97.5])]


def report(root: Path, out: Path) -> dict:
    truth = json.loads((Path(root) / "truth.json").read_text())
    names = ("sira", "b0", "b1", "b2")
    logs = {k: [] for k in names}
    crps = {k: [] for k in names}
    pits = {k: [] for k in names}
    paired = {k: {} for k in names[1:]}
    loss = {"sira": [], "b1": [], "b2": []}
    counts, cost = {"bets": 0, "dropped": 0, "surprises": 0, "leap_bets": 0}, 0.0
    verdicts = []
    for path in sorted(Path(out).glob("*/ledger.jsonl")):
        entries = Ledger(path.parent).entries()
        bets = {e["payload"]["bet"]: e["payload"] for e in entries if e["kind"] == "bet"}
        for e in entries:
            p = e["payload"]
            cost += p.get("cost_usd", 0.0) if e["kind"] == "event" else 0.0
            if e["kind"] == "surprise":
                counts["surprises"] += 1
            elif e["kind"] == "verdict":
                verdicts.append({"object": p["object"], "verdict": p["verdict"], "log10_e": p["log10_e"]})
            elif e["kind"] == "bet" and p.get("model") == "leverrier":
                counts["leap_bets"] += 1
            elif e["kind"] == "bet":
                counts["bets"] += 1
                counts["dropped"] += bool(p.get("dropped"))
                true = klass(truth[p["object"]]["type"])
                weights = {("other" if k == "null" else k): v for k, v in p["weights"].items()}
                b1 = p["baselines"]["b1"][0]["parts"]
                b1_weights = {("other" if q[0] == "null" else q[0]): q[1] for q in b1}
                for name, w in (("sira", weights), ("b1", b1_weights), ("b2", p.get("b2_classes", {}))):
                    loss[name].append(-math.log(max(w.get(true, 0.0) / (sum(w.values()) or 1), 1e-3)))
            elif e["kind"] == "outcome" and bets.get(p["bet"], {}).get("model") != "leverrier":
                rivals = p.get("baselines", {})
                if not all(k in rivals for k in names[1:]):
                    continue
                for name, score in [("sira", p)] + [(k, rivals[k]) for k in names[1:]]:
                    logs[name].append(score["log_score"])
                    if "crps" in score:
                        crps[name].append(score["crps"])
                    if "pit" in score:
                        pits[name].append(score["pit"])
                for k in names[1:]:
                    paired[k].setdefault(p["bet"], []).append(p["log_score"] - rivals[k]["log_score"])
    summary = {"code": code_version(), "cases": len(list(Path(out).glob("*/ledger.jsonl"))), "outcomes": len(logs["sira"]), **counts,
               "cost_usd": round(cost, 2), "verdicts": verdicts}
    for name in names:
        pit = np.array(pits[name])
        summary[name] = {"log_score": round(float(np.mean(logs[name])), 3) if logs[name] else None,
                         "crps": round(float(np.mean(crps[name])), 2) if crps[name] else None,
                         "coverage_90": round(float(np.mean(np.abs(pit - 0.5) <= 0.45)), 3) if pit.size else None,
                         "class_log_loss": round(float(np.mean(loss[name])), 3) if loss.get(name) else None}
    summary["sira_minus"] = {k: {"log_score": round(float(np.mean(np.concatenate([np.array(v) for v in paired[k].values()]))), 3)
                                 if paired[k] else None, "ci95": _boot(paired[k]) if paired[k] else None}
                             for k in names[1:]}
    return summary
