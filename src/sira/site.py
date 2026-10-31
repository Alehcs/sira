import json
import re
from datetime import datetime
from pathlib import Path

from .ledger import Ledger

LEVEL = re.compile(r"(Brighter|Fainter) than ([\d.]+) microjansky in (\w) (\d+) days from now\?")
READING = re.compile(r"^(real|bogus) \(([\d.]+)\)$")


def _date(mjd: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=mjd)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _question(q: dict) -> dict:
    # the question as fields, so the site can word it in any language
    m = LEVEL.match(q["text"])
    base = {"p": q["p_yes"], "due": _date(q["mjd"]), "text": q["text"]}
    if m:
        return base | {"kind": "level", "direction": "above" if m[1] == "Brighter" else "below",
                       "reference": float(m[2]), "band": m[3], "days": int(m[4])}
    return base | {"kind": "last", "direction": "above", "reference": round(q["reference"], 1),
                   "band": q["band"][-1], "days": 3}


def _sealed_at(entries: list[dict]):
    anchors = sorted((e["payload"]["seq"], e["payload"].get("tsa_time")) for e in entries if e["kind"] == "anchor")
    return lambda seq: next((t for s, t in anchors if s >= seq), None)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def telegrams(entries: list[dict]) -> list[dict]:
    sealed = _sealed_at(entries)
    answers = {(e["payload"]["bet"], e["payload"].get("which", "question")): e["payload"]
               for e in entries if e["kind"] == "answer"}
    out = []
    for e in entries:
        p = e["payload"]
        if e["kind"] != "bet" or "-leap-" in p["bet"]:
            continue
        risky = p.get("risky") or {}
        which = "risky" if risky and (p.get("director") or {}).get("question") == risky.get("id") else "question"
        a = answers.get((p["bet"], which))
        out.append({"seq": e["seq"], "bet": p["bet"], "object": p["object"], "model": p.get("model"),
                    "made_at": _date(p["made_at"]), "hash": e["hash"], "sealed_at": sealed(e["seq"]),
                    "question": _question(p[which]), "term": (p.get("wording") or {}).get("term"),
                    "answer": None if a is None else ({"void": True} if a.get("void") else
                                                       {"yes": a["yes"], "log_score": a["log_score"], "at": _date(a["mjd"])})})
    return out[::-1]


def record(entries: list[dict], tele: list[dict]) -> dict:
    done = [t["answer"] for t in tele if t["answer"] and not t["answer"].get("void")]
    right = sum(1 for t in tele if t["answer"] and not t["answer"].get("void") and (t["question"]["p"] >= 0.5) == t["answer"]["yes"])
    open_due = [t["question"]["due"] for t in tele if not t["answer"]]
    outcomes = [e["payload"] for e in entries if e["kind"] == "outcome" and "-leap-" not in e["payload"]["bet"]]
    paired = [o for o in outcomes if all(k in (o.get("baselines") or {}) for k in ("b0", "b1", "b2"))]
    rivals = {"sira": _mean([o["log_score"] for o in paired])}
    rivals |= {k: _mean([o["baselines"][k]["log_score"] for o in paired]) for k in ("b0", "b1", "b2")}
    return {"sealed": len(tele), "answered": len(done), "right": right, "next_due": min(open_due) if open_due else None,
            "outcomes": len(outcomes), "paired": len(paired), "log_score": rivals}


def surprises(entries: list[dict]) -> list[dict]:
    # live Le Verrier: each surprise, the bet it sealed and the sky's verdict on it
    rows = {"surprise": [], "leap": {}, "verdict": {}}
    for e in entries:
        p = e["payload"]
        if e["kind"] == "surprise" and p.get("surprised"):
            rows["surprise"].append(p | {"at": e["time"]})
        elif e["kind"] == "bet" and "-leap-" in p["bet"]:
            rows["leap"][p.get("parent")] = {"bet": p["bet"], "chosen": p.get("chosen"), "cost_usd": p.get("cost_usd"),
                                             "proposals": [{k: x.get(k) for k in ("name", "leap", "idea")} for x in p.get("proposals", [])]}
        elif e["kind"] == "verdict":
            rows["verdict"][p["bet"]] = {"verdict": p["verdict"], "log10_e": p["log10_e"], "n": p["n"], "at": e["time"]}
    out = []
    for s in rows["surprise"]:
        leap = rows["leap"].get(s["bet"])
        out.append({"object": s["object"], "at": s["at"], "misses": s["misses"], "n": s["n"], "p": s["p_value"],
                    "leap": leap, "verdict": rows["verdict"].get(leap["bet"]) if leap else None})
    return out


