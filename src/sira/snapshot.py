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
LIMITS = {"ia": 60, "cc": 40, "rare": 30, "rubin": 10, "bogus": 50, "examples": 50, "holdout": 80}

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


def _stamp(out: Path, rel: str, data: bytes, files: dict) -> None:
    # the raw FITS sits next to each PNG, so stamps can be rendered again another way
    files[rel] = _write(out / rel, stamps.to_png(data))
    files[rel[:-4] + ".fits"] = _write(out / (rel[:-4] + ".fits"), stamps.unzip(data))


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
        _stamp(out, f"stamps/{oid}/first_{kind}.png", alerce.stamp(c, oid, str(first["candid"]), kind), files)
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
            _stamp(out, rel, fink.cutout(c, first["source_id"], kind), files)
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


def first_stamps(c, oid: str, out: Path, folder: str) -> tuple[list[str], dict]:
    lc = alerce.lightcurve(c, oid)
    dets = [d for d in lc.get("detections", []) if d.get("has_stamp")]
    first = min(dets, key=lambda d: d["mjd"])
    files, paths = {}, [f"{folder}/{oid}_{kind}.png" for kind in KINDS]
    for kind, rel in zip(KINDS, paths):
        _stamp(out, rel, alerce.stamp(c, oid, str(first["candid"]), kind), files)
    return paths, files


def _stamp_set(pool, oids: list[str], out: Path, folder: str, label: str, failures: list, checksums: dict) -> list[dict]:
    found = []
    for oid, (result, err) in zip(oids, pool.map(lambda o: _safe(first_stamps, _client(), o, out, folder), oids)):
        if err:
            failures.append({"oid": oid, "error": err})
            continue
        paths, files = result
        checksums.update(files)
        found.append({"label": label, "oid": oid, "files": paths})
    return found


def holdout_real(bts_rows: list[dict], taken: set, n: int) -> dict[str, list[str]]:
    year = lambda r: mjd_to_date(r["peak_mjd"]).year
    groups = {"ia": [r for r in bts_rows if r["type"] == "SN Ia" and year(r) == 2024
                     and r["redshift"] and 0.02 <= r["redshift"] <= 0.12],
              "cc": [r for r in bts_rows if r["type"] in CC_TYPES and year(r) == 2024]}
    return {g: [r["oid"] for r in _shuffled(rows) if r["oid"] not in taken][: n // 2] for g, rows in groups.items()}


def code_version() -> str | None:
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()
    try:
        return git("rev-parse", "HEAD") + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")
    except Exception:
        return None


def _safe(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def build(out: Path, workers: int = 8, rubin: bool = True, limits: dict = LIMITS, log=print) -> dict:
    out, code = Path(out), code_version()
    failures, checksums, objects, truth = [], {}, [], {}
    c = client()
    with client(verify=False) as bts_client:  # BTS serves a self-signed certificate
        bts_rows = catalogs.bts(bts_client)
    cases = pick(bts_rows, catalogs.microlensing(c), limits)
    if rubin:
        found, err = _safe(rubin_cases, c, limits["rubin"])
        cases += found or []
        if err:
            failures.append({"oid": "rubin-cases", "error": err})
    query = {"classifier": "stamp_classifier", "class": "bogus", "probability": 0.9,
             "page_size": limits["bogus"], "order_by": "probability", "order_mode": "DESC"}
    bogus = [i["oid"] for i in alerce.objects(c, query)]
    # page 2 feeds the reader's examples, pages 3-4 a holdout no protocol has seen; none overlap
    spare = [i["oid"] for i in alerce.objects(c, query | {"page": 2}) if i["oid"] not in bogus][: limits["examples"]]
    seen = set(bogus) | set(spare)
    held = [i["oid"] for p in (3, 4) for i in alerce.objects(c, query | {"page": p}) if i["oid"] not in seen]
    held = list(dict.fromkeys(held))[: limits["holdout"]]
    held_real = holdout_real(bts_rows, {case["oid"] for case in cases}, limits["holdout"])
    log(f"fetching {len(cases)} objects, {len(bogus)} bogus, {len(spare)} spare and {len(held)} + "
        f"{sum(map(len, held_real.values()))} holdout stamps")

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

        real = [{"label": "real", "oid": o["oid"], "files": [f"stamps/{o['oid']}/first_{k}.png" for k in KINDS]}
                for o in objects if o["category"] in ("ia", "cc")]
        valset = real[: limits["bogus"]] + _stamp_set(pool, bogus, out, "valset/bogus", "bogus", failures, checksums)
        examples = real[limits["bogus"]:] + _stamp_set(pool, spare, out, "examples/bogus", "bogus", failures, checksums)
        holdout = [e | {"group": g} for g, oids in held_real.items()
                   for e in _stamp_set(pool, oids, out, "holdout/real", "real", failures, checksums)]
        holdout += [e | {"group": "bogus"} for e in _stamp_set(pool, held, out, "holdout/bogus", "bogus", failures, checksums)]

    # truth stays in its own file: the agents never read it, only the scorer does
    checksums["truth.json"] = _write(out / "truth.json", json.dumps(truth, indent=1).encode())
    checksums["valset.json"] = _write(out / "valset.json", json.dumps(valset, indent=1).encode())
    checksums["examples.json"] = _write(out / "examples.json", json.dumps(examples, indent=1).encode())
    checksums["holdout.json"] = _write(out / "holdout.json", json.dumps(holdout, indent=1).encode())
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code,
        "counts": dict(Counter(o["category"] for o in objects)),
        "splits": dict(Counter(o["split"] for o in objects)),
        "valset": dict(Counter(v["label"] for v in valset)),
        "examples": dict(Counter(e["label"] for e in examples)),
        "holdout": dict(Counter(h["group"] for h in holdout)),
        "objects": objects,
        "failures": failures,
        "checksums": checksums,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    c.close()
    return manifest
