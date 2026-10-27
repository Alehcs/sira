import httpx

from .fetch import get

API = "https://api.alerce.online/ztf/v1"
STAMPS = "https://avro.alerce.online/get_stamp"


def lightcurve(c: httpx.Client, oid: str, fresh: bool = False) -> dict:
    return get(c, f"{API}/objects/{oid}/lightcurve", fresh=fresh).json()


def stamp(c: httpx.Client, oid: str, candid: str, kind: str) -> bytes:
    return get(c, STAMPS, {"oid": oid, "candid": candid, "type": kind, "format": "fits"}).content


def objects(c: httpx.Client, params, fresh: bool = False) -> list[dict]:
    return get(c, f"{API}/objects/", params, fresh).json().get("items", [])
