import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from . import ledger, replay
from .archive import night_of
from .fetch import client
from .ledger import Ledger
from .live import _at, chance, measure
from .team import DOUBTED

RIVALS = ("sira", "b0", "b1", "b2")


def stamp(path: Path) -> dict:
    # a plan counts from the time FreeTSA signed its sha256, and Bitcoin later backs the same hash
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    tsr = path.with_name(path.name + ".tsr")
    tsr.write_bytes(ledger.rfc3161(client(), digest))
    ok, when = ledger.check_rfc3161(tsr, digest)
    if not ok:
        raise RuntimeError("the timestamp authority returned a receipt that does not verify")
    stamped = subprocess.run([ledger.OTS, "stamp", str(path)], capture_output=True, text=True).returncode == 0
    return {"sha256": digest, "tsa_time": when, "rfc3161": tsr.name, "ots": path.name + ".ots" if stamped else None}


def stamped(path: Path) -> dict:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ok, when = ledger.check_rfc3161(path.with_name(path.name + ".tsr"), digest)
    return {"sha256": digest, "valid": ok, "tsa_time": when,
            "ots": ledger.ots_state(path.with_name(path.name + ".ots"), digest)}


TEAM = ("llm_only", "theorist", "skeptic", "director", "senior", "forecaster", "lab")
SIZES = (1, 3, 5)
DRAWS = 10000


def _boot(values: list[float], seed: int = 0) -> list[float]:
    # whole cases are resampled, since the bets within one case move together
    x, rng = np.array(values), np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), (DRAWS, len(x)))].mean(axis=1)
    return [round(float(v), 3) for v in np.percentile(means, [2.5, 97.5])]


def _mean(xs) -> float | None:
    xs = list(xs)
    return round(float(np.mean(xs)), 3) if xs else None


def case_scores(path: Path, truth: dict) -> dict | None:
    # one replayed case, from its own ledger alone
    entries = Ledger(path).entries()
    bets = {e["payload"]["bet"]: e["payload"] for e in entries if e["kind"] == "bet"}
    out = {"logs": {k: [] for k in RIVALS}, "crps": {k: [] for k in RIVALS}, "pits": {k: [] for k in RIVALS},
           "ablations": {}, "class_loss": {"sira": [], "b1": [], "b2": []}, "senior": [], "cost_usd": 0.0,
           "bets": 0, "dropped": 0, "remembered": 0, "extra_skeptics_usd": 0.0, "senior_usd": 0.0,
           "surprises": 0, "verdicts": [], "partner": [], "questions": []}
    reviewed = {b for b, p in bets.items() if (p.get("director") or {}).get("senior")}
    for e in entries:
        p = e["payload"]
        if e["kind"] == "event":
            out["cost_usd"] += p.get("cost_usd") or 0.0
            if p.get("role") == "skeptic" and p.get("lens") != "physics":
                out["extra_skeptics_usd"] += p.get("cost_usd") or 0.0
            if p.get("role") == "senior":
                out["senior_usd"] += p.get("cost_usd") or 0.0
        elif e["kind"] == "surprise":
            out["surprises"] += 1
        elif e["kind"] == "verdict":
            out["verdicts"].append(p["verdict"])
        elif e["kind"] == "bet" and p.get("model") != "leverrier":
            out["bets"] += 1
            out["dropped"] += bool(p.get("dropped"))
            out["remembered"] += bool(p.get("remembered"))
            true = replay.klass(truth[p["object"]]["type"])
            b1 = replay._classes({q[0]: q[1] for q in p["baselines"]["b1"][0]["parts"]})
            for name, w in (("sira", replay._classes(p.get("classes") or p["weights"])), ("b1", b1),
                            ("b2", p.get("b2_classes", {}))):
                out["class_loss"][name].append(-math.log(max(w.get(true, 0.0) / (sum(w.values()) or 1), 1e-3)))
        elif e["kind"] == "outcome" and bets.get(p["bet"], {}).get("model") != "leverrier":
            rivals = p.get("baselines", {})
            if not all(k in rivals for k in RIVALS[1:]):
                continue
            for name, score in [("sira", p)] + [(k, rivals[k]) for k in RIVALS[1:]]:
                out["logs"][name].append(score["log_score"])
                if "crps" in score:
                    out["crps"][name].append(score["crps"])
                if "pit" in score:
                    out["pits"][name].append(score["pit"])
            bet = bets[p["bet"]]
            args = (p["flux"], p["flux_err"]) if p["kind"] == "det" else (p["limit"],)
            for name, parts in replay.variants(bet, p).items():
                out["ablations"].setdefault(name, []).append(p["log_score"] - measure(parts, p["kind"], *args)["log_score"])
            if p["bet"] in reviewed:
                plain = _unreviewed(bet, p)
                if plain:
                    out["senior"].append(p["log_score"] - measure(plain, p["kind"], *args)["log_score"])
            # the same physics pooled half and half with Muse's forecast, then with climatology instead
            llm = next((q for q in _at(bet["forecasts"], p["mjd"], p["band"]) if q[0] == "llm"), None)
            if llm is not None:
                physics = _at(bet["baselines"]["b1"], p["mjd"], p["band"])
                b0 = _at(bet["baselines"]["b0"], p["mjd"], p["band"])[0]
                out["partner"].append(measure(replay._pool(physics, llm, 0.5), p["kind"], *args)["log_score"]
                                      - measure(replay._pool(physics, b0, 0.5), p["kind"], *args)["log_score"])
        elif e["kind"] == "answer" and not p.get("void") and bets.get(p["bet"], {}).get("model") != "leverrier":
            # a settled question, with the chance each rival's sealed forecast gave the same yes
            bet = bets[p["bet"]]
            q = bet[p.get("which", "question")]
            row = {"object": p["object"], "yes": p["yes"], "sira": p["p_yes"]}
            for k in RIVALS[1:]:
                grid = bet.get("baselines", {}).get(k)
                row[k] = chance(_at(grid, q["mjd"], q["band"]), q["reference"], q.get("direction", "above")) if grid else None
            out["questions"].append(row)
    if not out["logs"]["sira"]:
        return None
    return out


