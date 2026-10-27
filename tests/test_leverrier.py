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


def lens_object(peak=61360.0, te=20.0):
    rng, rows = np.random.default_rng(1), []
    for t in np.arange(61300.0, 61420.0, 1.0):
        for band, fs in (("ztfg", 40.0), ("ztfr", 90.0)):
            f = fs * (_magnification(np.hypot(0.3, (t - peak) / te)) - 1)
            rows.append({"mjd": t, "band": band, "kind": "det", "flux": f + rng.normal(0, 0.03 * f + 1),
                         "flux_err": 0.03 * f + 1, "mag": 19.0, "available_at": t + 0.5})
    return {"oid": "ZTFlens", "survey": "ztf", "ra": 270.0, "dec": -28.0, "photometry": rows}


@pytest.fixture
def sealed_by_time(monkeypatch):
    from sira import ledger, verify
    clock = {"iso": None}
    # each fake receipt carries the moment it was stamped, as a real one does
    stamp = lambda c, h: f"{clock['iso']}|{h}".encode()
    check = lambda path, h: (path.exists() and path.read_bytes().decode().endswith(h), path.read_bytes().decode().split("|")[0])
    monkeypatch.setattr(ledger, "rfc3161", stamp)
    monkeypatch.setattr(ledger, "check_rfc3161", check)
    monkeypatch.setattr(verify, "check_rfc3161", check)
    monkeypatch.setattr(ledger, "OTS", "true")
    return clock


def iso(mjd):
    from astropy.time import Time
    return Time(mjd, format="mjd").to_datetime().replace(microsecond=0).isoformat() + "+00:00"


def test_a_live_surprise_becomes_a_le_verrier_bet_and_a_verdict(tmp_path, monkeypatch, sealed_by_time):
    from concurrent.futures import ThreadPoolExecutor

    from sira import highlights, live, verify
    from sira.ledger import Ledger

    obj = lens_object()
    monkeypatch.setattr(live, "observe", lambda c, oid, now: obj)
    monkeypatch.setattr(leverrier.catalogs, "mw_ebv", lambda c, ra, dec: 0.1)
    book = Ledger(tmp_path)
    grid = [{"mjd": 61341.0 + d, "band": b, "parts": [["ia", 0.9, 10.0, 1.0], ["null", 0.1, 10.0, 2.0]]}
            for d in range(5) for b in ("ztfg", "ztfr")]
    book.append("bet", {"bet": "b1", "object": "ZTFlens", "made_at": 61340.74, "weights": {"ia": 0.9, "null": 0.1},
                        "forecasts": grid})
    sealed_by_time["iso"] = iso(61340.75)
    book.anchor(None)
    live.resolve(book, None, 61346.0)
    llm = reply({"Le Verrier": {"name": "unseen lens", "idea": "a foreground lens", "predicts": "a symmetric peak",
                                "components": [{"type": "lens"}]}})
    with ThreadPoolExecutor(3) as pool:
        new, spent = leverrier.watch(book, None, llm, 61346.0, pool, "20261101T2100")
    kinds = [e["kind"] for e in new]
    assert kinds.count("surprise") == 1 and kinds.count("event") == 3 and kinds[-1] == "bet"
    leap = new[-1]["payload"]
    assert leap["model"] == "leverrier" and "old" in leap["baselines"] and leap["seen"]
    sealed_by_time["iso"] = iso(61346.02)
    book.anchor(None)
    live.resolve(book, None, 61358.0)
    verdicts = leverrier.judge(book, 61358.0)
    assert verdicts and verdicts[0]["payload"]["verdict"] == "neptune"
    sealed_by_time["iso"] = iso(61358.02)
    book.anchor(None)
    result = verify.verify(tmp_path)
    assert result["passes"], result["problems"]
    lines = book.path.read_text().splitlines()
    import json as _json
    forged = [_json.loads(l) for l in lines if '"kind": "verdict"' in l][0]["payload"] | {"verdict": "vulcan"}
    book.append("verdict", forged)
    assert any("does not follow from the scores" in p for p in verify.verify(tmp_path)["problems"])
    kinds = {m["kind"] for m in highlights.highlights(tmp_path)}
    assert {"verdict", "leap", "surprise"} <= kinds


def test_a_surprise_without_failing_outcomes_is_caught(tmp_path, sealed_by_time):
    from sira import verify
    from sira.ledger import Ledger

    book = Ledger(tmp_path)
    book.append("bet", {"bet": "b1", "object": "x", "made_at": 61340.74, "forecasts": [
        {"mjd": 61341.0, "band": "ztfr", "parts": [["ia", 1.0, 10.0, 1.0]]}]})
    sealed_by_time["iso"] = iso(61340.75)
    book.anchor(None)
    book.append("surprise", {"bet": "b1", "object": "x", "n": 5, "misses": 5, "p_value": 1e-9, "surprised": True})
    assert any("do not show it" in p for p in verify.verify(tmp_path)["problems"])
