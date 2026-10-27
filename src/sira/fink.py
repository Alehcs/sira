import httpx

from .fetch import post

API = "https://api.lsst.fink-portal.org/api/v1"


def tagged(c: httpx.Client, tag: str, start: str, stop: str, n: int = 200) -> list[dict]:
    payload = {"tag": tag, "n": n, "startdate": start, "stopdate": stop, "output-format": "json",
               "columns": "r:diaObjectId,f:xm_tns_type,f:xm_tns_fullname"}
    return post(c, f"{API}/tags", payload).json()


def sources(c: httpx.Client, object_id: str) -> list[dict]:
    payload = {"diaObjectId": object_id, "output-format": "json",
               "columns": "r:diaSourceId,r:midpointMjdTai,r:psfFlux,r:psfFluxErr,r:band,r:ra,r:dec"}
    return post(c, f"{API}/sources", payload).json()


def cutout(c: httpx.Client, source_id: str, kind: str) -> bytes:
    payload = {"diaSourceId": source_id, "kind": kind, "output-format": "FITS"}
    return post(c, f"{API}/cutouts", payload).content
