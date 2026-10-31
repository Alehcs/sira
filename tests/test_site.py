import json
from datetime import datetime, timezone

from sira import site


def entry(seq, kind, payload, time="2026-10-30T01:00:00+00:00"):
    return {"seq": seq, "kind": kind, "payload": payload, "time": time, "hash": f"{seq:064x}", "prev": None, "v": 2}


STANDARD = {"text": "Brighter in r three days from now than at its last r detection?", "band": "ztfr",
            "mjd": 61343.0, "p_yes": 0.27, "reference": 69.31, "direction": "above"}
RISKY = {"id": "q3", "text": "Fainter than 400 microjansky in r 4 days from now?", "band": "ztfr", "mjd": 61344.0,
         "p_yes": 0.94, "reference": 400, "direction": "below"}


def ledger_rows():
    return [
        entry(0, "bet", {"bet": "A-1", "object": "A", "model": "v0", "made_at": 61340.0, "question": STANDARD}),
        entry(1, "bet", {"bet": "B-1", "object": "B", "model": "v1", "made_at": 61340.0, "question": STANDARD,
                         "risky": RISKY, "director": {"question": "q3"}, "wording": {"term": "very likely"}}),
        entry(2, "anchor", {"seq": 1, "tsa_time": "2026-10-30T01:05:00+00:00", "head": "ab"}),
        entry(3, "outcome", {"bet": "B-1", "log_score": -2.0, "baselines": {k: {"log_score": v} for k, v in
                                                                             {"b0": -3.0, "b1": -2.5, "b2": -4.0}.items()}}),
        entry(4, "answer", {"bet": "B-1", "which": "risky", "yes": True, "log_score": -0.06, "mjd": 61344.2, "p_yes": 0.94}),
        entry(5, "answer", {"bet": "A-1", "which": "question", "void": True}),
    ]


def test_a_telegram_shows_the_question_the_director_staked_and_its_receipt():
    tele = {t["bet"]: t for t in site.telegrams(ledger_rows())}
    b = tele["B-1"]
    assert b["question"] | {"text": None} == {"p": 0.94, "due": "2026-10-31T00:00:00Z", "text": None, "kind": "level",
                                               "direction": "below", "reference": 400.0, "band": "r", "days": 4}
    assert b["sealed_at"] == "2026-10-30T01:05:00+00:00" and b["term"] == "very likely"
    assert b["answer"] == {"void": False, "yes": True, "log_score": -0.06, "at": "2026-10-31T04:48:00Z"}
    # a void answer says so, so it can never be read as a no
    assert tele["A-1"]["question"]["kind"] == "last" and tele["A-1"]["answer"] == {"void": True, "yes": None}


def test_an_answer_waits_for_the_first_nightly_a_day_and_a_half_after_its_question():
    # live.resolve writes the answer once now > question time + 1.5 days, and the nightly runs at 21:13 UTC
    assert site._answerable(61343.0) == "2026-10-31T21:13:00Z"  # question at 00:00 Oct 30, ready 12:00 Oct 31
    assert site._answerable(61343.4) == "2026-11-01T21:13:00Z"  # ready 21:36 Oct 31, after that night's run
    tele = {t["bet"]: t for t in site.telegrams(ledger_rows())}
    assert tele["B-1"]["answer_due"] == "2026-11-01T21:13:00Z" and tele["A-1"]["answer_due"] == "2026-10-31T21:13:00Z"


def test_the_record_counts_only_real_answers_and_pairs_the_rivals():
    rows = ledger_rows()
    r = site.record(rows, site.telegrams(rows))
    assert (r["sealed"], r["answered"], r["void"], r["right"], r["paired"]) == (2, 1, 1, 1, 1)
    assert r["log_score"] == {"sira": -2.0, "b0": -3.0, "b1": -2.5, "b2": -4.0} and r["next_due"] is None


def test_the_next_answers_are_due_when_the_ledger_can_write_them():
    rows = ledger_rows()[:3]
    r = site.record(rows, site.telegrams(rows))
    assert r["answered"] == 0 and r["next_due"] == "2026-10-31T21:13:00Z"


