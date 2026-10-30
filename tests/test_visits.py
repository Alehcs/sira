import pytest

from sira import visits
from sira.firewall import as_of
from test_live import sn_object
from test_team import ANSWERS, NOW, reply
from test_team import run as investigate

ALONE = {"no physics code to help": {"classes": {"ia": 0.7, "ii": 0.3}, "forecast": [{"band": "r", "day": 1, "flux": 50, "sd": 10}]}}


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


def test_the_summary_draws_the_forecast_after_now():
    bet, _ = investigate(ANSWERS)
    out = visits.summary(as_of(sn_object()[0], NOW), bet, None)
    assert all(f[0] > 0 and f[3] >= 0 for f in out["fan"]) and all(s[0] <= 0 for s in out["seen"])
    assert [t["hypothesis"] for t in out["theories"]] and set(out["skeptics"]) == {"instrument", "physics", "memory"}
