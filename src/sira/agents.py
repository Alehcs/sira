import json
import math
import re
import time

from .config import SPARK_OPEN
from .costs import price
from .firewall import tripwire
from .llm import LLM, SPARK, WONDER, usage_of

# who does what, on which model, and how hard it thinks
ROLES = {
    "lookout": ("baseten", SPARK_OPEN, None),
    "theorist": ("meta", SPARK, "high"),
    "skeptic": ("meta", SPARK, "high"),
    "director": ("meta", SPARK, "xhigh"),
    "senior": ("meta", WONDER, "max"),
    "forecaster": ("meta", SPARK, "minimal"),
    "leverrier": ("meta", WONDER, "high"),
}
LAB = ("You work in SIRA, a lab of AI astronomers that bets in public on how cosmic transients will evolve and "
       "lets the sky grade every bet. You never see names, survey IDs, dates or exact positions: times are days "
       "relative to now (negative is the past) and fluxes are in microjansky. The lab's physics code supplies the "
       "numbers; your job is judgement. Reply with JSON only.")
HYPOTHESES = {
    "ia": "a type Ia supernova, a white dwarf that exploded",
    "ii": "a type II supernova, a hydrogen-rich massive star that collapsed",
    "ibc": "a type Ib/c supernova, a massive star stripped of its envelope",
    "tde": "a tidal disruption event, a star torn apart by a massive black hole",
    "null": "none of the hypotheses above",
}
LENSES = ("instrument", "physics", "memory")
# IPCC AR5 likelihood scale, used to check the forecaster's wording against the number
IPCC = [(0.99, "virtually certain"), (0.90, "very likely"), (0.66, "likely"), (0.33, "about as likely as not"),
        (0.10, "unlikely"), (0.01, "very unlikely"), (0.0, "exceptionally unlikely")]


def _json(text: str | None) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def call(llm: LLM, role: str, task: str, payload: dict, case: str) -> tuple[dict, dict]:
    provider, model, effort = ROLES[role]
    user = task + "\n\n" + json.dumps(payload, separators=(",", ":"))
    tripwire(user)
    kwargs = {"response_format": {"type": "json_object"}} | ({"reasoning_effort": effort} if effort else {})
    start, cost, data, error = time.time(), 0.0, {}, None
    try:
        r = llm.chat(provider, model, [{"role": "system", "content": LAB}, {"role": "user", "content": user}],
                     f"agent:{role}", **kwargs)
        cost, data = price(provider, model, usage_of(r)), _json(r.choices[0].message.content)
    except Exception as e:
        error = type(e).__name__
    event = {"role": role, "case": case, "model": model, "effort": effort, "cost_usd": round(cost, 5),
             "seconds": round(time.time() - start, 1)}
    return data, event | ({"error": error} if error else {})


def lookout(llm: LLM, case: dict) -> tuple[dict, dict]:
    task = ("You are a Lookout. Tonight there are more candidates than the lab can study; it investigates about "
            "fifteen. Decide whether this transient deserves a full investigation now. Favour real, well sampled "
            "transients whose next few days are uncertain; pass on sparse, noisy or stale ones. "
            'JSON: {"investigate": true or false, "priority": number from 0 to 1, "why": "one sentence"}')
    data, event = call(llm, "lookout", task, case, case["case"])
    priority = min(max(float(data.get("priority", 0.0) or 0.0), 0.0), 1.0)
    out = {"investigate": bool(data.get("investigate")), "priority": priority, "why": str(data.get("why", ""))[:200]}
    return out, event | {"decision": "investigate" if out["investigate"] else "pass", "priority": priority,
                         "why": out["why"]}


def theorist(llm: LLM, kind: str, case: dict, phys: dict) -> tuple[dict, dict]:
    task = (f"You are the theorist for {HYPOTHESES[kind]}. Make the honest best case for it from the light curve "
            "and its fit, name its weakest point, and give one measurement within the next five days that would "
            "refute it. Do not argue for the rivals. "
            'JSON: {"argument": "two sentences", "weakest_point": "one sentence", "refuted_if": {"band": "g" or "r", '
            '"day": 1 to 5, "direction": "above" or "below", "flux": number, "why": "one sentence"}}')
    payload = {"case": case, "hypothesis": kind, "fit": phys["summaries"][kind],
               "rivals": {k: round(v, 3) for k, v in phys["weights"].items() if k != kind}}
    data, event = call(llm, "theorist", task, payload, case["case"])
    ref = data.get("refuted_if") if isinstance(data.get("refuted_if"), dict) else {}
    try:
        ref = {"band": "ztf" + str(ref["band"]).strip().lower()[-1], "day": int(ref["day"]),
               "direction": "above" if str(ref["direction"]).startswith("a") else "below",
               "flux": round(float(ref["flux"]), 2), "why": str(ref.get("why", ""))[:200]}
        ok = ref["band"] in ("ztfg", "ztfr") and 1 <= ref["day"] <= 5 and ref["flux"] > 0
    except (KeyError, TypeError, ValueError):
        ok = False
    out = {"hypothesis": kind, "argument": str(data.get("argument", ""))[:400],
           "weakest_point": str(data.get("weakest_point", ""))[:200], "refuted_if": ref if ok else None}
    return out, event | {"decision": f"defends {kind}", "why": out["argument"][:200]}