def test_beat_sira_ranks_everyone_by_their_mean_score():
    q = {"id": "2026-10-30-1", "object": "C", "text": STANDARD["text"], "band": "ztfr", "mjd": 61343.0,
         "direction": "above", "reference": 50.0, "commit": "c0"}
    rows = [
        entry(0, "round", {"round": "2026-10-30", "opens_at": "o", "closes_at": "c", "questions": [q]}),
        entry(1, "reveal", {"round": "2026-10-30", "answers": [{"id": q["id"], "p_yes": 0.2, "salt": "s", "key": "k"}]}),
        entry(2, "crowd", {"round": "2026-10-30", "bets": [
            {"question": q["id"], "player": "p1", "handle": "ana", "p_yes": 0.9, "made_at": "m"},
            {"question": q["id"], "player": "p2", "handle": "leo", "p_yes": 0.3, "made_at": "m"}]}),
        entry(3, "crowd_answer", {"question": q["id"], "round": "2026-10-30", "yes": False, "mjd": 61343.4, "flux": 40.0,
                                  "scores": {"sira": -0.22, "crowd": -0.92, "sira_crowd": -0.51,
                                             "players": {"p1": -2.3, "p2": -0.36}}}),
        entry(4, "crowd_answer", {"question": "2026-10-30-2", "round": "2026-10-30", "void": True}),
    ]
    beat = site.rounds(rows, {"C": {"stamps": "C.png", "panel": [63, 63], "taken": 61340.5}})
    r = beat["rounds"][0]
    assert r["answers"] == {q["id"]: 0.2} and r["players"] == 2 and r["crowd"] == {q["id"]: 0.6}
    assert r["results"]["2026-10-30-2"] == {"void": True, "yes": None} and r["results"][q["id"]]["void"] is False
    assert r["questions"][0]["images"] == {"stamps": "data/img/C.png", "panel": [63, 63], "taken": "2026-10-27T12:00:00Z",
                                           "host": None}
    assert [x["who"] for x in beat["board"]] == ["sira", "p2", "sira_crowd", "crowd", "p1"]
    assert next(x for x in beat["board"] if x["who"] == "p2")["handle"] == "leo"


WHY = ("Round positive source at the centre of the difference, as wide as the stars. It sits on the edge of a faint "
       "galaxy seen in the template, with clean subtraction around it and no dipoles anywhere in the field near it, so")


def candidate_rows():
    look = lambda seq, oid, call, p, time: entry(seq, "event", {"role": "lookout", "object": oid, "decision": call,
                                                                "priority": p, "cost_usd": 0.01}, time)
    return [
        look(0, "OLD", "investigate", 0.9, "2026-10-29T01:00:00+00:00"),
        entry(1, "event", {"role": "reader", "object": "B", "decision": "real (0.93)", "cost_usd": 0.01, "why": WHY[:200]},
              "2026-10-30T01:00:00+00:00"),
        look(2, "B", "investigate", 0.8, "2026-10-30T01:01:00+00:00"),
        look(3, "C", "pass", 0.4, "2026-10-30T01:01:00+00:00"),
        look(4, "C", "investigate", 0.6, "2026-10-30T01:02:00+00:00"),
        look(5, "C", "pass", 0.5, "2026-10-30T01:02:00+00:00"),
        entry(6, "bet", {"bet": "B-1", "object": "B", "model": "v1", "made_at": 61343.0, "question": STANDARD,
                         "risky": RISKY, "director": {"question": "q3"}, "wording": {"term": "very likely"}},
              "2026-10-30T01:20:00+00:00"),
    ]


def test_candidates_are_what_the_lookouts_weighed_last_night():
    got = site.candidates(candidate_rows())
    assert [(c["object"], c["priority"], c["picked"], c["reader"], c["p_real"], c["bet"]) for c in got] == [
        ("B", 0.8, True, "real", 0.93, True), ("C", 0.5, False, None, None, False)]
    # the reader's note ends on its last whole sentence, as in Investigate
    assert got[0]["why"] == "Round positive source at the centre of the difference, as wide as the stars."
    assert got[0]["telegram"] == {"seq": 6, "question": site._question(RISKY), "term": "very likely"}
    assert got[1]["why"] is None and got[1]["telegram"] is None
    assert got[1]["points"] is None and got[1]["images"] == {"stamps": None, "panel": None, "taken": None, "host": None}


