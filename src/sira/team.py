import hashlib

from . import agents, alerce, reader
from .config import SPARK_OPEN
from .firewall import blind, case_id
from .live import assemble, chance, physics

SENIOR_PER_NIGHT = 3  # Wonder at max effort is costly; the director may call it this often
DOUBT = (0.35, 0.65)  # a lookout this unsure gets two more opinions
ARTIFACT = 0.7  # an instrument skeptic this sure keeps the object off the ledger
NIGHTS = 3  # unless the source came back on this many nights, which a detector glitch does not
DOUBTED = 0.3  # a physics skeptic's objection scales a hypothesis by this much
REMEMBERED = 0.5
AUDIT = 0.1  # this share of plain bets goes to the senior anyway, so escalation is measured without bias


def case_of(view: dict) -> dict:
    case = blind(view)
    case["photometry"] = case["photometry"][-60:]
    return case


def eyes(llm, c, views: dict, pool) -> tuple[dict, list[dict]]:
    # the reader that passed G1 looks at each candidate's first stamps before the lookouts decide
    proto = reader.PROTOCOLS["v2"]
    shots = reader.packaged_shots(proto)

    def look(oid):
        dets = [r for r in views[oid]["photometry"] if r["kind"] == "det" and r.get("stamp", True) and r.get("candid")]
        if not dets:
            return oid, None, None
        first = min(dets, key=lambda r: r["mjd"])
        try:
            fits = [alerce.stamp(c, oid, first["candid"], k) for k in reader.KINDS]
            out = reader.read(llm, "spark-open", reader.draw(fits, proto.render), shots, proto.system, "agent:reader")
        except Exception as e:
            return oid, None, {"role": "reader", "case": case_id(oid), "cost_usd": 0.0, "decision": "could not read",
                               "error": type(e).__name__}
        reading = {"label": out["label"], "p_real": out["p_real"], "why": out["why"][:200]}
        return oid, reading, {"role": "reader", "case": case_id(oid), "model": SPARK_OPEN, "effort": None,
                              "cost_usd": out["usd"], "seconds": out["seconds"], "votes": out["votes"],
                              "decision": f"{out['label']} ({out['p_real']})", "why": reading["why"]}

    results = list(pool.map(look, views))
    return ({oid: r for oid, r, _ in results if r}, [e | {"object": oid} for oid, _, e in results if e])


def triage(llm, views: dict, n: int, pool, readings: dict | None = None) -> tuple[list[str], list[dict]]:
    readings = readings or {}
    cases = {oid: case_of(v) | ({"stamp_reader": readings[oid]} if oid in readings else {}) for oid, v in views.items()}
    first = dict(zip(cases, pool.map(lambda oid: agents.lookout(llm, cases[oid]), cases)))
    events, score = [], {}
    for oid, (out, event) in first.items():
        votes, evs = [out], [event]
        if DOUBT[0] <= out["priority"] <= DOUBT[1]:
            more = list(pool.map(lambda _: agents.lookout(llm, cases[oid]), range(2)))
            votes, evs = votes + [m[0] for m in more], evs + [m[1] for m in more]
        score[oid] = (2 * sum(v["investigate"] for v in votes) > len(votes), sum(v["priority"] for v in votes) / len(votes))
        events += [e | {"object": oid} for e in evs]
    picked = sorted((o for o, (go, _) in score.items() if go), key=lambda o: -score[o][1])[:n]
    return picked, events


def _questions(sira: dict, theories: list[dict], now: float) -> list[dict]:
    def make(qid, band, day, reference, direction, source):
        at = min((f for f in sira["forecasts"] if f["band"] == band), key=lambda f: abs(f["mjd"] - (now + day)))
        word = "Brighter" if direction == "above" else "Fainter"
        return {"id": qid, "text": f"{word} than {reference:g} microjansky in {band[-1]} {day} days from now?",
                "band": band, "mjd": at["mjd"], "reference": reference, "direction": direction,
                "p_yes": round(chance(at["parts"], reference, direction), 3),
                "bits": round(agents.bits([p for p in at["parts"] if p[0] != "llm"], reference, direction, chance), 3),
                "source": source}

    out = []
    q = sira["question"]
    if q:
        out.append(make("q0", q["band"], 3, q["reference"], "above", "standard") | {"text": q["text"]})
    for i, t in enumerate(theories, 1):
        r = t["refuted_if"]
        if r:
            out.append(make(f"q{i}", r["band"], r["day"], r["flux"], r["direction"], f"refutes {t['hypothesis']}"))
    return out


