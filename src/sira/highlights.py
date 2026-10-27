from pathlib import Path

from .ledger import Ledger

# how much a moment is worth to a viewer: verdicts above proposals above surprises above everyday bets
WEIGHT = {"verdict": 5, "leap": 4, "surprise": 3, "upset": 3, "duel": 2, "senior": 2, "risky": 2, "doubt": 1, "kill": 1}
DUEL = 5.0  # nats of total log score between SIRA and climatology on one bet that make a duel worth showing


def highlights(root: Path, top: int = 20) -> list[dict]:
    entries = Ledger(root).entries()
    bets = {e["payload"]["bet"]: e["payload"] for e in entries if e["kind"] == "bet"}
    moments = []

    def add(e, kind, text):
        moments.append({"seq": e["seq"], "time": e["time"], "object": e["payload"].get("object"), "kind": kind,
                        "weight": WEIGHT[kind], "text": text})

    for e in entries:
        p, kind = e["payload"], e["kind"]
        if kind == "verdict":
            word = {"neptune": "Neptune, the new idea won", "vulcan": "Vulcan, the new idea failed",
                    "abstain": "no verdict, the sky did not decide"}[p["verdict"]]
            add(e, "verdict", f"{word} (log10 e = {p['log10_e']} over {p['n']} measurements)")
        elif kind == "surprise":
            add(e, "surprise", f"the sealed forecast failed: {p['misses']} of {p['n']} measurements far outside it "
                               f"(p = {p['p_value']:.1g})")
        elif kind == "bet" and p.get("model") == "leverrier":
            add(e, "leap", f"Le Verrier proposed '{p['chosen']}' against the usual hypotheses")
        elif kind == "bet":
            for name, why in p.get("killed", {}).items():
                add(e, "kill", f"physics ruled out {name}: {why}")
            for item in ((p.get("skeptics") or {}).get("physics") or {}).get("implausible", []):
                add(e, "doubt", f"the physics skeptic doubted {item['hypothesis']}: {item['why']}")
            senior = (p.get("director") or {}).get("senior")
            if senior:
                how = "a random audit sent" if p["director"].get("audit") else "the director escalated"
                add(e, "senior", f"{how} the case to Wonder, which favoured {senior.get('favoured')}")
            if p.get("risky"):
                add(e, "risky", f"staked: {p['risky']['text']} (p = {p['risky']['p_yes']})")
        elif kind == "answer" and not p.get("void"):
            question = bets.get(p["bet"], {}).get(p.get("which", "question")) or {}
            upset = (p["yes"] and p["p_yes"] < 0.2) or (not p["yes"] and p["p_yes"] > 0.8)
            if upset or p.get("which") == "risky":
                add(e, "upset" if upset else "risky",
                    f"{question.get('text', 'the question')} came out {'yes' if p['yes'] else 'no'} at p = {p['p_yes']}")
    duels = {}
    for e in entries:
        p = e["payload"]
        if e["kind"] == "outcome" and "b0" in p.get("baselines", {}):
            duels.setdefault(p["bet"], [e, 0.0])[1] += p["log_score"] - p["baselines"]["b0"]["log_score"]
    for bet_id, (last, margin) in duels.items():
        if abs(margin) >= DUEL:
            who = "SIRA beat climatology" if margin > 0 else "climatology beat SIRA"
            add(last, "duel", f"{who} on {bets.get(bet_id, {}).get('object', bet_id)} by {abs(margin):.1f} nats of log score")
    moments.sort(key=lambda m: (-m["weight"], -m["seq"]))
    return moments[:top]