def test_a_card_carries_what_the_build_drew_for_it():
    pics = {"B": {"ra": 150.1, "dec": -20.2, "points": 4, "curve": [[61340.1, "ztfr", "det", 50.0, 2.0]], "first": 61330.0,
                  "stamps": "B.png", "panel": [63, 50], "taken": 61331.0, "host": "B.jpg"}}
    data = site.live(candidate_rows(), pics)
    b = data["candidates"][0]
    assert (b["ra"], b["dec"], b["points"], b["curve"]) == (150.1, -20.2, 4, [[61340.1, "ztfr", "det", 50.0, 2.0]])
    assert b["images"] == {"stamps": "data/img/B.png", "panel": [63, 50], "taken": "2026-10-18T00:00:00Z",
                           "host": "data/img/B.jpg"}
    # the cards hide what the lab could not investigate, by the same rule visits.py enforces
    assert data["min_points"] == 5


IDEA = ("A dark star passing in front of the source would brighten it and fade it again in the same way in every band, "
        "with no change of colour; the curve so far rises as one, so a lens fits it without any supernova at all.")


def test_the_logbook_tells_le_verriers_ideas_whole(tmp_path):
    rows = [
        entry(0, "bet", {"bet": "Z-1", "object": "Z", "model": "v1"}),
        entry(1, "surprise", {"bet": "Z-1", "object": "Z", "surprised": True, "misses": 4, "n": 5, "p_value": 0.001}),
        entry(2, "event", {"role": "leverrier", "object": "Z", "leap": "hidden", "decision": "proposes Unseen lens",
                           "why": IDEA[:200]}),
        entry(3, "event", {"role": "leverrier", "object": "Z", "leap": "new", "decision": "proposes Other idea", "why": "Short."}),
        entry(4, "bet", {"bet": "Z-leap-1", "object": "Z", "made_at": 61340.0, "chosen": "Unseen lens", "cost_usd": 0.5,
                         "proposals": [{"leap": "hidden", "name": "Unseen lens", "idea": IDEA},
                                       {"leap": "new", "name": "Other idea", "idea": "Short."}]}),
        entry(5, "verdict", {"bet": "Z-leap-1", "object": "Z", "verdict": "neptune", "log10_e": 6.5, "n": 12}),
    ]
    chain = site._logbook(tmp_path, rows)[0]["chains"][0]
    assert [(p["name"], p["idea"], p["chosen"]) for p in chain["proposals"]] == [("Unseen lens", IDEA, True),
                                                                                  ("Other idea", "Short.", False)]


