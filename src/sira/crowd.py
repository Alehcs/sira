import base64
import hashlib
import hmac
import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone

from . import live, photometry
from .firewall import as_of
from .ledger import Ledger, jcs, mjd

PER_ROUND = 3
TEAM = ("v1", "v2")
CLOSE = time(21, 0)  # 18:00 in Chile, before night falls at Palomar
LAST_OPEN = time(20, 30)  # GitHub can start the job hours late; a round this near the bell is not opened
OPEN_DELAY = timedelta(minutes=5)  # bets open a little after SIRA's answers are sealed
MIN_DETS, MIN_R = 10, 4  # a light curve worth betting on
FRESH = 5  # days since the last r detection; ZTF can skip a field for a few nights
SENIORS = 1  # Wonder at max effort, at most once a round
TEXT = "Brighter in r three days from now than at its last r detection?"


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _master() -> bytes:
    key = os.getenv("SIRA_ENVELOPE_KEY", "")
    if not key:
        raise RuntimeError("SIRA_ENVELOPE_KEY is not set")
    try:
        return bytes.fromhex(key)
    except ValueError:
        return key.encode()


def _mac(key: bytes, label: str) -> bytes:
    return hmac.new(key, label.encode(), hashlib.sha256).digest()


def _stream(key: bytes, n: int) -> bytes:
    # HMAC-SHA256 in counter mode: a keystream from the standard library alone
    out, i = b"", 0
    while len(out) < n:
        out += hmac.new(key, i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return out[:n]


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, _stream(key, len(data))))


def envelope(master: bytes, qid: str, p_yes: float) -> dict:
    salt, key = _mac(master, "salt:" + qid), _mac(master, "key:" + qid)
    plain = jcs({"p_yes": p_yes}).encode()
    return {"commit": hashlib.sha256(salt + plain).hexdigest(), "sealed": base64.b64encode(_xor(plain, key)).decode(),
            "salt": salt.hex(), "key": key.hex()}


def opens(question: dict, answer: dict) -> bool:
    # the revealed salt must match the commitment, and the revealed key must open the sealed answer to the same number
    plain = jcs({"p_yes": answer["p_yes"]}).encode()
    try:
        salt, key = bytes.fromhex(answer["salt"]), bytes.fromhex(answer["key"])
        body = base64.b64decode(question["sealed"])
    except ValueError:
        return False
    return hashlib.sha256(salt + plain).hexdigest() == question["commit"] and _xor(body, key) == plain


def unseal(master: bytes, question: dict) -> dict:
    key = _mac(master, "key:" + question["id"])
    answer = {"id": question["id"], "p_yes": json.loads(_xor(base64.b64decode(question["sealed"]), key))["p_yes"],
              "salt": _mac(master, "salt:" + question["id"]).hex(), "key": key.hex()}
    if not opens(question, answer):
        raise RuntimeError(f"{question['id']}: the sealed answer does not match its commitment")
    return answer


def player(user_id: str) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]


def log_score(p: float, yes: bool) -> float:
    return round(math.log(p if yes else 1 - p), 4)


def scores(p_sira: float, bets: list[dict], yes: bool) -> dict:
    # the crowd is the plain mean of the humans; SIRA + crowd averages the two forecasts
    humans = [b["p_yes"] for b in bets]
    crowd = sum(humans) / len(humans) if humans else None
    return {"sira": log_score(p_sira, yes), "crowd": log_score(crowd, yes) if humans else None,
            "sira_crowd": log_score((p_sira + crowd) / 2, yes) if humans else None,
            "players": {b["player"]: log_score(b["p_yes"], yes) for b in bets}}


def _seal_of(entries: list[dict], seq: int) -> float | None:
    times = [mjd(e["payload"]["tsa_time"]) for e in entries if e["kind"] == "anchor" and e["payload"]["seq"] >= seq]
    return min(times) if times else None


def _by(entries: list[dict], kind: str, key: str = "round") -> dict:
    return {e["payload"][key]: e for e in entries if e["kind"] == kind}


def _supabase() -> tuple[str, dict] | None:
    url, key = os.getenv("SUPABASE_URL", "").rstrip("/"), os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # a legacy JWT key also goes as the bearer token; the new secret keys must not
        headers["Authorization"] = f"Bearer {key}"
    return url, headers


