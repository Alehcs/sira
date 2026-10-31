import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from . import alerce, photometry, reader, snapshot, stamps
from .fetch import client
from .live import BANDS, seen

SECONDS = 300  # past this the build stops fetching, so a slow archive costs images, never the site
FLAT = 2.0  # outside its footprint, or on a saturated core, Legacy answers with a cutout of nearly one shade


def strip(fits: list[bytes]) -> tuple[bytes, list[int]]:
    # science, reference and difference with the reader's v2 stretch, one pixel per ZTF pixel and no gaps
    pngs = stamps.matched(*fits, common=reader.PROTOCOLS["v2"].render == "matched", upscale=1)
    sizes = {Image.open(io.BytesIO(p)).size for p in pngs}
    if len(sizes) > 1:
        raise ValueError("the three cutouts differ in size")
    return stamps.side_by_side(pngs, gap=0), list(sizes.pop())


def flat(jpg: bytes) -> bool:
    # the middle half of the pixels, so a few stray ones on a blank cutout do not make it a picture
    px = np.asarray(Image.open(io.BytesIO(jpg)).convert("L"), dtype=float)
    return float(np.subtract(*np.percentile(px, [75, 25]))) < FLAT


def one(c, oid: str, out: Path, fresh: bool = False) -> dict:
    lc = alerce.lightcurve(c, oid, fresh=fresh)
    rows = photometry.from_alerce(lc)
    pos = [d for d in lc.get("detections", []) if d.get("ra") is not None]
    dets = [r for r in rows if r["kind"] == "det"]
    if not pos or not dets:
        raise ValueError("no detections")
    ra, dec = float(np.mean([d["ra"] for d in pos])), float(np.mean([d["dec"] for d in pos]))
    found = {"ra": round(ra, 6), "dec": round(dec, 6), "first": min(r["mjd"] for r in dets),
             "points": sum(r["band"] in BANDS and r["flux"] > 0 for r in dets), "curve": seen({"photometry": rows})}
    # the stamps the reader judged: its first detection with a stamp, as in team.eyes
    shot = [r for r in dets if r.get("stamp", True) and r.get("candid")]
    if shot:
        first = min(shot, key=lambda r: r["mjd"])
        try:
            png, panel = strip([alerce.stamp(c, oid, first["candid"], k) for k in reader.KINDS])
            (out / f"{oid}.png").write_bytes(png)
            found |= {"stamps": f"{oid}.png", "panel": panel, "taken": first["mjd"]}
        except Exception:
            pass
    try:
        # rounded, so a position that drifts with new detections still finds its cutout in the cache
        jpg = snapshot._host(c, round(ra, 4), round(dec, 4))
        if not flat(jpg):
            (out / f"{oid}.jpg").write_bytes(jpg)
            found["host"] = f"{oid}.jpg"
    except Exception:
        pass
    return found


def build(oids: list[str], out: Path, fresh: set = frozenset(), seconds: float = SECONDS) -> dict[str, dict]:
    # every object fails on its own: no light curve, no stamps or no host, and the build goes on
    out.mkdir(parents=True, exist_ok=True)
    c, stop = client(), time.monotonic() + seconds
    c.timeout = 20

    def safe(oid):
        if time.monotonic() > stop:
            return oid, None
        try:
            return oid, one(c, oid, out, oid in fresh)
        except Exception:
            return oid, None

    with ThreadPoolExecutor(4) as pool:
        found = dict(pool.map(safe, list(dict.fromkeys(oids))))
    c.close()
    return {oid: f for oid, f in found.items() if f}
