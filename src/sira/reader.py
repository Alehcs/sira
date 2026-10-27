import base64
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .config import SPARK_OPEN
from .costs import price
from .llm import LLM, SPARK, usage_of
from .snapshot import code_version
from .stamps import side_by_side, zoom

# provider, model and default arguments for each reader under test
MODELS = {"spark-open": ("baseten", SPARK_OPEN, {}), "spark": ("meta", SPARK, {"reasoning_effort": "low"})}
GATE = 0.85
# first answers inside this band get two more opinions
UNSURE = (0.2, 0.8)

PROMPT = """You are an expert astronomer vetting candidate detections from the Zwicky Transient Facility (ZTF).

Each candidate is one image with four panels separated by white bars, left to right:
1. science: the new exposure,
2. template: a deep reference image of the same sky,
3. difference: science minus template,
4. zoom: the central 21 x 21 pixels of the difference, magnified three times.
The first three panels are 63 x 63 pixel cutouts (about 1 arcsec per pixel) centred on the candidate. Panels are contrast-stretched one by one, so compare shapes, not brightness, across panels.

Decide whether the candidate at the centre is real or bogus.
- Real: a genuine astrophysical change. The difference panel shows a positive, round source at the centre with the size and shape of a star, usually also visible in the science panel. It may sit on or near a galaxy in the template.
- Bogus: an artifact. Typical cases: positive and negative residuals of misaligned or saturated stars (dipoles, rings), cosmic rays or hot pixels sharper than a star, bad columns or rows, masked areas and detector edges (flat or blocky regions), satellite streaks, and noise with no clear source at the centre.

Answer with JSON only: {"label": "real" or "bogus", "p_real": probability from 0 to 1 that it is real, "why": one short sentence}."""

# few-shot examples from the snapshot's examples set: oid -> (p_real shown, what it shows)
EXAMPLES = {
    "ZTF25acfgotd": (0.9, "Clean positive point source at the centre of the difference, offset from a galaxy seen in the template."),
    "ZTF22ablmbim": (0.1, "A one or two pixel spike, much sharper than a star, with nothing in the template: a cosmic ray or hot pixel."),
    "ZTF24abyaspl": (0.85, "Clean positive point source at the centre; the small dipole at the galaxy core beside it is a residual, not the candidate."),
    "ZTF23aaatwyr": (0.02, "Saturated stars leave negative holes and bright halos in the difference: a subtraction residual."),
    "ZTF25aadhuhm": (0.9, "Clean positive point source at the centre; the masked square in the corner does not matter."),
    "ZTF20acmsqjq": (0.08, "Positive and negative pair at the core of a bright galaxy: a misaligned subtraction, not a new source."),
}