def publish(c, payload: dict) -> int:
    base = _supabase()
    if base is None:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are needed to open the questions")
    url, headers = base
    rows = [{"id": q["id"], "round": payload["round"], "object": q["object"], "text": q["text"], "band": q["band"],
             "mjd": q["mjd"], "direction": q["direction"], "reference": q["reference"], "seen": q["seen"],
             "commit": q["commit"], "opens_at": payload["opens_at"], "closes_at": payload["closes_at"]}
            for q in payload["questions"]]
    r = c.post(f"{url}/rest/v1/questions", params={"on_conflict": "id"}, json=rows,
               headers=headers | {"Prefer": "resolution=merge-duplicates,return=minimal"})
    r.raise_for_status()
    return len(rows)


def fetch_bets(c, ids: list[str], page: int = 1000) -> list[dict]:
    url, headers = _supabase()
    out = []
    while True:
        r = c.get(f"{url}/rest/v1/bets", headers=headers, params={
            "select": "question_id,user_id,handle,p_yes,created_at", "order": "id",
            "question_id": "in.(" + ",".join(f'"{i}"' for i in ids) + ")", "limit": page, "offset": len(out)})
        r.raise_for_status()
        rows = r.json()
        out += rows
        if len(rows) < page:
            return out


def picks(entries: list[dict], c, now: float, look=None) -> list[dict]:
    # the latest night's team bets, still active and well sampled, best sampled first
    look = look or (lambda oid, t: live.observe(c, oid, t))
    bets = [e["payload"] for e in entries if e["kind"] == "bet" and e["payload"].get("model") not in (None, "leverrier")
            and e["payload"]["made_at"] > now - 2]
    bets.sort(key=lambda b: (b.get("model") not in TEAM, -(b.get("n_points") or 0)))
    views, tried = [], set()
    for b in bets:
        if b["object"] in tried or len(views) >= 2 * PER_ROUND:
            continue
        tried.add(b["object"])
        try:
            view = as_of(look(b["object"], now), now)
        except Exception:
            continue
        dets = [r for r in view["photometry"] if r["kind"] == "det" and r["band"] in live.BANDS]
        red = [r for r in dets if r["band"] == "ztfr" and r["flux"] > 0]
        if len(dets) >= MIN_DETS and len(red) >= MIN_R and max(r["mjd"] for r in red) >= now - FRESH:
            views.append(view)
    return views


def _quiet(e: dict) -> dict:
    # before the bell the ledger shows who worked and what it cost, never what they said
    return {k: e[k] for k in ("role", "model", "effort", "cost_usd", "seconds", "object", "case") if k in e}


def forecasts(llm, c, views: list[dict], entries: list[dict], pool, budget: float) -> tuple[list, list, float, list]:
    from . import agents, catalogs
    from . import team as lab
    from .leverrier import adopted

    readings, events = lab.eyes(llm, c, {v["oid"]: v for v in views}, pool)
    spent, made, seniors, passed = sum(e["cost_usd"] for e in events), [], [SENIORS], []
    for view in views:
        if len(made) >= PER_ROUND or spent >= budget:
            break
        # the same v2 forecast the nightly seals: the team's physics pooled with the model's own forecast
        alone = pool.submit(agents.llm_only, llm, lab.case_of(view), live.DAYS, live.BANDS)
        try:
            result, more = lab.investigate(llm, view, catalogs.mw_ebv(c, view["ra"], view["dec"]), pool, seniors,
                                           readings.get(view["oid"]), adopted(entries, view["oid"]), alone)
        except Exception as e:
            passed.append(f"{view['oid']}: {type(e).__name__}")
            continue
        events += [e | {"object": view["oid"]} for e in more]
        spent += sum(e["cost_usd"] for e in more)
        if result and result.get("question"):
            made.append((view, result["question"]))
        else:
            passed.append(f"{view['oid']}: the team passed")
    return made, events, spent, passed


