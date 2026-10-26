from types import SimpleNamespace

import pytest

from sira.config import Caps
from sira.costs import BudgetExceeded, CostMeter
from sira.llm import LLM, usage_of


def fake_response(prompt=100, completion=20, cached=0, reasoning=0):
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )
    msg = SimpleNamespace(content="ready")
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg)])


class FakeClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response, self.error = response or fake_response(), error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def make_llm(tmp_path, clients, total=10.0):
    caps = {"meta": Caps(total, total), "baseten": Caps(total, total)}
    return LLM(CostMeter(tmp_path / "c.jsonl", caps), clients)


def test_usage_counts_reasoning_reported_outside_completion():
    u = usage_of(fake_response(completion=10, reasoning=50))
    assert u.output_tokens == 60


def test_usage_keeps_completion_when_reasoning_included():
    u = usage_of(fake_response(completion=80, reasoning=50, cached=40))
    assert (u.output_tokens, u.cached_tokens) == (80, 40)


def test_chat_records_cost(tmp_path):
    meta = FakeClient()
    llm = make_llm(tmp_path, {"meta": meta})
    llm.chat("meta", "muse-spark-1.3", [{"role": "user", "content": "hi"}], "t")
    assert meta.calls[0]["model"] == "muse-spark-1.3"
    assert llm.meter.spent("meta") > 0


def test_chat_refuses_when_over_cap(tmp_path):
    meta = FakeClient(fake_response(prompt=1_000_000))
    llm = make_llm(tmp_path, {"meta": meta}, total=1.0)
    llm.chat("meta", "muse-spark-1.3", [])
    with pytest.raises(BudgetExceeded):
        llm.chat("meta", "muse-spark-1.3", [])
    assert len(meta.calls) == 1


def test_fast_falls_back_to_meta(tmp_path):
    meta = FakeClient()
    llm = make_llm(tmp_path, {"meta": meta, "baseten": FakeClient(error=RuntimeError("down"))})
    llm.fast([{"role": "user", "content": "hi"}])
    assert meta.calls[0]["reasoning_effort"] == "minimal"