def _unreviewed(bet: dict, o: dict) -> list | None:
    # the forecast the director's own pick would have sealed: physics, the physics skeptic's doubts, then the pool
    parts = _at(bet["forecasts"], o["mjd"], o["band"])
    llm = next((q for q in parts if q[0] == "llm"), None)
    if llm is None:
        return None
    plain = [list(q) for q in _at(bet["baselines"]["b1"], o["mjd"], o["band"])]
    doubted = {i["hypothesis"] for i in ((bet.get("skeptics") or {}).get("physics") or {}).get("implausible", [])}
    for q in plain:
        if q[0] in doubted and q[0] != "null":
            q[1] *= DOUBTED
    return replay._pool(plain, llm, llm[1])


def replays(root: Path, runs: dict[str, Path]) -> dict:
    truth = json.loads((Path(root) / "truth.json").read_text())
    per = {name: {p.parent.name: case_scores(p.parent, truth) for p in sorted(Path(d).glob("*/ledger.jsonl"))}
           for name, d in runs.items()}
    oids = sorted({o for cases in per.values() for o in cases})
    category = {o: replay.klass(truth[o]["type"]) for o in oids}
    rows, failed = [], []
    for oid in oids:
        got = [per[r].get(oid) for r in runs if per[r].get(oid)]
        if not got:
            failed.append(oid)
            continue
        diff = {k: _mean(np.mean(np.subtract(c["logs"]["sira"], c["logs"][k])) for c in got) for k in RIVALS[1:]}
        rows.append({"object": oid, "type": truth[oid]["type"], "class": category[oid], "runs": len(got),
                     "outcomes": sum(len(c["logs"]["sira"]) for c in got),
                     "sira_minus": diff} | {f"run_{r}": {k: _mean(np.subtract(per[r][oid]["logs"]["sira"], per[r][oid]["logs"][k]))
                                                     for k in RIVALS[1:]} for r in runs if per[r].get(oid)})
    every = [c for cases in per.values() for c in cases.values() if c]
    flat = lambda key, name: [x for c in every for x in c[key][name]]
    out = {"cases": len(rows), "failed": failed, "runs": {r: sum(bool(c) for c in per[r].values()) for r in runs},
           "outcomes": sum(len(c["logs"]["sira"]) for c in every), "bets": sum(c["bets"] for c in every),
           "cost_usd": round(sum(c["cost_usd"] for c in every), 2), "rows": rows}
    out["primary"] = {k: {"mean": _mean(r["sira_minus"][k] for r in rows), "ci95": _boot([r["sira_minus"][k] for r in rows]),
                          "cases_ahead": sum(r["sira_minus"][k] > 0 for r in rows)} for k in RIVALS[1:]}
    out["by_run"] = {r: {k: {"mean": _mean(x[f"run_{r}"][k] for x in rows if f"run_{r}" in x),
                             "ci95": _boot([x[f"run_{r}"][k] for x in rows if f"run_{r}" in x])} for k in RIVALS[1:]}
                     for r in runs}
    out["by_class"] = {}
    for cls in sorted(set(category.values())):
        sub = [r for r in rows if r["class"] == cls]
        out["by_class"][cls] = {k: {"cases": len(sub), "mean": _mean(r["sira_minus"][k] for r in sub),
                                    "cases_ahead": sum(r["sira_minus"][k] > 0 for r in sub)} for k in RIVALS[1:]}
    out["forecasters"] = {}
    for name in RIVALS:
        pit = np.array(flat("pits", name))
        out["forecasters"][name] = {"log_score": _mean(flat("logs", name)), "crps": _mean(flat("crps", name)),
                                    "coverage_90": _mean(np.abs(pit - 0.5) <= 0.45) if pit.size else None,
                                    "class_log_loss": _mean(flat("class_loss", name)) if name != "b0" else None}
    names = sorted({k for c in every for k in c["ablations"]})
    out["ablations"] = {k: {"sira_minus": _mean(x for c in every for x in c["ablations"].get(k, [])),
                            "ci95": _boot([np.mean(c["ablations"][k]) for c in every if c["ablations"].get(k)])}
                        for k in names}
    out["team"] = {"dropped": sum(c["dropped"] for c in every), "remembered": sum(c["remembered"] for c in every),
                   "surprises": sum(c["surprises"] for c in every),
                   "verdicts": {v: sum(c["verdicts"].count(v) for c in every) for v in ("neptune", "vulcan", "abstain")}}
    reviewed = [c for c in every if c["senior"]]
    out["team"]["skeptics"] = {"extra_usd_per_bet": round(sum(c["extra_skeptics_usd"] for c in every) / max(out["bets"], 1), 4),
                               "bets_dropped": out["team"]["dropped"], "objects_flagged_remembered": out["team"]["remembered"]}
    out["team"]["director"] = {"reviewed_cases": len(reviewed), "reviewed_outcomes": sum(len(c["senior"]) for c in reviewed),
                               "sira_minus_unreviewed": _mean(x for c in reviewed for x in c["senior"]),
                               "ci95": _boot([np.mean(c["senior"]) for c in reviewed]) if reviewed else None,
                               "senior_usd": round(sum(c["senior_usd"] for c in every), 2)}
    out["posthoc"] = posthoc(rows, per, runs, every)
    return out


