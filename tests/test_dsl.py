import numpy as np
import pytest

from sira import dsl
from sira.models import FutureData, Phot, _magnification


def sampled(flux_of, start, stop, step, seed=0, bands=("ztfg", "ztfr")):
    rng = np.random.default_rng(seed)
    t = np.repeat(np.arange(start, stop, step, dtype=float), len(bands))
    band = np.tile(bands, len(t) // len(bands))
    true = flux_of(t, band)
    err = 0.03 * np.abs(true) + 2.0
    return Phot(t, band, true + rng.normal(0, err), err, t.max())


def test_a_lens_written_in_the_language_is_recovered():
    fs = {"ztfg": 40.0, "ztfr": 70.0}
    lens = lambda t, b: np.array([fs[x] for x in b]) * (_magnification(np.hypot(0.2, (t - 60020) / 30)) - 1)
    ph = sampled(lens, 59960, 60080, 2)
    f = dsl.fit_spec({"components": [{"type": "lens"}]}, ph, "hidden lens")
    assert abs(f.params["lens0.t0"] - 60020) < 2 and abs(f.params["lens0.u0"] - 0.2) < 0.1
    assert f.chi2 / f.ndof < 2 and f.seconds < 5


def test_components_add_up():
    ph = sampled(lambda t, b: 50 * np.exp(-0.5 * ((t - 60010) / 5) ** 2) + 20, 59990, 60030, 1)
    f = dsl.fit_spec({"components": [{"type": "flare"}, {"type": "constant"}]}, ph)
    mu, sd = f.predict([60010.0, 60028.0], ["ztfr", "ztfr"])
    assert mu[0] == pytest.approx(70, rel=0.1) and mu[1] == pytest.approx(20, rel=0.15) and np.all(sd > 0)


@pytest.mark.parametrize("spec", [{}, {"components": [{"type": "magic"}]},
                                  {"components": [{"type": "flare"}] * 4}])
def test_unknown_or_oversized_models_are_refused(spec):
    ph = sampled(lambda t, b: np.full(len(t), 10.0), 0, 20, 1)
    with pytest.raises(ValueError):
        dsl.fit_spec(spec, ph)


def test_the_language_respects_the_firewall():
    ph = sampled(lambda t, b: np.full(len(t), 10.0), 0, 20, 1)
    late = Phot(ph.t, ph.band, ph.flux, ph.err, as_of=5.0)
    with pytest.raises(FutureData):
        dsl.fit_spec({"components": [{"type": "constant"}]}, late)
