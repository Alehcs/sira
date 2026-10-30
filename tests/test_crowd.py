import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pytest
import sncosmo
from astropy.cosmology import Planck18

from sira import agents, catalogs, crowd, ledger, live, team, verify
from sira.ledger import Ledger, mjd
from sira.models import M_B

MASTER = "11" * 32
OPEN = datetime(2026, 11, 2, 13, 20, tzinfo=timezone.utc)
OPEN_MJD = mjd(OPEN.isoformat())


def iso(t: float) -> str:
    from astropy.time import Time
    return Time(t, format="mjd").to_datetime().replace(microsecond=0).isoformat() + "+00:00"


def sn_object(now=OPEN_MJD):
    m = sncosmo.Model(source="salt3")
    m.set(z=0.04, t0=now + 2, x1=0.0, c=0.0)
    m.set_source_peakabsmag(M_B, "bessellb", "ab", cosmo=Planck18)
    rng, rows = np.random.default_rng(0), []
    for t in np.arange(now - 18, now, 1.5):
        for band in ("ztfg", "ztfr"):
            f = float(m.bandflux(band, t, zp=23.9, zpsys="ab"))
            rows.append({"mjd": float(t), "band": band, "kind": "det", "flux": f + rng.normal(0, 0.03 * f + 2),
                         "flux_err": 0.03 * f + 2, "mag": 19.0, "available_at": float(t) + 0.5})
    return {"oid": "ZTF26crowd", "survey": "ztf", "ra": 150.0, "dec": 20.0, "photometry": rows}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    # receipts carry the moment they were stamped, as real ones do
    clock = {"iso": iso(OPEN_MJD - 0.4)}
    stamp = lambda c, h: f"{clock['iso']}|{h}".encode()
    check = lambda path, h: (path.exists() and path.read_bytes().decode().endswith(h), path.read_bytes().decode().split("|")[0])
    monkeypatch.setattr(ledger, "rfc3161", stamp)
    monkeypatch.setattr(ledger, "check_rfc3161", check)
    monkeypatch.setattr(verify, "check_rfc3161", check)
    monkeypatch.setattr(ledger, "OTS", "true")
    monkeypatch.setenv("SIRA_ENVELOPE_KEY", MASTER)
    monkeypatch.setattr(crowd, "_supabase", lambda: ("https://example.supabase.co", {}))
    obj = sn_object()
    monkeypatch.setattr(live, "observe", lambda c, oid, now: obj)
    monkeypatch.setattr(catalogs, "mw_ebv", lambda c, ra, dec: 0.02)
    monkeypatch.setattr(team, "eyes", lambda llm, c, views, pool: ({}, []))
    monkeypatch.setattr(agents, "llm_only", lambda llm, case, days, bands: ({"points": {}, "classes": {}}, {}))

    def investigate(llm, view, ebv, pool, seniors, reading=None, adopted=None, alone=None):
        said = {"role": "director", "model": "muse-spark-1.3", "effort": "xhigh", "cost_usd": 0.02, "seconds": 3.0,
                "case": "case-x", "decision": "bet q0", "why": "it is very likely to fade"}
        return live.forecast(view, ebv), [said]

    monkeypatch.setattr(team, "investigate", investigate)
    book = Ledger(tmp_path)
    book.append("bet", {"bet": "ZTF26crowd-1", "object": "ZTF26crowd", "model": "v1", "made_at": OPEN_MJD - 0.41,
                        "n_points": 24, "forecasts": []})
    book.anchor(None)
    return {"book": book, "clock": clock, "obj": obj, "root": tmp_path}


def opened(lab):
    lab["clock"]["iso"] = OPEN.isoformat()
    with ThreadPoolExecutor(2) as pool:
        return crowd.open_round(lab["book"], None, None, OPEN, pool)


def closed(lab, monkeypatch, bets):
    monkeypatch.setattr(crowd, "fetch_bets", lambda c, ids: bets)
    lab["clock"]["iso"] = "2026-11-02T21:30:00+00:00"
    return crowd.close_rounds(lab["book"], None, mjd("2026-11-02T21:30:00+00:00"))


def human(user, p, when, q="2026-11-02-1"):
    return {"question_id": q, "user_id": user, "handle": f"player {user}", "p_yes": p, "created_at": when}


def test_an_envelope_opens_only_with_its_own_answer():
    master = bytes.fromhex(MASTER)
    sealed = crowd.envelope(master, "2026-11-02-1", 0.266)
    q = {"id": "2026-11-02-1", "commit": sealed["commit"], "sealed": sealed["sealed"]}
    answer = {"id": q["id"], "p_yes": 0.266, "salt": sealed["salt"], "key": sealed["key"]}
    assert crowd.opens(q, answer) and crowd.unseal(master, q) == answer
    assert not crowd.opens(q, answer | {"p_yes": 0.734})
    assert not crowd.opens(q, answer | {"salt": "00" * 32})
    assert "0.266" not in json.dumps(q)