def posthoc(rows: list[dict], per: dict, runs: dict, every: list[dict]) -> dict:
    # measured after the plan, so not pre-registered: Muse against climatology as the physics' partner, and the questions
    partner = []
    for r in rows:
        got = [per[run][r["object"]]["partner"] for run in runs if per[run].get(r["object"]) and per[run][r["object"]]["partner"]]
        if got:
            partner.append(float(np.mean([np.mean(g) for g in got])))
    asked = [q for c in every for q in c["questions"]]
    yes = np.array([q["yes"] for q in asked], float)
    rate = float(yes.mean()) if asked else 0.0
    scored = {}
    for k in RIVALS:
        p = np.array([q[k] for q in asked], float)
        scored[k] = {"right": _mean((p > 0.5) == (yes == 1)), "brier": _mean((p - yes) ** 2)}
    return {"muse_or_climatology_as_partner": {"cases": len(partner), "mean": _mean(partner), "ci95": _boot(partner),
                                               "cases_ahead": sum(x > 0 for x in partner)},
            "questions": {"answered": len(asked), "objects": len({q["object"] for q in asked}), "yes_rate": round(rate, 3),
                          "base_rate_brier": round(rate * (1 - rate), 3), "by_forecaster": scored}}


def readers(folder: Path) -> dict:
    # the stamp reader on 160 held-out candidates, each protocol recomputed from its own reads
    from . import reader

    runs = {}
    for path in sorted(Path(folder).glob("holdout-*.json")):
        data = json.loads(path.read_text())
        runs[data["protocol"]] = data
    out = {name: reader.metrics(d["rows"]) | {"model": d["model"], "code": d["code"], "usd_per_read": d["usd_per_read"]}
           for name, d in runs.items()}
    if {"v1", "v2"} <= runs.keys():
        # McNemar's exact test on the candidates exactly one protocol read right
        right = {name: {r["oid"]: r["label"] == r["truth"] for r in d["rows"]} for name, d in runs.items()}
        both = right["v1"].keys() & right["v2"].keys()
        gained = sum(right["v2"][o] and not right["v1"][o] for o in both)
        lost = sum(right["v1"][o] and not right["v2"][o] for o in both)
        n = gained + lost
        tail = sum(math.comb(n, i) for i in range(min(gained, lost) + 1)) / 2 ** n if n else 1.0
        out["v2_vs_v1"] = {"gained": gained, "lost": lost, "p": round(min(1.0, 2 * tail), 3)}
    return out


