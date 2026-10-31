import json
import time
from types import SimpleNamespace

import pytest

from sira import visits
from sira.firewall import as_of
from test_live import sn_object
from test_team import ANSWERS, NOW, reply
from test_team import run as investigate

ALONE = {"no physics code to help": {"classes": {"ia": 0.7, "ii": 0.3}, "forecast": [{"band": "r", "day": 1, "flux": 50, "sd": 10}]}}
VOICES = {"physics skeptic": {"implausible": [{"hypothesis": "ia", "why": "too bright for its colour"}]},
          "memory skeptic": {"recognised": True, "name": "SN 2026abc", "confidence": 0.3}}


def bilingual(answers, broken=False):
    # the team's fake answers, and a translator that tags each note or fails; it remembers what the agents read
    team, heard = reply(answers), []

    def chat(provider, model, messages, tag="", **kwargs):
        if tag != "spanish":
            heard.append(json.dumps(messages))
            return team.chat(provider, model, messages, tag, **kwargs)
        time.sleep(0.01)
        if broken:
            raise RuntimeError("down")
        notes = json.loads(messages[-1]["content"])
        usage = SimpleNamespace(prompt_tokens=500, completion_tokens=100, prompt_tokens_details=None,
                                completion_tokens_details=None)
        text = json.dumps({k: f"[es] {v}" for k, v in notes.items()})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)
    return SimpleNamespace(chat=chat, heard=heard)


@pytest.fixture
def visit(monkeypatch):
    obj, _ = sn_object()
    saved = []
    monkeypatch.setattr(visits, "client", lambda: None)
    monkeypatch.setattr(visits, "now_mjd", lambda: NOW)
    monkeypatch.setattr(visits, "load", lambda c, i: {"id": i, "object": "ZTF26abcdefg", "status": "queued"})
    monkeypatch.setattr(visits, "save", lambda c, i, **f: saved.append(f))
    monkeypatch.setattr(visits, "in_round", lambda c, oid: False)
    monkeypatch.setattr(visits, "observe", lambda c, oid, now: obj)
    monkeypatch.setattr(visits.catalogs, "mw_ebv", lambda c, ra, dec: 0.02)
    monkeypatch.setattr(visits.lab, "eyes", lambda llm, c, views, pool: ({}, [{"role": "reader", "cost_usd": 0.01,
                                                                              "decision": "real (0.9)", "case": "case-x"}]))
    monkeypatch.setattr(visits, "LLM", lambda: reply(ANSWERS | ALONE))
    return {"obj": obj, "saved": saved, "monkeypatch": monkeypatch}


def test_a_visit_reports_each_stage_and_ends_with_the_bet_in_words(visit):
    visits.run("ZTF26abcdefg", 7)
    saved = visit["saved"]
    grows = [len(f["steps"]) for f in saved if "steps" in f]
    assert saved[0]["status"] == "running" and saved[-1]["status"] == "done"
    assert grows[0] == 1 and len(set(grows)) >= 3 and grows == sorted(grows)
    assert not any("case" in s for f in saved if "steps" in f for s in f["steps"])
    result = saved[-1]["result"]
    assert result["question"]["kind"] == "level" and result["term"] and result["fan"] and result["director"]["action"] == "bet"


def test_a_visit_with_too_few_points_fails_before_any_model_is_called(visit):
    visit["obj"]["photometry"] = visit["obj"]["photometry"][:4]
    visit["monkeypatch"].setattr(visits, "LLM", lambda: pytest.fail("no model should be called"))
    with pytest.raises(RuntimeError, match="too_few_points"):
        visits.run("ZTF26abcdefg", 7)
    assert visit["saved"][-1] | {"finished_at": None} == {"status": "failed", "error": "too_few_points", "finished_at": None}


def test_an_object_in_todays_round_waits_for_the_bell(visit):
    visit["monkeypatch"].setattr(visits, "in_round", lambda c, oid: True)
    with pytest.raises(RuntimeError, match="in_round"):
        visits.run("ZTF26abcdefg", 7)


