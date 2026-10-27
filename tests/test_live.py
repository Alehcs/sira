import numpy as np
import pytest
import sncosmo
from astropy.cosmology import Planck18

from sira import ledger, live
from sira import verify as verify_module
from sira.firewall import as_of
from sira.ledger import Ledger
from sira.models import ALPHA, BETA, M_B

SEALED_AT = "2026-10-27T18:00:00+00:00"  # MJD 61340.75


def sn_object(now=61340.75):
    m = sncosmo.Model(source="salt3")
    m.set(z=0.04, t0=now - 3, x1=0.0, c=0.0)
    m.set_source_peakabsmag(M_B, "bessellb", "ab", cosmo=Planck18)
    rng, rows = np.random.default_rng(0), []
    for t in np.arange(now - 20, now, 1.5):
        for band in ("ztfg", "ztfr"):
            f = float(m.bandflux(band, t, zp=23.9, zpsys="ab"))
            rows.append({"mjd": t, "band": band, "kind": "det", "flux": f + rng.normal(0, 0.03 * f + 2),
                         "flux_err": 0.03 * f + 2, "mag": 20.0, "available_at": t + 0.5})
    return {"oid": "ZTF26test", "survey": "ztf", "ra": 150.0, "dec": 20.0, "photometry": rows}, m


def test_forecast_mixes_hypotheses_and_keeps_room_for_none_of_them():
    obj, _ = sn_object()
    result = live.forecast(as_of(obj, 61340.75), 0.02)
    assert sum(result["weights"].values()) == pytest.approx(1, abs=1e-3)
    assert result["weights"]["null"] == live.NULL_WEIGHT
    assert len(result["forecasts"]) == len(live.DAYS) * len(live.BANDS)
    assert 0 <= result["question"]["p_yes"] <= 1
    assert all(f["eig"] >= 0 for f in result["forecasts"])
    assert result["decision"]["action"] in ("wait", "think", "confident")
    assert len(result["baselines"]["b0"]) == len(result["forecasts"])


def test_forecasts_are_interpolated_between_days():
    grid = [{"mjd": 1.0, "band": "ztfr", "parts": [["ia", 1.0, 10.0, 1.0]]},
            {"mjd": 2.0, "band": "ztfr", "parts": [["ia", 1.0, 20.0, 3.0]]}]
    assert live._at(grid, 1.5, "ztfr") == [["ia", 1.0, 15.0, 2.0]]
    assert live._at(grid, 3.0, "ztfr") == [["ia", 1.0, 20.0, 3.0]]


def test_only_measurements_after_the_seal_are_scored(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "rfc3161", lambda c, h: b"r")
    monkeypatch.setattr(ledger, "check_rfc3161", lambda path, h: (True, SEALED_AT))
    monkeypatch.setattr(verify_module, "check_rfc3161", lambda path, h: (True, SEALED_AT))
    monkeypatch.setattr(ledger, "OTS", "true")
    obj, m = sn_object()
    book = Ledger(tmp_path)
    book.append("bet", {"bet": "b1", "object": obj["oid"], "made_at": 61340.74}
                | live.forecast(as_of(obj, 61340.75), 0.02))
    book.anchor(None)
    later = [{"mjd": t, "band": "ztfr", "kind": "det", "flux": float(m.bandflux("ztfr", t, zp=23.9, zpsys="ab")),
              "flux_err": 3.0, "mag": 19.0, "available_at": t + 0.5} for t in (61340.70, 61342.0, 61343.8)]
    monkeypatch.setattr(live, "observe", lambda c, oid, now: {"photometry": later})
    new = live.resolve(book, None, 61346.0)
    outcomes = [e for e in new if e["kind"] == "outcome"]
    assert [o["payload"]["mjd"] for o in outcomes] == [61342.0, 61343.8]
    assert all(np.isfinite(o["payload"]["log_score"]) and 0 <= o["payload"]["pit"] <= 1 for o in outcomes)
    assert [e["kind"] for e in new].count("answer") == 1
    assert live.resolve(book, None, 61346.0) == []
    assert all("b0" in o["payload"]["baselines"] for o in outcomes)
    assert verify_module.verify(tmp_path)["passes"]
    lines = book.path.read_text().splitlines()
    forged = __import__("json").loads(lines[2])
    forged["payload"]["baselines"]["b0"]["log_score"] = -0.001
    book.path.write_text("\n".join(lines[:2]) + "\n")
    book.append("outcome", forged["payload"])
    assert any("does not follow" in p for p in verify_module.verify(tmp_path)["problems"])