def test_a_round_seals_answers_then_closes_scores_and_verifies(lab, monkeypatch):
    result = opened(lab)
    assert result["questions"] == ["2026-11-02-1"]
    book = lab["book"]
    entries = book.entries()
    rnd = next(e for e in entries if e["kind"] == "round")["payload"]
    q = rnd["questions"][0]
    assert {"commit", "sealed", "seen"} <= set(q) and "p_yes" not in q
    said = [e["payload"] for e in entries if e["kind"] == "event"]
    assert said and all("why" not in e and "decision" not in e for e in said)
    monkeypatch.setattr(crowd, "publish", lambda c, payload: len(payload["questions"]))
    assert crowd.publish_round(book, None, OPEN.replace(minute=30))["published"] == 1
    new = closed(lab, monkeypatch, [human("a", 0.70, "2026-11-02T15:00:00.123+00:00"),
                                    human("b", 0.20, "2026-11-02T18:00:00+00:00"),
                                    human("c", 0.90, "2026-11-02T21:05:00+00:00"),
                                    human("a", 0.10, "2026-11-02T16:00:00+00:00")])
    assert [e["kind"] for e in new] == ["crowd", "anchor", "reveal"]
    kept = new[0]["payload"]["bets"]
    assert [b["handle"] for b in kept] == ["player a", "player b"]
    sira = new[2]["payload"]["answers"][0]["p_yes"]
    after = q["mjd"] + 0.2
    later = dict(lab["obj"], photometry=lab["obj"]["photometry"] + [
        {"mjd": after, "band": "ztfr", "kind": "det", "flux": 2 * q["reference"], "flux_err": 3.0, "mag": 18.0,
         "available_at": after + 0.5}])
    monkeypatch.setattr(live, "observe", lambda c, oid, now: later)
    lab["clock"]["iso"] = iso(q["mjd"] + 2.01)
    scored = crowd.score_rounds(book, None, q["mjd"] + 2)
    p = scored[0]["payload"]
    assert p["yes"] is True and p["mjd"] == after
    assert p["scores"]["sira"] == round(math.log(sira), 4)
    assert p["scores"]["crowd"] == round(math.log(0.45), 4)
    assert p["scores"]["sira_crowd"] == round(math.log((sira + 0.45) / 2), 4)
    assert set(p["scores"]["players"]) == {crowd.player("a"), crowd.player("b")}
    book.anchor(None)
    report = verify.verify(lab["root"])
    assert report["passes"], report["problems"]
    assert (report["rounds"], report["crowd_bets"], report["crowd_answers"]) == (1, 2, 1)
    forged = p | {"scores": p["scores"] | {"crowd": -0.01}}
    book.append("crowd_answer", forged)
    assert any("does not follow" in x or "second one" in x for x in verify.verify(lab["root"])["problems"])


def test_a_tampered_reveal_fails_verify(lab, monkeypatch):
    opened(lab)
    book = lab["book"]
    monkeypatch.setattr(crowd, "fetch_bets", lambda c, ids: [])
    monkeypatch.setattr(crowd, "unseal", lambda master, q: {"id": q["id"], "p_yes": 0.5, "salt": "00" * 32,
                                                            "key": "00" * 32})
    lab["clock"]["iso"] = "2026-11-02T21:30:00+00:00"
    crowd.close_rounds(book, None, mjd("2026-11-02T21:30:00+00:00"))
    book.anchor(None)
    problems = verify.verify(lab["root"])["problems"]
    assert any("does not open its sealed envelope" in x for x in problems)


def test_a_reveal_before_the_bell_is_caught(lab, monkeypatch):
    opened(lab)
    book = lab["book"]
    q = book.entries()[-2]["payload"]["questions"][0]
    book.append("crowd", {"round": "2026-11-02", "bets": []})
    book.append("reveal", {"round": "2026-11-02", "answers": [crowd.unseal(bytes.fromhex(MASTER), q)]})
    lab["clock"]["iso"] = "2026-11-02T14:00:00+00:00"
    book.anchor(None)
    problems = verify.verify(lab["root"])["problems"]
    assert any("sealed before the bell" in x for x in problems)
    assert any("after the bell" in x for x in problems)


def test_no_round_opens_or_publishes_after_half_past_eight_utc(lab, monkeypatch):
    late = OPEN.replace(hour=20, minute=31)
    with ThreadPoolExecutor(1) as pool:
        assert "too late" in crowd.open_round(lab["book"], None, None, late, pool)["skipped"]
    assert not [e for e in lab["book"].entries() if e["kind"] == "round"]
    opened(lab)
    monkeypatch.setattr(crowd, "publish", lambda c, payload: pytest.fail("published after 20:30"))
    assert "too late" in crowd.publish_round(lab["book"], None, late)["skipped"]


def test_a_round_that_cannot_be_stamped_is_taken_back(lab, monkeypatch):
    def down(c, h):
        raise RuntimeError("timestamp authority down")

    monkeypatch.setattr(ledger, "rfc3161", down)
    before = lab["book"].path.read_bytes()
    with pytest.raises(RuntimeError):
        opened(lab)
    assert lab["book"].path.read_bytes() == before


def test_scores_compare_sira_the_crowd_and_both():
    bets = [{"player": "a", "p_yes": 0.6}, {"player": "b", "p_yes": 0.2}]
    s = crowd.scores(0.8, bets, True)
    assert s == {"sira": round(math.log(0.8), 4), "crowd": round(math.log(0.4), 4),
                 "sira_crowd": round(math.log(0.6), 4),
                 "players": {"a": round(math.log(0.6), 4), "b": round(math.log(0.2), 4)}}
    assert crowd.scores(0.8, [], False) == {"sira": round(math.log(0.2), 4), "crowd": None, "sira_crowd": None,
                                            "players": {}}