def open_round(ledger: Ledger, c, llm, now: datetime, pool, budget: float = 2.0, dry: bool = False, look=None) -> dict:
    day, entries = now.date().isoformat(), ledger.entries()
    last = datetime.combine(now.date(), LAST_OPEN, timezone.utc)
    if day in _by(entries, "round"):
        return {"skipped": f"round {day} is already open"}
    if now + OPEN_DELAY > last:
        return {"skipped": f"too late to open round {day}: it would close in under 30 minutes"}
    master = None if dry else _master()
    t = mjd(_iso(now))
    views = picks(entries, c, t, look)
    made, events, spent, passed = forecasts(llm, c, views, entries, pool, budget)
    if not made:
        return {"skipped": "no object gave a question", "passed": passed, "spent_usd": round(spent, 4)}
    # the team takes minutes, so bets open a little after its answers are ready, not after the job started
    ready = _now()
    if ready + OPEN_DELAY > last:
        return {"skipped": f"too late to open round {day}: its answers were ready at {ready:%H:%M} UTC, "
                           "so it would close in under 30 minutes", "passed": passed, "spent_usd": round(spent, 4)}
    opens_at, closes_at = _iso(ready + OPEN_DELAY), _iso(datetime.combine(now.date(), CLOSE, timezone.utc))
    questions, answers = [], []
    for i, (view, q) in enumerate(made, 1):
        qid = f"{day}-{i}"
        questions.append({"id": qid, "object": view["oid"], "text": TEXT, "band": q["band"], "mjd": q["mjd"],
                          "direction": q["direction"], "reference": q["reference"], "seen": live.seen(view)})
        answers.append(q["p_yes"])
    if dry:
        return {"round": day, "opens_at": opens_at, "closes_at": closes_at, "spent_usd": round(spent, 4), "passed": passed,
                "questions": [{k: v for k, v in q.items() if k != "seen"} | {"points": len(q["seen"]), "p_yes": p}
                              for q, p in zip(questions, answers)]}
    for q, p in zip(questions, answers):
        q |= {k: v for k, v in envelope(master, q["id"], p).items() if k in ("commit", "sealed")}
    before = ledger.path.read_bytes() if ledger.path.exists() else b""
    for e in events:
        ledger.append("event", _quiet(e) | {"round": day})
    entry = ledger.append("round", {"round": day, "opens_at": opens_at, "closes_at": closes_at, "model": "v2",
                                    "cost_usd": round(spent, 4), "questions": questions})
    try:
        anchor = ledger.anchor(c)
        stamped = anchor["payload"]["tsa_time"]
        if mjd(stamped) > mjd(opens_at):
            raise RuntimeError(f"round {day} was stamped at {stamped}, after it was due to open at {opens_at}, "
                               "so it was taken back")
    except BaseException:
        # nothing was published yet, so a round that could not be stamped in time is taken back whole
        ledger.path.write_bytes(before)
        for f in ledger.receipts.glob(entry["hash"] + ".*"):
            f.unlink()
        raise
    return {"round": day, "questions": [q["id"] for q in questions], "opens_at": opens_at, "closes_at": closes_at,
            "spent_usd": round(spent, 4), "passed": passed, "anchor": anchor["payload"]}


def publish_round(ledger: Ledger, c, now: datetime) -> dict:
    entries, day = ledger.entries(), now.date().isoformat()
    r = _by(entries, "round").get(day)
    if r is None:
        return {"skipped": f"no round {day} in the ledger"}
    if now.time() >= LAST_OPEN:
        return {"skipped": f"too late to open round {day}"}
    seal = _seal_of(entries, r["seq"])
    if seal is None or seal > mjd(r["payload"]["opens_at"]):
        return {"skipped": f"round {day} is not sealed before it opens, so it stays closed"}
    return {"round": day, "published": publish(c, r["payload"])}


def close_rounds(ledger: Ledger, c, now: float) -> list[dict]:
    # after the bell: seal the humans' bets, stamp them, then reveal SIRA's answers
    new = []
    for day, r in _by(ledger.entries(), "round").items():
        p = r["payload"]
        if mjd(p["closes_at"]) > now or day in _by(ledger.entries(), "reveal"):
            continue
        master = _master()
        if _supabase() is None:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are needed to close a round")
        ids, opened, closed = [q["id"] for q in p["questions"]], mjd(p["opens_at"]), mjd(p["closes_at"])
        if day not in _by(ledger.entries(), "crowd"):
            kept, seen = [], set()
            for b in fetch_bets(c, ids):
                made = _iso(datetime.fromisoformat(b["created_at"]))
                who = player(b["user_id"])
                if b["question_id"] in ids and opened <= mjd(made) <= closed and (b["question_id"], who) not in seen:
                    seen.add((b["question_id"], who))
                    kept.append({"question": b["question_id"], "player": who, "handle": b["handle"],
                                 "p_yes": float(b["p_yes"]), "made_at": made})
            new.append(ledger.append("crowd", {"round": day, "bets": kept}))
        entries = ledger.entries()
        crowd = _by(entries, "crowd")[day]
        stamped = [e for e in entries if e["kind"] == "anchor" and e["seq"] > crowd["seq"]
                   and mjd(e["payload"]["tsa_time"]) >= closed]
        if not stamped:
            anchor = ledger.anchor(c)
            if anchor is None or mjd(anchor["payload"]["tsa_time"]) < closed:
                raise RuntimeError(f"round {day}: no stamp after the bell, so SIRA's answers stay sealed")
            new.append(anchor)
        new.append(ledger.append("reveal", {"round": day, "answers": [unseal(master, q) for q in p["questions"]]}))
    return new


