import json

import pytest

from sira import evidence, replay
from test_replay import season  # noqa: F401
from test_team import ANSWERS, reply


def test_a_case_counts_once_however_many_bets_it_holds():
    lo, hi = evidence._boot([1.0, 1.0, 1.0, -3.0])
    assert lo < 0 < hi and evidence._boot([2.0] * 5) == [2.0, 2.0]


def test_the_lab_keeps_the_lowest_bic_among_the_first_k_le_verriers(tmp_path):
    q = lambda name, bic, verdict, usd: {"name": name, "components": [{"type": "x"}], "bic": bic, "cost_usd": usd,
                                         "against_old": {"verdict": verdict, "log10_e": 3.0 if verdict == "neptune" else 0.1}}
    lens = {"checks": [{}], "proposals": [q("dust", 90, "abstain", 0.05), {"name": "bad", "fit": "not fitted", "cost_usd": 0.04},
                                          q("lens", 40, "neptune", 0.05), q("drift", 30, "vulcan", 0.05), q("lens2", 10, "neptune", 0.05)]}
    quiet = {"checks": [{}, {}]}
    (tmp_path / "leverrier-L1.json").write_text(json.dumps(lens))
    (tmp_path / "leverrier-I1.json").write_text(json.dumps(quiet))
    out = evidence.leverriers(tmp_path, {"microlensing": ["L1", "L9"], "ia": ["I1"]})
    row = out["rows"][0]
    assert [row[k]["name"] for k in ("1", "3", "5")] == ["dust", "lens", "lens2"]
    assert [row[k]["verdict"] for k in ("1", "3", "5")] == ["abstain", "neptune", "neptune"]
    assert row["5"]["usd"] == pytest.approx(0.24) and out["objects"]["microlensing"] == {"n": 2, "replayed": 1, "surprised": 1}
    assert out["sizes"][3]["neptune_on_lenses"] == 1 and out["sizes"][3]["discoveries_per_usd"] == pytest.approx(1 / 0.14, rel=1e-2)


def _e(seq, kind, payload, time="2026-10-30T02:00:00+00:00"):
    return {"seq": seq, "kind": kind, "payload": payload, "time": time}


def test_the_live_record_counts_answers_up_to_the_freeze_head():
    entries = [_e(0, "event", {"role": "lookout", "object": "A", "decision": "investigate", "cost_usd": 0.01}),
               _e(1, "event", {"role": "lookout", "object": "A", "decision": "pass", "cost_usd": 0.01}),
               _e(2, "event", {"role": "lookout", "object": "A", "decision": "pass", "cost_usd": 0.01}),
               _e(3, "event", {"role": "theorist", "object": "A", "cost_usd": 0.1}),
               _e(4, "event", {"role": "director", "object": "B", "cost_usd": 0.1, "round": 1}),
               _e(5, "bet", {"bet": "A-1", "object": "A"}),
               _e(6, "answer", {"bet": "A-1", "p_yes": 0.8, "yes": True, "log_score": -0.22}),
               _e(7, "answer", {"bet": "A-2", "p_yes": 0.3, "yes": True, "log_score": -1.2}),
               _e(8, "answer", {"bet": "A-3", "void": True}),
               _e(9, "answer", {"bet": "A-4", "p_yes": 0.9, "yes": True, "log_score": -0.1})]
    out = evidence.live(entries, seq=8)
    assert {k: out["record"][k] for k in ("answered", "right", "void")} == {"answered": 2, "right": 1, "void": 1}
    assert out["record"]["brier"] == pytest.approx((0.04 + 0.49) / 2, abs=1e-3)
    assert out["cost"]["investigated"] == 1 and out["cost"]["usd"] == pytest.approx(0.13)  # the round's work stays out
    assert out["lookouts"] == {"looks": 1, "voted": 1, "vote_changed_decision": 1, "extra_usd": 0.02}


def test_two_runs_of_the_same_case_count_as_one_object(season):  # noqa: F811
    answers = ANSWERS | {"no physics code to help": {"classes": {"ia": 0.6, "ii": 0.4},
                                                     "forecast": [{"band": "r", "day": 1, "flux": 50, "sd": 10}]}}
    for run in ("a", "b"):
        replay.case(season, "ZTF26test", season / run, reply(answers), gap=5, n=3)
    out = evidence.replays(season, {"a": season / "a", "b": season / "b"})
    assert out["cases"] == 1 and out["rows"][0]["runs"] == 2 and not out["failed"]
    assert out["primary"]["b2"]["mean"] == pytest.approx(out["rows"][0]["sira_minus"]["b2"], abs=1e-3)
    assert set(out["forecasters"]) == {"sira", "b0", "b1", "b2"} and "no_llm" in out["ablations"]


def test_the_replays_also_report_muse_against_climatology_and_the_questions_after_the_plan(season):  # noqa: F811
    answers = ANSWERS | {"no physics code to help": {"classes": {"ia": 0.6, "ii": 0.4},
                                                     "forecast": [{"band": "r", "day": 1, "flux": 50, "sd": 10}]}}
    replay.case(season, "ZTF26test", season / "a", reply(answers), gap=5, n=3)
    out = evidence.replays(season, {"a": season / "a"})["posthoc"]
    partner = out["muse_or_climatology_as_partner"]
    assert partner["cases"] == 1 and partner["cases_ahead"] in (0, 1) and len(partner["ci95"]) == 2
    asked = out["questions"]
    assert set(asked["by_forecaster"]) == {"sira", "b0", "b1", "b2"} and asked["objects"] <= 1
    assert 0 <= asked["base_rate_brier"] <= 0.25


def test_the_reader_is_scored_from_its_own_reads_and_the_protocols_are_compared_pair_by_pair(tmp_path):
    truth = ["real"] * 4 + ["bogus"] * 4
    rows = lambda wrong: [{"oid": f"Z{i}", "truth": t, "label": ("bogus" if t == "real" else "real") if i in wrong else t,
                           "p_real": 0.2 if (t == "real") == (i in wrong) else 0.8} for i, t in enumerate(truth)]
    for name, wrong in (("v1", {0, 4}), ("v2", set())):
        (tmp_path / f"holdout-{name}.json").write_text(json.dumps({"protocol": name, "model": "spark-open", "code": "c",
                                                                   "usd_per_read": 0.01, "rows": rows(wrong)}))
    out = evidence.readers(tmp_path)
    assert out["v2"]["balanced_accuracy"] == 1.0 and out["v1"]["balanced_accuracy"] == 0.75 and out["v2"]["auc"] == 1.0
    assert out["v2_vs_v1"] == {"gained": 2, "lost": 0, "p": 0.5}
