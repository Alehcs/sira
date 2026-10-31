import hashlib
import json
from pathlib import Path

from . import alerce, reader
from .gallery import flat, strip
from .ledger import Ledger
from .snapshot import split

SKIP = {"ZTF19aavisrq"}  # the Lab tells its whole story
TEXT = "Brighter in r three days from now than at its last r detection?"
TRIES = 5  # early detections asked for stamps before an object is left out
PATH = "replays/practice/"  # where the images sit, from the site's root


def _stamps(c, root: Path, obj: dict, before: float) -> list[bytes] | None:
    # stamps in hand by the first question: the snapshot's, or the archive's for an earlier detection it never flagged
    first = obj.get("first_stamps") or {}
    if first.get("files") and first["available_at"] <= before:
        return [(root / f).with_suffix(".fits").read_bytes() for f in first["files"]]
    early = sorted((r for r in obj["photometry"] if r["kind"] == "det" and r.get("candid") and r["available_at"] <= before),
                   key=lambda r: r["mjd"])
    for r in early[:TRIES]:
        try:
            return [alerce.stamp(c, obj["oid"], r["candid"], k) for k in reader.KINDS]
        except Exception:
            continue
    return None


def _save(folder: Path, data: bytes, suffix: str) -> str:
    # named by content, so a file says nothing of the object it shows
    name = hashlib.sha256(data).hexdigest()[:16] + suffix
    (folder / name).write_bytes(data)
    return PATH + name


def bank(replays: Path, root: Path, out: Path, c=None) -> dict:
    # replayed questions SIRA already answered, asked with nothing that names the object or its dates
    truth = json.loads((root / "truth.json").read_text())
    folder = out / "practice"
    folder.mkdir(parents=True, exist_ok=True)
    for old in [*folder.glob("*.png"), *folder.glob("*.jpg")]:
        old.unlink()
    # a fixed shuffle, so the order says nothing of when each object was found
    oids = sorted((p.name for p in replays.iterdir() if (p / "ledger.jsonl").exists() and p.name not in SKIP),
                  key=lambda o: hashlib.sha256(f"practice:{o}".encode()).hexdigest())
    questions, reveal = [], []
    for oid in oids:
        if split(oid) != "dev":
            raise ValueError(f"{oid} is in the test split")
        entries = Ledger(replays / oid).entries()
        bets = {e["payload"]["bet"]: e["payload"] for e in entries if e["kind"] == "bet"}
        outcomes = [e["payload"] for e in entries if e["kind"] == "outcome"]
        answers = [e["payload"] for e in entries if e["kind"] == "answer"]
        asked = sorted(((bets[a["bet"]], a) for a in answers if a.get("which", "question") == "question" and not a.get("void")
                        and not bets[a["bet"]].get("dropped") and (bets[a["bet"]].get("question") or {}).get("text") == TEXT),
                       key=lambda ba: ba[0]["made_at"])
        if not asked:
            continue
        obj = json.loads((root / "objects" / f"{oid}.json").read_text())
        fits = _stamps(c, root, obj, asked[0][0]["made_at"])
        if fits is None:
            continue
        png, panel = strip(fits)
        stamps = _save(folder, png, ".png")
        group = len(reveal) + 1
        for step, (b, a) in enumerate(asked, 1):
            t, q = b["made_at"], b["question"]
            mine = sorted((o for o in outcomes if o["bet"] == b["bet"]), key=lambda o: o["mjd"])
            after = [[round(o["mjd"] - t, 3), o["band"][-1], o["kind"], o.get("flux", o.get("limit")), o.get("flux_err")]
                     for o in mine]
            settled = next(r for r, o in zip(after, mine) if o["band"] == q["band"] and abs(o["mjd"] - a["mjd"]) < 1e-6)
            questions.append({"label": len(questions) + 1, "group": group, "step": step,
                              "ask": {"seen": [[round(r[0] - t, 3), r[1][-1], r[2], r[3], r[4]] for r in b["seen"]],
                                      "kind": "last", "direction": "above", "band": q["band"][-1],
                                      "reference": round(q["reference"], 1), "days": round(q["mjd"] - t),
                                      "stamps": stamps, "panel": panel},
                              "answer": {"yes": a["yes"], "sira": q["p_yes"], "log_score": a["log_score"],
                                         "settled": settled, "after": after, "class": truth[oid]["type"]}})
        host = obj.get("host") or {}
        jpg = (root / host["file"]).read_bytes() if host.get("file") and host.get("predates_event") else None
        reveal.append({"group": group, "object": oid, "alerce": f"https://alerce.online/object/{oid}",
                       "host": _save(folder, jpg, ".jpg") if jpg and not flat(jpg) else None})
    data = {"questions": questions, "reveal": reveal}
    (out / "practice.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    return data
