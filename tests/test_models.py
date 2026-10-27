import numpy as np
import pytest
import sncosmo
from astropy.cosmology import Planck18

from sira import models
from sira.models import ALPHA, BETA, M_B, FutureData, Phot, fit, ia_distance, phot


def sampled(flux_of, start, stop, step, seed, as_of=None, bands=("ztfg", "ztfr")):
    rng = np.random.default_rng(seed)
    t = np.repeat(np.arange(start, stop, step, dtype=float), len(bands))
    band = np.tile(bands, len(t) // len(bands))
    true = flux_of(t, band)
    err = 0.03 * np.abs(true) + 2.0
    return Phot(t, band, true + rng.normal(0, err), err, as_of if as_of is not None else t.max()), true


def salt3(z=0.05, t0=60000.0, x1=0.5, c=0.0):
    m = sncosmo.Model(source="salt3")
    m.set(z=z, t0=t0, x1=x1, c=c)
    m.set_source_peakabsmag(M_B - ALPHA * x1 + BETA * c, "bessellb", "ab", cosmo=Planck18)
    return m


def test_ia_fit_recovers_the_peak_and_forecasts_the_decline():
    m = salt3()
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 3, seed=1)
    f = fit("ia", ph)
    assert abs(f.params["t0"] - 60000) < 2 and f.seconds < 5
    mu, sd = f.predict([60030.0], ["ztfr"])
    truth = m.bandflux("ztfr", 60030.0, zp=23.9, zpsys="ab")
    assert abs(mu[0] - truth) < 3 * sd[0]


def test_ia_light_curve_alone_gives_the_redshift():
    m = salt3(z=0.06)
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 2, seed=2)
    assert ia_distance(ph)["z"] == pytest.approx(0.06, rel=0.1)


def test_lens_fit_recovers_the_event():
    t0, u0, te, fs = 60020.0, 0.2, 30.0, {"ztfg": 50.0, "ztfr": 80.0}
    def flux(t, b):
        u = np.hypot(u0, (t - t0) / te)
        return np.array([fs[x] for x in b]) * (models._magnification(u) - 1)
    ph, _ = sampled(flux, 59960, 60080, 2, seed=3)
    f = fit("lens", ph)
    assert abs(f.params["t0"] - t0) < 2 and abs(f.params["u0"] - u0) < 0.1 and f.seconds < 5
    mu, sd = f.predict([60020.0, 60100.0], ["ztfr", "ztfr"])
    assert np.all(sd > 0) and mu[0] > mu[1]


def test_fits_refuse_points_from_after_the_cut():
    m = salt3()
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 3, seed=4, as_of=60010.0)
    for kind in ("ia", "lens"):
        with pytest.raises(FutureData):
            fit(kind, ph)


def test_phot_keeps_positive_detections_unless_signed():
    view = {"as_of": 60010.0, "photometry": [
        {"mjd": 60000.0, "band": "ztfg", "kind": "det", "flux": 10.0, "flux_err": 1.0},
        {"mjd": 60001.0, "band": "ztfg", "kind": "det", "flux": -5.0, "flux_err": 1.0},
        {"mjd": 60002.0, "band": "ztfg", "kind": "limit", "flux": 3.0, "flux_err": 0.0},
    ]}
    assert len(phot(view)) == 1 and len(phot(view, signed=True)) == 2


def test_too_little_data_gives_no_fit():
    ph = Phot(np.array([60000.0]), np.array(["ztfg"]), np.array([10.0]), np.array([1.0]), 60001.0)
    assert fit("ia", ph) is None and fit("lens", ph) is None


def test_budget_rejects_a_supernova_placed_too_far_away():
    m = salt3(z=0.04)
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 3, seed=5)
    near, far = models.fit_template("ia", ph, z=0.04), models.fit_template("ia", ph, z=0.15)
    assert models.budget(near)["possible"] and 0.3 < models.budget(near)["nickel"] < 1.2
    assert not models.budget(far)["possible"]
    assert models.budget(fit("lens", ph)) is None


def test_every_hypothesis_fits_and_forecasts_through_one_entry_point():
    m = salt3()
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 2, seed=6)
    for kind in models.HYPOTHESES:
        f = fit(kind, ph)
        mu, sd = f.predict([60045.0, 60060.0], ["ztfg", "ztfr"])
        assert f.model == kind and f.seconds < 5 and np.all(np.isfinite(mu)) and np.all(sd > 0), kind


def test_forecast_past_the_template_keeps_fading_with_growing_doubt():
    m = salt3()
    ph, _ = sampled(lambda t, b: m.bandflux(b, t, zp=23.9, zpsys="ab"), 59985, 60040, 2, seed=7)
    mu, sd = fit("ia", ph).predict([60045.0, 60070.0, 60100.0], ["ztfr"] * 3)
    assert mu[0] > mu[1] > mu[2] > 0
    assert sd[1] / mu[1] < sd[2] / mu[2]
