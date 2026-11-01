import ast
import re
import time

import numpy as np
from scipy.optimize import least_squares

from .models import Fit, Phot, _cov, _guard

# what an equation may use: arithmetic, numbers, t, its own parameters and helpers, and these functions; nothing else runs
FUNCTIONS = {"sqrt": np.sqrt, "exp": np.exp, "log": np.log, "abs": np.abs, "tanh": np.tanh,
             "step": lambda x: np.where(x > 0, 1.0, 0.0), "max": np.maximum, "min": np.minimum}
PAIRS = ("max", "min")
CONSTANTS = {"pi": np.pi}
OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power}
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*$")
MAX_TEXT = 400
MAX_PARAMS = 14
MAX_HELPERS = 6

# the point-lens magnification (u²+2)/(u·√(u²+4)) in the ways it is written, once spaces, ^ and (t) are gone
LENS = [re.compile(r"\((\w+)\*\*2\+2\)/\(\1\*sqrt\(\1\*\*2\+4\)\)"),
        re.compile(r"\((\w+)\*\1\+2\)/\(\1\*sqrt\(\1\*\1\+4\)\)"),
        re.compile(r"\((\w+)\*\*2\+2\)/\(\1\*\(\1\*\*2\+4\)\*\*(0\.5|\(1/2\))\)"),
        re.compile(r"\((\w+)\+2\)/sqrt\(\1\*\(\1\+4\)\)"),
        # with the square as its own name, u2 = u²
        re.compile(r"\((\w+)\+2\)/\(sqrt\(\1\)\*sqrt\(\1\+4\)\)"),
        re.compile(r"\((\w+)\+2\)/sqrt\(\1\)/sqrt\(\1\+4\)")]


def _right(text) -> str:
    # "flux_b(t) = ..." and "u(t) = ..." are read from their right-hand side
    if not isinstance(text, str) or not text.strip():
        raise ValueError("an expression is missing")
    text = text.split("=", 1)[1] if "=" in text else text
    if len(text) > MAX_TEXT:
        raise ValueError(f"an expression is longer than {MAX_TEXT} characters")
    return text.strip().replace("^", "**")