def test_export_draws_tonights_candidates_fresh_and_writes_every_file(tmp_path, monkeypatch):
    from sira import gallery

    asked = {}

    def draw(oids, out, fresh=frozenset(), seconds=0):
        asked.update(oids=oids, out=out, fresh=fresh)
        return {"B": {"ra": 150.1, "dec": -20.2, "points": 4, "curve": [], "first": 61330.0}}

    monkeypatch.setattr(gallery, "build", draw)
    book = tmp_path / "ledger"
    book.mkdir()
    (book / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in candidate_rows()) + "\n")
    data = site.export(book, tmp_path / "data", now=datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert asked["oids"][:2] == ["B", "C"] and set(asked["oids"]) == {"B", "C", "OLD"} and asked["fresh"] == {"B", "C"}
    assert asked["out"] == tmp_path / "data" / "img" and data["candidates"][0]["ra"] == 150.1
    saved = json.loads((tmp_path / "data" / "live.json").read_text())
    assert saved["record"] == data["record"] and json.loads((tmp_path / "data" / "archive.json").read_text())["objects"]
    assert (tmp_path / "data" / "archive.csv").read_text().startswith("object,ra,dec,night,")


def test_export_draws_the_open_and_recent_rounds_first_and_fresh(tmp_path, monkeypatch):
    from sira import gallery

    asked = {}

    def draw(oids, out, fresh=frozenset(), seconds=0):
        asked.update(oids=oids, fresh=fresh)
        return {"R1": {"stamps": "R1.png", "panel": [63, 63], "taken": 61340.5, "host": "R1.jpg"}}

    def round_of(seq, day, closes, oids):
        qs = [{"id": f"{day}-{i}", "object": o, "text": STANDARD["text"], "band": "ztfr", "mjd": 61350.0,
               "direction": "above", "reference": 50.0, "commit": "c0"} for i, o in enumerate(oids, 1)]
        return entry(seq, "round", {"round": day, "opens_at": f"{day}T18:00:00+00:00", "closes_at": closes, "questions": qs})

    monkeypatch.setattr(gallery, "build", draw)
    rows = candidate_rows() + [round_of(7, "2026-10-20", "2026-10-20T21:00:00+00:00", ["GONE"]),
                               round_of(8, "2026-10-29", "2026-10-29T21:00:00+00:00", ["R2"]),
                               round_of(9, "2026-10-31", "2026-10-31T21:00:00+00:00", ["R1", "B"])]
    book = tmp_path / "ledger"
    book.mkdir()
    (book / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in rows) + "\n")
    data = site.export(book, tmp_path / "data", now=datetime(2026, 10, 31, 19, tzinfo=timezone.utc))
    # the open round, then the recent one, are drawn before anything else; an old round waits its turn
    assert asked["oids"][:3] == ["R1", "B", "R2"] and "GONE" in asked["oids"][3:]
    assert {"R1", "B", "R2"} <= asked["fresh"] and "GONE" not in asked["fresh"]
    q = data["beat"]["rounds"][0]["questions"][0]
    assert q["object"] == "R1" and q["images"]["stamps"] == "data/img/R1.png" and q["images"]["host"] == "data/img/R1.jpg"


def replay():
    # five team bets, a surprise on the second, one Le Verrier bet and the sky's verdict on it
    rows = []
    add = lambda kind, payload: rows.append(entry(len(rows), kind, payload))
    say = lambda role, decision, **kw: add("event", {"role": role, "decision": decision, "cost_usd": 0.01, **kw})
    fan = lambda mjd: [{"band": f"ztf{b}", "mjd": mjd + 1, "parts": [["ia", 0.5, 100.0, 10.0], ["null", 0.5, 120.0, 10.0]]}
                       for b in "gr"]

    def bet(mjd, theories=("ia", "ibc")):
        for h in theories:
            say("theorist", f"defends {h}")
        say("skeptic", "real", lens="instrument")
        say("director", "bet q0")
        add("bet", {"bet": f"A-{mjd}", "made_at": mjd, "baselines": {"b1": fan(mjd)}, "decision": {"action": "wait"},
                    "director": {"question": "q0", "why": f"q0 at {mjd}"}, "question": STANDARD | {"mjd": mjd + 3},
                    "wording": {"term": "likely", "text": f"Likely at {mjd}."}, "weights": {"ia": 0.7, "ibc": 0.2, "null": 0.1},
                    "skeptics": {"instrument": {"why": "A smooth rise."}},
                    "theories": [{"hypothesis": h, "argument": f"The {h} case."} for h in theories]})

    say("reader", "bogus (0.15)", why="Broken subtractions everywhere.", seconds=6.9)
    bet(105.0)
    add("answer", {"bet": "A-105.0", "which": "question", "yes": True, "log_score": -0.58, "mjd": 108.0})
    bet(110.0)
    for mjd, band, pit in [(111.0, "ztfr", 0.5), (112.0, "ztfr", 0.995), (112.5, "ztfg", 0.002)]:
        add("outcome", {"bet": "A-110.0", "mjd": mjd, "band": band, "flux": 90.0, "baselines": {"b1": {"pit": pit}}})
    add("surprise", {"bet": "A-110.0", "forecast": "b1", "misses": 2, "n": 3, "p_value": 0.0003, "surprised": True})
    say("leverrier", "proposes Lens", leap="hidden")
    say("leverrier", "proposes Drift", leap="instrument")
    add("bet", {"bet": "A-leap-115.0", "made_at": 115.0, "chosen": "Lens", "cost_usd": 0.2, "forecasts": fan(115.0),
                "baselines": {"old": fan(115.0)}, "proposals": [{"leap": "hidden", "name": "Lens", "bic": 23.0, "idea": "A lens."},
                                                               {"leap": "instrument", "name": "Drift", "bic": 384.1, "idea": "A drift."}]})
    bet(115.0)
    add("verdict", {"bet": "A-leap-115.0", "verdict": "neptune", "log10_e": 37.8, "n": 8})
    bet(120.0, ("adopted", "ia"))
    bet(125.0)
    add("answer", {"bet": "A-125.0", "which": "question", "yes": False, "log_score": -0.03, "mjd": 128.0})
    seen = lambda mjd, band, **kw: {"mjd": mjd, "band": band, "available_at": mjd + 0.5, **kw}
    obj = {"oid": "A", "ra": 297.7061439, "dec": 34.6372846, "photometry": [
        seen(100.0, "ztfr", kind="det", flux=50.0, flux_err=5.0), seen(90.0, "ztfr", kind="limit", mag=21.4),
        seen(101.0, "ztfg", kind="det", flux=30.0, flux_err=4.0), seen(126.0, "ztfr", kind="det", flux=200.0, flux_err=9.0)]}
    return rows, obj


