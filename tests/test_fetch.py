import httpx
import pytest

from sira import fetch


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)


def fake_client(statuses, seen=None):
    calls = iter(statuses)

    def handler(request):
        if seen is not None:
            seen.append(str(request.url))
        return httpx.Response(next(calls), headers={"Retry-After": "0"}, text="ok")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_rate_limit_then_succeeds():
    assert fetch.get(fake_client([429, 503, 200]), "https://example.org/a").status_code == 200


def test_client_errors_fail_fast():
    with pytest.raises(httpx.HTTPStatusError):
        fetch.get(fake_client([404, 200]), "https://example.org/b")


def test_gives_up_after_retries():
    with pytest.raises(httpx.HTTPStatusError):
        fetch.get(fake_client([429, 429, 429, 429]), "https://example.org/c")


def test_second_call_comes_from_cache():
    seen = []
    c = fake_client([200], seen)
    first = fetch.get(c, "https://example.org/d", {"x": 1})
    again = fetch.get(c, "https://example.org/d", {"x": 1})
    assert len(seen) == 1
    assert again.text == first.text == "ok"


def test_failures_are_not_cached():
    with pytest.raises(httpx.HTTPStatusError):
        fetch.get(fake_client([404]), "https://example.org/e")
    assert fetch.get(fake_client([200]), "https://example.org/e").status_code == 200


def test_fresh_reads_skip_the_cache():
    seen = []
    c = fake_client([200, 200], seen)
    fetch.get(c, "https://example.org/f")
    fetch.get(c, "https://example.org/f", fresh=True)
    assert len(seen) == 2
