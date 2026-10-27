import json

import pytest

from sira import ledger
from sira.ledger import GENESIS, Ledger, digest, verify

SEALED_AT = "2026-10-27T18:00:00+00:00"  # MJD 61340.75


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(ledger, "rfc3161", lambda c, h: b"receipt for " + h.encode())
    monkeypatch.setattr(ledger, "check_rfc3161",
                        lambda c, path, h: (path.read_bytes() == b"receipt for " + h.encode(), SEALED_AT))
    monkeypatch.setattr(ledger, "OTS", "true")


def bet(book, name="b1"):
    return book.append("bet", {"bet": name, "object": "ZTF26x", "forecasts": []}, now="2026-10-27T17:00:00+00:00")


def test_chain_links_every_entry_to_the_one_before(tmp_path):
    book = Ledger(tmp_path)
    entries = [book.append("x", {"i": i}) for i in range(3)]
    assert entries[0]["prev"] == GENESIS and entries[2]["prev"] == entries[1]["hash"]
    assert all(digest(e) == e["hash"] for e in book.entries())


def test_anchored_bets_verify(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    anchor = book.anchor(None)
    assert anchor["payload"]["head"] == book.entries()[0]["hash"]
    result = verify(tmp_path, None)
    assert result["passes"] and result["bets_sealed"] == 1 and not result["problems"]


def test_editing_any_entry_breaks_the_chain(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    lines = book.path.read_text().splitlines()
    first = json.loads(lines[0])
    first["payload"]["object"] = "ZTF26y"
    book.path.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
    result = verify(tmp_path, None)
    assert not result["passes"] and any("breaks the chain" in p for p in result["problems"])


def test_a_bet_without_an_anchor_does_not_pass(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    bet(book, "b2")
    result = verify(tmp_path, None)
    assert result["bets"] == 2 and result["bets_sealed"] == 1 and not result["passes"]


def test_outcomes_measured_before_the_seal_are_flagged(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    book.append("outcome", {"bet": "b1", "mjd": 61340.70, "band": "ztfr"})
    assert any("before their bet was sealed" in p for p in verify(tmp_path, None)["problems"])
    book.path.write_text("\n".join(book.path.read_text().splitlines()[:-1]) + "\n")
    book.append("outcome", {"bet": "b1", "mjd": 61340.80, "band": "ztfr"})
    assert verify(tmp_path, None)["passes"]


def test_a_forged_receipt_is_caught(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    anchor = book.anchor(None)
    (tmp_path / anchor["payload"]["rfc3161"]).write_bytes(b"forged")
    assert any("RFC 3161" in p for p in verify(tmp_path, None)["problems"])


def test_anchor_is_skipped_when_nothing_is_new(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    assert book.anchor(None) is not None and book.anchor(None) is None
