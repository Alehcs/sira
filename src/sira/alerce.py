import httpx

from .fetch import get

API = "https://api.alerce.online/ztf/v1"
STAMPS = "https://avro.alerce.online/get_stamp"


def lightcurve(c: httpx.Client, oid: str) -> dict:
    return get(c, f"{API}/objects/{oid}/lightcurve").json()


def stamp(c: httpx.Client, oid: str, candid: str, kind: str) -> bytes:
    return get(c, STAMPS, {"oid": oid, "candid": candid, "type": kind, "format": "fits"}).content


def objects(c: httpx.Client, params: dict) -> list[dict]:
    return get(c, f"{API}/objects/", params).json().get("items", [])
