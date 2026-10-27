import json
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .costs import price
from .llm import LLM, SPARK, WONDER, usage_of
from .snapshot import _shuffled, code_version, mjd_to_date

MODELS = {"spark": ("meta", SPARK, {"reasoning_effort": "minimal"}),
          "wonder": ("meta", WONDER, {"reasoning_effort": "minimal"})}
YEARS = range(2019, 2027)
# the cases the demo leans on must show they are not remembered
STARS = ("ZTF25aapwxhm", "ZTF25abxedzr", "ZTF25aasnrmc", "ZTF25aarhgtc", "ZTF25abwvuln", "ZTF25aaymnha",
         "ZTF25aajfjhm", "ZTF19aavnrqt")

SYSTEM = ("You are an astronomer. Answer only from what you remember about specific objects. "
          "If you do not remember an object, set known to false. Never guess.")
BY_NAME = ("What do you remember about the transient {label}?\n"
           'Reply with JSON only: {{"known": true or false, "type": "classification or null", '
           '"redshift": number or null, "host": "host galaxy or null"}}')
BY_SKY = ("A transient at RA {ra:.4f} deg, Dec {dec:+.4f} deg (J2000) peaked around {date}.\n"
          'Do you recognise this object? Reply with JSON only: {{"known": true or false, '
          '"name": "designation or null", "type": "classification or null", "redshift": number or null}}')


def events(bts_rows: list[dict], mulens_rows: list[dict], per_year: int = 2) -> list[dict]:
    keep = lambda r: {k: r.get(k) for k in ("oid", "name", "type", "redshift", "peak_mjd", "peak_mag", "ra", "dec")}
    found = [keep(r) | {"group": "star"} for r in bts_rows if r["oid"] in STARS]
    found += [{"oid": r["oid"], "name": r["oid"], "type": "microlensing", "redshift": None, "peak_mjd": r["t0_mjd"],
               "peak_mag": None, "ra": r["ra"], "dec": r["dec"], "group": "star"} for r in mulens_rows if r["oid"] in STARS]
    year = lambda r: mjd_to_date(r["peak_mjd"]).year
    for y in YEARS:
        rows = [r for r in bts_rows if year(r) == y and r["oid"] not in STARS and r["redshift"]
                and r["type"] not in ("", "-") and r["peak_mag"] and r["ra"] is not None]
        # the brightest events of a year are the ones people wrote about
        bright = sorted(rows, key=lambda r: r["peak_mag"])[:per_year]
        faint = [r for r in _shuffled(rows) if r["peak_mag"] > 18][:per_year]
        found += [keep(r) | {"group": "bright"} for r in bright] + [keep(r) | {"group": "faint"} for r in faint]
    return [e | {"year": year(e)} for e in found]


def coarse(kind: str | None) -> str | None:
    t = re.sub(r"\b(sn|type)\b", " ", (kind or "").lower())
    if not t.strip() or t.strip() in ("null", "none", "unknown"):
        return None
    for key, words in (("lens", ("lens", "lensing", "microlensing")), ("tde", ("tde", "tidal")),
                       ("slsn", ("slsn", "superluminous")), ("ia", ("ia", "iax")),
                       ("stripped", ("ib", "ic", "iib", "ibn", "icn", "ib/c")), ("ii", ("ii", "iin", "iip", "iil"))):
        if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in words):
            return key
    return "other"


def _json(text: str | None) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _z(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def z_ok(answer: dict, truth: dict) -> bool:
    z, true = _z(answer.get("redshift")), truth.get("redshift")
    return bool(z is not None and true and abs(z - true) / true < 0.1)


def type_ok(answer: dict, truth: dict) -> bool:
    return coarse(answer.get("type")) == coarse(truth["type"]) is not None


def name_ok(answer: dict, truth: dict) -> bool:
    said = re.sub(r"[\s_-]", "", str(answer.get("name") or "")).lower()
    core = re.sub(r"^(sn|at|tde)", "", truth["name"].lower())
    return bool(said) and (core in said or truth["oid"].lower() in said)


def score(event: dict, by_name: dict, by_sky: dict) -> dict:
    known = lambda a: a.get("known") is True
    return {
        "name_known": known(by_name), "name_type_ok": type_ok(by_name, event), "name_z_ok": z_ok(by_name, event),
        "sky_known": known(by_sky), "sky_name_ok": name_ok(by_sky, event), "sky_type_ok": type_ok(by_sky, event),
        "sky_z_ok": z_ok(by_sky, event),
        # remembered means a specific fact came back: its redshift from the name, or its name from the sky
        "remembered": z_ok(by_name, event) or name_ok(by_sky, event),
    }


def chance(rows: list[dict]) -> dict:
    # each answer scored against every other event's truth: what luck alone gets right
    pairs = [(a, b) for a in rows for b in rows if a["oid"] != b["oid"]]
    return {"name_type_ok": round(float(np.mean([type_ok(a["by_name"], b) for a, b in pairs])), 3),
            "name_z_ok": round(float(np.mean([z_ok(a["by_name"], b) for a, b in pairs])), 3)}


def run(bts_rows: list[dict], mulens_rows: list[dict], model: str, llm: LLM | None = None, workers: int = 8) -> dict:
    llm, (provider, name, kwargs) = llm or LLM(), MODELS[model]
    picked = events(bts_rows, mulens_rows)

    def ask(text: str) -> tuple[dict, float]:
        r = llm.chat(provider, name, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                     f"f9:{model}", **kwargs)
        return _json(r.choices[0].message.content), price(provider, name, usage_of(r))

    def one(e: dict) -> dict:
        label = e["name"] if e["name"] == e["oid"] else f"{e['name']} (ZTF name {e['oid']})"
        date = mjd_to_date(e["peak_mjd"]).isoformat()
        (a, c1), (b, c2) = ask(BY_NAME.format(label=label)), ask(BY_SKY.format(ra=e["ra"], dec=e["dec"], date=date))
        return e | {"by_name": a, "by_sky": b, "usd": round(c1 + c2, 6)} | score(e, a, b)

    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(one, picked))
    rate = lambda rs, k: round(float(np.mean([r[k] for r in rs])), 3) if rs else None
    keys = ("name_known", "name_type_ok", "name_z_ok", "sky_known", "sky_name_ok", "remembered")
    return {
        "model": model, "code": code_version(), "n": len(rows),
        "overall": {k: rate(rows, k) for k in keys},
        "chance": chance(rows),
        "by_year": {y: {k: rate([r for r in rows if r["year"] == y], k) for k in ("name_known", "name_z_ok", "remembered")}
                    for y in YEARS},
        "by_group": {g: {k: rate([r for r in rows if r["group"] == g], k) for k in keys} for g in ("bright", "faint", "star")},
        "remembered": [r["oid"] for r in rows if r["remembered"]],
        "usd": round(sum(r["usd"] for r in rows), 4),
        "rows": rows,
    }
