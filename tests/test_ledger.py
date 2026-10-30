import json

import pytest

from sira import ledger, verify as checks
from sira.ledger import GENESIS, Ledger, canonical, digest, jcs
from sira.verify import verify

SEALED_AT = "2026-10-27T18:00:00+00:00"  # MJD 61340.75
REAL_CHECK = ledger.check_rfc3161
MADE_AT = 61340.74  # 17:45, a quarter of an hour before the seal


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    fake = lambda path, h: (path.exists() and path.read_bytes() == b"receipt for " + h.encode(), SEALED_AT)
    monkeypatch.setattr(ledger, "rfc3161", lambda c, h: b"receipt for " + h.encode())
    monkeypatch.setattr(ledger, "check_rfc3161", fake)
    monkeypatch.setattr(checks, "check_rfc3161", fake)
    monkeypatch.setattr(ledger, "OTS", "true")


def bet(book, name="b1", made_at=MADE_AT, question=None):
    payload = {"bet": name, "object": "ZTF26x", "model": "v1", "made_at": made_at, "question": question,
               "forecasts": [{"mjd": 61341.7, "band": "ztfr", "parts": [["ia", 0.9, 50.0, 5.0], ["null", 0.1, 60.0, 10.0]]},
                             {"mjd": 61342.7, "band": "ztfr", "parts": [["ia", 0.9, 45.0, 5.0], ["null", 0.1, 60.0, 11.0]]}]}
    return book.append("bet", payload, now="2026-10-27T16:48:00+00:00")


def outcome(book, mjd=61341.2, flux=48.0, err=2.0, name="b1"):
    from sira import live
    parts = live._at(book.entries()[0]["payload"]["forecasts"], mjd, "ztfr")
    return book.append("outcome", {"bet": name, "object": "ZTF26x", "mjd": mjd, "band": "ztfr", "kind": "det"}
                       | live.measure(parts, "det", flux, err))


def test_numbers_hash_the_way_javascript_writes_them():
    values = [0.0, -0.0, 3.0, 1e-05, 1.5e-07, 1e16, 1e20, 1e22, 0.1, 123.456, 1.2345e-05, 61341.7347, -2.5e-06]
    # what JSON.stringify prints for the same list in Node
    assert jcs(values) == ("[0,0,3,0.00001,1.5e-7,10000000000000000,100000000000000000000,1e+22,0.1,123.456,"
                           "0.000012345,61341.7347,-0.0000025]")
    assert jcs({"b": [True, None], "a": "é"}) == '{"a":"é","b":[true,null]}'
    with pytest.raises(ValueError):
        jcs(float("nan"))
    import numpy as np
    assert jcs({"f": np.float64(11.47), "i": np.int64(3), "b": np.bool_(True)}) == '{"b":true,"f":11.47,"i":3}'


def test_numpy_values_keep_the_chain_whole(tmp_path):
    import numpy as np
    book = Ledger(tmp_path)
    book.append("event", {"role": "lab", "cost_usd": np.float64(11.47), "n": np.int64(2)})
    book.append("event", {"role": "lab", "cost_usd": np.float32(0.25)})
    assert verify(tmp_path)["passes"]


def test_format_one_entries_still_verify(tmp_path):
    old = {"seq": 0, "time": "2026-10-27T16:00:00+00:00", "kind": "event", "payload": {"role": "lab", "cost_usd": 0.0},
           "prev": GENESIS}
    old["hash"] = digest(old)
    assert canonical(old) == (b'{"kind":"event","payload":{"cost_usd":0.0,"role":"lab"},"prev":"' + GENESIS.encode()
                              + b'","seq":0,"time":"2026-10-27T16:00:00+00:00"}')
    (tmp_path / "ledger.jsonl").write_text(json.dumps(old) + "\n")
    book = Ledger(tmp_path)
    book.append("event", {"role": "lab", "cost_usd": 0.0})
    assert verify(tmp_path)["passes"]


def test_an_entry_outside_the_protocol_fails_and_says_where(tmp_path):
    Ledger(tmp_path).append("bet", {"bet": "b1", "object": "ZTF26x", "model": "v1", "made_at": MADE_AT, "forecasts": []})
    result = verify(tmp_path)
    assert not result["passes"] and result["problems"][0].startswith("entry 0 does not follow the protocol at payload/forecasts")


