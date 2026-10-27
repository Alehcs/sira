import hashlib
import json
import os
import threading
import time
from pathlib import Path

import httpx

CACHE = Path(os.getenv("SIRA_CACHE", "data/cache"))
# seconds between requests to the same host, to stay polite with public services
GAPS = {"api.alerce.online": 0.4, "avro.alerce.online": 0.4, "www.legacysurvey.org": 1.0, "irsa.ipac.caltech.edu": 0.3}

_last: dict[str, float] = {}
_lock = threading.Lock()


def client(verify: bool = True) -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True, verify=verify,
                        headers={"User-Agent": "sira/0.1 (Meta AI hackathon research)"})


def _throttle(url: str) -> None:
    host = httpx.URL(url).host
    gap = GAPS.get(host, 0.1)
    with _lock:
        now = time.monotonic()
        slot = max(now, _last.get(host, 0.0) + gap)
        _last[host] = slot
    if slot > now:
        time.sleep(slot - now)


def _wait(r: httpx.Response | None, attempt: int) -> float:
    after = r.headers.get("Retry-After", "") if r is not None else ""
    if after.isdigit():
        return min(float(after), 60.0)
    return 5.0 * 2 ** attempt if r is not None and r.status_code == 429 else 2 ** attempt


def _retry(call, url: str, tries: int = 4) -> httpx.Response:
    r = None
    for i in range(tries):
        try:
            _throttle(url)
            r = call()
            # 429 and 5xx are worth another try, other errors are not
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
        except httpx.TransportError:
            if i == tries - 1:
                raise
        if i < tries - 1:
            time.sleep(_wait(r, i))
    r.raise_for_status()
    return r


def _cached(method: str, url: str, body, call) -> httpx.Response:
    key = hashlib.sha256(f"{method} {url} {json.dumps(body, sort_keys=True, default=str)}".encode()).hexdigest()
    path = CACHE / key[:2] / key
    if path.exists():
        return httpx.Response(200, content=path.read_bytes(), request=httpx.Request(method, url))
    r = _retry(call, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r


def get(c: httpx.Client, url: str, params=None, fresh: bool = False) -> httpx.Response:
    call = lambda: c.get(url, params=params)
    # live data must never come from the cache
    return _retry(call, url) if fresh else _cached("GET", url, params, call)


def post(c: httpx.Client, url: str, payload: dict) -> httpx.Response:
    return _cached("POST", url, payload, lambda: c.post(url, json=payload))
