import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

META_URL = "https://api.meta.ai/v1"
BASETEN_URL = "https://inference.baseten.co/v1"
SPARK_OPEN = "meta-models/muse-spark-open-1026"


def _money(name: str, default: float | None = None) -> float | None:
    value = os.getenv(name, "")
    return float(value) if value.strip() else default


@dataclass(frozen=True)
class Caps:
    total: float
    daily: float | None = None


CAPS = {
    "meta": Caps(_money("SIRA_CAP_META_TOTAL", 150), _money("SIRA_CAP_META_DAILY")),
    "baseten": Caps(_money("SIRA_CAP_BASETEN_TOTAL", 100), _money("SIRA_CAP_BASETEN_DAILY")),
}

# optional daily caps for expensive models, on top of the provider caps
MODEL_CAPS = {m: cap for m, cap in {"muse-wonder-1.0": _money("SIRA_CAP_WONDER_DAILY")}.items() if cap is not None}

KEYS = {
    "meta": os.getenv("MODEL_API_KEY", ""),
    "baseten": os.getenv("BASETEN_API_KEY", ""),
}

URLS = {"meta": META_URL, "baseten": BASETEN_URL}

COST_LOG = Path(os.getenv("SIRA_COST_LOG", "var/costs.jsonl"))
