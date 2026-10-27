import time

import httpx


def client(verify: bool = True) -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True, verify=verify,
                        headers={"User-Agent": "sira/0.1 (Meta AI hackathon research)"})


def _wait(r: httpx.Response | None, attempt: int) -> float:
    after = r.headers.get("Retry-After", "") if r is not None else ""
    return min(float(after), 30.0) if after.isdigit() else 2 ** attempt


def _retry(call, tries: int = 4) -> httpx.Response:
    r = None
    for i in range(tries):
        try:
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


def get(c: httpx.Client, url: str, params=None) -> httpx.Response:
    return _retry(lambda: c.get(url, params=params))


def post(c: httpx.Client, url: str, payload: dict) -> httpx.Response:
    return _retry(lambda: c.post(url, json=payload))