def leverriers(folder: Path, kinds: dict[str, list[str]]) -> dict:
    # k Le Verriers are the first k proposals; the lab keeps the lowest BIC on the past, and only its verdict counts
    rows = []
    for kind, oids in kinds.items():
        for oid in oids:
            path = Path(folder) / f"leverrier-{oid}.json"
            data = json.loads(path.read_text()) if path.exists() else None
            row = {"object": oid, "kind": kind, "replayed": bool(data and "checks" in data),
                   "surprised": bool(data and data.get("proposals") is not None)}
            for k in SIZES:
                asked = (data or {}).get("proposals", [])[:k]
                fitted = [q for q in asked if q.get("bic") is not None and q.get("components")]
                pick = min(fitted, key=lambda q: q["bic"]) if fitted else None
                row[str(k)] = {"usd": round(sum(q.get("cost_usd") or 0 for q in asked), 4),
                               "verdict": pick["against_old"]["verdict"] if pick else None,
                               "log10_e": pick["against_old"]["log10_e"] if pick else None,
                               "name": pick["name"] if pick else None}
            rows.append(row)
    sizes = {}
    for k in SIZES:
        usd = sum(r[str(k)]["usd"] for r in rows)
        right = sum(r[str(k)]["verdict"] == "neptune" for r in rows if r["kind"] == "microlensing")
        wrong = sum(r[str(k)]["verdict"] == "neptune" for r in rows if r["kind"] == "ia")
        sizes[k] = {"usd": round(usd, 2), "neptune_on_lenses": right, "neptune_on_ia": wrong,
                    "vulcan_on_lenses": sum(r[str(k)]["verdict"] == "vulcan" for r in rows if r["kind"] == "microlensing"),
                    "discoveries_per_usd": round(right / usd, 2) if usd else None}
    count = lambda kind, key: sum(r[key] for r in rows if r["kind"] == kind)
    return {"objects": {kind: {"n": len(oids), "replayed": count(kind, "replayed"), "surprised": count(kind, "surprised")}
                        for kind, oids in kinds.items()}, "sizes": sizes, "rows": rows}


