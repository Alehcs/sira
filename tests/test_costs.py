import pytest

from sira.config import Caps
from sira.costs import BudgetExceeded, CostMeter, Usage, price


def meter(tmp_path, total=1.0, daily=0.5):
    caps = {"meta": Caps(total, daily), "baseten": Caps(total, daily)}
    return CostMeter(tmp_path / "costs.jsonl", caps)


def test_price_uses_cached_rate():
    u = Usage(input_tokens=1_000_000, cached_tokens=400_000, output_tokens=100_000)
    # 600k fresh * 1.25 + 400k cached * 0.15 + 100k out * 4.25
    assert price("meta", "muse-spark-1.3", u) == pytest.approx(0.75 + 0.06 + 0.425)


def test_unknown_model_has_no_price():
    with pytest.raises(KeyError):
        price("meta", "not-a-model", Usage())


def test_record_and_spent(tmp_path):
    m = meter(tmp_path)
    m.record("meta", "muse-wonder-1.0", Usage(input_tokens=10_000, output_tokens=1_000))
    assert m.spent("meta") == pytest.approx(0.06)
    assert m.spent("baseten") == 0


def test_daily_cap_blocks(tmp_path):
    m = meter(tmp_path, total=10, daily=0.05)
    m.record("meta", "muse-wonder-1.0", Usage(input_tokens=10_000, output_tokens=1_000))
    with pytest.raises(BudgetExceeded, match="daily"):
        m.check("meta")
    m.check("baseten")


def test_total_cap_blocks(tmp_path):
    m = meter(tmp_path, total=0.05, daily=10)
    m.record("meta", "muse-wonder-1.0", Usage(input_tokens=10_000, output_tokens=1_000))
    with pytest.raises(BudgetExceeded, match="total"):
        m.check("meta")


def test_wonder_daily_cap_blocks_only_wonder(tmp_path):
    m = CostMeter(tmp_path / "c.jsonl", {"meta": Caps(100, 100)}, {"muse-wonder-1.0": 0.05})
    m.record("meta", "muse-wonder-1.0", Usage(input_tokens=10_000, output_tokens=1_000))
    with pytest.raises(BudgetExceeded, match="muse-wonder"):
        m.check("meta", "muse-wonder-1.0")
    m.check("meta", "muse-spark-1.3")


def test_no_daily_cap_means_only_the_total_counts(tmp_path):
    caps = {"meta": Caps(1.0), "baseten": Caps(1.0)}
    m = CostMeter(tmp_path / "c.jsonl", caps, {})
    m.record("meta", "muse-spark-1.3", Usage(input_tokens=400_000))
    m.check("meta")
    assert m.left("meta") == pytest.approx(0.5)
