import csv
import io
import re

import httpx

from .fetch import get

BTS = "https://sites.astro.caltech.edu/ztf/bts/explorer.php"
MULENS = "https://zenodo.org/api/records/13829674/files/machine_readable_high_confidence.csv/content"
ALERT_ID = re.compile(r"^ZTF\d{2}[a-z]{7}$")


def _num(text: str | None) -> float | None:
    m = re.match(r"^\s*(-?[\d.]+)", text or "")
    return float(m.group(1)) if m else None


def parse_bts(text: str) -> list[dict]:
    lines = [line for line in text.splitlines() if line.strip()]
    out = []
    for r in csv.DictReader(lines):
        peak = _num(r.get("peakt"))
        if peak is None:
            continue
        out.append({
            "oid": r["ZTFID"],
            "name": r["IAUID"],
            "type": r["type"].strip(),
            "redshift": _num(r.get("redshift")),
            # BTS peakt is JD - 2458000
            "peak_mjd": peak + 57999.5,
            "av": _num(r.get("A_V")),
        })
    return out


def parse_mulens(text: str) -> list[dict]:
    out, seen = [], set()
    for r in csv.DictReader(io.StringIO(text)):
        oid = r["ZTF_ID"].strip()
        if not ALERT_ID.match(oid) or oid in seen:
            continue
        seen.add(oid)
        # catalog times are HJD - 2450000
        out.append({"oid": oid, "t0_mjd": _num(r["t_0"]) + 49999.5, "tE": _num(r["t_E"]), "u0": abs(_num(r["u_0"]))})
    return out


def bts(c: httpx.Client) -> list[dict]:
    return parse_bts(get(c, BTS, {"f": "s", "format": "csv"}).text)


def microlensing(c: httpx.Client) -> list[dict]:
    return parse_mulens(get(c, MULENS).text)
