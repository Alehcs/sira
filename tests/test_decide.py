import pytest

from sira.decide import decide, eig, entropy


def test_entropy_in_bits():
    assert entropy([0.5, 0.5]) == pytest.approx(1.0) and entropy([1.0]) == 0.0


def test_eig_is_zero_when_hypotheses_agree_and_one_bit_when_they_split():
    assert eig([["a", 0.5, 100, 5], ["b", 0.5, 100, 5]], 3) == pytest.approx(0, abs=1e-6)
    assert eig([["a", 0.5, 100, 5], ["b", 0.5, 200, 5]], 3) == pytest.approx(1, abs=1e-3)
    assert 0 < eig([["a", 0.5, 100, 5], ["b", 0.5, 110, 5]], 3) < 1


def grid(bits, now=100.0):
    return [{"mjd": now + d, "band": "ztfr", "eig": b} for d, b in zip((1, 2, 3, 4, 5), bits)]


def test_wait_when_the_sky_will_settle_it_soon():
    d = decide(grid([0.0, 0.5, 0.1, 0.0, 0.0]), {"ia": 0.5, "ii": 0.5}, 100.0)
    assert d["action"] == "wait" and d["most_telling"]["mjd"] == 102.0


def test_think_when_unsure_and_the_sky_is_slow():
    assert decide(grid([0.01] * 3 + [0.9, 0.9]), {"ia": 0.3, "ii": 0.3, "tde": 0.3, "null": 0.1}, 100.0)["action"] == "think"


def test_confident_otherwise():
    assert decide(grid([0.01] * 5), {"ia": 0.9, "null": 0.1}, 100.0)["action"] == "confident"