def live(entries: list[dict], seq: int | None = None) -> dict:
    # the live record, the cost of an investigation and the lookouts' vote, from the public ledger up to a head
    entries = [e for e in entries if seq is None or e["seq"] <= seq]
    answers = [e["payload"] for e in entries if e["kind"] == "answer"]
    real = [a for a in answers if not a.get("void")]
    right = [a for a in real if (a["p_yes"] > 0.5 and a["yes"]) or (a["p_yes"] < 0.5 and not a["yes"])]
    record = {"answered": len(real), "void": len(answers) - len(real), "right": len(right),
              "brier": _mean((a["p_yes"] - a["yes"]) ** 2 for a in real), "log_score": _mean(a["log_score"] for a in real),
              "rows": [{"bet": a["bet"], "p_yes": a["p_yes"], "yes": a["yes"]} for a in real]}
    nights = {}
    for e in entries:
        p = e["payload"]
        if "round" in p or e["kind"] not in ("event", "bet"):
            continue
        n = nights.setdefault(night_of(e["time"]), {"usd": 0.0, "bets": 0, "team": False, "by_role": {}})
        if e["kind"] == "event":
            n["usd"] += p.get("cost_usd") or 0.0
            n["team"] |= p.get("role") in TEAM
            role = p.get("role") or "other"
            n["by_role"][role] = n["by_role"].get(role, 0.0) + (p.get("cost_usd") or 0.0)
        elif "-leap-" not in p["bet"]:
            n["bets"] += 1
    team = {k: v for k, v in nights.items() if v["team"] and v["bets"]}
    usd, bets = sum(v["usd"] for v in team.values()), sum(v["bets"] for v in team.values())
    roles = {}
    for v in team.values():
        for r, x in v["by_role"].items():
            roles[r] = roles.get(r, 0.0) + x
    cost = {"nights": len(team), "investigated": bets, "usd": round(usd, 2), "usd_per_investigation": round(usd / bets, 3) if bets else None,
            "by_role_per_investigation": {r: round(x / bets, 4) for r, x in sorted(roles.items())} if bets else {}}
    votes = {}
    for e in entries:
        p = e["payload"]
        if e["kind"] == "event" and p.get("role") == "lookout":
            votes.setdefault((p["object"], night_of(e["time"])), []).append(p)
    voted = [v for v in votes.values() if len(v) > 1]
    flipped = sum((2 * sum(x["decision"] == "investigate" for x in v) > len(v)) != (v[0]["decision"] == "investigate")
                  for v in voted)
    lookouts = {"looks": len(votes), "voted": len(voted), "vote_changed_decision": flipped,
                "extra_usd": round(sum(x.get("cost_usd") or 0 for v in voted for x in v[1:]), 3)}
    head = next((e["payload"] for e in reversed(entries) if e["kind"] == "anchor"), {})
    return {"head": {"seq": head.get("seq"), "hash": head.get("head"), "tsa_time": head.get("tsa_time")},
            "record": record, "cost": cost, "lookouts": lookouts}


ROLES = {"theorist": "theorists", "skeptic": "skeptics", "lookout": "lookouts", "llm_only": "Muse's own forecast",
         "senior": "senior (Wonder)", "leverrier": "Le Verrier (Wonder)", "reader": "stamp reader"}
INK, MUTED, HAIR, G, R, WARN, OK = "#10151b", "#4a5462", "#c9d0d8", "#0a7559", "#a35200", "#b01e44", "#0b6b74"