def test_chain_links_every_entry_to_the_one_before(tmp_path):
    book = Ledger(tmp_path)
    entries = [book.append("x", {"i": i}) for i in range(3)]
    assert entries[0]["prev"] == GENESIS and entries[2]["prev"] == entries[1]["hash"]
    assert all(digest(e) == e["hash"] for e in book.entries())


def test_anchored_bets_verify(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    anchor = book.anchor(None)
    assert anchor["payload"]["head"] == book.entries()[0]["hash"] and anchor["payload"]["code"]
    result = verify(tmp_path)
    assert result["passes"] and result["bets_sealed"] == 1 and result["head"].startswith("1:")


def test_editing_any_entry_breaks_the_chain(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    lines = book.path.read_text().splitlines()
    first = json.loads(lines[0])
    first["payload"]["object"] = "ZTF26y"
    book.path.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
    result = verify(tmp_path)
    assert not result["passes"] and any("breaks the chain" in p for p in result["problems"])


def test_a_bet_without_an_anchor_does_not_pass(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    bet(book, "b2")
    result = verify(tmp_path)
    assert result["bets"] == 2 and result["bets_sealed"] == 1 and not result["passes"]


def test_a_bet_sealed_long_after_its_claimed_time_is_flagged(tmp_path):
    book = Ledger(tmp_path)
    bet(book, made_at=MADE_AT - 2)
    book.anchor(None)
    assert any("an hour after" in p for p in verify(tmp_path)["problems"])


def test_duplicate_bet_ids_are_flagged(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    bet(book)
    book.anchor(None)
    assert any("appears twice" in p for p in verify(tmp_path)["problems"])


def test_outcomes_must_come_after_the_seal_and_follow_from_the_forecast(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    book.anchor(None)
    outcome(book, mjd=61340.72)
    assert any("before its bet was sealed" in p for p in verify(tmp_path)["problems"])
    book.path.write_text("\n".join(book.path.read_text().splitlines()[:-1]) + "\n")
    outcome(book)
    assert verify(tmp_path)["passes"]
    forged = json.loads(book.path.read_text().splitlines()[-1])
    book.path.write_text("\n".join(book.path.read_text().splitlines()[:-1]) + "\n")
    book.append("outcome", {k: v for k, v in forged["payload"].items()} | {"log_score": 0.0})
    assert any("does not follow from the sealed forecast" in p for p in verify(tmp_path)["problems"])


def test_answers_are_recomputed_from_the_sealed_question(tmp_path):
    question = {"band": "ztfr", "mjd": 61341.3, "reference": 50.0, "p_yes": 0.2}
    book = Ledger(tmp_path)
    bet(book, question=question)
    book.anchor(None)
    outcome(book, flux=48.0)
    book.append("answer", {"bet": "b1", "object": "ZTF26x", "mjd": 61341.2, "yes": True, "p_yes": 0.95,
                           "log_score": -0.05})
    assert any("does not follow from the sealed question" in p for p in verify(tmp_path)["problems"])


def test_rewritten_history_is_caught_with_a_known_head(tmp_path):
    book = Ledger(tmp_path)
    first = bet(book)
    book.anchor(None)
    assert verify(tmp_path, known=(f"0:{first['hash']}",))["passes"]
    assert any("rewritten" in p for p in verify(tmp_path, known=("0:" + "1" * 64,))["problems"])


def test_a_forged_receipt_is_caught(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    anchor = book.anchor(None)
    (tmp_path / anchor["payload"]["rfc3161"]).write_bytes(b"forged")
    assert any("RFC 3161" in p for p in verify(tmp_path)["problems"])


def test_an_altered_root_certificate_is_refused(tmp_path, monkeypatch):
    fake = tmp_path / "ca.pem"
    fake.write_text(ledger.TSA_CA.read_text() + "\n# one more root\n")
    monkeypatch.setattr(ledger, "TSA_CA", fake)
    with pytest.raises(RuntimeError):
        REAL_CHECK(tmp_path / "x.tsr", "0" * 64)


def test_anchor_is_skipped_when_nothing_is_new(tmp_path):
    book = Ledger(tmp_path)
    bet(book)
    assert book.anchor(None) is not None and book.anchor(None) is None
