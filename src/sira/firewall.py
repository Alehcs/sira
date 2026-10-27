import copy
import hashlib
import json

import astropy.units as u
from astropy.coordinates import SkyCoord

# keys that carry the answer; a view never has them, whatever the object holds
TRUTH = {"type", "redshift", "name", "truth", "category", "split", "peak_mjd"}
# a magnitude ZTF can never measure; planted after the cut, it must never reach a model
CANARY_MAG = 7.777


class Leak(RuntimeError):
    pass


def as_of(obj: dict, t: float) -> dict:
    view = {k: v for k, v in obj.items() if k not in TRUTH | {"photometry", "first_stamps", "host"}}
    view["photometry"] = [dict(r) for r in obj.get("photometry", []) if r["available_at"] <= t]
    stamps = obj.get("first_stamps") or {}
    view["first_stamps"] = dict(stamps) if stamps.get("available_at", float("inf")) <= t else None
    host = obj.get("host") or {}
    # a host image taken after the event could show the event itself
    view["host"] = dict(host) if host.get("predates_event") else None
    view["as_of"] = t
    return view


def case_id(oid: str) -> str:
    return "case-" + hashlib.sha256(f"sira:{oid}".encode()).hexdigest()[:10]


def blind(view: dict) -> dict:
    # what an LLM may see: no names, no IDs, no calendar dates, no exact position
    t = view["as_of"]
    rows = [{"day": round(r["mjd"] - t, 3), "band": r["band"].replace("ztf", "").replace("lsst", ""),
             "kind": r["kind"], "mag": r.get("mag"), "mag_err": r.get("mag_err")}
            for r in sorted(view["photometry"], key=lambda r: r["mjd"])]
    out = {"case": case_id(view["oid"]), "survey": view.get("survey"), "photometry": rows,
           "has_stamps": bool(view.get("first_stamps")), "has_host_image": bool(view.get("host"))}
    if view.get("ra") is not None and view.get("dec") is not None:
        b = SkyCoord(ra=view["ra"] * u.deg, dec=view["dec"] * u.deg).galactic.b.deg
        out["galactic_latitude"] = int(5 * round(b / 5))
    return out


def plant(obj: dict, t: float, n: int = 3) -> dict:
    out = copy.deepcopy(obj)
    for k in range(1, n + 1):
        out["photometry"].append({"mjd": t + k, "band": "ztfg", "kind": "det", "mag": CANARY_MAG, "mag_err": 0.01,
                                  "flux": 10 ** (-0.4 * (CANARY_MAG - 23.9)), "flux_err": 1.0, "candid": "canary",
                                  "available_at": t + k + 0.5})
    return out


def tripwire(payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    if str(CANARY_MAG) in text:
        raise Leak("a canary from the future reached the model")
