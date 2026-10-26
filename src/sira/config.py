import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

META_URL = "https://api.meta.ai/v1"
BASETEN_URL = "https://inference.baseten.co/v1"
SPARK_OPEN = "meta-models/muse-spark-open-1026"


def _money(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Caps:
    total: float
    daily: float


CAPS = {
    "meta": Caps(_money("SIRA_CAP_META_TOTAL", 140), _money("SIRA_CAP_META_DAILY", 15)),
    "baseten": Caps(_money("SIRA_CAP_BASETEN_TOTAL", 90), _money("SIRA_CAP_BASETEN_DAILY", 15)),
}

# daily caps for expensive models, on top of the provider caps
MODEL_CAPS = {"muse-wonder-1.0": _money("SIRA_CAP_WONDER_DAILY", 3)}

KEYS = {
    "meta": os.getenv("MODEL_API_KEY", ""),
    "baseten": os.getenv("BASETEN_API_KEY", ""),
}

URLS = {"meta": META_URL, "baseten": BASETEN_URL}

COST_LOG = Path(os.getenv("SIRA_COST_LOG", "var/costs.jsonl"))
