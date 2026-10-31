import csv
from datetime import datetime, timezone

from sira import archive
from test_site import RISKY, STANDARD, entry

BET = {"bet": "A-1", "object": "A", "model": "v1", "made_at": 61340.0, "n_points": 12, "question": STANDARD, "risky": RISKY,
       "director": {"question": "q3", "action": "bet"}, "wording": {"term": "very likely", "text": "Very likely fainter."},
       "classes": {"ia": 0.7, "ii": 0.2, "ibc": 0.05, "tde": 0.0, "other": 0.05}, "weights": {"ia": 0.8, "null": 0.1},
       "theories": [{"hypothesis": "ia", "argument": "A normal Ia."}], "seen": [[61330.0, "ztfr", "det", 50.0, 2.0]],
       "forecasts": [{"mjd": 61341.0, "band": "ztfr", "parts": [["ia", 0.9, 60.0, 5.0], ["null", 0.1, 50.0, 10.0]]}]}


def rows(bell=None):
    out = [
        entry(0, "event", {"role": "reader", "object": "A", "decision": "bogus (0.3)", "why": "A dipole."}, "2026-10-26T01:00:00+00:00"),
        entry(1, "event", {"role": "reader", "object": "A", "decision": "real (0.9)", "why": "A point source."}, "2026-10-27T01:00:00+00:00"),
        entry(2, "event", {"role": "lookout", "object": "A", "decision": "investigate", "priority": 0.8}, "2026-10-27T01:00:00+00:00"),
        entry(3, "event", {"role": "lookout", "object": "A", "decision": "pass", "priority": 0.4}, "2026-10-27T01:00:00+00:00"),
        entry(4, "event", {"role": "lookout", "object": "A", "decision": "investigate", "priority": 0.6}, "2026-10-27T01:00:00+00:00"),
        entry(5, "event", {"role": "theorist", "object": "A", "decision": "defends ia", "why": "Rising like an Ia."},
              "2026-10-27T01:01:00+00:00"),
        entry(6, "bet", BET, "2026-10-27T01:02:00+00:00"),
        entry(7, "anchor", {"seq": 6, "tsa_time": "2026-10-27T01:03:00+00:00", "head": "ab"}),
        entry(8, "outcome", {"bet": "A-1", "object": "A", "band": "ztfr", "mjd": 61341.2, "kind": "det", "flux": 58.0,
                             "flux_err": 3.0, "log_score": -2.1, "pit": 0.4, "crps": 3.3,
                             "baselines": {"b0": {"log_score": -3.0, "pit": 0.2}}}, "2026-10-28T01:00:00+00:00"),
        entry(9, "answer", {"bet": "A-1", "object": "A", "which": "risky", "void": True}, "2026-11-01T01:00:00+00:00"),
    ]
    if bell:
        out.append(entry(10, "round", {"round": "2026-10-29", "opens_at": "2026-10-29T14:00:00+00:00", "closes_at": bell,
                                       "questions": [{"id": "2026-10-29-1", "object": "A"}]}, "2026-10-29T14:00:00+00:00"))
    return out


def at(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def test_a_night_is_named_by_its_evening_in_chile():
    assert archive.night_of("2026-10-31T00:51:24+00:00") == "2026-10-30"
    assert archive.night_of("2026-10-27T17:41:28+00:00") == "2026-10-27"


def test_a_bet_stays_shut_for_48_hours_and_shows_only_its_telegram():
    book = archive.build(rows(), {}, at("2026-10-28T23:00:00+00:00"))
    a = book["objects"][0]
    bet = a["bets"][0]
    assert not bet["open"] and bet["open_at"] == "2026-10-29T00:00:00Z" and bet["staked"] == "risky"
    assert bet["question"]["p"] == 0.94 and bet["term"] == "very likely" and bet["sealed_at"] == "2026-10-27T01:03:00+00:00"
    assert not {"classes", "theories", "seen", "fan", "director", "wording", "standard"} & set(bet)
    # the team's words that night stay out of the file, and so does how the bet scored
    assert a["team"] == [] and a["shut"] == {"2026-10-26": "2026-10-29T00:00:00Z"}
    assert "log_score" not in a["outcomes"][0] and a["outcomes"][0]["flux"] == 58.0
    assert [r["label"] for r in a["reads"]] == ["bogus", "real"]


def test_after_48_hours_the_bet_shows_everything_it_holds():
    a = archive.build(rows(), {}, at("2026-10-29T01:00:00+00:00"))["objects"][0]
    bet = a["bets"][0]
    assert bet["open"] and bet["classes"]["ia"] == 0.7 and bet["standard"]["kind"] == "last" and bet["risky"]["kind"] == "level"
    assert bet["fan"]["ztfr"] == [[61341.0, 59.0, 6.44]] and bet["fan"]["ztfg"] == [] and bet["seen"] == BET["seen"]
    assert [t["decision"] for t in a["team"]] == ["defends ia"] and a["shut"] == {}
    assert a["outcomes"][0]["log_score"] == -2.1 and a["outcomes"][0]["baselines"] == {"b0": -3.0}


def test_a_bet_drawn_into_a_round_waits_for_its_bell():
    late = rows("2026-10-29T21:00:00+00:00")
    assert not archive.build(late, {}, at("2026-10-29T20:00:00+00:00"))["objects"][0]["bets"][0]["open"]
    assert archive.build(late, {}, at("2026-10-29T21:00:00+00:00"))["objects"][0]["bets"][0]["open"]


def test_the_record_keeps_the_readers_calls_the_lookouts_votes_and_void_answers():
    pics = {"A": {"ra": 150.0, "dec": -20.0, "first": 61329.5, "stamps": "A.png", "panel": [63, 63], "taken": 61330.0}}
    a = archive.build(rows(), pics, at("2026-10-29T01:00:00+00:00"))["objects"][0]
    assert [(r["label"], r["p_real"], r["changed"]) for r in a["reads"]] == [("bogus", 0.3, False), ("real", 0.9, True)]
    assert a["lookouts"] == [{"night": "2026-10-26", "votes": 3, "priority": 0.6, "picked": True}]
    assert a["answers"][0] | {"at": None} == {"bet": "A-1", "which": "risky", "night": "2026-10-31", "at": None, "void": True,
                                              "yes": None, "log_score": None, "measured": None}
    assert a["nights"] == ["2026-10-25", "2026-10-26"] and (a["first"], a["last"]) == ("2026-10-25", "2026-10-26")
    assert (a["ra"], a["l"] is not None, a["first_detection"]) == (150.0, True, "2026-10-16T12:00:00Z")
    assert a["images"]["stamps"] == "data/img/A.png"


def test_the_csv_has_a_row_per_object_and_night(tmp_path):
    book = archive.build(rows(), {}, at("2026-10-29T01:00:00+00:00"))
    archive.table(book, tmp_path / "archive.csv")
    got = list(csv.DictReader((tmp_path / "archive.csv").open()))
    assert [(r["night"], r["reader_label"], r["bet"]) for r in got] == [("2026-10-25", "bogus", ""), ("2026-10-26", "real", "A-1")]
    last = got[-1]
    assert (last["lookout_votes"], last["lookouts_picked"], last["p_yes"], last["class_top"], last["answer"]) == (
        "3", "1", "0.94", "ia", "void")
    assert (last["outcomes"], last["log_scores"], last["sealed_at"]) == ("1", "-2.1", "2026-10-27T01:03:00+00:00")
