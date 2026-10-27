import numpy as np
import pytest
import sncosmo
from astropy.cosmology import Planck18

from sira import ledger, live
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


def test_forecasts_are_interpolated_between_days():
    grid = [{"mjd": 1.0, "band": "ztfr", "parts": [["ia", 1.0, 10.0, 1.0]]},
            {"mjd": 2.0, "band": "ztfr", "parts": [["ia", 1.0, 20.0, 3.0]]}]
    assert live._at(grid, 1.5, "ztfr") == [["ia", 1.0, 15.0, 2.0]]
    assert live._at(grid, 3.0, "ztfr") == [["ia", 1.0, 20.0, 3.0]]


def test_only_measurements_after_the_seal_are_scored(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "rfc3161", lambda c, h: b"r")
    monkeypatch.setattr(ledger, "check_rfc3161", lambda c, path, h: (True, SEALED_AT))
    monkeypatch.setattr(ledger, "OTS", "true")
    obj, m = sn_object()
    book = Ledger(tmp_path)
    book.append("bet", {"bet": "b1", "object": obj["oid"]} | live.forecast(as_of(obj, 61340.75), 0.02))
    book.anchor(None)
    later = [{"mjd": t, "band": "ztfr", "kind": "det", "flux": float(m.bandflux("ztfr", t, zp=23.9, zpsys="ab")),
              "flux_err": 3.0, "mag": 19.0, "available_at": t + 0.5} for t in (61340.70, 61342.0, 61343.8)]
    monkeypatch.setattr(live, "observe", lambda c, oid, now: {"photometry": later})
    new = live.resolve(book, None, 61345.0)
    outcomes = [e for e in new if e["kind"] == "outcome"]
    assert [o["payload"]["mjd"] for o in outcomes] == [61342.0, 61343.8]
    assert all(np.isfinite(o["payload"]["log_score"]) and 0 <= o["payload"]["pit"] <= 1 for o in outcomes)
    assert [e["kind"] for e in new].count("answer") == 1
    assert live.resolve(book, None, 61345.0) == []
    assert ledger.verify(tmp_path, None)["passes"]
