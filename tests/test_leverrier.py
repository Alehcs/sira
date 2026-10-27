import json

import numpy as np
import pytest

from sira import leverrier
from sira.models import _magnification
from test_team import reply


def test_surprise_needs_improbably_many_misses():
    assert not leverrier.surprised([0.5, 0.2, 0.8, 0.995])["surprised"]
    assert leverrier.surprised([0.001, 0.999, 0.5, 0.0005, 0.4, 0.999])["surprised"]
    assert not leverrier.surprised([])["surprised"]


def rows(values, t0=100.0):
    return [{"mjd": t0 + i, "band": "ztfr", "kind": "det", "flux": v, "flux_err": 1.0} for i, v in enumerate(values)]


def test_verdicts_follow_the_evidence():
    data = rows([50.0] * 10)
    right = lambda r: [["a", 1.0, 50.0, 2.0]]
    wrong = lambda r: [["b", 1.0, 30.0, 2.0]]
    assert leverrier.verdict(right, wrong, data)["verdict"] == "neptune"
    assert leverrier.verdict(wrong, right, data)["verdict"] == "vulcan"
    assert leverrier.verdict(right, right, data)["verdict"] == "abstain"


def test_proposals_are_read_and_trimmed():
    llm = reply({"Le Verrier": {"name": "hidden lens", "idea": "a lens", "predicts": "symmetry",
                                "components": [{"type": "lens"}, {"type": "constant"}, {"type": "trend"}, {"type": "flare"}]}})
    out, event = leverrier.propose(llm, "hidden", {"case": "c"}, {"ia": 0.9}, [])
    assert out["name"] == "hidden lens" and len(out["components"]) == 3 and event["role"] == "leverrier"


@pytest.fixture
def lens_snapshot(tmp_path, monkeypatch):
    rng, phot = np.random.default_rng(0), []
    for t in np.arange(60000.0, 60200.0, 2.0):
        for band, fs in (("ztfg", 40.0), ("ztfr", 90.0)):
            f = fs * (_magnification(np.hypot(0.3, (t - 60100.0) / 40.0)) - 1)
            phot.append({"mjd": t, "band": band, "kind": "det", "flux": f + rng.normal(0, 0.03 * f + 1),
                         "flux_err": 0.03 * f + 1, "mag": 19.0, "available_at": t + 0.5})
    (tmp_path / "objects").mkdir()
    (tmp_path / "objects" / "ZTFlens.json").write_text(json.dumps({"oid": "ZTFlens", "survey": "ztf", "ra": 270.0,
                                                                   "dec": -28.0, "photometry": phot}))
    monkeypatch.setattr(leverrier.catalogs, "mw_ebv", lambda c, ra, dec: 0.1)
    monkeypatch.setattr(leverrier, "client", lambda: None)
    return tmp_path


def test_a_lens_the_lab_was_never_given_is_found_on_surprise(lens_snapshot):
    llm = reply({"Le Verrier": {"name": "unseen lens", "idea": "a foreground lens", "predicts": "a symmetric fall",
                                "components": [{"type": "lens"}]}})
    report = leverrier.case(lens_snapshot, "ZTFlens", llm)
    assert report["checks"][-1]["surprise"]["surprised"]
    assert report["best"]["verdict"] == "neptune" and len(report["events"]) == 3