def test_a_hypothesis_with_a_broken_forecast_is_dropped(monkeypatch):
    obj, _ = sn_object()
    real = live.fit

    def broken(kind, ph, ebv=0.0):
        f = real(kind, ph, ebv)
        if f is not None and kind == "ii":
            f.flux = lambda p, t, band: np.full(len(t), np.nan)
        return f

    monkeypatch.setattr(live, "fit", broken)
    result = live.forecast(as_of(obj, 61340.75), 0.02)
    assert "ii" not in result["weights"] and sum(result["weights"].values()) == pytest.approx(1, abs=1e-3)
    assert all(np.isfinite(x) for f in result["forecasts"] for part in f["parts"] for x in part[1:])


def test_without_keys_the_team_falls_back_to_physics(tmp_path, monkeypatch):
    from sira import config
    monkeypatch.setattr(config, "KEYS", {"meta": "", "baseten": ""})
    monkeypatch.setattr(live, "client", lambda: None)
    monkeypatch.setattr(live, "active", lambda c, now, n: [])
    monkeypatch.setattr(ledger.Ledger, "anchor", lambda self, c: None)
    monkeypatch.setattr(live, "upgrade", lambda root: None)
    result = live.run(tmp_path, team=True)
    assert result["bets"] == 0 and any("no API keys" in s for s in result["skipped"])


def test_a_type_ia_is_not_ruled_out_by_brightness_without_a_distance():
    # far too bright for its redshift, which the light curve alone cannot tell
    m = sncosmo.Model(source="salt3")
    m.set(z=0.04, t0=61337.75, x1=0.0, c=0.0)
    m.set_source_peakabsmag(-21.5, "bessellb", "ab", cosmo=Planck18)
    obj, _ = sn_object()
    for r in obj["photometry"]:
        r["flux"] = float(m.bandflux(r["band"], r["mjd"], zp=23.9, zpsys="ab"))
        r["flux_err"] = 0.03 * r["flux"] + 2
    result = live.forecast(as_of(obj, 61340.75), 0.02)
    assert "ia" not in result["killed"] and result["weights"]["ia"] > 0.5


def test_a_team_bet_pools_the_physics_with_the_models_own_forecast():
    obj, _ = sn_object()
    view = as_of(obj, 61340.75)
    phys = live.physics(view, 0.02)
    mind = {"classes": {"ia": 0.8, "other": 0.2}, "points": {("ztfr", 1): (123.0, 5.0)}}
    alone, pooled = live.assemble(phys, phys["weights"], view), live.assemble(phys, phys["weights"], view, mind)
    for a, b in zip(alone["forecasts"], pooled["forecasts"]):
        assert b["parts"][-1][:2] == ["llm", live.LLM_SHARE] and b["eig"] == a["eig"]
        assert sum(p[1] for p in b["parts"]) == pytest.approx(1, abs=1e-3)
    day1 = next(f for f in pooled["forecasts"] if f["band"] == "ztfr" and f["mjd"] == pytest.approx(61341.75))
    assert day1["parts"][-1][2:] == [123.0, 5.0]
    q = pooled["question"]
    at = next(f for f in pooled["forecasts"] if f["mjd"] == q["mjd"] and f["band"] == q["band"])
    assert q["p_yes"] == round(live.chance(at["parts"], q["reference"], "above"), 3)
    assert [f["parts"] for f in pooled["baselines"]["b2"]] == [[["llm", 1.0, *f["parts"][-1][2:]]] for f in pooled["forecasts"]]
    assert sum(pooled["classes"].values()) == pytest.approx(1, abs=1e-3) and pooled["classes"]["ia"] >= 0.4
    assert "b2" not in alone["baselines"] and "classes" not in alone