def test_the_lab_draws_both_bands_their_limits_and_the_measurements_the_forecast_missed():
    lab = site._lab(*replay())
    assert lab["phot"] == [[-10.0, "r", "lim", 10.0, None, -9.5], [0.0, "r", "det", 50.0, 5.0, 0.5],
                           [1.0, "g", "det", 30.0, 4.0, 1.5], [26.0, "r", "det", 200.0, 9.0, 26.5]]
    assert lab["misses"] == [[12.0, "r", 90.0, 0.995], [12.5, "g", 90.0, 0.002]]
    assert len(lab["misses"]) == lab["facts"]["surprise"]["misses"]
    assert lab["fans"]["cp2"] == {"g": [[11.0, 110.0, 14.1]], "r": [[11.0, 110.0, 14.1]]} and set(lab["fans"]["lens"]) == {"g", "r"}
    assert (lab["l"], lab["b"]) == (70.0549, 4.1027)


def test_the_lab_keeps_each_seal_its_question_its_answer_and_the_words_behind_it():
    lab = site._lab(*replay())
    first, last = lab["bets"][0], lab["bets"][-1]
    assert first["question"] | {"text": None, "due": None} == {"p": 0.27, "due": None, "text": None, "kind": "last",
                                                                "direction": "above", "reference": 69.3, "band": "r", "days": 3}
    assert first["answer"] == {"yes": True, "log_score": -0.58, "at": 8.0} and first["action"] == "wait"
    assert last["answer"]["yes"] is False and lab["bets"][2]["answer"] is None
    leap = lab["leaps"][0]
    assert [(p["leap"], p["bic"]) for p in leap["proposals"]] == [("hidden", 23.0), ("instrument", 384.1)]
    assert leap["chosen"] == "Lens" and leap["verdict"] | {"hash": None, "time": None} == {
        "hash": None, "time": None, "verdict": "neptune", "log10_e": 37.8, "n": 8}
    said = lab["said"]
    assert len(said) == len(lab["now"]) == 14
    assert said[:5] == ["Broken subtractions everywhere.", "The ia case.", "A smooth rise.", "q0 at 105.0", "Likely at 105.0."]
    assert said[7] == "A lens." and said[9] == "The adopted case." and said[11] == "Likely at 125.0." and said[5] is None


def test_the_lab_gives_the_observatory_the_calls_behind_each_step_and_their_seconds():
    calls = site._lab(*replay())["calls"]
    assert len(calls) == 14 and calls[0] == [{"role": "reader", "decision": "bogus (0.15)", "seconds": 6.9}]
    assert [c["decision"] for c in calls[1]] == ["defends ia", "defends ibc"]
    assert calls[2] == [{"role": "skeptic", "lens": "instrument", "decision": "real"}]
    assert calls[7] == [{"role": "leverrier", "leap": "hidden", "decision": "proposes Lens"},
                        {"role": "leverrier", "leap": "instrument", "decision": "proposes Drift"}]
    assert [c["decision"] for c in calls[9]] == ["defends adopted", "defends ia", "real"]
    assert calls[10] == [{"role": "director", "decision": "bet q0"}] and calls[5] == calls[12] == calls[13] == []


