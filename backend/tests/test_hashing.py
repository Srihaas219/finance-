from datetime import date
from decimal import Decimal

from app.core.hashing import canonical_json, hash_record, sha256_hex


def test_canonical_json_key_order_independent():
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"c": {"x": 2, "y": 1}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_hash_record_reproducible():
    rec = {"loan_id": "L1", "balance": Decimal("1200.50"), "orig": date(2021, 3, 1)}
    assert hash_record(rec) == hash_record(dict(reversed(list(rec.items()))))


def test_decimal_normalization():
    # 1.50 and 1.5 must hash identically.
    assert hash_record({"x": Decimal("1.50")}) == hash_record({"x": Decimal("1.5")})


def test_sha256_known_value():
    assert sha256_hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
