import numpy as np
from scipy import stats

WAIT_BITS = 0.2  # if the sky will settle this much within three days, waiting is the cheapest action
THINK_BITS = 1.0  # a posterior spread over more than about two hypotheses deserves more thought
HORIZON = 3.0


def entropy(weights) -> float:
    w = np.array([x for x in weights if x > 0], dtype=float)
    w = w / w.sum()
    return max(float(-(w * np.log2(w)).sum()), 0.0)


def eig(parts: list, err: float) -> float:
    # bits a measurement with this error would tell us about which hypothesis is right
    w, mu, sd = (np.array([p[i] for p in parts], dtype=float) for i in (1, 2, 3))
    w, s = w / w.sum(), np.hypot(sd, err)
    y = np.linspace((mu - 8 * s).min(), (mu + 8 * s).max(), 4001)
    dens = (w[:, None] * stats.norm.pdf(y[None, :], mu[:, None], s[:, None])).sum(axis=0)
    mixed = -np.trapezoid(dens * np.log2(np.clip(dens, 1e-300, None)), y)
    alone = float((w * 0.5 * np.log2(2 * np.pi * np.e * s ** 2)).sum())
    return max(float(mixed) - alone, 0.0)


def decide(forecasts: list[dict], weights: dict, now: float) -> dict:
    soon = [f["eig"] for f in forecasts if f["mjd"] <= now + HORIZON]
    wait, spread = max(soon, default=0.0), entropy(weights.values())
    if wait >= WAIT_BITS:
        action = "wait"
    elif spread >= THINK_BITS:
        action = "think"
    else:
        action = "confident"
    best = max(forecasts, key=lambda f: f["eig"]) if forecasts else None
    return {"action": action, "eig_wait": round(wait, 3), "entropy": round(spread, 3),
            "most_telling": {"mjd": best["mjd"], "band": best["band"], "eig": best["eig"]} if best else None}