def skeptic(llm: LLM, lens: str, case: dict, phys: dict) -> tuple[dict, dict]:
    tasks = {
        "instrument": ("You are the instrument skeptic. Look for signs that this is the detector and not the sky: "
                       "single-night spikes, flux jumping between nights faster than any explosion, detections "
                       "scattered around zero, or a light curve from a single night. "
                       'JSON: {"artifact": true or false, "confidence": number from 0 to 1, "why": "one sentence"}'),
        "physics": ("You are the physics skeptic. Using only the numbers given (peak absolute magnitude, nickel mass, "
                    "fitted redshift, colour, rise and decline), say which hypotheses are physically implausible and "
                    "why. Be strict but fair; lack of data is not implausibility. "
                    'JSON: {"implausible": [{"hypothesis": "name", "why": "one sentence"}]}'),
        "memory": ("You are the memory skeptic. Do you recognise this specific event from what you have read? If you "
                   "truly remember it, name it and what you remember; if not, say so plainly. "
                   'JSON: {"recognised": true or false, "name": "designation or null", "confidence": number from 0 to 1}'),
    }
    payload = {"case": case, "hypotheses": phys["summaries"], "killed_by_physics_code": phys["killed"]}
    data, event = call(llm, "skeptic", tasks[lens], payload, case["case"])
    if lens == "instrument":
        out = {"artifact": bool(data.get("artifact")), "confidence": min(max(float(data.get("confidence", 0) or 0), 0), 1),
               "why": str(data.get("why", ""))[:200]}
        decision = "artifact" if out["artifact"] else "real"
    elif lens == "physics":
        items = data.get("implausible") if isinstance(data.get("implausible"), list) else []
        out = {"implausible": [{"hypothesis": str(i.get("hypothesis", "")).lower(), "why": str(i.get("why", ""))[:200]}
                               for i in items if isinstance(i, dict) and str(i.get("hypothesis", "")).lower() in HYPOTHESES]}
        decision = "doubts " + ", ".join(i["hypothesis"] for i in out["implausible"]) if out["implausible"] else "no objection"
    else:
        out = {"recognised": bool(data.get("recognised")), "name": data.get("name"),
               "confidence": min(max(float(data.get("confidence", 0) or 0), 0), 1)}
        decision = "recognises it" if out["recognised"] else "does not recognise it"
    return out, event | {"lens": lens, "decision": decision}


def director(llm: LLM, case: dict, state: dict, senior: bool = False) -> tuple[dict, dict]:
    role = "senior" if senior else "director"
    if senior:
        task = ("You are the senior reviewer. Weigh the hypotheses, the theorists' cases and the skeptics' objections. "
                "Say which hypothesis the evidence favours, whether an explanation outside the list would fit better, "
                "and choose the question to stake. You may rescale hypotheses by factors between 0.3 and 3. "
                'JSON: {"favoured": "name", "missing": "one sentence or null", "question": "id", '
                '"factors": {"name": number}, "why": "two sentences"}')
    else:
        task = ("You are the director. The lab's forecast for this object is sealed tonight in any case; you choose "
                "which yes/no question to stake on it. Prefer the question whose answer teaches the most (bits). If "
                "every question is near-certain, stake the one that could refute the leading hypothesis: a sure "
                "prediction that fails is the most valuable lesson. Escalate to the senior reviewer only when the "
                "hypotheses disagree strongly and the sky will not settle it within days. "
                'JSON: {"action": "bet" or "escalate", "question": "id", "why": "one sentence"}')
    data, event = call(llm, role, task, state, case["case"])
    ids = {q["id"] for q in state["questions"]}
    out = {"action": "escalate" if data.get("action") == "escalate" else "bet",
           "question": data.get("question") if data.get("question") in ids else state["questions"][0]["id"],
           "why": str(data.get("why", ""))[:300]}
    if senior:
        factors = data.get("factors") if isinstance(data.get("factors"), dict) else {}
        out |= {"favoured": str(data.get("favoured", "")), "missing": data.get("missing"),
                "factors": {k: min(max(float(v), 0.3), 3.0) for k, v in factors.items()
                            if k in HYPOTHESES and isinstance(v, (int, float))}}
    return out, event | {"decision": out.get("action", "review") + f" {out['question']}", "why": out["why"][:200]}


def ipcc(p: float) -> str:
    return next(term for floor, term in IPCC if p >= floor)


def forecaster(llm: LLM, case: dict, question: dict) -> tuple[dict, dict]:
    task = ("You are the forecaster. Write the staked question as one plain sentence a non-astronomer understands, "
            "with the IPCC likelihood term that matches the probability: virtually certain (99% or more), very likely "
            "(90%+), likely (66%+), about as likely as not (33-66%), unlikely (below 33%), very unlikely (below 10%), "
            'exceptionally unlikely (below 1%). JSON: {"text": "one sentence"}')
    data, event = call(llm, "forecaster", task, {"question": question["text"], "p_yes": question["p_yes"]}, case["case"])
    text = str(data.get("text", ""))[:300]
    # P3: the words must match the number
    out = {"text": text, "term": ipcc(question["p_yes"]), "words_match": ipcc(question["p_yes"]) in text.lower()}
    return out, event | {"decision": "words the bet", "why": text[:200]}


def bits(parts: list, reference: float, direction: str, chance) -> float:
    # what a yes/no answer would tell us about which hypothesis is right
    h = lambda p: 0.0 if p <= 0 or p >= 1 else -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
    w = sum(p[1] for p in parts)
    each = [(p[1] / w, chance([p], reference, direction)) for p in parts]
    return max(h(sum(wk * pk for wk, pk in each)) - sum(wk * h(pk) for wk, pk in each), 0.0)
