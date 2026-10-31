import json
import re
from pathlib import Path

import pytest

from sira import alerce, practice, reader
from sira.firewall import case_id
from sira.ledger import Ledger
from sira.snapshot import split

PUBLIC = Path(__file__).parents[1] / "site" / "public"
SNAPSHOT = Path(__file__).parents[1] / "data" / "snapshot"
ASK = {"seen", "kind", "direction", "band", "reference", "days", "stamps", "panel"}
EARLY, LATE, NONE = "ZTF25aazqavg", "ZTF25ablgkgi", "ZTF25ablvccx"  # all three in the dev split


def cutout(kind, oid="ZTF25acfgotd"):
    return (reader.PACKAGED / f"{oid}_{kind}.fits.gz").read_bytes()


def chunks(png: bytes) -> list[str]:
    out, i = [], 8
    while i < len(png):
        out.append(png[i + 4:i + 8].decode())
        i += 12 + int.from_bytes(png[i:i + 4], "big")
    return out


def leaks(ask: dict, words: list[str]) -> None:
    # nothing a search engine could take back to the object: no name, case id, date, MJD, candid or position field
    assert set(ask) == ASK and re.fullmatch(r"replays/practice/[0-9a-f]{16}\.png", ask["stamps"])
    text = json.dumps(ask).replace(ask["stamps"], "")
    assert "ZTF" not in text and "case-" not in text and not any(w in text for w in words)
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
    assert max(abs(float(x)) for x in re.findall(r"-?\d+(?:\.\d+)?", text)) < 40000
    assert all(len(r) == 5 and -1000 < r[0] <= 0 and r[1] in ("g", "r") and r[2] in ("det", "limit") for r in ask["seen"])


def snapshot_object(root: Path, oid: str, stamps_at: float, early: list[float]) -> None:
    folder = root / "stamps" / oid
    folder.mkdir(parents=True)
    for kind in reader.KINDS:
        (folder / f"first_{kind}.fits").write_bytes(cutout(kind))
    rows = [{"mjd": m, "band": "ztfr", "kind": "det", "candid": f"{int(m * 1000)}", "stamp": False, "available_at": m + 0.5}
            for m in early]
    obj = {"oid": oid, "ra": 123.456789, "dec": -12.345678, "photometry": rows,
           "first_stamps": {"candid": "9" * 18, "mjd": stamps_at, "available_at": stamps_at + 0.5,
                            "files": [f"stamps/{oid}/first_{k}.png" for k in reader.KINDS]},
           "host": {"file": None, "predates_event": True}}
    (root / "objects").mkdir(exist_ok=True)
    (root / "objects" / f"{oid}.json").write_text(json.dumps(obj))


def replay(root: Path, oid: str, times: list[float], skip_extra: bool = False) -> None:
    book = Ledger(root / oid)
    for k, t in enumerate(times):
        bet = f"{oid}-{t:.2f}"
        q = {"text": practice.TEXT, "band": "ztfr", "mjd": t + 3, "reference": 50.0 + k, "direction": "above", "p_yes": 0.3}
        seen = [[t - 30 + i, "ztfr" if i % 2 else "ztfg", "det", 40.0 + i, 2.0] for i in range(4 + k)]
        book.append("bet", {"bet": bet, "object": oid, "model": "v1", "made_at": t, "seen": seen, "question": q,
                            "risky": {"id": "q1", "text": "Fainter than 40 microjansky in r 2 days from now?"}})
        book.append("outcome", {"bet": bet, "object": oid, "mjd": t + 1.2, "band": "ztfg", "kind": "limit", "limit": 30.0})
        book.append("outcome", {"bet": bet, "object": oid, "mjd": t + 2.6, "band": "ztfr", "kind": "det", "flux": 61.0,
                                "flux_err": 2.5})
        book.append("answer", {"bet": bet, "object": oid, "which": "question", "yes": k % 2 == 0, "mjd": t + 2.6,
                               "p_yes": 0.3, "log_score": -1.2})
        book.append("answer", {"bet": bet, "object": oid, "which": "risky", "yes": True, "mjd": t + 2.6, "p_yes": 0.5,
                               "log_score": -0.7})
    if skip_extra:
        # a dropped bet and a void answer never reach the bank
        t = times[-1] + 5
        for bet, extra, answer in [(f"{oid}-drop", {"dropped": True}, {"yes": True}), (f"{oid}-void", {}, {"void": True})]:
            q = {"text": practice.TEXT, "band": "ztfr", "mjd": t + 3, "reference": 50.0, "direction": "above", "p_yes": 0.3}
            book.append("bet", {"bet": bet, "object": oid, "model": "v1", "made_at": t, "seen": [], "question": q} | extra)
            book.append("answer", {"bet": bet, "object": oid, "which": "question", "mjd": t + 2.6, "p_yes": 0.3,
                                   "log_score": -0.3} | answer)


