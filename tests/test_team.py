import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

from sira import agents, team
from sira.firewall import Leak, as_of, plant
from test_live import sn_object

NOW = 61340.75


def reply(answers):
    def chat(provider, model, messages, tag="", **kwargs):
        task = json.dumps(messages)
        text = next((json.dumps(a) for key, a in answers.items() if key in task), "{}")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None,
                                completion_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)
    return SimpleNamespace(chat=chat)


ANSWERS = {
    "You are a Lookout": {"investigate": True, "priority": 0.9, "why": "well sampled"},
    "You are the theorist": {"argument": "fits well", "weakest_point": "colour",
                             "refuted_if": {"band": "r", "day": 4, "direction": "below", "flux": 5.0, "why": "would fade"}},
    "instrument skeptic": {"artifact": False, "confidence": 0.1, "why": "smooth"},
    "physics skeptic": {"implausible": []},
    "memory skeptic": {"recognised": False, "name": None, "confidence": 0.0},
    "You are the director": {"action": "bet", "question": "q1", "why": "most bits"},
    "You are the forecaster": {"text": "It is very unlikely that it fades below 5 microjansky."},
}


def run(answers, seniors=None):
    obj, _ = sn_object()
    with ThreadPoolExecutor(4) as pool:
        return team.investigate(reply(answers), as_of(obj, NOW), 0.02, pool, seniors or [0])


def test_the_team_argues_and_stakes_a_question():
    bet, events = run(ANSWERS)
    roles = [e["role"] for e in events]
    assert roles.count("skeptic") == 3 and 1 <= roles.count("theorist") <= 3 and roles[-2:] == ["director", "forecaster"]
    assert bet["risky"]["id"] == "q1" and bet["risky"]["source"].startswith("refutes")
    assert set(bet["baselines"]) == {"b0", "b1"} and bet["team"]["calls"] == len(events)
    assert all(np.isfinite(p[2]) for f in bet["forecasts"] for p in f["parts"])


def test_an_artifact_never_reaches_the_ledger():
    answers = ANSWERS | {"instrument skeptic": {"artifact": True, "confidence": 0.9, "why": "one-night spike"}}
    bet, events = run(answers)
    assert bet is None and events[-1]["decision"].startswith("dropped")


def test_a_physics_objection_lowers_a_hypothesis():
    plain, _ = run(ANSWERS)
    leader = max((k for k in plain["weights"] if k != "null"), key=plain["weights"].get)
    doubted, _ = run(ANSWERS | {"physics skeptic": {"implausible": [{"hypothesis": leader, "why": "too bright"}]}})
    assert doubted["weights"][leader] < plain["weights"][leader]


def test_the_director_falls_back_to_a_valid_question():
    bet, _ = run(ANSWERS | {"You are the director": {"action": "skip", "question": "q99"}})
    assert bet is not None and bet["risky"] is None and bet["director"]["question"] == "q0"


def test_escalation_uses_the_senior_once():
    answers = ANSWERS | {"You are the director": {"action": "escalate", "question": "q1", "why": "split"},
                         "senior reviewer": {"favoured": "ia", "missing": None, "question": "q0",
                                             "factors": {"ia": 9.0}, "why": "fits"}}
    seniors = [1]
    bet, events = run(answers, seniors)
    assert seniors == [0] and "senior" in [e["role"] for e in events] and bet["director"]["question"] == "q0"
    assert bet["director"]["senior"]["factors"]["ia"] == 3.0


def test_lookouts_vote_when_unsure():
    obj, _ = sn_object()
    views = {"a": as_of(obj, NOW), "b": as_of(obj, NOW)}
    unsure = ANSWERS | {"You are a Lookout": {"investigate": True, "priority": 0.5}}
    with ThreadPoolExecutor(4) as pool:
        picked, events = team.triage(reply(unsure), views, 1, pool)
    assert len(picked) == 1 and len(events) == 6


def test_a_canary_stops_the_call():
    obj, _ = sn_object()
    leaked = as_of(plant(obj, NOW - 5), NOW)
    with pytest.raises(Leak):
        agents.lookout(reply(ANSWERS), team.case_of(leaked))


def test_the_forecasters_words_are_checked_against_the_number():
    q = {"text": "Fainter?", "p_yes": 0.95}
    good, _ = agents.forecaster(reply({"forecaster": {"text": "It is very likely to fade."}}), {"case": "c"}, q)
    bad, _ = agents.forecaster(reply({"forecaster": {"text": "It is unlikely to fade."}}), {"case": "c"}, q)
    assert good["words_match"] and not bad["words_match"]


def test_the_packaged_reader_examples_fit_spark_open():
    from sira import reader
    shots = reader.packaged_shots(reader.PROTOCOLS["v2"])
    assert len(shots) == 7 and {s[1] for s in shots} == {"real", "bogus"}


def test_the_reader_looks_before_the_lookouts(monkeypatch):
    from pathlib import Path
    from sira import reader
    sample = [(reader.PACKAGED / f"ZTF25acfgotd_{k}.fits.gz").read_bytes() for k in reader.KINDS]
    monkeypatch.setattr(team.alerce, "stamp", lambda c, oid, candid, kind: sample[reader.KINDS.index(kind)])
    obj, _ = sn_object()
    for r in obj["photometry"]:
        r["candid"] = "1"
    llm = reply(ANSWERS | {"vetting candidate detections": {"label": "real", "p_real": 0.9, "why": "clean point source"}})
    with ThreadPoolExecutor(4) as pool:
        readings, events = team.eyes(llm, None, {"a": as_of(obj, NOW)}, pool)
    assert readings["a"]["label"] == "real" and events[0]["role"] == "reader" and events[0]["object"] == "a"


def test_random_audits_send_plain_bets_to_the_senior(monkeypatch):
    monkeypatch.setattr(team, "AUDIT", 1.0)
    answers = ANSWERS | {"senior reviewer": {"favoured": "ia", "missing": None, "question": "q1", "factors": {}, "why": "ok"}}
    bet, events = run(answers, [1])
    assert bet["director"]["audit"] and "senior" in [e["role"] for e in events]
