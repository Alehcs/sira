import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import CAPS, COST_LOG, MODEL_CAPS, Caps

# USD per million tokens: (input, cached input, output)
PRICES = {
    ("meta", "muse-spark-1.3"): (1.25, 0.15, 4.25),
    ("meta", "muse-spark-1.2"): (1.25, 0.15, 4.25),
    ("meta", "muse-spark-1.3-contributor"): (0.10, 0.002, 0.20),
    ("meta", "muse-spark-1.2-contributor"): (0.10, 0.002, 0.20),
    ("meta", "muse-wonder-1.0"): (4.00, 0.20, 20.00),
    # Baseten price not published for the hackathon model; conservative until measured
    ("baseten", "meta-models/muse-spark-open-1026"): (1.25, 0.15, 4.25),
}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0


def price(provider: str, model: str, usage: Usage) -> float:
    if (provider, model) not in PRICES:
        raise KeyError(f"no price for {provider}/{model}")
    p_in, p_cached, p_out = PRICES[(provider, model)]
    fresh = max(usage.input_tokens - usage.cached_tokens, 0)
    return (fresh * p_in + usage.cached_tokens * p_cached + usage.output_tokens * p_out) / 1e6


class CostMeter:
    def __init__(self, path: Path = COST_LOG, caps: dict[str, Caps] = CAPS, model_caps: dict[str, float] = MODEL_CAPS):
        self.path = Path(path)
        self.caps = caps
        self.model_caps = model_caps

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def spent(self, provider: str, day: str | None = None, model: str | None = None) -> float:
        rows = [r for r in self._rows() if r["provider"] == provider and (model is None or r["model"] == model)]
        if day:
            rows = [r for r in rows if r["time"].startswith(day)]
        return sum(r["usd"] for r in rows)

    def check(self, provider: str, model: str | None = None) -> None:
        caps = self.caps[provider]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.spent(provider) >= caps.total:
            raise BudgetExceeded(f"{provider}: total cap ${caps.total} reached")
        if caps.daily is not None and self.spent(provider, today) >= caps.daily:
            raise BudgetExceeded(f"{provider}: daily cap ${caps.daily} reached")
        if model in self.model_caps and self.spent(provider, today, model) >= self.model_caps[model]:
            raise BudgetExceeded(f"{model}: daily cap ${self.model_caps[model]} reached")

    def record(self, provider: str, model: str, usage: Usage, tag: str = "") -> float:
        usd = price(provider, model, usage)
        row = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": provider,
            "model": model,
            **asdict(usage),
            "usd": round(usd, 6),
            "tag": tag,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return usd

    def left(self, provider: str) -> float:
        caps, today = self.caps[provider], datetime.now(timezone.utc).strftime("%Y-%m-%d")
        left = caps.total - self.spent(provider)
        return left if caps.daily is None else min(left, caps.daily - self.spent(provider, today))

    def summary(self) -> dict[str, dict[str, float]]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {
            p: {"total": round(self.spent(p), 4), "today": round(self.spent(p, today), 4),
                "cap_total": c.total, "cap_daily": c.daily}
            for p, c in self.caps.items()
        }
