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
    beat = site.rounds(rows)
    r = beat["rounds"][0]
    assert r["answers"] == {q["id"]: 0.2} and r["players"] == 2 and r["crowd"] == {q["id"]: 0.6}
    assert r["results"]["2026-10-30-2"] == {"void": True, "yes": None} and r["results"][q["id"]]["void"] is False
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
