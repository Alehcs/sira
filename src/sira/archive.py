import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import astropy.units as u
from astropy.coordinates import SkyCoord

from . import scoring
from .site import READING, _date, _images, _question, _sealed_at, _staked

EMBARGO = timedelta(hours=48)  # crowd.picks draws a round's objects from bets made in the last two days
TEAM = ("llm_only", "theorist", "skeptic", "director", "senior", "forecaster", "lab")
CHILE = ZoneInfo("America/Santiago")
COLUMNS = ("object", "ra", "dec", "night", "lookout_votes", "lookout_priority", "lookouts_picked", "reader_label",
           "reader_p_real", "reader_votes", "bet", "model", "question", "p_yes", "term", "seal_sha256", "sealed_at",
           "open_at", "class_top", "class_p", "outcomes", "log_scores", "answer")


def night_of(time: str) -> str:
    # a night is named by its evening in Chile, where the nightly runs
    return datetime.fromisoformat(time).astimezone(CHILE).date().isoformat()


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fan(forecasts: list[dict], band: str) -> list[list]:
    # each forecast day as mean and spread, enough to draw the bet's band
    return [[f["mjd"], *(round(x, 2) for x in scoring.mix_moments(f["parts"]))] for f in forecasts if f["band"] == band]


def _bet(e: dict, night: str, sealed, bells: dict, now: datetime) -> dict:
    p, which = e["payload"], _staked(e["payload"])
    made = datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=p["made_at"])
    # a bet drawn into a Beat SIRA round stays shut until that round's bell, even past 48 hours
    opens = max([made + EMBARGO] + [datetime.fromisoformat(t) for t in bells.get(p["object"], [])])
    bet = {"bet": p["bet"], "night": night, "at": e["time"], "seq": e["seq"], "hash": e["hash"], "model": p.get("model"),
           "made_at": _date(p["made_at"]), "sealed_at": sealed(e["seq"]), "n_points": p.get("n_points"),
           "staked": which, "question": _question(p[which]), "term": (p.get("wording") or {}).get("term"),
           "open_at": _iso(opens), "open": now >= opens}
    if bet["open"]:
        # once no round can draw it, the bet shows everything it holds
        bet |= {"standard": _question(p["question"]) if p.get("question") else None,
                "risky": _question(p["risky"]) if p.get("risky") else None, "classes": p.get("classes"),
                "weights": p.get("weights"), "killed": p.get("killed"), "wording": (p.get("wording") or {}).get("text"),
                "director": p.get("director"), "theories": p.get("theories"), "skeptics": p.get("skeptics"),
                "seen": p.get("seen"), "fan": {b: _fan(p["forecasts"], b) for b in ("ztfg", "ztfr")}}
    return bet