LONG = ("The flat plateau over two weeks matches a cooling hydrogen envelope. The fit has chi2 per point 0.68 and the stamp "
        "shows a star-like source on a faint galaxy, so a hydrogen-rich collapse is the likeliest story for what it shows.")


def nightly():
    # two nights of team bets: B on the first, C and D on the second, D weighed by more lookouts, and a v0 bet
    rows = []
    add = lambda kind, payload, time: rows.append(entry(len(rows), kind, payload, time))
    fan = [{"band": f"ztf{b}", "mjd": 61344.0 + d, "parts": [["ii", 0.5, 100.0, 10.0], ["llm", 0.5, 120.0, 10.0]]}
           for d in (1, 2) for b in "gr"]

    def night(oid, time, lookouts=1, model="v1"):
        say = lambda role, decision, **kw: add("event", {"role": role, "object": oid, "decision": decision, "cost_usd": 0.01,
                                                          "seconds": 2.0, **kw}, time)
        say("forecaster", "words the bet", why="Short words.")
        say("director", "bet q3", why="Cut director note")
        say("skeptic", "doubts ibc", lens="physics")
        say("skeptic", "real", lens="instrument")
        say("llm_only", "forecasts 10 points alone")
        say("theorist", "defends ii", why=LONG[:200])
        say("reader", "real (0.86)", why="Compact source at the centre.")
        for _ in range(lookouts):
            say("lookout", "investigate", priority=0.7, why="A lookout note " + "x" * 190)
        add("bet", {"bet": f"{oid}-{time[:10]}", "object": oid, "model": model, "made_at": 61344.0, "question": STANDARD,
                    "risky": RISKY, "director": {"question": "q3", "why": "q3 carries the most bits."},
                    "wording": {"term": "likely", "text": "It is likely to fade."},
                    "theories": [{"hypothesis": "ii", "argument": LONG}],
                    "skeptics": {"instrument": {"why": "A smooth rise."},
                                 "physics": {"implausible": [{"hypothesis": "ibc", "why": "Too flat."}]}},
                    "classes": {"ii": 0.6, "ia": 0.4}, "weights": {"ii": 0.9, "null": 0.1}, "decision": {"action": "wait"},
                    "forecasts": fan, "seen": [[61340.0, "ztfr", "det", 50.0, 2.0], [61330.0, "ztfg", "limit", 10.0, None]]},
            time)

    night("B", "2026-10-29T01:00:00+00:00", lookouts=3)
    night("C", "2026-10-30T01:00:00+00:00")
    night("D", "2026-10-30T01:10:00+00:00", lookouts=2)
    night("V", "2026-10-30T01:20:00+00:00", lookouts=5, model="v0")
    add("answer", {"bet": "C-2026-10-30", "which": "risky", "yes": False, "log_score": -0.1, "mjd": 61348.0},
        "2026-11-03T01:00:00+00:00")
    return rows


def test_the_lab_shows_the_latest_nights_bet_the_most_calls_weighed():
    got = site.latest(nightly(), now=datetime(2026, 11, 2, 1, tzinfo=timezone.utc))
    assert (got["object"], got["night"], got["model"]) == ("D", "2026-10-29", "v1")
    # the calls in the order the team works: lookouts, reader, theorists, skeptics, Muse alone, director, forecaster
    assert [(e["role"], e.get("lens")) for e in got["events"]] == [
        ("lookout", None), ("lookout", None), ("reader", None), ("theorist", None), ("skeptic", "instrument"),
        ("skeptic", "physics"), ("llm_only", None), ("director", None), ("forecaster", None)]
    assert got["question"] == site._question(RISKY) and got["staked"] == "risky" and got["term"] == "likely"
    assert got["hash"] == f"{29:064x}" and got["made_at"] == "2026-10-31T00:00:00Z"
    assert got["cost"] == 0.09 and got["calls"] == 9 and got["answer"] is None