def rounds(entries: list[dict]) -> dict:
    # Beat SIRA: each round's questions, SIRA's revealed answers, the crowd and the scores
    by = {}
    for e in entries:
        p = e["payload"]
        if e["kind"] == "round":
            by[p["round"]] = {"round": p["round"], "opens_at": p["opens_at"], "closes_at": p["closes_at"],
                              "questions": [{k: q[k] for k in ("id", "object", "commit")} | {"question": _question(
                                  {"text": q["text"], "p_yes": None, "mjd": q["mjd"], "reference": q["reference"], "band": q["band"]})}
                                  for q in p["questions"]], "answers": {}, "players": 0, "results": {}}
        elif e["kind"] == "reveal" and p["round"] in by:
            by[p["round"]]["answers"] = {a["id"]: a["p_yes"] for a in p["answers"]}
        elif e["kind"] == "crowd" and p["round"] in by:
            by[p["round"]]["players"] = len({b["player"] for b in p["bets"]})
            by[p["round"]]["crowd"] = {q: _mean([b["p_yes"] for b in p["bets"] if b["question"] == q])
                                       for q in {b["question"] for b in p["bets"]}}
        elif e["kind"] == "crowd_answer" and p["round"] in by:
            by[p["round"]]["results"][p["question"]] = {"void": True} if p.get("void") else {"yes": p["yes"], "scores": p["scores"]}
    table = {}
    for r in by.values():
        for res in r["results"].values():
            if res.get("void"):
                continue
            s = res["scores"]
            for who, v in [("sira", s.get("sira")), ("crowd", s.get("crowd")), ("sira_crowd", s.get("sira_crowd"))]:
                if v is not None:
                    table.setdefault(who, []).append(v)
            for player, v in s.get("players", {}).items():
                table.setdefault(player, []).append(v)
    handles = {b["player"]: b["handle"] for e in entries if e["kind"] == "crowd" for b in e["payload"]["bets"]}
    board = sorted(({"who": k, "handle": handles.get(k), "resolved": len(v), "mean": _mean(v)} for k, v in table.items()),
                   key=lambda x: -(x["mean"] if x["mean"] is not None else -1e9))
    return {"rounds": sorted(by.values(), key=lambda r: r["round"], reverse=True), "board": board}


def candidates(entries: list[dict], n: int = 24) -> list[dict]:
    # what the lookouts weighed on the last night, so a visitor can send the lab after any of it
    looks = [e for e in entries if e["kind"] == "event" and e["payload"].get("role") == "lookout" and e["payload"].get("object")]
    if not looks:
        return []
    last = datetime.fromisoformat(looks[-1]["time"])
    night = [e for e in entries if abs((datetime.fromisoformat(e["time"]) - last).total_seconds()) < 3 * 3600]
    votes = {}
    for e in night:
        p = e["payload"]
        if e["kind"] == "event" and p.get("role") == "lookout" and p.get("object"):
            votes.setdefault(p["object"], []).append((p.get("decision") == "investigate", p.get("priority") or 0.0))
    seen, bet = {}, set()
    for e in night:
        p = e["payload"]
        m = READING.match(str(p.get("decision", ""))) if p.get("role") == "reader" else None
        if e["kind"] == "event" and m:
            seen[p.get("object")] = (m[1], float(m[2]))
        elif e["kind"] == "bet":
            bet.add(p["object"])
    rows = [{"object": oid, "priority": round(_mean([v[1] for v in vs]), 2), "picked": 2 * sum(v[0] for v in vs) > len(vs),
             "reader": seen.get(oid, (None, None))[0], "p_real": seen.get(oid, (None, None))[1], "bet": oid in bet}
            for oid, vs in votes.items()]
    return sorted(rows, key=lambda r: -r["priority"])[:n]


