import hashlib
import subprocess
from pathlib import Path

from . import ledger
from .fetch import client


def stamp(path: Path) -> dict:
    # a plan counts from the time FreeTSA signed its sha256, and Bitcoin later backs the same hash
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    tsr = path.with_name(path.name + ".tsr")
    tsr.write_bytes(ledger.rfc3161(client(), digest))
    ok, when = ledger.check_rfc3161(tsr, digest)
    if not ok:
        raise RuntimeError("the timestamp authority returned a receipt that does not verify")
    stamped = subprocess.run([ledger.OTS, "stamp", str(path)], capture_output=True, text=True).returncode == 0
    return {"sha256": digest, "tsa_time": when, "rfc3161": tsr.name, "ots": path.name + ".ots" if stamped else None}


def stamped(path: Path) -> dict:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ok, when = ledger.check_rfc3161(path.with_name(path.name + ".tsr"), digest)
    return {"sha256": digest, "valid": ok, "tsa_time": when,
            "ots": ledger.ots_state(path.with_name(path.name + ".ots"), digest)}