def settle(question: dict, rows: list[dict], after: float) -> dict | None:
    # the first r measurement within a day of the question's time, taken after the humans' bets were sealed
    near = [r for r in rows if r["band"] == question["band"] and r["mjd"] > after and abs(r["mjd"] - question["mjd"]) <= 1]
    if not near:
        return None
    first = min(near, key=lambda r: r["mjd"])
    above = question.get("direction", "above") == "above"
    if first["kind"] == "det":
        value = round(first["flux"], 2)
        return {"mjd": first["mjd"], "kind": "det", "flux": value, "yes": (value > question["reference"]) == above}
    value = round(photometry.flux(first["mag"], 0)[0], 2) if "mag" in first else first["flux"]
    # a limit below the reference rules out brighter; a limit above it leaves the question open
    return {"mjd": first["mjd"], "kind": "limit", "flux": value, "yes": False if value < question["reference"] else None}


def score_rounds(ledger: Ledger, c, now: float, look=None) -> list[dict]:
    look = look or (lambda oid, t: live.observe(c, oid, t))
    entries = ledger.entries()
    reveals, crowds = _by(entries, "reveal"), _by(entries, "crowd")
    answered = set(_by(entries, "crowd_answer", "question"))
    new = []
    for day, r in _by(entries, "round").items():
        if day not in reveals or day not in crowds:
            continue
        after = _seal_of(entries, crowds[day]["seq"])
        sira = {a["id"]: a["p_yes"] for a in reveals[day]["payload"]["answers"]}
        for q in r["payload"]["questions"]:
            if q["id"] in answered or now <= q["mjd"] + 1.5 or after is None:
                continue
            got = settle(q, look(q["object"], now)["photometry"], after)
            head = {"question": q["id"], "round": day}
            if got is None or got["yes"] is None:
                new.append(ledger.append("crowd_answer", head | {"void": True}))
                continue
            bets = [b for b in crowds[day]["payload"]["bets"] if b["question"] == q["id"]]
            new.append(ledger.append("crowd_answer", head | {k: got[k] for k in ("yes", "mjd", "kind", "flux")}
                                     | {"scores": scores(sira[q["id"]], bets, got["yes"])}))
    return new


def night(ledger: Ledger, c, now: float, look=None) -> dict:
    # the nightly's part: close the rounds past their bell, then score the questions the sky has answered
    out = {"closed": 0, "answered": 0, "skipped": []}
    if not _by(ledger.entries(), "round"):
        return out
    try:
        out["closed"] = sum(e["kind"] == "reveal" for e in close_rounds(ledger, c, now))
    except Exception as e:
        out["skipped"].append(f"closing rounds: {type(e).__name__}: {e}")
    try:
        out["answered"] = len(score_rounds(ledger, c, now, look))
    except Exception as e:
        out["skipped"].append(f"scoring rounds: {type(e).__name__}: {e}")
    return out