def live(entries: list[dict]) -> dict:
    tele = telegrams(entries)
    anchors = [e for e in entries if e["kind"] == "anchor"]
    head = anchors[-1]["payload"] if anchors else {}
    return {"head": {"hash": head.get("head"), "tsa_time": head.get("tsa_time"), "run": head.get("run"), "seq": head.get("seq")},
            "entries": len(entries), "telegrams": tele, "record": record(entries, tele),
            "surprises": surprises(entries), "beat": rounds(entries), "candidates": candidates(entries)}


def _lab(rows: list[dict], obj: dict) -> dict:
    # the lab's replay: the g and r light curve with its limits, every sealed forecast and the facts each step tells
    from astropy.coordinates import SkyCoord

    from .leverrier import TAIL
    from .photometry import flux

    t0 = min(p["mjd"] for p in obj["photometry"] if p["kind"] != "limit")
    day = lambda m: round(m - t0, 3)
    dets = [p for p in obj["photometry"] if p["kind"] != "limit"]

    def moments(points):
        def row(f):
            m = sum(w * mu for _, w, mu, _ in f["parts"])
            v = sum(w * (sd * sd + mu * mu) for _, w, mu, sd in f["parts"]) - m * m
            return [day(f["mjd"]), round(m, 1), round(max(v, 0) ** 0.5, 1)]
        return {b: [row(f) for f in points if f["band"] == f"ztf{b}"] for b in "gr"}

    def measured(p):
        # an upper limit is drawn at the flux of its limiting magnitude
        if p["kind"] == "limit":
            return [day(p["mjd"]), p["band"][-1], "lim", round(flux(p["mag"], 0)[0], 2), None, day(p["available_at"])]
        return [day(p["mjd"]), p["band"][-1], "det", round(p["flux"], 2), round(p["flux_err"], 2), day(p["available_at"])]

    def staked(p):
        risky = p.get("risky")
        return risky if risky and (p.get("director") or {}).get("question") == risky.get("id") else p["question"]

    def answered(a):
        if a is None:
            return None
        p = a["payload"]
        return {"void": True} if p.get("void") else {"yes": p["yes"], "log_score": p["log_score"], "at": day(p["mjd"])}

    bets = [r for r in rows if r["kind"] == "bet" and "-leap-" not in r["payload"]["bet"]]
    leaps = [r for r in rows if r["kind"] == "bet" and "-leap-" in r["payload"]["bet"]]
    events = [r for r in rows if r["kind"] == "event"]
    of = lambda kind: [r for r in rows if r["kind"] == kind]
    first = lambda pred: next(r for r in rows if pred(r))

    def team(k, role):
        lo = bets[k - 1]["seq"] if k else -1
        return [r for r in events if lo < r["seq"] < bets[k]["seq"] and r["payload"]["role"] == role]

    answers = {r["payload"]["bet"]: r for r in of("answer")}
    surprise = first(lambda r: r["kind"] == "surprise" and r["payload"]["surprised"])
    verdicts = of("verdict")
    adopted = first(lambda r: r["kind"] == "event" and r["payload"]["role"] == "theorist" and "adopted" in r["payload"]["decision"])
    last = bets[-1]
    marks = [team(0, "reader")[0], team(0, "theorist")[-1], team(0, "skeptic")[-1], team(0, "director")[-1],
             bets[0], bets[1], surprise, [r for r in events if r["payload"]["role"] == "leverrier" and r["seq"] < leaps[0]["seq"]][-1],
             verdicts[0], adopted, team(len(bets) - 1, "director")[-1], last, answers[last["payload"]["bet"]], verdicts[-1]]
    spent = [round(sum(e["payload"].get("cost_usd", 0) for e in events if e["seq"] <= m["seq"]), 2) for m in marks]
    times = [day(b["payload"]["made_at"]) for b in bets]
    now = [times[0]] * 5 + [times[1], times[2], times[2], times[3], times[3], times[4], times[4],
                            day(answers[last["payload"]["bet"]]["payload"]["mjd"]) + 0.5, day(last["payload"]["made_at"]) + 5]
    sealed_at = [times[0]] * 6 + [times[1], times[2], times[2], times[3], times[4], times[4], times[4], times[4]]
    reader = team(0, "reader")[0]["payload"]

    # the measurements the surprised forecast missed: a PIT in either tail, as Le Verrier counts them
    shock = surprise["payload"]
    misses = [[day(p["mjd"]), p["band"][-1], round(p["flux"], 2), p["baselines"][shock["forecast"]]["pit"]]
              for p in (r["payload"] for r in of("outcome")) if p["bet"] == shock["bet"]
              and not TAIL <= p["baselines"][shock["forecast"]]["pit"] <= 1 - TAIL]
    verdict_of = {r["payload"]["bet"]: r for r in verdicts}

    def leap(r):
        v = verdict_of[r["payload"]["bet"]]
        return {"hash": r["hash"][:12], "time": r["time"], "chosen": r["payload"]["chosen"],
                "proposals": [{k: x[k] for k in ("leap", "name", "bic")} for x in r["payload"]["proposals"]],
                "verdict": {"hash": v["hash"][:12], "time": v["time"]} | {k: v["payload"][k] for k in ("verdict", "log10_e", "n")}}

    # each step's agent in its own words, where the ledger kept them whole
    argued = lambda b, h: next(t["argument"] for t in b["payload"]["theories"] if t["hypothesis"] == h)
    lead = max((h for h in bets[0]["payload"]["weights"] if h != "null"), key=bets[0]["payload"]["weights"].get)
    adopter = next(b for b in bets if any(t["hypothesis"] == "adopted" for t in b["payload"]["theories"]))
    idea = next(x["idea"] for x in leaps[0]["payload"]["proposals"] if x["name"] == leaps[0]["payload"]["chosen"])
    said = [reader["why"], argued(bets[0], lead), bets[0]["payload"]["skeptics"]["instrument"]["why"],
            bets[0]["payload"]["director"]["why"], bets[0]["payload"]["wording"]["text"], None, None, idea, None,
            argued(adopter, "adopted"), last["payload"]["director"]["why"], last["payload"]["wording"]["text"], None, None]
    sky = SkyCoord(obj["ra"], obj["dec"], unit="deg").galactic
    return {
        "object": obj["oid"], "first_detection": _date(t0), "mjd": round(t0, 5),
        "ra": obj["ra"], "dec": obj["dec"], "l": round(float(sky.l.deg), 4), "b": round(float(sky.b.deg), 4),
        "phot": [measured(p) for p in sorted(obj["photometry"], key=lambda p: p["mjd"])],
        "counts": [sum(1 for p in dets if day(p["available_at"]) <= t) for t in now],
        "now": now, "sealed_at": sealed_at, "spent": spent,
        "fans": {f"cp{i + 1}": moments(b["payload"]["baselines"]["b1"]) for i, b in enumerate(bets)}
                | {"lens": moments(leaps[0]["payload"]["forecasts"]), "old": moments(leaps[0]["payload"]["baselines"]["old"])},
        "misses": misses,
        "bets": [{"hash": b["hash"][:12], "time": b["time"], "p": staked(b["payload"])["p_yes"],
                  "question": _question(staked(b["payload"])), "term": b["payload"]["wording"]["term"],
                  "weights": b["payload"]["weights"], "action": b["payload"]["decision"]["action"],
                  "theories": [r["payload"]["decision"].replace("defends ", "") for r in team(k, "theorist")],
                  "answer": answered(answers.get(b["payload"]["bet"]))}
                 for k, b in enumerate(bets)],
        "leaps": [leap(r) for r in leaps],
        "said": said,
        "facts": {
            "reader": float(re.search(r"\(([\d.]+)\)", reader["decision"])[1]),
            "skeptics": {r["payload"]["lens"]: r["payload"]["decision"] for r in team(0, "skeptic")},
            "theories": [r["payload"]["decision"].replace("defends ", "") for r in team(0, "theorist")],
            "surprise": {k: surprise["payload"][k] for k in ("misses", "n", "p_value")},
            "proposals": [r["payload"]["decision"].replace("proposes ", "") for r in events
                          if r["payload"]["role"] == "leverrier" and r["seq"] < leaps[0]["seq"]],
            "chosen": leaps[0]["payload"]["chosen"], "leap_cost": leaps[0]["payload"]["cost_usd"],
            "verdict": {k: verdicts[0]["payload"][k] for k in ("verdict", "log10_e", "n")},
            "second": {k: verdicts[-1]["payload"][k] for k in ("verdict", "log10_e", "n")},
            "answer": answers[last["payload"]["bet"]]["payload"]["yes"],
            "cost": round(sum(e["payload"].get("cost_usd", 0) for e in events), 2),
            "calls": sum(1 for e in events if e["payload"].get("cost_usd", 0) > 0),
        },
    }


