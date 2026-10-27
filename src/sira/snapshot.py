import hashlib
import json
import subprocess
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import alerce, catalogs, fink, photometry, stamps
from .fetch import client, get

LEGACY = "https://www.legacysurvey.org/viewer/cutout.jpg"
KINDS = ("science", "template", "difference")
CC_TYPES = {"SN II", "SN IIP", "SN IIb", "SN IIn", "SN Ib", "SN Ic", "SN Ib/c", "SN Ic-BL"}
RARE = ("TDE", "SLSN", "SN Ibn", "SN Icn", "SN Ia-CSM", "SN Iax", "SN Ia-91bg")
LIMITS = {"ia": 60, "cc": 40, "rare": 30, "rubin": 10, "bogus": 50}

_local = threading.local()
# Legacy Survey rate-limits hard, so keep host cutouts to two at a time
_host_slots = threading.Semaphore(2)


def _client():
    if not hasattr(_local, "c"):
        _local.c = client()
    return _local.c


def mjd_to_date(mjd: float) -> date:
    return date(1858, 11, 17) + timedelta(days=mjd)


def split(oid: str) -> str:
    return "dev" if int(hashlib.sha256(oid.encode()).hexdigest(), 16) % 2 == 0 else "test"


def _shuffled(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: hashlib.sha256(r["oid"].encode()).hexdigest())


def pick(bts_rows: list[dict], mulens_rows: list[dict], limits: dict = LIMITS) -> list[dict]:
    year = lambda r: mjd_to_date(r["peak_mjd"]).year
    groups = {
        "ia": [r for r in bts_rows if r["type"] == "SN Ia" and year(r) == 2025
               and r["redshift"] and 0.02 <= r["redshift"] <= 0.12],
        "cc": [r for r in bts_rows if r["type"] in CC_TYPES and year(r) == 2025],
        "rare": [r for r in bts_rows if r["type"].startswith(RARE) and 2024 <= year(r) <= 2026],
    }
    cases = []
    for cat, rows in groups.items():
        for r in _shuffled(rows)[: limits[cat]]:
            truth = {"type": r["type"], "redshift": r["redshift"], "peak_mjd": r["peak_mjd"], "name": r["name"]}
            cases.append({"oid": r["oid"], "survey": "ztf", "category": cat, "truth": truth})
    for r in mulens_rows:
        truth = {"type": "microlensing", "t0_mjd": r["t0_mjd"], "tE": r["tE"], "u0": r["u0"]}
        cases.append({"oid": r["oid"], "survey": "ztf", "category": "microlensing", "truth": truth})
    for case in cases:
        case["split"] = split(case["oid"])
    return cases


def rubin_cases(c, limit: int) -> list[dict]:
    found = {}
    for r in fink.tagged(c, "in_tns", "2026-02-24", "2026-07-15", n=500):
        oid, kind = str(r.get("r:diaObjectId")), str(r.get("f:xm_tns_type") or "").strip()
        if kind and kind.lower() not in ("nan", "none") and oid not in found:
            found[oid] = {"oid": oid, "survey": "rubin", "category": "rubin",
                          "truth": {"type": kind, "name": r.get("f:xm_tns_fullname")}}
    cases = _shuffled(list(found.values()))[:limit]
    for case in cases:
        case["split"] = split(case["oid"])
    return cases


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _host(c, ra: float, dec: float) -> bytes:
    with _host_slots:
        return get(c, LEGACY, {"ra": ra, "dec": dec, "layer": "ls-dr10", "pixscale": 0.262, "size": 128}).content


def ztf_object(c, case: dict, out: Path) -> tuple[dict, dict]:
    oid = case["oid"]
    lc = alerce.lightcurve(c, oid)
    rows = photometry.from_alerce(lc)
    dets = [d for d in lc.get("detections", []) if d.get("has_stamp")]
    if not rows or not dets:
        raise ValueError("no detections with stamps")
    first = min(dets, key=lambda d: d["mjd"])
    files = {}
    for kind in KINDS:
        rel = f"stamps/{oid}/first_{kind}.png"
        files[rel] = _write(out / rel, stamps.to_png(alerce.stamp(c, oid, str(first["candid"]), kind)))
    ra = sum(d["ra"] for d in dets) / len(dets)
    dec = sum(d["dec"] for d in dets) / len(dets)
    host = f"stamps/{oid}/host.jpg"
    image, _ = _safe(_host, c, ra, dec)
    if image:
        files[host] = _write(out / host, image)
    obj = {
        "oid": oid, "survey": "ztf", "ra": ra, "dec": dec, "photometry": rows,
        "first_stamps": {"candid": str(first["candid"]), "mjd": first["mjd"],
                         "available_at": first["mjd"] + photometry.LATENCY,
                         "files": [f"stamps/{oid}/first_{k}.png" for k in KINDS]},
        # Legacy DR10 imaging ends in 2021, so later events can't be in it
        "host": {"file": host if image else None, "predates_event": first["mjd"] > 59580},
    }
    return obj, files


