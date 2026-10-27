import time

import numpy as np
import pytest

from sira.baselines import fit_instrument, fit_null
from sira.models import FLOOR, FutureData, Phot


def flare(n=300, amp=200.0, seed=5):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(60000, 60200, n))
    band = rng.choice(["ztfg", "ztfr"], n)
    err = rng.uniform(2, 6, n)
    flux = amp * np.exp(-0.5 * ((t - 60080) / 30) ** 2) + err * rng.standard_normal(n)
    return Phot(t, band, flux, err, t.max() + 0.5)


def test_null_carries_each_band_forward_with_growing_doubt():
    ph = flare()
    f = fit_null(ph)
    dt = np.array([1.0, 10.0, 100.0])
    for b in ("ztfg", "ztfr"):
        last = np.flatnonzero(ph.band == b)[-1]
        mu, sd = f.predict(ph.t[last] + dt, b)
        assert np.all(mu == ph.flux[last])
        assert sd == pytest.approx(np.hypot(FLOOR * mu, f.extra["scale"] * np.sqrt(1 + dt / 10)))
    # a band never seen falls back on the latest point of any band
    mu, sd = f.predict(ph.as_of + dt, "ztfi")
    assert np.all(mu == ph.flux[-1]) and np.all(np.diff(sd) > 0)
    assert f.extra["scale"] >= np.median(ph.err)


def test_null_uses_the_latest_point_not_the_last_row():
    ph = flare()
    p = np.random.default_rng(0).permutation(len(ph))
    shuffled = Phot(ph.t[p], ph.band[p], ph.flux[p], ph.err[p], ph.as_of)
    t = ph.as_of + np.array([1.0, 30.0])
    assert np.allclose(fit_null(shuffled).predict(t, "ztfg"), fit_null(ph).predict(t, "ztfg"))


def test_instrument_forecasts_nothing_at_the_noise_level():
    ph = flare()
    f = fit_instrument(ph)
    mu, sd = f.predict(ph.as_of + np.array([1.0, 50.0]), "ztfg")
    assert np.all(mu == 0)
    assert sd == pytest.approx(2 * np.median(ph.err))
    assert f.chi2 == pytest.approx(np.sum((ph.flux / ph.sigma) ** 2))


def test_instrument_explains_noise_but_not_a_flare():
    quiet, loud = fit_instrument(flare(amp=0.0)), fit_instrument(flare())
    assert quiet.chi2 / quiet.ndof < 1.3
    assert loud.chi2 / loud.ndof > 10


def test_no_data_gives_no_fit():
    empty = Phot(np.zeros(0), np.zeros(0, dtype=str), np.zeros(0), np.zeros(0), 60000.0)
    assert fit_null(empty) is None and fit_instrument(empty) is None


@pytest.mark.parametrize("fit", [fit_null, fit_instrument])
def test_baselines_take_under_five_seconds(fit):
    ph = flare()
    start = time.perf_counter()
    assert fit(ph) is not None
    assert time.perf_counter() - start < 5


@pytest.mark.parametrize("fit", [fit_null, fit_instrument])
def test_a_point_after_the_cut_is_refused(fit):
    ph = flare()
    with pytest.raises(FutureData):
        fit(Phot(ph.t, ph.band, ph.flux, ph.err, ph.t.max() - 1))