def _logbook(var: Path, team_rows: list[dict]) -> list[dict]:
    # Le Verrier in the replays: each surprise, the three proposals and the sky's verdicts
    lanes = []
    events = [r for r in team_rows if r["kind"] == "event" and r["payload"]["role"] == "leverrier"]
    leaps = [r for r in team_rows if r["kind"] == "bet" and "-leap-" in r["payload"]["bet"]]
    verdicts = {r["payload"]["bet"]: r for r in team_rows if r["kind"] == "verdict"}
    shocks = [r for r in team_rows if r["kind"] == "surprise" and r["payload"]["surprised"]]
    chains = []
    for leap, shock in zip(leaps, shocks):
        mine = [e["payload"] for e in events if e["seq"] < leap["seq"] and e["seq"] > shock["seq"]]
        v = verdicts[leap["payload"]["bet"]]["payload"]
        chains.append({"at": _date(leap["payload"]["made_at"]), "misses": shock["payload"]["misses"], "n": shock["payload"]["n"],
                       "p": shock["payload"]["p_value"], "cost_usd": round(leap["payload"]["cost_usd"], 2),
                       "proposals": [{"leap": m["leap"], "name": m["decision"].replace("proposes ", ""), "idea": m["why"],
                                      "chosen": m["decision"].endswith(leap["payload"]["chosen"])} for m in mine],
                       "verdict": {k: v[k] for k in ("verdict", "log10_e", "n")}})
    lanes.append({"object": team_rows[0]["payload"]["object"], "source": "team", "chains": chains, "adopted": True})
    for path in sorted(var.glob("leverrier-*.json")):
        a = json.loads(path.read_text())
        hit = next((c for c in a["checks"] if c["surprise"]["surprised"]), None)
        if not hit:
            lanes.append({"object": a["oid"], "source": "leverrier", "chains": []})
            continue
        lanes.append({"object": a["oid"], "source": "leverrier", "chains": [{
            "at": _date(a["now"]), "misses": hit["surprise"]["misses"], "n": hit["surprise"]["n"], "p": hit["surprise"]["p_value"],
            "cost_usd": round(sum(e["cost_usd"] for e in a["events"]), 2),
            "proposals": [{"leap": p["leap"], "name": p["name"], "idea": p["idea"], "verdict": p["against_old"]["verdict"],
                           "log10_e": p["against_old"]["log10_e"], "n": p["against_old"]["n"]} for p in a["proposals"]]}]})
    return lanes


