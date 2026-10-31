import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import agents, catalogs, crowd, scoring, spanish
from . import team as lab
from .fetch import client
from .firewall import as_of
from .live import BANDS, DAYS, now_mjd, observe
from .llm import LLM
from .site import _question

# a visitor picks a live object and the whole team investigates it; the run is shown on the site, never sealed
OBJECT = re.compile(r"^ZTF\d{2}[a-z]{7}$")
SHOWN = ("role", "lens", "model", "effort", "decision", "why", "cost_usd", "seconds", "error")
MIN_POINTS = 5  # the physics needs this many detections to fit anything


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clip(text: str) -> str:
    # the team's notes arrive cut at 200 characters; a visitor reads them up to their last whole sentence
    if len(text) < 200 or (text.endswith(".") and not text[-2:-1].isdigit()):  # "slow ~0." is a number cut short
        return text
    cut = text.rfind(". ")
    return text[:cut + 1] if cut > 0 else text.rstrip() + "…"


def said(lenses: dict) -> dict:
    # the skeptics' events carry no words, so the chat takes them from the result
    whole = lambda t: t if t.endswith((".", "…", "!", "?")) else t + "."
    name = str(lenses["memory"].get("name") or "").strip()[:80]
    return {"instrument": _clip(lenses["instrument"]["why"]),
            "physics": " ".join(f"{spanish.HYP.get(i['hypothesis'], (i['hypothesis'],))[0]}: {whole(_clip(i['why']))}"
                                for i in lenses["physics"]["implausible"] if i["why"]),
            "memory": name if lenses["memory"]["recognised"] and name.lower() not in ("null", "none") else ""}


def _rows(table: str) -> tuple[str, dict]:
    base = crowd._supabase()
    if base is None:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are needed to report to the site")
    return f"{base[0]}/rest/v1/{table}", base[1]


def load(c, ident: int) -> dict | None:
    url, headers = _rows("investigations")
    r = c.get(url, headers=headers, params={"id": f"eq.{ident}", "select": "id,object,status"})
    r.raise_for_status()
    return next(iter(r.json()), None)


def save(c, ident: int, **fields) -> None:
    url, headers = _rows("investigations")
    c.patch(url, headers=headers | {"Prefer": "return=minimal"}, params={"id": f"eq.{ident}"}, json=fields).raise_for_status()


def in_round(c, oid: str) -> bool:
    # an object in today's Beat SIRA round waits for the bell, or a visitor could read SIRA's sealed answer
    url, headers = _rows("questions")
    r = c.get(url, headers=headers, params={"select": "id", "object": f"eq.{oid}", "closes_at": f"gt.{_now()}"})
    r.raise_for_status()
    return bool(r.json())


def summary(view: dict, result: dict | None, reading: dict | None) -> dict:
    # what the site draws: the curve and its forecast, the bet in words, and the team's reasons
    now = view["as_of"]
    seen = [[round(r["mjd"] - now, 3), r["band"], round(r["flux"], 1), round(r["flux_err"], 1)]
            for r in view["photometry"] if r["kind"] == "det" and r["band"] in BANDS and r["flux"] > 0]
    out = {"seen": seen[-80:], "reader": reading}
    if result is None:
        return out | {"dropped": True}
    fan = []
    for f in result["forecasts"]:
        mean, sd = scoring.mix_moments(f["parts"])
        fan.append([round(f["mjd"] - now, 3), f["band"], round(mean, 1), round(sd, 1)])
    lenses = result["skeptics"]
    return out | {
        "question": _question(result.get("risky") or result["question"]),
        "term": result["wording"]["term"], "sentence": result["wording"]["text"],
        "classes": result.get("classes") or result["weights"],
        "theories": [{k: t[k] for k in ("hypothesis", "argument", "weakest_point")} for t in result["theories"]],
        "skeptics": {"instrument": lenses["instrument"], "physics": lenses["physics"]["implausible"],
                     "memory": {k: lenses["memory"].get(k) for k in ("recognised", "name")}},
        "director": {k: result["director"].get(k) for k in ("action", "question", "why")},
        "fan": fan,
    }


def run(oid: str, ident: int | None = None) -> dict:
    if not OBJECT.match(oid):
        raise ValueError(f"{oid} is not a ZTF object name")
    c, now = client(), now_mjd()
    if ident is not None:
        row = load(c, ident)
        if not row or row["object"] != oid or row["status"] != "queued":
            raise RuntimeError(f"investigation {ident} is not waiting for {oid}")
    write = (lambda **f: save(c, ident, **f)) if ident is not None else (lambda **f: None)
    write(status="running", started_at=_now())
    steps, es, asked, lock, spent = [], {}, set(), threading.Lock(), 0.0

    def rows():
        return [s | {"why_es": es[s["why"]]} if s.get("why") in es else s for s in steps]

    def show():
        # the Spanish lands from other threads, so the row is written by one at a time and always whole
        with lock:
            write(steps=rows(), cost_usd=round(sum(s["cost_usd"] for s in steps) + spent, 4))

    def translate(texts):
        # for the site only: no agent reads it, and if it fails the English stays
        nonlocal spent
        try:
            more, usd = spanish.translate(llm, texts)
            with lock:
                es.update(more)
                spent += usd
            show()
        except Exception as e:
            print(f"no Spanish for {len(texts)} notes: {type(e).__name__}", file=sys.stderr)

    def report(events, words=None):
        fresh = [{k: _clip(e[k]) if k == "why" else e[k] for k in SHOWN if k in e} for e in events]
        for s in fresh:
            if (words or {}).get(s.get("lens")):
                s["why"] = words[s["lens"]]
        with lock:
            steps[:] = fresh
        show()
        new = [w for w in dict.fromkeys(s.get("why") for s in fresh) if w and w not in asked]
        asked.update(new)
        if new:
            pool.submit(translate, new)

    try:
        if ident is not None and in_round(c, oid):
            raise RuntimeError("in_round")
        view = as_of(observe(c, oid, now), now)
        if sum(r["kind"] == "det" and r["band"] in BANDS and r["flux"] > 0 for r in view["photometry"]) < MIN_POINTS:
            raise RuntimeError("too_few_points")
        llm, ebv = LLM(), catalogs.mw_ebv(c, view["ra"], view["dec"])
        with ThreadPoolExecutor(8) as pool:
            # the model's own forecast starts at once, as in the nightly; no senior, to keep a visit cheap
            alone = pool.submit(agents.llm_only, llm, lab.case_of(view), DAYS, BANDS)
            readings, first = lab.eyes(llm, c, {oid: view}, pool)
            report(first)
            result, events = lab.investigate(llm, view, ebv, pool, [0], readings.get(oid), None, alone,
                                             report=lambda more: report(first + more))
            # leaving the pool waits for the last Spanish, so the site has it before it stops polling at done
            report(first + events, said(result["skeptics"]) if result else None)
        out = summary(view, result, readings.get(oid))
    except Exception as e:
        write(status="failed", error=str(e)[:200] if isinstance(e, RuntimeError) else type(e).__name__, finished_at=_now())
        raise
    write(status="done", result=out, finished_at=_now())
    return {"object": oid, "steps": rows(), "result": out}