def check(entries: list[dict], sealed: dict, online: bool = False, c=None, now: float | None = None) -> tuple[list, dict]:
    # what verify recomputes: commitments, the bell, the humans' bets and every score
    problems = []
    seal = lambda seq: min((t for head, t in sealed.items() if head >= seq), default=None)
    stamped = [(e["seq"], sealed.get(e["payload"]["seq"])) for e in entries if e["kind"] == "anchor"]
    rounds, questions = {}, {}
    for e in (e for e in entries if e["kind"] == "round"):
        p = e["payload"]
        if p["round"] in rounds:
            problems.append(f"round {p['round']} appears twice")
        rounds[p["round"]] = e
        s = seal(e["seq"])
        if s is None or s > mjd(p["opens_at"]):
            problems.append(f"round {p['round']}: not sealed before its questions opened")
        if mjd(p["opens_at"]) > mjd(p["closes_at"]) - 25 / 1440:
            problems.append(f"round {p['round']}: opened too close to its bell")
        for q in p["questions"]:
            if q["id"] in questions:
                problems.append(f"question {q['id']} appears twice")
            questions[q["id"]] = q | {"_round": p["round"]}
    crowds, reveals = {}, {}
    for e in (e for e in entries if e["kind"] == "crowd"):
        p, r = e["payload"], rounds.get(e["payload"]["round"])
        if r is None or p["round"] in crowds:
            problems.append(f"crowd {e['seq']}: no round for it, or a second one")
            continue
        crowds[p["round"]] = e
        opened, closes = mjd(r["payload"]["opens_at"]), mjd(r["payload"]["closes_at"])
        s = seal(e["seq"])
        if s is not None and s < closes:
            problems.append(f"crowd {p['round']}: sealed before the bell, so bets may be missing")
        ids, pairs = {q["id"] for q in r["payload"]["questions"]}, set()
        for b in p["bets"]:
            if b["question"] not in ids or not opened <= mjd(b["made_at"]) <= closes or not 0.01 <= b["p_yes"] <= 0.99 \
                    or (b["question"], b["player"]) in pairs or len(b["player"]) != 16:
                problems.append(f"crowd {p['round']}: a bet by {b['player']} on {b['question']} breaks the rules")
            pairs.add((b["question"], b["player"]))
    for e in (e for e in entries if e["kind"] == "reveal"):
        p, r = e["payload"], rounds.get(e["payload"]["round"])
        if r is None or p["round"] in reveals:
            problems.append(f"reveal {e['seq']}: no round for it, or a second one")
            continue
        reveals[p["round"]] = e
        closes = mjd(r["payload"]["closes_at"])
        # an anchor stamped after the bell sits before the reveal, so SIRA's answers came out only after it
        if not any(seq < e["seq"] and t is not None and t >= closes for seq, t in stamped):
            problems.append(f"reveal {p['round']}: not proven to come after the bell")
        given = {a["id"]: a for a in p["answers"]}
        for q in r["payload"]["questions"]:
            if q["id"] not in given or not opens(q, given[q["id"]]):
                problems.append(f"reveal {p['round']}: the answer to {q['id']} does not open its sealed envelope")
    answers = [e for e in entries if e["kind"] == "crowd_answer"]
    done = set()
    for e in answers:
        p, q = e["payload"], questions.get(e["payload"]["question"])
        day = q["_round"] if q else None
        if q is None or day not in reveals or day not in crowds or p["question"] in done:
            problems.append(f"crowd answer {e['seq']}: no revealed, crowded question for it, or a second one")
            continue
        done.add(p["question"])
        after = seal(crowds[day]["seq"])
        if p.get("void"):
            continue
        sira = {a["id"]: a["p_yes"] for a in reveals[day]["payload"]["answers"]}[q["id"]]
        bets = [b for b in crowds[day]["payload"]["bets"] if b["question"] == q["id"]]
        row = {"band": q["band"], "mjd": p["mjd"], "kind": p["kind"], "flux": p["flux"]}
        got = settle(q, [row], after if after is not None else math.inf)
        if got is None or got["yes"] != p["yes"] or not _same(scores(sira, bets, p["yes"]), p["scores"]):
            problems.append(f"crowd answer {e['seq']}: does not follow from the sealed answers and the measurement")
    if online:
        problems += _online(c, questions, crowds, answers, entries, sealed, now if now is not None else live.now_mjd())
    counts = {"rounds": len(rounds), "crowd_bets": sum(len(e["payload"]["bets"]) for e in crowds.values()),
              "crowd_answers": len(answers)}
    return problems, counts


def _same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-3 * max(1.0, abs(b))
    return a == b


def _online(c, questions: dict, crowds: dict, answers: list[dict], entries: list[dict], sealed: dict, now: float) -> list:
    # the archive decides which measurement settled each question
    problems = []
    seal = lambda seq: min((t for head, t in sealed.items() if head >= seq), default=None)
    for e in answers:
        p, q = e["payload"], questions.get(e["payload"]["question"])
        if q is None or q["_round"] not in crowds:
            continue
        after = seal(crowds[q["_round"]]["seq"])
        rows = [r | ({"flux": round(photometry.flux(r["mag"], 0)[0], 2)} if r["kind"] == "limit" else {})
                for r in live.observe(c, q["object"], now)["photometry"]]
        got = settle(q, rows, after if after is not None else math.inf)
        if p.get("void"):
            if got is not None and got["yes"] is not None:
                problems.append(f"crowd answer {e['seq']}: called void, but the archive settles it")
        elif got is None or abs(got["mjd"] - p["mjd"]) > 1e-5 or not _same(got["flux"], p["flux"]):
            problems.append(f"crowd answer {e['seq']}: its measurement is not the archive's first one after the bell")
    for qid, q in questions.items():
        if now > q["mjd"] + 3 and q["_round"] in crowds and qid not in {e["payload"]["question"] for e in answers}:
            problems.append(f"question {qid}: the sky answered, but the ledger never scored it")
    return problems
