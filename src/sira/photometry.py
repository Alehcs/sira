import math

BANDS = {1: "ztfg", 2: "ztfr", 3: "ztfi"}
# alerts are public within hours; half a day keeps replay on the safe side
LATENCY = 0.5


def flux(mag: float, err: float) -> tuple[float, float]:
    f = 10 ** (-0.4 * (mag - 23.9))  # AB mag to microjansky
    return f, f * 0.4 * math.log(10) * err


def _negative(value) -> bool:
    return value in (-1, 0, "-1", "0", "f", "false", False)


def from_alerce(lc: dict) -> list[dict]:
    rows = []
    for d in lc.get("detections", []):
        if d.get("magpsf") is None or d.get("fid") not in BANDS:
            continue
        err = d.get("sigmapsf") or 0.1
        f, fe = flux(d["magpsf"], err)
        rows.append({
            "mjd": d["mjd"], "band": BANDS[d["fid"]], "kind": "det",
            "mag": d["magpsf"], "mag_err": err,
            "flux": -f if _negative(d.get("isdiffpos")) else f, "flux_err": fe,
            "candid": str(d.get("candid")), "available_at": d["mjd"] + LATENCY,
        })
    for n in lc.get("non_detections", []):
        if n.get("diffmaglim") is None or n.get("fid") not in BANDS:
            continue
        rows.append({
            "mjd": n["mjd"], "band": BANDS[n["fid"]], "kind": "limit",
            "mag": n["diffmaglim"], "available_at": n["mjd"] + LATENCY,
        })
    return sorted(rows, key=lambda r: r["mjd"])


def from_fink(sources: list[dict]) -> list[dict]:
    rows = []
    for s in sources:
        mjd, f = s.get("r:midpointMjdTai"), s.get("r:psfFlux")
        if mjd is None or f is None:
            continue
        rows.append({
            "mjd": mjd, "band": "lsst" + str(s.get("r:band")), "kind": "det",
            # Rubin fluxes come in nanojansky
            "flux": f / 1000, "flux_err": (s.get("r:psfFluxErr") or 0) / 1000,
            "source_id": str(s.get("r:diaSourceId")), "available_at": mjd + LATENCY,
        })
    return sorted(rows, key=lambda r: r["mjd"])