def test_only_ztf_names_are_investigated():
    with pytest.raises(ValueError):
        visits.run("ZTF26abc; rm -rf /")


def test_every_note_reaches_the_site_in_both_languages_before_done(visit):
    llm = bilingual(ANSWERS | ALONE | VOICES)
    visit["monkeypatch"].setattr(visits, "LLM", lambda: llm)
    out = visits.run("ZTF26abcdefg", 7)
    saved = visit["saved"]
    last = [f for f in saved if "steps" in f][-1]
    notes = [s for s in last["steps"] if s.get("why")]
    assert saved[-1]["status"] == "done" and last["steps"] == out["steps"]
    assert {s["role"] for s in notes} >= {"theorist", "skeptic", "director", "forecaster"}
    assert all(s["why_es"] == f"[es] {s['why']}" for s in notes)
    assert {s["lens"]: s["why"] for s in notes if s["role"] == "skeptic"} == {
        "instrument": "smooth", "physics": "Type Ia supernova: too bright for its colour.", "memory": "SN 2026abc"}
    assert last["cost_usd"] > round(sum(s["cost_usd"] for s in last["steps"]), 4)
    assert not any("[es]" in m for m in llm.heard)


def test_a_failed_translation_leaves_the_english_and_the_visit_goes_on(visit):
    visit["monkeypatch"].setattr(visits, "LLM", lambda: bilingual(ANSWERS | ALONE, broken=True))
    out = visits.run("ZTF26abcdefg", 7)
    saved = visit["saved"]
    last = [f for f in saved if "steps" in f][-1]
    assert saved[-1]["status"] == "done" and out["result"]["term"]
    assert not any("why_es" in s for f in saved if "steps" in f for s in f["steps"])
    assert [s["why"] for s in last["steps"] if s.get("why")] and last["cost_usd"] == round(sum(s["cost_usd"] for s in last["steps"]), 4)


def test_the_row_is_written_by_one_thread_at_a_time(visit):
    busy, clashes = [], []

    def save(c, i, **fields):
        if busy:
            clashes.append(fields)
        busy.append(fields)
        time.sleep(0.005)
        visit["saved"].append(fields)
        busy.pop()

    visit["monkeypatch"].setattr(visits, "save", save)
    visit["monkeypatch"].setattr(visits, "LLM", lambda: bilingual(ANSWERS | ALONE))
    visits.run("ZTF26abcdefg", 7)
    assert clashes == [] and visit["saved"][-1]["status"] == "done"


def test_the_skeptics_speak_from_the_result():
    lenses = {"instrument": {"artifact": False, "confidence": 0.9, "why": "Smooth rise over 20 days"},
              "physics": {"implausible": [{"hypothesis": "ii", "why": "Peak before the first detection"},
                                          {"hypothesis": "ibc", "why": "y" * 199 + "."},
                                          {"hypothesis": "tde", "why": "x" * 200}]},
              "memory": {"recognised": True, "name": "null", "confidence": 0.9}}
    assert visits.said(lenses) == {"instrument": "Smooth rise over 20 days", "memory": "", "physics": (
        f"Type II supernova: Peak before the first detection. Type Ibc supernova: {'y' * 199}. Tidal disruption: {'x' * 200}…")}


def test_a_note_cut_on_a_decimal_point_ends_on_its_last_whole_sentence():
    head = "Near normal Ia peak luminosity."
    note = head + " " + "x" * (195 - len(head)) + " ~0."
    assert len(note) == 200 and visits._clip(note) == head


def test_the_summary_draws_the_forecast_after_now():
    bet, _ = investigate(ANSWERS)
    out = visits.summary(as_of(sn_object()[0], NOW), bet, None)
    assert all(f[0] > 0 and f[3] >= 0 for f in out["fan"]) and all(s[0] <= 0 for s in out["seen"])
    assert [t["hypothesis"] for t in out["theories"]] and set(out["skeptics"]) == {"instrument", "physics", "memory"}
