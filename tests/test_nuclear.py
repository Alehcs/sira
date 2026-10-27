import time

import numpy as np
import pytest
from astropy import units as u
from astropy.modeling.physical_models import BlackBody

from sira.models import FutureData, Phot
from sira.nuclear import fit_agn, fit_tde

TDE = {"t_peak": 60100.0, "sigma": 12.0, "t0": 60.0, "amp_r": 300.0, "T": 2.2e4}
WAVE = {"ztfg": 4746.0, "ztfr": 6366.0, "ztfi": 7829.0}
MEANS = {"ztfg": 15.0, "ztfr": 0.0, "ztfi": -10.0}


def tde_flux(t, band):
    # written apart from the module, with astropy's blackbody for the colours
    bb = BlackBody(temperature=TDE["T"] * u.K)
    colour = {b: (bb(w * u.AA) / bb(WAVE["ztfr"] * u.AA)).value for b, w in WAVE.items()}
    dt = np.asarray(t) - TDE["t_peak"]
    rise = np.exp(-0.5 * (np.minimum(dt, 0) / TDE["sigma"]) ** 2)
    fall = (1 + np.maximum(dt, 0) / TDE["t0"]) ** (-5 / 3)
    return TDE["amp_r"] * np.array([colour[b] for b in np.atleast_1d(band)]) * np.where(dt < 0, rise, fall)


def tde_phot(n=300, until=60300.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(60050, until, n))
    band = rng.choice(list(WAVE), n, p=[0.45, 0.45, 0.1])
    err = 4 + 0.02 * tde_flux(t, band)
    return Phot(t, band, tde_flux(t, band) + err * rng.standard_normal(n), err, until)


def drw_phot(n=300, tau=60.0, sigma=40.0, span=1500.0, seed=3):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(59000, 59000 + span, n))
    band = np.array(list(MEANS))[np.arange(n) % 3]
    # exact Ornstein-Uhlenbeck steps between consecutive epochs
    x = [sigma * rng.standard_normal()]
    for d in np.exp(-np.diff(t) / tau):
        x.append(d * x[-1] + sigma * np.sqrt(1 - d * d) * rng.standard_normal())
    err = np.full(n, 5.0)
    flux = np.array([MEANS[b] for b in band]) + np.array(x) + err * rng.standard_normal(n)
    return Phot(t, band, flux, err, t.max() + 0.5)


def test_tde_recovers_peak_time_and_temperature():
    f = fit_tde(tde_phot())
    p = f.params
    assert abs(p["t_peak"] - TDE["t_peak"]) < 3
    assert p["t0"] == pytest.approx(TDE["t0"], rel=0.3)
    assert p["T"] == pytest.approx(TDE["T"], rel=0.25)
    assert f.chi2 / f.ndof < 1.5


def test_tde_forecast_declines_after_the_peak():
    ph = tde_phot(n=120, until=60140.0)
    t = ph.as_of + np.array([5.0, 20.0, 60.0])
    mu, sd = fit_tde(ph).predict(t, "ztfr")
    assert np.all(np.diff(mu) < 0)
    assert np.all(np.abs(mu - tde_flux(t, "ztfr")) < 3 * sd)


def test_tde_colour_stays_uncertain_from_one_band():
    ph = tde_phot()
    r = ph.band == "ztfr"
    f = fit_tde(Phot(ph.t[r], ph.band[r], ph.flux[r], ph.err[r], ph.as_of))
    mu, sd = f.predict([ph.as_of + 10] * 2, ["ztfg", "ztfr"])
    assert sd[0] / mu[0] > 3 * sd[1] / mu[1]


def test_agn_recovers_the_damping_time():
    f = fit_agn(drw_phot())
    assert 60 / 3 < f.extra["tau"] < 60 * 3
    assert f.extra["sigma"] == pytest.approx(40, rel=0.5)
    assert f.params["mean_ztfg"] - f.params["mean_ztfi"] == pytest.approx(25, abs=3)
    assert f.chi2 / f.ndof == pytest.approx(1, abs=0.2)


def test_agn_forecast_reverts_to_the_mean_with_growing_sd():
    ph = drw_phot()
    f = fit_agn(ph)
    t = ph.as_of + np.array([1.0, 10.0, 100.0, 1000.0])
    mu, sd = f.predict(t, "ztfr")
    gap = np.abs(mu - f.params["mean_ztfr"])
    assert np.all(np.diff(gap) < 0) and gap[-1] < 1e-3
    assert np.all(np.diff(f.noise(t, "ztfr")) > 0) and np.all(np.diff(sd[:3]) > 0)
    # far out only the process's own spread and the uncertain mean are left
    i = f.names.index("mean_ztfr")
    assert sd[-1] == pytest.approx(np.sqrt(f.extra["sigma"] ** 2 + f.cov[i, i]), rel=0.02)


def test_agn_takes_signed_or_positive_fluxes():
    ph = drw_phot()
    pos = ph.flux > 0
    assert not pos.all()
    for view in (ph, Phot(ph.t[pos], ph.band[pos], ph.flux[pos], ph.err[pos], ph.as_of)):
        mu, sd = fit_agn(view).predict(ph.as_of + 30, "ztfg")
        assert np.isfinite(mu).all() and np.all(sd > 0)


def test_too_little_data_gives_no_fit():
    ph = tde_phot(n=5)
    assert fit_tde(ph) is None and fit_agn(ph) is None


@pytest.mark.parametrize("fit, make", [(fit_tde, tde_phot), (fit_agn, drw_phot)])
def test_fits_take_under_five_seconds(fit, make):
    ph = make()
    assert len(ph) == 300
    start = time.perf_counter()
    assert fit(ph) is not None
    assert time.perf_counter() - start < 5


@pytest.mark.parametrize("fit", [fit_tde, fit_agn])
def test_a_point_after_the_cut_is_refused(fit):
    ph = tde_phot()
    with pytest.raises(FutureData):
        fit(Phot(ph.t, ph.band, ph.flux, ph.err, ph.t.max() - 1))