@pytest.fixture
def made(tmp_path, monkeypatch):
    root, replays = tmp_path / "snapshot", tmp_path / "replays"
    root.mkdir()
    (root / "truth.json").write_text(json.dumps({o: {"type": "SN Ia"} for o in (EARLY, LATE, NONE, "ZTF19aavisrq")}))
    snapshot_object(root, EARLY, 60800.0, [])
    snapshot_object(root, LATE, 60900.0, [60700.0, 60701.0])
    snapshot_object(root, NONE, 60900.0, [])
    snapshot_object(root, "ZTF19aavisrq", 60000.0, [])
    replay(replays, EARLY, [60810.0, 60815.0], skip_extra=True)
    replay(replays, LATE, [60720.0, 60730.0, 60740.0])
    replay(replays, NONE, [60720.0])
    replay(replays, "ZTF19aavisrq", [60010.0])
    asked = []

    def stamp(c, oid, candid, kind):
        asked.append((oid, candid))
        if candid == "60700000":
            raise RuntimeError("not in the archive")
        return cutout(kind, "ZTF24abyaspl")

    monkeypatch.setattr(alerce, "stamp", stamp)
    data = practice.bank(replays, root, tmp_path / "out")
    return {"data": data, "asked": asked, "out": tmp_path / "out"}


def test_the_bank_asks_only_settled_standard_questions_in_checkpoint_order(made):
    data = made["data"]
    assert sorted(r["object"] for r in data["reveal"]) == sorted([EARLY, LATE])
    by = {r["group"]: r["object"] for r in data["reveal"]}
    steps = [(by[q["group"]], q["step"], q["ask"]["reference"]) for q in data["questions"]]
    assert sorted(steps) == [(EARLY, 1, 50.0), (EARLY, 2, 51.0), (LATE, 1, 50.0), (LATE, 2, 51.0), (LATE, 3, 52.0)]
    assert [q["label"] for q in data["questions"]] == [1, 2, 3, 4, 5]
    assert [q["step"] for q in data["questions"] if by[q["group"]] == LATE] == [1, 2, 3]
    q = next(q for q in data["questions"] if by[q["group"]] == LATE and q["step"] == 2)
    assert q["ask"]["seen"][0] == [-30.0, "g", "det", 40.0, 2.0] and q["ask"]["days"] == 3 and q["ask"]["band"] == "r"
    assert q["answer"] == {"yes": False, "sira": 0.3, "log_score": -1.2, "settled": [2.6, "r", "det", 61.0, 2.5],
                           "after": [[1.2, "g", "limit", 30.0, None], [2.6, "r", "det", 61.0, 2.5]], "class": "SN Ia"}


def test_stamps_come_from_before_the_first_question_or_the_object_is_left_out(made):
    # EARLY's snapshot stamps predate its questions; LATE's do not, so the archive gives an earlier detection's
    # stamps, skipping one it does not keep; NONE has nothing earlier, so it is left out
    assert made["asked"] == [(LATE, "60700000"), (LATE, "60701000"), (LATE, "60701000"), (LATE, "60701000")]
    names = {r["group"]: r["object"] for r in made["data"]["reveal"]}
    files = {names[q["group"]]: q["ask"]["stamps"] for q in made["data"]["questions"]}
    assert files[EARLY] != files[LATE] and all((made["out"] / f.removeprefix("replays/")).exists() for f in files.values())


def test_nothing_in_a_question_names_its_object(made):
    names = [r["object"] for r in made["data"]["reveal"]]
    for q in made["data"]["questions"]:
        leaks(q["ask"], names + [case_id(o) for o in names] + ["123.4567", "-12.3456", "9" * 18, "60700000"])
    for png in (made["out"] / "practice").glob("*.png"):
        assert set(chunks(png.read_bytes())) <= {"IHDR", "IDAT", "IEND"}


def test_an_object_from_the_test_split_stops_the_bank(tmp_path):
    oid = next(f"ZTF25aaaaa{a}{b}" for a in "abcdefgh" for b in "abcdefgh" if split(f"ZTF25aaaaa{a}{b}") == "test")
    (tmp_path / "snapshot").mkdir()
    (tmp_path / "snapshot" / "truth.json").write_text("{}")
    replay(tmp_path / "replays", oid, [60720.0])
    with pytest.raises(ValueError, match="test split"):
        practice.bank(tmp_path / "replays", tmp_path / "snapshot", tmp_path / "out")


def test_the_published_bank_names_nothing_before_the_reveal():
    data = json.loads((PUBLIC / "replays" / "practice.json").read_text())
    by = {r["group"]: r["object"] for r in data["reveal"]}
    names = list(by.values())
    assert names and all(split(o) == "dev" for o in names) and "ZTF19aavisrq" not in names
    assert [q["label"] for q in data["questions"]] == list(range(1, len(data["questions"]) + 1))
    for g in {q["group"] for q in data["questions"]}:
        mine = [q for q in data["questions"] if q["group"] == g]
        # one object's checkpoints come together and in order, each having seen at least what the one before saw
        assert [q["step"] for q in mine] == list(range(1, len(mine) + 1))
        assert [q["label"] for q in mine] == list(range(mine[0]["label"], mine[0]["label"] + len(mine)))
        dets = [sum(r[2] == "det" for r in q["ask"]["seen"]) for q in mine]
        assert dets == sorted(dets)
    for q in data["questions"]:
        words = names + [case_id(o) for o in names]
        # where the snapshot is at hand, the object's own position and candids are checked too
        obj = SNAPSHOT / "objects" / f"{by[q['group']]}.json"
        if obj.exists():
            o = json.loads(obj.read_text())
            words += [f"{o['ra']:.4f}", f"{o['dec']:.4f}"] + [r["candid"] for r in o["photometry"] if r.get("candid")]
        leaks(q["ask"], words)
        assert set(q["answer"]) == {"yes", "sira", "log_score", "settled", "after", "class"}
        assert set(chunks((PUBLIC / q["ask"]["stamps"]).read_bytes())) <= {"IHDR", "IDAT", "IEND"}
