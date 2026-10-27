import numpy as np
import pytest
from scipy import integrate, stats

from sira.scoring import coverage, crps, log_score, log_score_limit, pit, score, spread, uniformity


def test_standard_normal_values():
    assert log_score(0.0, 0.0, 1.0) == pytest.approx(-0.918939, abs=1e-6)
    # 2 phi(0) - 1/sqrt(pi)
    assert crps(0.0, 0.0, 1.0) == pytest.approx(0.233695, abs=1e-6)
    assert pit(0.0, 0.0, 1.0) == 0.5
    assert spread(3.0, 4.0) == 5.0


def test_crps_matches_its_integral_definition():
    y, mu, sigma = 13.0, 10.0, 2.0
    cdf = lambda x: stats.norm.cdf(x, mu, sigma)
    below = integrate.quad(lambda x: cdf(x) ** 2, -np.inf, y)[0]
    above = integrate.quad(lambda x: (1 - cdf(x)) ** 2, y, np.inf)[0]
    assert crps(y, mu, sigma) == pytest.approx(below + above)


def test_sharp_forecast_crps_is_the_absolute_error():
    assert crps(13.0, 10.0, 1e-9) == pytest.approx(3.0)


def test_scores_are_symmetric_about_the_mean():
    mu, sigma, d = 40.0, 7.0, np.array([0.5, 3.0, 12.0])
    assert log_score(mu + d, mu, sigma) == pytest.approx(log_score(mu - d, mu, sigma))
    assert crps(mu + d, mu, sigma) == pytest.approx(crps(mu - d, mu, sigma))
    assert pit(mu + d, mu, sigma) + pit(mu - d, mu, sigma) == pytest.approx(1.0)


def test_limit_far_above_the_forecast_costs_nothing():
    assert log_score_limit(100.0, 10.0, 5.0) == pytest.approx(0.0, abs=1e-12)
    assert log_score_limit(50.0, 50.0, 5.0) == pytest.approx(np.log(0.5))


def test_forecast_far_above_the_limit_scores_very_low_but_finite():
    s = log_score_limit(100.0, 1000.0, 10.0)
    assert -5000 < s < -4000
    # far in the tail log cdf(z) ~ log pdf(z) - log|z|, where log(cdf(z)) would be -inf
    assert s == pytest.approx(stats.norm.logpdf(-90.0) - np.log(90.0), rel=1e-6)


def test_coverage_uses_the_central_interval():
    # the 90% interval reaches 1.645 sigma either side
    assert coverage(np.array([-1.6, 0.0, 1.6]), 0.0, 1.0).all()
    assert not coverage(np.array([-1.7, 1.7]), 0.0, 1.0).any()
    assert coverage(25.0, 20.0, 2.0, level=0.99) and not coverage(25.0, 20.0, 2.0)


def test_pits_of_a_correct_forecast_are_uniform():
    rng = np.random.default_rng(0)
    mu, sigma = rng.normal(100, 30, 2000), rng.uniform(1, 20, 2000)
    y = rng.normal(mu, sigma)
    u = uniformity(pit(y, mu, sigma))
    assert sum(u["counts"]) == 2000 and u["p_value"] > 0.05
    assert coverage(y, mu, sigma).mean() == pytest.approx(0.9, abs=0.02)
    # twice too confident, the PITs pile up at both ends
    assert uniformity(pit(y, mu, sigma / 2))["p_value"] < 1e-6


def test_score_mixes_detections_and_limits():
    rows = [{"mu": 0.0, "sigma": 3.0, "y": 0.0, "err": 4.0},
            {"mu": 10.0, "sigma": 1.0, "y": 13.0, "err": 0.0},
            {"mu": 0.0, "sigma": 2.0, "limit": 2.0, "err": 100.0}]
    s = score(rows)
    assert s["n"] == 3 and s["n_limits"] == 1
    # predictive sd is 5 and 1 for the detections; the limit adds a fifth of itself as noise and ignores err
    logs = [-0.918939 - np.log(5), -0.918939 - 4.5, stats.norm.logcdf(2.0 / np.hypot(2.0, 0.4))]
    assert s["log_score"] == pytest.approx(np.mean(logs), abs=1e-6)
    assert s["crps"] == pytest.approx((5 * 0.233695 + crps(3.0, 0.0, 1.0)) / 2, abs=1e-6)
    assert s["pit_mean"] == pytest.approx((0.5 + stats.norm.cdf(3.0)) / 2)
    assert s["coverage_90"] == 0.5
    assert s["uniformity"]["counts"] == [0, 0, 0, 0, 0, 1, 0, 0, 0, 1]


def test_score_with_only_limits_leaves_detection_metrics_empty():
    s = score([{"mu": 5.0, "sigma": 1.0, "limit": 5.0}])
    assert s["n"] == 1 and s["log_score"] == pytest.approx(np.log(0.5))
    assert s["crps"] is None and s["pit_mean"] is None and s["coverage_90"] is None
    assert s["uniformity"] == {"counts": [0] * 10, "p_value": None}