def rubin_object(c, case: dict, out: Path) -> tuple[dict, dict]:
    oid = case["oid"]
    src = fink.sources(c, oid)
    rows = photometry.from_fink(src)
    if not rows:
        raise ValueError("no sources")
    first, files, stamp_files = rows[0], {}, []
    try:
        for kind in ("Science", "Template", "Difference"):
            rel = f"stamps/{oid}/first_{kind.lower()}.png"
            files[rel] = _write(out / rel, stamps.to_png(fink.cutout(c, first["source_id"], kind)))
            stamp_files.append(rel)
    except Exception:
        stamp_files = []
    pos = [s for s in src if s.get("r:ra") is not None]
    obj = {
        "oid": oid, "survey": "rubin", "photometry": rows,
        "ra": sum(s["r:ra"] for s in pos) / len(pos) if pos else None,
        "dec": sum(s["r:dec"] for s in pos) / len(pos) if pos else None,
        "first_stamps": {"source_id": first["source_id"], "mjd": first["mjd"],
                         "available_at": first["available_at"], "files": stamp_files},
    }
    return obj, files


def bogus_stamps(c, oid: str, out: Path) -> tuple[list[str], dict]:
    lc = alerce.lightcurve(c, oid)
    dets = [d for d in lc.get("detections", []) if d.get("has_stamp")]
    first = min(dets, key=lambda d: d["mjd"])
    files = {}
    for kind in KINDS:
        rel = f"valset/bogus/{oid}_{kind}.png"
        files[rel] = _write(out / rel, stamps.to_png(alerce.stamp(c, oid, str(first["candid"]), kind)))
    return list(files), files


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _safe(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def build(out: Path, workers: int = 8, rubin: bool = True, limits: dict = LIMITS, log=print) -> dict:
    out = Path(out)
    failures, checksums, objects, truth = [], {}, [], {}
    c = client()
    with client(verify=False) as bts_client:  # BTS serves a self-signed certificate
        cases = pick(catalogs.bts(bts_client), catalogs.microlensing(c), limits)
    if rubin:
        found, err = _safe(rubin_cases, c, limits["rubin"])
        cases += found or []
        if err:
            failures.append({"oid": "rubin-cases", "error": err})
    bogus = [i["oid"] for i in alerce.objects(c, {"classifier": "stamp_classifier", "class": "bogus",
                                                     "probability": 0.9, "page_size": limits["bogus"],
                                                     "order_by": "probability", "order_mode": "DESC"})]
    log(f"fetching {len(cases)} objects and {len(bogus)} bogus stamps")

    def run(case):
        fn = rubin_object if case["survey"] == "rubin" else ztf_object
        return case, *_safe(fn, _client(), case, out)

    with ThreadPoolExecutor(workers) as pool:
        for i, (case, result, err) in enumerate(pool.map(run, cases), 1):
            if err:
                failures.append({"oid": case["oid"], "error": err})
                continue
            obj, files = result
            rel = f"objects/{case['oid']}.json"
            checksums.update(files)
            checksums[rel] = _write(out / rel, json.dumps(obj).encode())
            objects.append({k: case[k] for k in ("oid", "survey", "category", "split")} | {"file": rel})
            truth[case["oid"]] = case["truth"]
            if i % 25 == 0:
                log(f"{i}/{len(cases)} objects")

        valset = [{"label": "real", "oid": o["oid"], "files": [f"stamps/{o['oid']}/first_{k}.png" for k in KINDS]}
                  for o in objects if o["category"] in ("ia", "cc")][: limits["bogus"]]
        for oid, (result, err) in zip(bogus, pool.map(lambda o: _safe(bogus_stamps, _client(), o, out), bogus)):
            if err:
                failures.append({"oid": oid, "error": err})
                continue
            paths, files = result
            checksums.update(files)
            valset.append({"label": "bogus", "oid": oid, "files": paths})

    # truth stays in its own file: the agents never read it, only the scorer does
    checksums["truth.json"] = _write(out / "truth.json", json.dumps(truth, indent=1).encode())
    checksums["valset.json"] = _write(out / "valset.json", json.dumps(valset, indent=1).encode())
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": _git_sha(),
        "counts": dict(Counter(o["category"] for o in objects)),
        "splits": dict(Counter(o["split"] for o in objects)),
        "valset": dict(Counter(v["label"] for v in valset)),
        "objects": objects,
        "failures": failures,
        "checksums": checksums,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    c.close()
    return manifest
