import json

import numpy as np
import pytest

from sira import replay
from test_live import sn_object
from test_team import ANSWERS, reply


@pytest.fixture
def season(tmp_path, monkeypatch):
    obj, _ = sn_object(now=61360.0)
    obj["photometry"] = [r for r in obj["photometry"]]
    (tmp_path / "objects").mkdir()
    (tmp_path / "objects" / "ZTF26test.json").write_text(json.dumps(obj))
    (tmp_path / "truth.json").write_text(json.dumps({"ZTF26test": {"type": "SN Ia", "redshift": 0.04}}))
    monkeypatch.setattr(replay.catalogs, "mw_ebv", lambda c, ra, dec: 0.02)
    monkeypatch.setattr("sira.leverrier.catalogs.mw_ebv", lambda c, ra, dec: 0.02)
    return tmp_path


def test_checkpoints_start_at_the_fifth_point_and_need_a_future():
    obj, _ = sn_object(now=61360.0)
    times = replay.checkpoints(obj, gap=5, n=6)
    dets = sorted(r["mjd"] for r in obj["photometry"])
    assert times and times[0] == pytest.approx(dets[4] + 0.5, abs=1e-3) and all(t + 5 <= dets[-1] for t in times)


def test_truth_types_map_to_the_lab_classes():
    assert [replay.klass(t) for t in ("SN Ia", "SN IIP", "SN IIb", "TDE-H-He", "SLSN-I", "microlensing")] == \
           ["ia", "ii", "ibc", "tde", "other", "other"]


def test_a_season_replays_every_forecaster_on_the_same_data(season):
    answers = ANSWERS | {"no physics code to help": {"classes": {"ia": 0.6, "ii": 0.4},
                                                     "forecast": [{"band": "r", "day": 1, "flux": 50, "sd": 10}]}}
    result = replay.case(season, "ZTF26test", season / "out", reply(answers), gap=5, n=3)
    assert result["checkpoints"] >= 1
    summary = replay.report(season, season / "out")
    assert summary["bets"] == result["checkpoints"] and summary["outcomes"] > 0
    assert all(summary[k]["log_score"] is not None for k in ("sira", "b0", "b1", "b2"))
    assert set(summary["sira_minus"]) == {"b0", "b1", "b2"} and summary["sira"]["class_log_loss"] is not None
