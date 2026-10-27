import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from astropy.time import Time

from .fetch import get

GENESIS = "0" * 64
TSA = "https://freetsa.org/tsr"
TSA_CA = "https://freetsa.org/files/cacert.pem"
# pinned, so a swapped certificate can never vouch for a forged receipt
TSA_CA_SHA256 = "a6379e7cecc05faa3cbf076013d745e327bbbaa38c0b9af22469d4701d18aabc"
OTS = str(Path(sys.executable).parent / "ots")


def canonical(entry: dict) -> bytes:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(entry: dict) -> str:
    return hashlib.sha256(canonical(entry)).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mjd(iso: str) -> float:
    when = datetime.fromisoformat(iso).astimezone(timezone.utc).replace(tzinfo=None)
    return float(Time(when, scale="utc").mjd)


class Ledger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "ledger.jsonl"
        self.receipts = self.root / "receipts"

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, kind: str, payload: dict, now: str | None = None) -> dict:
        entries = self.entries()
        entry = {"seq": len(entries), "time": now or utcnow(), "kind": kind, "payload": payload,
                 "prev": entries[-1]["hash"] if entries else GENESIS}
        entry["hash"] = digest(entry)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        return entry

    def anchor(self, c: httpx.Client) -> dict | None:
        entries = self.entries()
        if not entries or entries[-1]["kind"] == "anchor":
            return None
        head = entries[-1]
        self.receipts.mkdir(parents=True, exist_ok=True)
        # the stamped document is the head entry itself, so its sha256 is the head hash
        doc = self.receipts / f"{head['hash']}.json"
        doc.write_bytes(canonical(head))
        tsr = self.receipts / f"{head['hash']}.tsr"
        tsr.write_bytes(rfc3161(c, head["hash"]))
        ok, when = check_rfc3161(c, tsr, head["hash"])
        if not ok:
            raise RuntimeError("the timestamp authority returned a receipt that does not verify")
        stamped = subprocess.run([OTS, "stamp", str(doc)], capture_output=True, text=True).returncode == 0
        return self.append("anchor", {"head": head["hash"], "seq": head["seq"], "tsa": TSA, "tsa_time": when,
                                      "rfc3161": f"receipts/{tsr.name}",
                                      "ots": f"receipts/{doc.name}.ots" if stamped else None})


def rfc3161(c: httpx.Client, hex_digest: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        query = Path(tmp) / "q.tsq"
        subprocess.run(["openssl", "ts", "-query", "-digest", hex_digest, "-sha256", "-cert", "-out", str(query)],
                       check=True, capture_output=True)
        r = c.post(TSA, content=query.read_bytes(), headers={"Content-Type": "application/timestamp-query"})
        r.raise_for_status()
        return r.content


def _tsa_ca(c: httpx.Client) -> bytes:
    pem = get(c, TSA_CA).content
    with tempfile.NamedTemporaryFile(suffix=".pem") as f:
        f.write(pem)
        f.flush()
        out = subprocess.run(["openssl", "x509", "-in", f.name, "-noout", "-fingerprint", "-sha256"],
                             capture_output=True, text=True).stdout
    if out.split("=")[-1].strip().replace(":", "").lower() != TSA_CA_SHA256:
        raise RuntimeError("the timestamp authority certificate does not match the pinned one")
    return pem


def check_rfc3161(c: httpx.Client, tsr: Path, hex_digest: str) -> tuple[bool, str | None]:
    with tempfile.NamedTemporaryFile(suffix=".pem") as ca:
        ca.write(_tsa_ca(c))
        ca.flush()
        ok = subprocess.run(["openssl", "ts", "-verify", "-digest", hex_digest, "-in", str(tsr), "-CAfile", ca.name],
                            capture_output=True, text=True).returncode == 0
    text = subprocess.run(["openssl", "ts", "-reply", "-in", str(tsr), "-text"], capture_output=True, text=True).stdout
    line = next((l for l in text.splitlines() if l.startswith("Time stamp:")), None)
    when = None
    if line:
        when = datetime.strptime(line.split(":", 1)[1].strip(), "%b %d %H:%M:%S %Y %Z")
        when = when.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    return ok, when


def ots_state(path: Path) -> str:
    if not path.exists():
        return "missing"
    info = subprocess.run([OTS, "info", str(path)], capture_output=True, text=True).stdout
    return "bitcoin" if "BitcoinBlockHeaderAttestation" in info else "pending"


def upgrade(root: Path) -> None:
    for proof in sorted((Path(root) / "receipts").glob("*.ots")):
        if ots_state(proof) == "pending":
            subprocess.run([OTS, "upgrade", str(proof)], capture_output=True)


def verify(root: Path, c: httpx.Client) -> dict:
    root, problems = Path(root), []
    entries = Ledger(root).entries()
    prev = GENESIS
    for i, e in enumerate(entries):
        if e["seq"] != i or e["prev"] != prev or digest(e) != e["hash"]:
            problems.append(f"entry {i} breaks the chain")
        prev = e["hash"]
    sealed, ots = {}, {"bitcoin": 0, "pending": 0, "missing": 0}
    for a in (e for e in entries if e["kind"] == "anchor"):
        p = a["payload"]
        doc = root / "receipts" / f"{p['head']}.json"
        if p["seq"] >= len(entries) or entries[p["seq"]]["hash"] != p["head"]:
            problems.append(f"anchor {a['seq']} points at an entry that is not in the chain")
            continue
        if not doc.exists() or hashlib.sha256(doc.read_bytes()).hexdigest() != p["head"]:
            problems.append(f"anchor {a['seq']}: stamped document missing or altered")
        ok, when = check_rfc3161(c, root / p["rfc3161"], p["head"])
        if not ok:
            problems.append(f"anchor {a['seq']}: RFC 3161 receipt does not verify")
            continue
        sealed[p["seq"]] = when
        ots[ots_state(root / p["ots"]) if p.get("ots") else "missing"] += 1
    bets = {e["payload"]["bet"]: e for e in entries if e["kind"] == "bet"}
    seal = {}
    for bet_id, e in bets.items():
        # a bet is sealed by the first anchor that covers it
        times = [when for seq, when in sealed.items() if seq >= e["seq"]]
        seal[bet_id] = min(times, key=mjd) if times else None
    late = [o["seq"] for o in entries if o["kind"] == "outcome"
            and (seal.get(o["payload"]["bet"]) is None or o["payload"]["mjd"] <= mjd(seal[o["payload"]["bet"]]))]
    if late:
        problems.append(f"outcomes measured before their bet was sealed: {late[:5]}")
    n_sealed = sum(v is not None for v in seal.values())
    return {"entries": len(entries), "anchors": len(sealed), "bets": len(bets), "bets_sealed": n_sealed,
            "outcomes": sum(e["kind"] == "outcome" for e in entries), "ots": ots, "problems": problems,
            "passes": not problems and n_sealed == len(bets)}
