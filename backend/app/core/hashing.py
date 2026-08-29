"""Canonical, reproducible hashing used for file/row/verified-record hashes (ADR-007).

A single canonicalization function guarantees every layer hashes identically, so a
judge can recompute any hash from the stored data.
"""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _canonical(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    if isinstance(obj, Decimal):
        # Normalize so 1.50 and 1.5 hash identically.
        return format(obj.normalize(), "f")
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace, normalized scalars."""
    return json.dumps(_canonical(obj), separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_record(obj: Any) -> str:
    """SHA-256 over the canonical JSON of a record (dict/list/scalars)."""
    return sha256_hex(canonical_json(obj))
