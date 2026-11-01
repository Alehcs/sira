import numpy as np
import pytest

from sira import equation, leverrier
from sira.models import Phot, _magnification
from test_leverrier import lens_snapshot  # noqa: F401
from test_team import reply

LENS = {"flux": "flux_b(t) = Fb_b + Fs_b*(u(t)^2+2)/(u(t)*sqrt(u(t)^2+4))",
        "helpers": {"u(t)": "sqrt(u0^2 + ((t-t0)/tE)^2)"},
        "parameters": {"Fb_b": {"guess": 5, "low": -100, "high": 500}, "Fs_b": {"guess": 50, "low": 0, "high": 1000},
                       "u0": {"guess": 0.5, "low": 0.001, "high": 2}, "t0": {"guess": 0, "low": -150, "high": 150},
                       "tE": {"guess": 30, "low": 1, "high": 300}}}


@pytest.mark.parametrize("text", ["__import__('os').system('ls')", "t.__class__", "(lambda: 1)()", "[1 for x in t]",
                                  "open('x')", "eval('1')", "t[0]", "nope * t", "sqrt(t, t)", "1 if t else 2", "x" * 401])
def test_an_equation_may_only_do_arithmetic_on_its_own_names(text):
    with pytest.raises(ValueError):
        equation.expression(text, {"t"})


def test_an_equation_reads_helpers_per_band_values_and_carets():
    names, guess, lo, hi, evaluate = equation.read(LENS, ["g", "r"])
    assert names == ["Fb_g", "Fb_r", "Fs_g", "Fs_r", "u0", "t0", "tE"] and list(guess) == [5, 5, 50, 50, 0.5, 0, 30]
    t, band = np.array([0.0, 0.0, 40.0]), np.array(["g", "r", "r"])
    p = np.array([1.0, 2.0, 10.0, 20.0, 0.3, 0.0, 40.0])
    a = _magnification(np.array([0.3, 0.3, np.hypot(0.3, 1.0)]))
    assert np.allclose(evaluate(p, t, band), [1 + 10 * a[0], 2 + 20 * a[1], 2 + 20 * a[2]])


def test_a_parameter_without_a_guess_and_a_range_is_refused():
    with pytest.raises(ValueError):
        equation.read({"flux": "A*t", "parameters": {"A": {"meaning": "scale"}}}, ["r"])
    with pytest.raises(ValueError):
        equation.read({"flux": "A*t", "parameters": {"A": {"guess": 1, "low": 2, "high": 1}}}, ["r"])


def test_the_lens_law_is_recognised_however_it_is_written():
    assert equation.lens_law(LENS)
    assert equation.lens_law({"flux": "B_b + S_b*A", "helpers": {"A": "(x*x + 2)/(x*sqrt(x*x + 4))"}})
    assert equation.lens_law({"flux": "F*(U+2)/sqrt(U*(U+4))"})
    assert equation.lens_law({"flux": "blend_b + src_b * magn", "helpers": {"u2": "u0^2 + ((t - tpeak) / te)^2", "magn": "(u2 + 2) / (sqrt(u2) * sqrt(u2 + 4))"}})
    assert not equation.lens_law({"flux": "A*exp(-t/tau)*(1+t/tR)^2"})


def test_a_written_lens_is_fitted_back_from_its_light_curve():
    rng, now, rows = np.random.default_rng(0), 60100.0, []
    for t in np.arange(60000.0, 60100.0, 1.5):
        for b, fs in (("ztfg", 40.0), ("ztfr", 90.0)):
            f = 3.0 + fs * _magnification(np.hypot(0.3, (t - 60080.0) / 35.0))
            rows.append((t, b, f + rng.normal(0, 0.02 * f), 0.02 * f))
    t, band, flux, err = (np.array(c) for c in zip(*rows))
    fit = equation.fit(LENS, Phot(t.astype(float), band.astype(str), flux.astype(float), err.astype(float), now), now)
    got = fit.params
    assert got["u0"] == pytest.approx(0.3, rel=0.15) and got["tE"] == pytest.approx(35.0, rel=0.15)
    assert got["t0"] == pytest.approx(-20.0, abs=1.5) and fit.chi2 / fit.ndof < 3


def test_le_verrier_can_write_its_own_law_and_have_the_future_judge_it(lens_snapshot):  # noqa: F811
    law = {"name": "written lens", "idea": "an unseen lens", "predicts": "a symmetric fall",
           "flux": "Fs_b*((u^2+2)/(u*sqrt(u^2+4)) - 1)", "helpers": {"u": "sqrt(u0^2 + ((t-t0)/tE)^2)"},
           "parameters": {"Fs_b": {"guess": 50, "low": 0, "high": 1000}, "u0": {"guess": 0.5, "low": 0.001, "high": 2},
                          "t0": {"guess": 0, "low": -150, "high": 150}, "tE": {"guess": 30, "low": 1, "high": 300}}}
    report = leverrier.case(lens_snapshot, "ZTFlens", reply({"closed-form equation": law}), leaps=["equation"])
    proposal = report["proposals"][0]
    assert proposal["lens_law"] and proposal["equation"]["helpers"] == law["helpers"]
    assert report["best"]["verdict"] == "neptune" and report["events"][0]["decision"] == "writes written lens"
