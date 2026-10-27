from openai import OpenAI

from .config import KEYS, SPARK_OPEN, URLS
from .costs import BudgetExceeded, CostMeter, Usage

SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"


def usage_of(response) -> Usage:
    u = response.usage
    if u is None:
        return Usage()
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
    output = u.completion_tokens or 0
    # some providers report reasoning outside completion_tokens
    if reasoning > output:
        output += reasoning
    return Usage(input_tokens=u.prompt_tokens or 0, cached_tokens=cached, output_tokens=output)


class LLM:
    def __init__(self, meter: CostMeter | None = None, clients: dict | None = None):
        self.meter = meter or CostMeter()
        self.clients = clients or {}

    def _client(self, provider: str):
        if provider not in self.clients:
            if not KEYS[provider]:
                raise RuntimeError(f"missing API key for {provider}")
            # Baseten answers 429 when too many requests run at once, so back off and retry
            self.clients[provider] = OpenAI(base_url=URLS[provider], api_key=KEYS[provider], max_retries=6)
        return self.clients[provider]

    def chat(self, provider: str, model: str, messages: list[dict], tag: str = "", **kwargs):
        self.meter.check(provider, model)
        response = self._client(provider).chat.completions.create(model=model, messages=messages, **kwargs)
        self.meter.record(provider, model, usage_of(response), tag)
        return response

    # System 1: Spark Open on Baseten, falls back to Spark minimal on Meta
    def fast(self, messages: list[dict], tag: str = "s1", **kwargs):
        try:
            return self.chat("baseten", SPARK_OPEN, messages, tag, **kwargs)
        except (BudgetExceeded, RuntimeError):
            return self.chat("meta", SPARK, messages, tag + ":fallback", reasoning_effort="minimal", **kwargs)
