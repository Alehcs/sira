import time

import httpx


def client(verify: bool = True) -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True, verify=verify,
                        headers={"User-Agent": "sira/0.1 (Meta AI hackathon research)"})


def _retry(call, tries: int = 3) -> httpx.Response:
    for i in range(tries):
        try:
            r = call()
            if r.status_code < 500:
                r.raise_for_status()
                return r
        except httpx.TransportError:
            if i == tries - 1:
                raise
        time.sleep(2 ** i)
    r.raise_for_status()
    return r


def get(c: httpx.Client, url: str, params=None) -> httpx.Response:
    return _retry(lambda: c.get(url, params=params))


def post(c: httpx.Client, url: str, payload: dict) -> httpx.Response:
    return _retry(lambda: c.post(url, json=payload))
