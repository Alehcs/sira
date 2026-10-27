import httpx
import pytest

from sira import fetch


def fake_client(statuses):
    calls = iter(statuses)

    def handler(request):
        status = next(calls)
        return httpx.Response(status, headers={"Retry-After": "0"}, text="ok")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    r = fetch.get(fake_client([429, 503, 200]), "https://example.org")
    assert r.status_code == 200


def test_client_errors_fail_fast(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        fetch.get(fake_client([404, 200]), "https://example.org")


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        fetch.get(fake_client([429, 429, 429, 429]), "https://example.org")
