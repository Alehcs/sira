import pytest

from sira.photometry import LATENCY, flux, from_alerce, from_fink


def test_mag_23_9_is_one_microjansky():
    f, fe = flux(23.9, 0.1)
    assert f == pytest.approx(1.0)
    assert fe == pytest.approx(0.0921, abs=1e-3)


def test_alerce_rows_are_sorted_and_delayed():
    lc = {
        "detections": [
            {"mjd": 60010.0, "fid": 2, "magpsf": 19.0, "sigmapsf": 0.05, "isdiffpos": 1, "candid": 2},
            {"mjd": 60005.0, "fid": 1, "magpsf": 19.5, "sigmapsf": 0.08, "isdiffpos": -1, "candid": 1},
        ],
        "non_detections": [{"mjd": 60001.0, "fid": 1, "diffmaglim": 20.4}],
    }
    rows = from_alerce(lc)
    assert [r["kind"] for r in rows] == ["limit", "det", "det"]
    assert rows[1]["band"] == "ztfg" and rows[1]["flux"] < 0
    assert all(r["available_at"] == r["mjd"] + LATENCY for r in rows)


def test_fink_flux_goes_to_microjansky():
    rows = from_fink([{"r:midpointMjdTai": 61100.2, "r:psfFlux": 5000.0, "r:psfFluxErr": 100.0, "r:band": "r", "r:diaSourceId": 7}])
    assert rows[0]["band"] == "lsstr"
    assert rows[0]["flux"] == pytest.approx(5.0)