def _compile(node, known: set[str], helpers: set[str]):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = float(node.value)
        return lambda env: value
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            value = CONSTANTS[node.id]
            return lambda env: value
        if node.id not in known:
            raise ValueError(f"unknown name {node.id}")
        name = node.id
        return lambda env: env[name]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner, sign = _compile(node.operand, known, helpers), -1.0 if isinstance(node.op, ast.USub) else 1.0
        return lambda env: sign * inner(env)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        a, b, op = _compile(node.left, known, helpers), _compile(node.right, known, helpers), OPS[type(node.op)]
        return lambda env: op(a(env), b(env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id
        # a helper written as u(t) is the helper itself
        if name in helpers and len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "t":
            return lambda env: env[name]
        if name in FUNCTIONS and len(node.args) == (2 if name in PAIRS else 1):
            fn, args = FUNCTIONS[name], [_compile(a, known, helpers) for a in node.args]
            return lambda env: fn(*[a(env) for a in args])
    raise ValueError(f"{ast.dump(node)[:60]} is not allowed in an equation")


def expression(text, known: set[str], helpers: set[str] = frozenset()):
    try:
        tree = ast.parse(_right(text), mode="eval").body
    except SyntaxError as e:
        raise ValueError(f"not an expression: {e.msg}") from None
    return _compile(tree, known, helpers)


def _range(name: str, spec) -> tuple[float, float, float]:
    # a guess and a range from the proposal; a parameter without both cannot be fitted honestly
    spec = spec if isinstance(spec, dict) else {}
    try:
        guess, low, high = (float(spec[k]) for k in ("guess", "low", "high"))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"parameter {name} needs a guess, a low and a high") from None
    if not all(np.isfinite([guess, low, high])) or low >= high:
        raise ValueError(f"parameter {name} has no usable range")
    return float(np.clip(guess, low, high)), low, high


def read(eq: dict, bands: list[str]):
    # the proposal's flux, helpers and parameters; a name ending in _b takes one value per band
    params = eq.get("parameters") if isinstance(eq.get("parameters"), dict) else {}
    helpers = eq.get("helpers") if isinstance(eq.get("helpers"), dict) else {}
    if not params or len(params) > MAX_PARAMS or len(helpers) > MAX_HELPERS:
        raise ValueError(f"an equation needs 1 to {MAX_PARAMS} parameters and at most {MAX_HELPERS} helpers")
    names, guess, lo, hi, slots = [], [], [], [], {}
    for p, spec in params.items():
        if not NAME.match(p) or p in FUNCTIONS or p in CONSTANTS or p == "t":
            raise ValueError(f"bad parameter name {p}")
        g, low, high = _range(p, spec)
        for b in (bands if p.endswith("_b") else [None]):
            slots.setdefault(p, {})[b] = len(names)
            names.append(f"{p[:-2]}_{b}" if b else p)
            guess.append(g), lo.append(low), hi.append(high)
    known, steps = {"t"} | set(params), []
    for h, text in helpers.items():
        h = h.replace("(t)", "")
        if not NAME.match(h) or h in known or h in FUNCTIONS or h in CONSTANTS:
            raise ValueError(f"bad helper name {h}")
        steps.append((h, expression(text, known, {s for s, _ in steps})))
        known = known | {h}
    flux = expression(eq.get("flux"), known, {s for s, _ in steps})

    def evaluate(p, t, band):
        out = np.full(len(t), np.nan)
        for b in bands:
            rows = band == b
            if not rows.any():
                continue
            env = {"t": t[rows]}
            for name, where in slots.items():
                env[name] = p[where[b] if b in where else where[None]]
            for h, step in steps:
                env[h] = step(env)
            out[rows] = np.broadcast_to(flux(env), rows.sum())
        return out

    return names, np.array(guess), np.array(lo), np.array(hi), evaluate


def _draw(rng, guess, lo, hi) -> np.ndarray:
    # half the starts near the proposal's own guess, half anywhere in its range, by decades where the range spans them
    near = rng.uniform() < 0.5
    out = []
    for g, low, high in zip(guess, lo, hi):
        if near:
            x = g * np.exp(rng.normal(0, 0.3)) if g > 0 else g + rng.normal(0, 0.1 * (high - low))
        elif low > 0 and high / low > 100:
            x = np.exp(rng.uniform(np.log(low), np.log(high)))
        else:
            x = rng.uniform(low, high)
        out.append(np.clip(x, low, high))
    return np.array(out)


def fit(eq: dict, ph: Phot, now: float, name: str = "equation", starts: int = 16, seed: int = 0) -> Fit | None:
    # times in the equation are days from now, as the case showed them; fluxes are in microjansky
    _guard(ph)
    start, short = time.time(), lambda band: np.array([str(b).replace("ztf", "") for b in band])
    bands = sorted(set(short(ph.band)))
    names, guess, lo, hi, evaluate = read(eq, bands)
    if len(ph) < len(names) + 2:
        return None

    def flux(p, t, band):
        with np.errstate(all="ignore"):
            return evaluate(p, np.asarray(t, dtype=float) - now, short(band))

    resid = lambda p: np.nan_to_num((flux(p, ph.t, ph.band) - ph.flux) / ph.sigma, nan=1e3, posinf=1e3, neginf=-1e3)
    rng, best = np.random.default_rng(seed), None
    for k in range(starts):
        p0 = guess if k == 0 else _draw(rng, guess, lo, hi)
        try:
            r = least_squares(resid, np.clip(p0, lo, hi), bounds=(lo, hi))
        except (ValueError, FloatingPointError, OverflowError, ZeroDivisionError):
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None or not np.isfinite(best.cost) or not np.all(np.isfinite(flux(best.x, ph.t, ph.band))):
        return None
    chi2, ndof = float(2 * best.cost), max(len(ph) - len(names), 1)
    return Fit(name, names, best.x, _cov(best.jac, lo, hi, max(1.0, chi2 / ndof)), flux, chi2, ndof,
               time.time() - start, {"equation": eq})


def lens_law(eq: dict) -> bool:
    # whether the flux or its helpers contain the point-lens magnification, in any of the forms above
    texts = [eq.get("flux")] + list((eq.get("helpers") or {}).values() if isinstance(eq.get("helpers"), dict) else [])
    for text in texts:
        norm = re.sub(r"\s+", "", str(text or "")).replace("^", "**").replace("(t)", "")
        if any(p.search(norm) for p in LENS):
            return True
    return False
