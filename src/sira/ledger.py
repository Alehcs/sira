import decimal
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from astropy.time import Time

from .snapshot import code_version

GENESIS = "0" * 64
TSA = "https://freetsa.org/tsr"
# the authority's root ships with the code and is pinned whole, so no download can swap or extend it
TSA_CA = Path(__file__).parent / "freetsa_ca.pem"
TSA_CA_SHA256 = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
OTS = str(Path(sys.executable).parent / "ots")
FORMAT = 2  # entries from format 2 on are hashed as RFC 8785 JSON, which any language can rebuild


def _number(x) -> str:
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        raise ValueError("NaN and infinity cannot be hashed")
    if x == int(x) and abs(x) < 2 ** 53:
        return str(int(x))
    # Python's repr has the shortest round-trip digits, as ECMAScript does; only the layout differs
    mantissa, _, exp = repr(x).partition("e")
    if not exp:
        return mantissa
    e = int(exp)
    if -7 < e < 21:
        return format(decimal.Decimal(repr(x)), "f")
    return mantissa + "e" + ("+" if e > 0 else "-") + str(abs(e))


def jcs(v) -> str:
    if isinstance(v, np.generic):
        # numpy scalars print as np.float64(...); hash the plain number the file will hold
        v = v.item()
    if v is None or isinstance(v, bool):
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return _number(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(v[k]) for k in sorted(v)) + "}"
    raise TypeError(f"cannot hash a {type(v).__name__}")


def canonical(entry: dict) -> bytes:
    body = {k: v for k, v in entry.items() if k != "hash"}
    if body.get("v", 1) >= 2:
        return jcs(body).encode("utf-8")
    # format 1, kept so the first night's entries still verify
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
        entry = {"v": FORMAT, "seq": len(entries), "time": now or utcnow(), "kind": kind, "payload": payload,
                 "prev": entries[-1]["hash"] if entries else GENESIS}
        # plain JSON values only, so the file holds exactly what was hashed
        entry = json.loads(jcs(entry))
        entry["hash"] = digest(entry)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
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
        ok, when = check_rfc3161(tsr, head["hash"])
        if not ok:
            raise RuntimeError("the timestamp authority returned a receipt that does not verify")
        stamped = subprocess.run([OTS, "stamp", str(doc)], capture_output=True, text=True).returncode == 0
        run = os.environ.get("GITHUB_RUN_ID")
        repo = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}"
        return self.append("anchor", {"head": head["hash"], "seq": head["seq"], "tsa": TSA, "tsa_time": when,
                                      "rfc3161": f"receipts/{tsr.name}",
                                      "ots": f"receipts/{doc.name}.ots" if stamped else None,
                                      "code": os.environ.get("GITHUB_SHA") or code_version(),
                                      "run": f"{repo}/actions/runs/{run}" if run else None})


def rfc3161(c: httpx.Client, hex_digest: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        query = Path(tmp) / "q.tsq"
        subprocess.run(["openssl", "ts", "-query", "-digest", hex_digest, "-sha256", "-cert", "-out", str(query)],
                       check=True, capture_output=True)
        r = c.post(TSA, content=query.read_bytes(), headers={"Content-Type": "application/timestamp-query"})
        r.raise_for_status()
        return r.content


def check_rfc3161(tsr: Path, hex_digest: str) -> tuple[bool, str | None]:
    if hashlib.sha256(TSA_CA.read_bytes()).hexdigest() != TSA_CA_SHA256:
        raise RuntimeError("the bundled timestamp authority certificate was altered")
    if not tsr.exists():
        return False, None
    ok = subprocess.run(["openssl", "ts", "-verify", "-digest", hex_digest, "-in", str(tsr), "-CAfile", str(TSA_CA)],
                        capture_output=True, text=True).returncode == 0
    text = subprocess.run(["openssl", "ts", "-reply", "-in", str(tsr), "-text"], capture_output=True, text=True).stdout
    line = next((l for l in text.splitlines() if l.startswith("Time stamp:")), None)
    when = None
    if line:
        when = datetime.strptime(line.split(":", 1)[1].strip(), "%b %d %H:%M:%S %Y %Z")
        when = when.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    return ok, when


def ots_state(path: Path, hex_digest: str) -> str:
    if not path.exists():
        return "missing"
    info = subprocess.run([OTS, "info", str(path)], capture_output=True, text=True).stdout
    # a proof only counts if it was made for this exact document
    if f"File sha256 hash: {hex_digest}" not in info:
        return "mismatch"
    return "bitcoin" if "BitcoinBlockHeaderAttestation" in info else "pending"


def upgrade(root: Path) -> None:
    for proof in sorted((Path(root) / "receipts").glob("*.ots")):
        if ots_state(proof, proof.name.split(".")[0]) == "pending":
            subprocess.run([OTS, "upgrade", str(proof)], capture_output=True)