def replays(var: Path, snapshot: Path, out: Path, oid: str = "ZTF19aavisrq") -> None:
    # the saved replays the site tells, written once from var/ because var/ stays out of git
    import httpx

    from . import alerce, reader

    rows = [json.loads(line) for line in (var / "replay" / "dev2" / oid / "ledger.jsonl").read_text().splitlines()]
    obj = json.loads((snapshot / "objects" / f"{oid}.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    (out / "lab.json").write_text(json.dumps(_lab(rows, obj), separators=(",", ":"), ensure_ascii=False))
    (out / "logbook.json").write_text(json.dumps(_logbook(var, rows), separators=(",", ":"), ensure_ascii=False))
    first = min((p for p in obj["photometry"] if p["kind"] != "limit"), key=lambda p: p["mjd"])
    with httpx.Client(timeout=30) as c:
        fits = [alerce.stamp(c, oid, first["candid"], k) for k in reader.KINDS]
    (out / "stamps.png").write_bytes(reader.draw(fits, reader.PROTOCOLS["v2"].render))


def export(ledger_dir: Path, out: Path) -> dict:
    data = live(Ledger(ledger_dir).entries())
    out.mkdir(parents=True, exist_ok=True)
    (out / "live.json").write_text(json.dumps(data, separators=(",", ":")))
    return data