def _mind(alone) -> tuple[dict | None, list[dict]]:
    # the model's own forecast, made beside the team; if that call failed, SIRA bets on its physics alone
    if alone is None:
        return None, []
    try:
        out, event = alone.result()
    except Exception:
        return None, []
    return out, [event]


def investigate(llm, view: dict, ebv: float, pool, seniors: list, reading: dict | None = None,
                adopted: dict | None = None, alone=None, report=None) -> tuple[dict | None, list[dict]]:
    tell = report or (lambda events: None)  # hears the events after each stage, for a visitor watching live
    phys = physics(view, ebv, adopted=adopted)
    if not phys:
        return None, _mind(alone)[1]
    case, now = case_of(view) | ({"stamp_reader": reading} if reading else {}), view["as_of"]
    top = sorted(phys["summaries"], key=lambda k: -phys["summaries"][k]["weight"])[:3]
    jobs = [("t", k) for k in top] + [("s", lens) for lens in agents.LENSES]
    results = list(pool.map(lambda j: agents.theorist(llm, j[1], case, phys) if j[0] == "t"
                            else agents.skeptic(llm, j[1], case, phys), jobs))
    theories = [r[0] for r in results[:len(top)]]
    lenses = {lens: r[0] for lens, r in zip(agents.LENSES, results[len(top):])}
    mind, events = _mind(alone)
    events += [r[1] for r in results]
    tell(events)
    nights = len({int(r["mjd"]) for r in view["photometry"] if r["kind"] == "det"})
    if lenses["instrument"]["artifact"] and lenses["instrument"]["confidence"] >= ARTIFACT and nights < NIGHTS:
        return None, events + [{"role": "lab", "case": case["case"], "cost_usd": 0.0,
                                "decision": "dropped: the instrument skeptic calls it an artifact"}]
    weights = dict(phys["weights"])
    for item in lenses["physics"]["implausible"]:
        if item["hypothesis"] in weights and item["hypothesis"] != "null":
            weights[item["hypothesis"]] *= DOUBTED
    b1, sira = assemble(phys, phys["weights"], view), assemble(phys, weights, view, mind)
    questions = _questions(sira, theories, now)
    if not questions:
        return None, events
    state = {"weights": sira["weights"], "sky_soon": sira["decision"],
             "skeptics": {k: v for k, v in lenses.items() if k != "memory"},
             "theories": [{k: t[k] for k in ("hypothesis", "argument", "weakest_point")} for t in theories],
             "questions": [{k: q[k] for k in ("id", "text", "p_yes", "bits")} for q in questions],
             "senior_reviews_left": seniors[0]}
    choice, event = agents.director(llm, case, state)
    events.append(event)
    tell(events)
    draw =int(hashlib.sha256(f"audit:{case['case']}:{int(now)}".encode()).hexdigest(), 16) % 1000
    audit = choice["action"] == "bet" and draw < AUDIT * 1000
    if (choice["action"] == "escalate" or audit) and seniors[0] > 0:
        seniors[0] -= 1
        review, event = agents.director(llm, case, state, senior=True)
        events.append(event)
        tell(events)
        for k, factor in review["factors"].items():
            if k in weights:
                weights[k] *= factor
        sira = assemble(phys, weights, view, mind)
        questions = _questions(sira, theories, now)
        choice = choice | {"question": review["question"] if review["question"] in {q["id"] for q in questions}
                           else choice["question"], "senior": review, "audit": audit}
    picked = next(q for q in questions if q["id"] == choice["question"])
    words, event = agents.forecaster(llm, case, picked)
    events.append(event)
    memory = lenses["memory"]
    return sira | {
        "risky": picked if picked["id"] != "q0" else None, "wording": words,
        "baselines": sira["baselines"] | {"b1": b1["forecasts"]},
        "theories": theories, "skeptics": lenses, "director": choice,
        "remembered": bool(memory["recognised"] and memory["confidence"] >= REMEMBERED),
        "team": {"calls": len(events), "cost_usd": round(sum(e["cost_usd"] for e in events), 4)},
    }, events