def image(png: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def messages(query: bytes, shots: list[tuple[bytes, str, float, str]]) -> list[dict]:
    msgs = [{"role": "system", "content": PROMPT}]
    for png, label, p_real, why in shots:
        msgs += [{"role": "user", "content": [image(png)]},
                 {"role": "assistant", "content": json.dumps({"label": label, "p_real": p_real, "why": why})}]
    return msgs + [{"role": "user", "content": [image(query)]}]


def parse(text: str | None) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    label = data.get("label") if data.get("label") in ("real", "bogus") else None
    try:
        p_real = min(max(float(data["p_real"]), 0.0), 1.0)
    except (KeyError, TypeError, ValueError):
        p_real = None
    if label is None and p_real is not None:
        label = "real" if p_real >= 0.5 else "bogus"
    return {"label": label, "p_real": p_real, "why": str(data.get("why", ""))[:300]}


def triplet(root: Path, files: list[str]) -> bytes:
    pngs = [(root / f).read_bytes() for f in files]
    return side_by_side(pngs + [zoom(pngs[-1])])


def shots(root: Path) -> list[tuple[bytes, str, float, str]]:
    found = {e["oid"]: e for e in json.loads((root / "examples.json").read_text())}
    return [(triplet(root, found[oid]["files"]), found[oid]["label"], p, why) for oid, (p, why) in EXAMPLES.items()]


def read(llm: LLM, model: str, query: bytes, examples: list, tag: str = "reader", votes: int = 3, **kwargs) -> dict:
    provider, name, defaults = MODELS[model]
    start, usd = time.time(), 0.0

    def ask():
        nonlocal usd
        r = llm.chat(provider, name, messages(query, examples), tag, **(defaults | kwargs))
        usd += price(provider, name, usage_of(r))
        return parse(r.choices[0].message.content)

    answers = [ask()]
    first = answers[0]
    if votes > 1 and (first["p_real"] is None or UNSURE[0] < first["p_real"] < UNSURE[1]):
        answers += [ask() for _ in range(votes - 1)]
    ps = [a["p_real"] for a in answers if a["p_real"] is not None]
    p_real = round(float(np.mean(ps)), 3) if ps else None
    label = first["label"] if p_real is None else ("real" if p_real >= 0.5 else "bogus")
    return {"label": label, "p_real": p_real, "why": first["why"], "p_first": first["p_real"],
            "votes": len(answers), "seconds": round(time.time() - start, 1), "usd": round(usd, 6)}


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    p, n = np.array(pos)[:, None], np.array(neg)[None, :]
    return float(((p > n) + 0.5 * (p == n)).mean())


def metrics(rows: list[dict], seed: int = 0) -> dict:
    real = np.array([r["truth"] == "real" for r in rows])
    # unanswered reads count as mistakes in both classes
    hit = np.array([r["label"] == r["truth"] for r in rows])
    rng = np.random.default_rng(seed)
    pos, neg = np.flatnonzero(real), np.flatnonzero(~real)
    boots = [(hit[rng.choice(pos, len(pos))].mean() + hit[rng.choice(neg, len(neg))].mean()) / 2 for _ in range(2000)]
    scored = [r for r in rows if r["p_real"] is not None]
    bacc = (hit[real].mean() + hit[~real].mean()) / 2
    return {
        "n": len(rows), "real": int(real.sum()), "bogus": int((~real).sum()),
        "balanced_accuracy": round(float(bacc), 3),
        "ci95": [round(float(x), 3) for x in np.percentile(boots, [2.5, 97.5])],
        "real_recall": round(float(hit[real].mean()), 3), "bogus_recall": round(float(hit[~real].mean()), 3),
        "auc": auc([r["p_real"] for r in scored if r["truth"] == "real"],
                   [r["p_real"] for r in scored if r["truth"] == "bogus"]),
        "unanswered": sum(r["label"] is None for r in rows),
        "passes_gate": bool(bacc >= GATE),
    }


def check(root: Path, model: str, few_shot: bool = True, workers: int = 8, llm: LLM | None = None,
          votes: int = 3, **kwargs) -> dict:
    root, llm = Path(root), llm or LLM()
    cases = json.loads((root / "valset.json").read_text())
    if set(EXAMPLES) & {c["oid"] for c in cases}:
        raise ValueError("an example is also in the valset")
    examples = shots(root) if few_shot else []

    def one(case):
        try:
            return read(llm, model, triplet(root, case["files"]), examples, f"g1:{model}", votes, **kwargs)
        except Exception as e:
            return {"label": None, "p_real": None, "why": f"{type(e).__name__}: {e}"[:300], "p_first": None,
                    "votes": 0, "seconds": None, "usd": 0.0}

    with ThreadPoolExecutor(workers) as pool:
        rows = [{"oid": c["oid"], "truth": c["label"]} | r for c, r in zip(cases, pool.map(one, cases))]
    usd = sum(r["usd"] for r in rows)
    single = metrics([r | {"label": None if r["p_first"] is None else ("real" if r["p_first"] >= 0.5 else "bogus")}
                      for r in rows])
    return {"model": model, "shots": len(examples), "code": code_version(),
            "valset_sha256": hashlib.sha256((root / "valset.json").read_bytes()).hexdigest(), **metrics(rows),
            "single_read": {k: single[k] for k in ("balanced_accuracy", "real_recall", "bogus_recall")},
            "revoted": sum(r["votes"] > 1 for r in rows),
            "usd": round(usd, 4), "usd_per_read": round(usd / len(rows), 5), "rows": rows}