def test_the_latest_investigation_keeps_every_reason_whole():
    events = {e["role"]: e for e in site.latest(nightly(), now=datetime(2026, 11, 2, 1, tzinfo=timezone.utc))["events"]}
    # the theorist's argument comes uncut from the bet, the director's and forecaster's words too
    assert events["theorist"]["why"] == LONG
    assert events["director"]["why"] == "q3 carries the most bits." and events["forecaster"]["why"] == "It is likely to fade."
    assert events["reader"]["why"] == "Compact source at the centre."
    # a note the ledger cut with no sentence to end on shows the cut
    assert events["lookout"]["why"].endswith("x…") and events["lookout"]["priority"] == 0.7
    assert events["llm_only"]["why"] is None and events["skeptic"]["why"] is None
    assert site._whole(LONG[:200]) == "The flat plateau over two weeks matches a cooling hydrogen envelope."


def test_the_latest_investigation_draws_what_sira_saw_and_its_sealed_fan():
    got = site.latest(nightly(), now=datetime(2026, 11, 2, 1, tzinfo=timezone.utc))
    assert got["seen"] == [[-14.0, "g", "lim", 10.0, None], [-4.0, "r", "det", 50.0, 2.0]]
    assert got["fan"] == {"g": [[1.0, 110.0, 14.14], [2.0, 110.0, 14.14]], "r": [[1.0, 110.0, 14.14], [2.0, 110.0, 14.14]]}
    assert got["first_detection"] == "2026-10-27T00:00:00Z" and got["classes"] == {"ii": 0.6, "ia": 0.4}
    assert got["skeptics"]["physics"]["implausible"] == [{"hypothesis": "ibc", "why": "Too flat."}]
    assert got["images"] == {"stamps": None, "panel": None, "taken": None, "host": None} and got["ra"] is None


def test_the_lab_waits_48_hours_and_for_the_bell_of_a_round_that_holds_the_object():
    rows = nightly()
    # a fresh bet could still be drawn into a round, so nothing shows for two days
    assert site.latest(rows, now=datetime(2026, 11, 1, 23, tzinfo=timezone.utc)) is None
    rows.append(entry(len(rows), "round", {"round": "2026-11-02", "opens_at": "2026-11-02T18:00:00+00:00",
                                           "closes_at": "2026-11-02T21:00:00+00:00", "questions": [{"object": "D"}]}))
    assert site.latest(rows, now=datetime(2026, 11, 2, 19, tzinfo=timezone.utc))["object"] == "C"
    assert site.latest(rows, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc))["object"] == "D"
    # with the next round holding D too, C shows, with its answer once the ledger has it
    later = rows + [entry(99, "round", {"closes_at": "2026-11-09T21:00:00+00:00", "questions": [{"object": "D"}]})]
    c = site.latest(later, now=datetime(2026, 11, 4, tzinfo=timezone.utc))
    assert c["object"] == "C" and c["answer"] == {"void": False, "yes": False, "log_score": -0.1, "at": "2026-11-04T00:00:00Z"}
    assert site.latest(rows[:1]) is None


def test_export_writes_the_latest_investigation(tmp_path, monkeypatch):
    from sira import gallery

    monkeypatch.setattr(gallery, "build", lambda oids, out, fresh=frozenset(), seconds=0: {
        "D": {"ra": 150.1, "dec": -20.2, "stamps": "D.png", "panel": [63, 63], "taken": 61340.0, "host": "D.jpg"}})
    book = tmp_path / "ledger"
    book.mkdir()
    (book / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in nightly()) + "\n")
    site.export(book, tmp_path / "data", now=datetime(2026, 11, 2, 1, tzinfo=timezone.utc))
    got = json.loads((tmp_path / "data" / "latest.json").read_text())
    assert got["object"] == "D" and got["images"]["stamps"] == "data/img/D.png" and (got["ra"], got["dec"]) == (150.1, -20.2)
    assert got["l"] is not None and got["b"] is not None