def figures(results: dict, out: Path) -> list[str]:
    import matplotlib
    import matplotlib.ticker

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": HAIR, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "sira", "svg.fonttype": "none"})
    out.mkdir(parents=True, exist_ok=True)
    made = []

    def save(fig, name):
        fig.tight_layout()
        for ext in ("svg", "png"):
            fig.savefig(out / f"{name}.{ext}", dpi=200, metadata={"Date": None} if ext == "svg" else None)
        plt.close(fig)
        made.append(name)

    test = results.get("test")
    if test and test["rows"]:
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        for i, (k, label) in enumerate((("b2", "Muse alone (B2)"), ("b1", "physics alone (B1)"))):
            xs = np.array([r["sira_minus"][k] for r in test["rows"]])
            y = i + (np.argsort(np.argsort(xs)) % 5 - 2) * 0.09
            ax.scatter(np.clip(xs, -6, 12), y, s=16, color=[G if x > 0 else WARN for x in xs], zorder=3)
            lo, hi = test["primary"][k]["ci95"]
            ax.plot([lo, hi], [i - 0.38] * 2, color=INK, lw=2.5)
            ax.plot([test["primary"][k]["mean"]] * 2, [i - 0.3, i - 0.46], color=INK, lw=2.5)
        ax.axvline(0, color=MUTED, lw=1)
        ax.invert_yaxis()
        ax.set_yticks([0, 1], ["SIRA − Muse alone", "SIRA − physics alone"])
        ax.set_xlabel("log score per measurement, SIRA minus rival (nats; right is SIRA better)")
        ax.set_title(f"{test['cases']} test objects SIRA never saw, one dot each\nbar: mean and 95% interval over objects",
                     fontsize=10, color=INK, loc="left")
        save(fig, "forecasts")

    phys = results.get("physics")
    if phys:
        rows = phys["distance"]["rows"]
        fig, ax = plt.subplots(figsize=(4.8, 4.2))
        top = max(r["z"] for r in rows) * 1.15
        ax.plot([0, top], [0, top], color=HAIR, lw=1)
        high = max(top, max(r["z_pred"] for r in rows) * 1.08)
        for good, ia, color, label in ((True, True, G, "SN Ia, well measured"), (False, True, G, "SN Ia, other fits"),
                                       (None, False, R, "other types treated as Ia")):
            pts = [r for r in rows if r["ia"] == ia and (good is None or r["good"] == good)]
            ax.scatter([r["z"] for r in pts], [r["z_pred"] for r in pts], s=16, label=f"{label} ({len(pts)})",
                       facecolors="none" if good is False else color, edgecolors=color, linewidths=1)
        ax.set_xlim(0, top)
        ax.set_ylim(0, high)
        ax.set_xlabel("host galaxy redshift (spectroscopic)")
        ax.set_ylabel("redshift from the light curve alone")
        d = phys["distance"]
        ax.set_title(f"median error {d['good_fits']['ia']['median_abs_err']:.1%} on {d['good_fits']['ia']['n']} well-measured SN Ia\n"
                     f"({d['all']['ia']['median_abs_err']:.1%} on all {d['all']['ia']['n']})", fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        save(fig, "distance")

        v = phys["verdicts"]
        fig, ax = plt.subplots(figsize=(6.2, 2.8))
        for i, (kind, label) in enumerate((("lens", "lensing events"), ("ia", "SN Ia"))):
            s = v["sets"][kind]
            left = 0
            for n, color, word in ((s["decisive_right"], G, "right"), (s["decisive_wrong"], WARN, "wrong"),
                                   (s["abstain"], HAIR, "abstain")):
                ax.barh(i, n, left=left, color=color, height=0.55)
                if n >= 3:
                    ax.text(left + n / 2, i, f"{n} {word}", ha="center", va="center", fontsize=8,
                            color="white" if color != HAIR else INK)
                left += n
            small = [f"{n} {w}" for n, w in ((s["decisive_wrong"], "wrong"), (s["abstain"], "abstain")) if 0 < n < 3]
            if small:
                ax.text(left + 0.3, i, ", ".join(small), va="center", fontsize=8, color=MUTED)
        ax.set_yticks([0, 1], ["lensing events", "SN Ia"])
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.set_xlabel("objects")
        ax.set_title(f"lens or supernova, judged on the future it never saw\n{v['decisive_accuracy']:.0%} right when decisive, "
                     f"{v['abstain_rate']:.0%} abstained", fontsize=10, loc="left")
        save(fig, "verdicts")

    lv = results.get("leverrier")
    if lv:
        fig, ax = plt.subplots(figsize=(5.8, 3.4))
        sizes = [lv["sizes"][k] for k in SIZES]
        ax.bar(range(len(SIZES)), [z["discoveries_per_usd"] or 0 for z in sizes], color=G, width=0.55)
        for i, z in enumerate(sizes):
            ax.text(i, (z["discoveries_per_usd"] or 0) + 0.2, f"{z['neptune_on_lenses']} found, {z['neptune_on_ia']} false\nUS${z['usd']:.2f}",
                    ha="center", va="bottom", fontsize=8, color=MUTED)
        ax.set_xticks(range(len(SIZES)), [f"{k} Le Verrier{'s' if k > 1 else ''}" for k in SIZES])
        ax.set_ylim(0, max(z["discoveries_per_usd"] or 0 for z in sizes) * 1.35 + 0.5)
        ax.set_ylabel("discoveries per US$")
        surprised = lv["objects"]["microlensing"]["surprised"]
        ax.set_title(f"{surprised} of {lv['objects']['microlensing']['replayed']} test lensing events surprised the physics;\n"
                     f"no SN Ia did ({lv['objects']['ia']['replayed']})", fontsize=10, loc="left")
        save(fig, "team_size")

    lr = results.get("live")
    if lr:
        rec, cost = lr["record"], lr["cost"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.2), gridspec_kw={"width_ratios": [1, 1.2]})
        if rec["answered"]:
            bins = np.linspace(0, 1, 6)
            ps = np.array([r["p_yes"] for r in rec["rows"]])
            ys = np.array([r["yes"] for r in rec["rows"]], float)
            idx = np.clip(np.digitize(ps, bins) - 1, 0, 4)
            mids = [(bins[i] + bins[i + 1]) / 2 for i in range(5) if (idx == i).any()]
            a1.plot([0, 1], [0, 1], color=HAIR, lw=1)
            a1.scatter(mids, [ys[idx == i].mean() for i in range(5) if (idx == i).any()],
                       s=[30 + 6 * (idx == i).sum() for i in range(5) if (idx == i).any()], color=INK)
            a1.set_xlim(0, 1)
            a1.set_ylim(-0.02, 1.02)
            a1.set_xlabel("SIRA's sealed probability")
            a1.set_ylabel("how often it happened")
        else:
            a1.axis("off")
            a1.text(0, 0.5, "no question answered yet at this head", color=MUTED, fontsize=9)
        a1.set_title(f"live: {rec['right']} of {rec['answered']} right", fontsize=10, loc="left")
        roles = cost["by_role_per_investigation"]
        names = sorted(roles, key=roles.get)
        a2.barh([ROLES.get(n, n) for n in names], [roles[n] for n in names], color=INK, height=0.6)
        a2.set_xlabel("US$ per investigated transient")
        a2.set_title(f"US${cost['usd_per_investigation']:.2f} per investigation, {cost['investigated']} live",
                     fontsize=10, loc="left")
        save(fig, "live")
    return made


