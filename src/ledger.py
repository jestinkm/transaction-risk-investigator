"""
A local, append-only, hash-chained audit ledger for investigation reports.

This is deliberately NOT a distributed blockchain — the hackathon rules say
Gemini is the only thing allowed to touch the network, so there is no
consensus, no mining, no external chain. What it *does* borrow from
blockchain design is the core integrity trick: every entry embeds the hash
of the entry before it, so if anyone edits a past report after the fact,
recomputing the chain from genesis will no longer match the stored hashes
and `verify_chain()` will say exactly where it broke. For a fraud desk,
that's the actually useful property — an investigation trail that can prove
it hasn't been quietly altered.

Storage is a single append-only JSON Lines file so it's trivial to inspect,
diff, or ship, and it self-heals with a genesis block if the file is missing.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ledger.jsonl")
GENESIS_HASH = "0" * 64


def _hash_report(report: dict) -> str:
    canonical = json.dumps(report, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_entry(index: int, timestamp: str, customer_id: str, report_hash: str, prev_hash: str) -> str:
    payload = f"{index}|{timestamp}|{customer_id}|{report_hash}|{prev_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_all():
    if not os.path.exists(LEDGER_PATH):
        return []
    entries = []
    with open(LEDGER_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_entry(customer_id: str, report: dict) -> dict:
    """Seals `report` into the ledger and returns the new entry (without the
    full report body — just enough to prove it was recorded and where)."""
    entries = _read_all()
    prev_hash = entries[-1]["entry_hash"] if entries else GENESIS_HASH
    index = len(entries)
    timestamp = datetime.now(timezone.utc).isoformat()
    report_hash = _hash_report(report)
    entry_hash = _hash_entry(index, timestamp, customer_id, report_hash, prev_hash)

    entry = {
        "index": index,
        "timestamp": timestamp,
        "customer_id": customer_id,
        "report_hash": report_hash,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
    }
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def get_chain(limit: int = 25) -> list:
    entries = _read_all()
    return entries[-limit:]


def verify_chain() -> dict:
    """Recomputes every entry_hash from scratch and compares against what's
    stored. Returns {valid, length, broken_at} — broken_at is the first
    index where the recomputed hash doesn't match, or None if the whole
    chain checks out."""
    entries = _read_all()
    prev_hash = GENESIS_HASH
    for entry in entries:
        expected = _hash_entry(
            entry["index"], entry["timestamp"], entry["customer_id"],
            entry["report_hash"], prev_hash,
        )
        if expected != entry["entry_hash"] or entry["prev_hash"] != prev_hash:
            return {"valid": False, "length": len(entries), "broken_at": entry["index"]}
        prev_hash = entry["entry_hash"]
    return {"valid": True, "length": len(entries), "broken_at": None}
