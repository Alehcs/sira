import json
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sira.firewall import CANARY_MAG, Leak, as_of, blind, case_id, plant, tripwire

row = st.builds(
    lambda mjd, lag, band, kind, mag: {"mjd": mjd, "available_at": mjd + lag, "band": band, "kind": kind, "mag": mag,
                                       "mag_err": 0.1, "flux": 10 ** (-0.4 * (mag - 23.9)), "flux_err": 1.0},
    st.floats(60000, 60100), st.floats(0, 2), st.sampled_from(["ztfg", "ztfr", "ztfi"]),
    st.sampled_from(["det", "limit"]), st.floats(14, 21))
objects = st.builds(
    lambda rows, stamp_at: {"oid": "ZTF25abcdefg", "survey": "ztf", "ra": 150.1234, "dec": -12.5678, "photometry": rows,
                            "first_stamps": {"mjd": stamp_at - 0.5, "available_at": stamp_at, "files": ["a.png"]},
                            "host": {"file": "h.jpg", "predates_event": True},
                            "truth": {"type": "SN Ia"}, "type": "SN Ia", "redshift": 0.05, "name": "SN2025abc"},
    st.lists(row, max_size=40), st.floats(60000, 60100))
times = st.floats(59990, 60110)


@given(objects, times)
def test_nothing_from_after_t(obj, t):
    view = as_of(obj, t)
    assert all(r["available_at"] <= t for r in view["photometry"])
    assert len(view["photometry"]) == sum(r["available_at"] <= t for r in obj["photometry"])
    assert (view["first_stamps"] is None) == (obj["first_stamps"]["available_at"] > t)


@given(objects, times, times)
def test_later_views_only_add_rows(obj, t1, t2):
    early, late = as_of(obj, min(t1, t2)), as_of(obj, max(t1, t2))
    assert all(r in late["photometry"] for r in early["photometry"])


@given(objects, times)
def test_views_are_idempotent_and_never_carry_the_answer(obj, t):
    view = as_of(obj, t)
    again = as_of(view, t)
    assert again == view
    assert not {"truth", "type", "redshift", "name"} & set(view)


@settings(max_examples=50)
@given(objects, times)
def test_planted_canaries_never_reach_a_model(obj, t):
    planted = plant(obj, t)
    view = as_of(planted, t)
    seen = blind(view)
    tripwire(seen)
    assert str(CANARY_MAG) not in json.dumps(seen)
    assert all(r["day"] <= 0 for r in seen["photometry"])


@settings(max_examples=50)
@given(objects, times)
def test_blind_view_hides_identity_and_dates(obj, t):
    text = json.dumps(blind(as_of(obj, t)))
    for secret in ("ZTF25abcdefg", "150.1234", "-12.5678", "SN2025abc"):
        assert secret not in text
    # no calendar time: every number left is a relative day, a magnitude or an error
    assert all(abs(float(x)) < 1000 for x in re.findall(r"-?\d+\.?\d*", text.replace(case_id("ZTF25abcdefg"), "")))
    assert case_id("ZTF25abcdefg") in text


def test_tripwire_fires_when_the_future_leaks():
    obj = {"oid": "ZTF25abcdefg", "photometry": []}
    leaked = as_of(plant(obj, 60000.0), 60010.0)
    with pytest.raises(Leak):
        tripwire(blind(leaked))


def test_host_image_taken_after_the_event_is_hidden():
    obj = {"oid": "x", "photometry": [], "host": {"file": "h.jpg", "predates_event": False}}
    assert as_of(obj, 60000.0)["host"] is None