def build(entries: list[dict], pics: dict, now: datetime) -> dict:
    # the Archive tab: one record per object the lab ever weighed, from the public ledger alone
    from .visits import _clip

    sealed, bells, shut, objs = _sealed_at(entries), {}, set(), {}
    for e in entries:
        if e["kind"] == "round":
            for q in e["payload"]["questions"]:
                bells.setdefault(q["object"], []).append(e["payload"]["closes_at"])

    def obj(oid):
        return objs.setdefault(oid, {"object": oid, "looks": [], "reads": [], "team": [], "bets": [], "outcomes": [],
                                     "answers": []})

    for e in entries:
        p = e["payload"]
        if not p.get("object") or "round" in p or "-leap-" in p.get("bet", ""):
            continue
        night, o = night_of(e["time"]), obj(p["object"])
        if e["kind"] == "event":
            base = {"night": night, "at": e["time"], "seq": e["seq"], "model": p.get("model"), "effort": p.get("effort"),
                    "seconds": p.get("seconds"), "cost_usd": p.get("cost_usd"), "why": _clip(p["why"]) if p.get("why") else None}
            if p["role"] == "lookout":
                o["looks"].append(base | {"decision": p["decision"], "priority": p.get("priority")})
            elif p["role"] == "reader":
                m = READING.match(p["decision"])
                o["reads"].append(base | {"label": m[1] if m else None, "p_real": float(m[2]) if m else None,
                                          "votes": p.get("votes")})
            elif p["role"] in TEAM:
                o["team"].append(base | {"role": p["role"], "lens": p.get("lens"), "decision": p["decision"]})
        elif e["kind"] == "bet" and p.get(_staked(p)):
            o["bets"].append(_bet(e, night, sealed, bells, now))
            if not o["bets"][-1]["open"]:
                shut.add(p["bet"])
        elif e["kind"] == "outcome":
            row = {"bet": p["bet"], "night": night, "at": e["time"], "band": p["band"], "mjd": p["mjd"], "kind": p["kind"],
                   "flux": p.get("flux"), "flux_err": p.get("flux_err"), "limit": p.get("limit")}
            # how a shut bet scored would hint at its forecast, so only the measurement shows until it opens
            if p["bet"] not in shut:
                row |= {"log_score": p["log_score"], "pit": p.get("pit"), "crps": p.get("crps"),
                        "baselines": {k: v["log_score"] for k, v in (p.get("baselines") or {}).items()}}
            o["outcomes"].append(row)
        elif e["kind"] == "answer":
            o["answers"].append({"bet": p["bet"], "which": p.get("which", "question"), "night": night, "at": e["time"],
                                 "void": bool(p.get("void")), "yes": None if p.get("void") else p["yes"],
                                 "log_score": p.get("log_score"), "measured": _date(p["mjd"]) if p.get("mjd") else None})

    for o in objs.values():
        o["nights"] = sorted({x["night"] for x in o["looks"] + o["reads"] + o["team"] + o["bets"]})
        o["first"], o["last"] = (o["nights"][0], o["nights"][-1]) if o["nights"] else (None, None)
        o["shut"] = {b["night"]: b["open_at"] for b in o["bets"] if not b["open"]}
        # the team's words on a bet still shut stay out of the export, not only out of sight
        o["team"] = [t for t in o["team"] if t["night"] not in o["shut"]]
        for before, r in zip([None] + o["reads"], o["reads"]):
            r["changed"] = before is not None and r["label"] != before["label"]
        by = {}
        for lk in o["looks"]:
            by.setdefault(lk["night"], []).append(lk)
        o["lookouts"] = [{"night": n, "votes": len(v), "priority": round(sum(x["priority"] or 0 for x in v) / len(v), 2),
                          "picked": 2 * sum(x["decision"] == "investigate" for x in v) > len(v)} for n, v in sorted(by.items())]
        found = pics.get(o["object"]) or {}
        o["ra"], o["dec"], o["l"], o["b"] = found.get("ra"), found.get("dec"), None, None
        if o["ra"] is not None:
            g = SkyCoord(ra=o["ra"] * u.deg, dec=o["dec"] * u.deg).galactic
            o["l"], o["b"] = round(float(g.l.deg), 2), round(float(g.b.deg), 2)
        seen = [r[0] for b in o["bets"] for r in b.get("seen") or [] if r[2] == "det"]
        first = found.get("first") or (min(seen) if seen else None)
        o["first_detection"] = _date(first) if first else None
        o["images"] = _images(found)

    nights = {}
    for e in entries:
        p = e["payload"]
        if e["kind"] not in ("event", "bet", "outcome") or "round" in p or "-leap-" in p.get("bet", ""):
            continue
        n = nights.setdefault(night_of(e["time"]), {"night": night_of(e["time"]), "start": e["time"], "weighed": set(),
                                                     "objects": set(), "bets": 0, "outcomes": 0, "sealed": None})
        if e["kind"] == "event" and p.get("role") == "lookout":
            n["weighed"].add(p["object"])
        if p.get("object"):
            n["objects"].add(p["object"])
        n["bets"] += e["kind"] == "bet"
        n["outcomes"] += e["kind"] == "outcome"
        n["sealed"] = sealed(e["seq"])
    head = next((e["payload"] for e in reversed(entries) if e["kind"] == "anchor"), {})
    return {"built_at": _iso(now), "head": {"hash": head.get("head"), "tsa_time": head.get("tsa_time"), "run": head.get("run"),
                                            "seq": head.get("seq")},
            "entries": len(entries), "embargo_hours": int(EMBARGO.total_seconds() // 3600),
            "nights": [n | {"weighed": len(n["weighed"]), "objects": len(n["objects"])} for _, n in sorted(nights.items())],
            "objects": sorted(objs.values(), key=lambda o: o["object"])}


def table(book: dict, path: Path) -> None:
    # one row per object and night, for a spreadsheet
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for o in book["objects"]:
            for n in o["nights"]:
                lk = next((x for x in o["lookouts"] if x["night"] == n), {})
                rd = next((x for x in reversed(o["reads"]) if x["night"] == n), {})
                for b in [x for x in o["bets"] if x["night"] == n] or [{}]:
                    q, odds = b.get("question") or {}, b.get("classes") or b.get("weights") or {}
                    top = max(odds.items(), key=lambda kv: kv[1]) if odds else ("", "")
                    outs = [x for x in o["outcomes"] if b and x["bet"] == b["bet"]]
                    said = next((a for a in o["answers"] if b and a["bet"] == b["bet"] and a["which"] == b["staked"]), None)
                    w.writerow([o["object"], o["ra"], o["dec"], n, lk.get("votes"), lk.get("priority"),
                                int(lk["picked"]) if lk else None, rd.get("label"), rd.get("p_real"), rd.get("votes"),
                                b.get("bet"), b.get("model"), q.get("text"), q.get("p"), b.get("term"), b.get("hash"),
                                b.get("sealed_at"), b.get("open_at"), *top, len(outs),
                                " ".join(str(x["log_score"]) for x in outs if "log_score" in x),
                                ("void" if said["void"] else "yes" if said["yes"] else "no") if said else None])
