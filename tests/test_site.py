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
    assert b["answer"] == {"yes": True, "log_score": -0.06, "at": "2026-10-31T04:48:00Z"}
    assert tele["A-1"]["question"]["kind"] == "last" and tele["A-1"]["answer"] == {"void": True}


def test_the_record_counts_only_real_answers_and_pairs_the_rivals():
    rows = ledger_rows()
    r = site.record(rows, site.telegrams(rows))
    assert (r["sealed"], r["answered"], r["right"], r["paired"]) == (2, 1, 1, 1)
    assert r["log_score"] == {"sira": -2.0, "b0": -3.0, "b1": -2.5, "b2": -4.0} and r["next_due"] is None


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
    beat = site.rounds(rows)
    r = beat["rounds"][0]
    assert r["answers"] == {q["id"]: 0.2} and r["players"] == 2 and r["crowd"] == {q["id"]: 0.6}
    assert r["results"]["2026-10-30-2"] == {"void": True}
    assert [x["who"] for x in beat["board"]] == ["sira", "p2", "sira_crowd", "crowd", "p1"]
    assert next(x for x in beat["board"] if x["who"] == "p2")["handle"] == "leo"


def test_candidates_are_what_the_lookouts_weighed_last_night():
    look = lambda seq, oid, call, p, time: entry(seq, "event", {"role": "lookout", "object": oid, "decision": call,
                                                                "priority": p, "cost_usd": 0.01}, time)
    rows = [
        look(0, "OLD", "investigate", 0.9, "2026-10-29T01:00:00+00:00"),
        entry(1, "event", {"role": "reader", "object": "B", "decision": "real (0.93)", "cost_usd": 0.01}, "2026-10-30T01:00:00+00:00"),
        look(2, "B", "investigate", 0.8, "2026-10-30T01:01:00+00:00"),
        look(3, "C", "pass", 0.4, "2026-10-30T01:01:00+00:00"),
        look(4, "C", "investigate", 0.6, "2026-10-30T01:02:00+00:00"),
        look(5, "C", "pass", 0.5, "2026-10-30T01:02:00+00:00"),
        entry(6, "bet", {"bet": "B-1", "object": "B"}, "2026-10-30T01:20:00+00:00"),
    ]
    got = site.candidates(rows)
    assert got == [{"object": "B", "priority": 0.8, "picked": True, "reader": "real", "p_real": 0.93, "bet": True},
                   {"object": "C", "priority": 0.5, "picked": False, "reader": None, "p_real": None, "bet": False}]


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

    say("reader", "bogus (0.15)", why="Broken subtractions everywhere.")
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