def equations(folder: Path, pieces: list[dict] | None = None) -> dict:
    # the pre-registered equation experiment: what Wonder wrote with no pieces, what the lab kept and what the future said
    folder = Path(folder)
    plan = json.loads((folder / "plan.json").read_text())
    rows = []
    for kind, oids in plan["objects"].items():
        for oid in oids:
            path = folder / f"leverrier-{oid}.json"
            data = json.loads(path.read_text()) if path.exists() else None
            written = (data or {}).get("proposals")
            fitted = [p for p in written or [] if p.get("bic") is not None]
            pick = min(fitted, key=lambda p: p["bic"]) if fitted else None
            rows.append({"object": oid, "kind": kind, "replayed": bool(data and "checks" in data),
                         "surprised": written is not None, "written": len(written or []),
                         "lens_laws": sum(bool(p.get("lens_law")) for p in written or []),
                         "usd": round(sum(p.get("cost_usd") or 0 for p in written or []), 4),
                         "chosen": {"name": pick["name"], "lens_law": pick["lens_law"], "verdict": pick["against_old"]["verdict"],
                                    "log10_e": pick["against_old"]["log10_e"], "equation": pick["equation"]} if pick else None})
    count = lambda rs, test: sum(1 for r in rs if test(r))
    verdicts = lambda rs: {v: count(rs, lambda r: r["chosen"] and r["chosen"]["verdict"] == v) for v in ("neptune", "abstain", "vulcan")} | {
        "not_fitted": count(rs, lambda r: not r["chosen"])}
    lenses = [r for r in rows if r["kind"] == "microlensing" and r["surprised"]]
    others = [r for r in rows if r["kind"] != "microlensing" and r["surprised"]]
    out = {"plan": stamped(folder / "plan.json"),
           "objects": {k: {"n": len(v), "replayed": count(rows, lambda r, k=k: r["kind"] == k and r["replayed"]),
                           "surprised": count(rows, lambda r, k=k: r["kind"] == k and r["surprised"])} for k, v in plan["objects"].items()},
           "lenses": {"surprised": len(lenses), "chosen_lens_law": count(lenses, lambda r: r["chosen"] and r["chosen"]["lens_law"]),
                      "any_lens_law": count(lenses, lambda r: r["lens_laws"] > 0),
                      "lens_laws_written": sum(r["lens_laws"] for r in lenses), "equations_written": sum(r["written"] for r in lenses),
                      "verdicts": verdicts(lenses)},
           "others": {"surprised": len(others), "chosen_lens_law": count(others, lambda r: r["chosen"] and r["chosen"]["lens_law"]),
                      "verdicts": verdicts(others)},
           "usd": round(sum(r["usd"] for r in rows), 2), "rows": rows}
    if pieces:
        # the same lens surprises with three pieces-built proposals, from the team-size experiment
        same = {r["object"]: r["3"]["verdict"] for r in pieces if r["kind"] == "microlensing" and r["surprised"]}
        out["lenses"]["pieces_verdicts"] = {v: sum(1 for r in lenses if same.get(r["object"]) == v) for v in ("neptune", "abstain", "vulcan")}
    return out


