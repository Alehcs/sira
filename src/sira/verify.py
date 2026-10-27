import hashlib
from pathlib import Path

from . import live
from .ledger import GENESIS, Ledger, check_rfc3161, digest, mjd, ots_state

HOUR = 1 / 24


def _close(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 1e-3 * max(1.0, abs(b))
    return a == b


def verify(root: Path, c=None, online: bool = False, known: tuple = (), now: float | None = None) -> dict:
    root, problems = Path(root), []
    entries = Ledger(root).entries()
    prev = GENESIS
    for i, e in enumerate(entries):
        if e["seq"] != i or e["prev"] != prev or digest(e) != e["hash"]:
            problems.append(f"entry {i} breaks the chain")
        prev = e["hash"]
    for mark in known:
        # heads published elsewhere (a post, a log) must still be in the chain, or history was rewritten
        seq, h = mark.split(":")
        if int(seq) >= len(entries) or entries[int(seq)]["hash"] != h:
            problems.append(f"entry {mark} is no longer in the ledger: history was rewritten")
    sealed, ots = {}, {"bitcoin": 0, "pending": 0, "missing": 0, "mismatch": 0}
    for a in (e for e in entries if e["kind"] == "anchor"):
        p = a["payload"]
        if p["seq"] >= a["seq"] or entries[p["seq"]]["hash"] != p["head"]:
            problems.append(f"anchor {a['seq']} points at an entry that is not before it in the chain")
            continue
        doc = root / "receipts" / f"{p['head']}.json"
        if not doc.exists() or hashlib.sha256(doc.read_bytes()).hexdigest() != p["head"]:
            problems.append(f"anchor {a['seq']}: stamped document missing or altered")
        ok, when = check_rfc3161(root / p["rfc3161"], p["head"])
        if not ok:
            problems.append(f"anchor {a['seq']}: RFC 3161 receipt does not verify")
            continue
        if when != p.get("tsa_time"):
            problems.append(f"anchor {a['seq']}: recorded time differs from its receipt")
        sealed[p["seq"]] = mjd(when)
        state = ots_state(root / p["ots"], p["head"]) if p.get("ots") else "missing"
        ots[state] += 1
        if state == "mismatch":
            problems.append(f"anchor {a['seq']}: the OpenTimestamps proof is for another document")
    bets = {}
    for b in (e for e in entries if e["kind"] == "bet"):
        p = b["payload"]
        if p["bet"] in bets:
            problems.append(f"bet id {p['bet']} appears twice")
        times = [t for seq, t in sealed.items() if seq >= b["seq"]]
        p = p | {"_seal": min(times) if times else None, "_seq": b["seq"]}
        if p["_seal"] is not None and p.get("made_at") is not None and p["_seal"] - p["made_at"] > HOUR:
            problems.append(f"bet {p['bet']}: sealed more than an hour after it says it was made")
        bets[p["bet"]] = p
    outcomes = [e for e in entries if e["kind"] == "outcome"]
    for o in outcomes:
        p, bet = o["payload"], bets.get(o["payload"]["bet"])
        if bet is None or bet["_seal"] is None or p["mjd"] <= bet["_seal"] or o["seq"] < bet["_seq"]:
            problems.append(f"outcome {o['seq']}: measured before its bet was sealed")
            continue
        value = p.get("flux") if p["kind"] == "det" else p.get("limit")
        redo = live.measure(live._at(bet["forecasts"], p["mjd"], p["band"]), p["kind"], value, p.get("flux_err", 0.0))
        if not all(_close(redo[k], p.get(k)) for k in redo):
            problems.append(f"outcome {o['seq']}: its score does not follow from the sealed forecast")
    answers = [e for e in entries if e["kind"] == "answer"]
    for a in answers:
        p, bet = a["payload"], bets.get(a["payload"]["bet"])
        if bet is None or not bet.get("question"):
            problems.append(f"answer {a['seq']}: no sealed question to answer")
            continue
        mine = [o["payload"] for o in outcomes if o["payload"]["bet"] == p["bet"] and o["seq"] < a["seq"]
                and o["payload"]["mjd"] > (bet["_seal"] or float("inf"))]
        redo = live.settle(bet["question"], mine)
        if not all(_close(v, p.get(k)) for k, v in redo.items()):
            problems.append(f"answer {a['seq']}: does not follow from the sealed question and the scored measurements")
    if online:
        problems += _online(c, bets, outcomes, now if now is not None else live.now_mjd())
    n_sealed = sum(b["_seal"] is not None for b in bets.values())
    return {"entries": len(entries), "head": f"{entries[-1]['seq']}:{entries[-1]['hash']}" if entries else None,
            "anchors": len(sealed), "bets": len(bets), "bets_sealed": n_sealed, "outcomes": len(outcomes),
            "answers": len(answers), "ots": ots, "online": online, "problems": problems,
            "passes": not problems and n_sealed == len(bets)}


def _online(c, bets: dict, outcomes: list[dict], now: float) -> list[str]:
    # the archive is the judge: nothing scored may be invented, and once a window closes nothing may be missing
    problems = []
    for bet in bets.values():
        if bet["_seal"] is None:
            continue
        last = max(f["mjd"] for f in bet["forecasts"])
        rows = [r for r in live.observe(c, bet["object"], now)["photometry"]
                if r["band"] in live.BANDS and bet["_seal"] < r["mjd"] <= last + 1]
        actual = {(round(r["mjd"], 6), r["band"]): r for r in rows}
        scored = {(round(o["payload"]["mjd"], 6), o["payload"]["band"]): o["payload"] for o in outcomes
                  if o["payload"]["bet"] == bet["bet"]}
        for key, p in scored.items():
            r = actual.get(key)
            if r is None or (p["kind"] == "det" and not _close(round(r["flux"], 2), p["flux"])):
                problems.append(f"bet {bet['bet']}: a scored measurement at {key[0]} is not in the archive")
        if now > last + 3 and set(actual) - set(scored):
            problems.append(f"bet {bet['bet']}: {len(set(actual) - set(scored))} archive measurements left unscored")
    return problems