def collect(root: Path, ledger_dir: Path | None, seq: int | None = None) -> dict:
    root = Path(root)
    plan = json.loads((root / "plan.json").read_text())
    results = {"plan": stamped(root / "plan.json")}
    runs = {r: root / "test" / r for r in plan["replay"]["runs"] if (root / "test" / r).exists()}
    if runs:
        results["test"] = replays(root, runs)
        results["test"]["failed"] = sorted(set(results["test"]["failed"]) |
                                           (set(plan["replay"]["cases"]) - {r["object"] for r in results["test"]["rows"]}))
    if (root / "leverrier").exists():
        results["leverrier"] = leverriers(root / "leverrier", plan["team_size"]["leverrier"]["objects"])
    if (root / "physics.json").exists():
        results["physics"] = json.loads((root / "physics.json").read_text())
    if (root / "reader").exists():
        results["reader"] = readers(root / "reader")
    if (root / "equations" / "plan.json").exists():
        results["equations"] = equations(root / "equations", (results.get("leverrier") or {}).get("rows"))
    if ledger_dir:
        results["live"] = live(Ledger(ledger_dir).entries(), seq)
    return results


def physics(snapshot: Path, root: Path) -> dict:
    # the two physics headlines on the test split, and the truth the replays are graded against
    from . import accept

    snapshot, root = Path(snapshot), Path(root)
    plan = json.loads((root / "plan.json").read_text())
    truth = json.loads((snapshot / "truth.json").read_text())
    keep = set(plan["replay"]["cases"]) | {o for v in plan["team_size"]["leverrier"]["objects"].values() for o in v}
    (root / "truth.json").write_text(json.dumps({k: truth[k] for k in sorted(keep)}, indent=1) + "\n")
    out = {"distance": accept.at1(snapshot, split="test"), "verdicts": accept.at2(snapshot, split="test")}
    (root / "physics.json").write_text(json.dumps(out, indent=1) + "\n")
    return out
