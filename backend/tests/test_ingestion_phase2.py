"""Phase 2 hardening: atomicity, hash reproducibility, large fixture, empty file,
full RBAC, immutability across re-upload, duplicate full rows."""
import io
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.hashing import sha256_hex
from tests.conftest import auth
from tests.test_ingestion import _csv, _row, _upload

REPO_ROOT = Path(__file__).resolve().parents[2]
LOAN_TAPE = REPO_ROOT / "data" / "raw" / "loan_tape.csv"


def test_empty_file_rejected(client, login):
    token = login(client, "operator@loantrust.demo", "operator123")
    r = client.post("/uploads", headers=auth(token),
                    files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")})
    assert r.status_code == 400


def test_consumer_cannot_upload(client, login):
    # Completes the RBAC matrix for uploads (operator only).
    r = _upload(client, login, _csv(_row()), role=("consumer@loantrust.demo", "consumer123"))
    assert r.status_code == 403


def test_file_hash_reproducible(client, login):
    content = _csv(_row("HASH1"), _row("HASH2"))
    body = _upload(client, login, content).json()
    # The stored hash must equal an independently-computed SHA-256 of the exact bytes.
    assert body["file_hash"] == sha256_hex(content)
    assert len(body["file_hash"]) == 64


def test_rollback_on_failure_is_atomic(client, login, monkeypatch):
    """If normalization raises mid-import, NOTHING is persisted (single-txn atomicity)."""
    from app.core.db import SessionLocal
    from app.ingestion import service
    from app.models.raw_record import RawRecord
    from app.models.source_file import SourceFile

    real = service.normalize_row_full
    calls = {"n": 0}

    def boom(raw):
        calls["n"] += 1
        if calls["n"] >= 2:  # fail on the 2nd row, after row 1 was already flushed
            raise RuntimeError("injected failure")
        return real(raw)

    monkeypatch.setattr(service, "normalize_row_full", boom)

    db = SessionLocal()
    before_files = db.scalar(select(func.count()).select_from(SourceFile))
    before_raw = db.scalar(select(func.count()).select_from(RawRecord))
    with pytest.raises(RuntimeError):
        service.ingest_csv(
            db, filename="rollback.csv", content=_csv(_row("R1"), _row("R2"), _row("R3")),
            uploaded_by_id="u-operator", uploaded_by_role="data_operator",
        )
    db.rollback()
    after_files = db.scalar(select(func.count()).select_from(SourceFile))
    after_raw = db.scalar(select(func.count()).select_from(RawRecord))
    db.close()
    assert after_files == before_files, "source_file must not persist on failed import"
    assert after_raw == before_raw, "raw_records must not persist on failed import"


def test_raw_immutable_across_reupload(client, login):
    content = _csv(_row("IMM1"), _row("IMM2"))
    first = _upload(client, login, content).json()

    from app.core.db import SessionLocal
    from app.models.raw_record import RawRecord

    db = SessionLocal()
    raw_before = db.scalars(
        select(RawRecord).where(RawRecord.source_file_id == first["id"]).order_by(RawRecord.row_number)
    ).all()
    snapshot = [(r.row_number, r.row_hash, dict(r.raw_payload)) for r in raw_before]
    db.close()

    # Re-upload identical content -> duplicate; original raw evidence must be untouched.
    dup = _upload(client, login, content).json()
    assert dup["duplicate"] is True

    db = SessionLocal()
    raw_after = db.scalars(
        select(RawRecord).where(RawRecord.source_file_id == first["id"]).order_by(RawRecord.row_number)
    ).all()
    after = [(r.row_number, r.row_hash, dict(r.raw_payload)) for r in raw_after]
    # No new raw rows attached to the duplicate upload id.
    dup_raw = db.scalar(select(func.count()).select_from(RawRecord).where(RawRecord.source_file_id == dup["id"]))
    db.close()
    assert after == snapshot, "original raw records must be byte-identical after a re-upload"
    assert dup_raw == 0, "duplicate upload must not create new raw evidence"


def test_duplicate_full_rows_within_file_are_preserved(client, login):
    # Two identical data rows -> two raw records with the SAME row_hash (dupes are data, kept).
    dup_row = _row("SAMELOAN", borrower_id="SAMEB")
    body = _upload(client, login, _csv(dup_row, dup_row)).json()
    assert body["imported_count"] == 2
    from app.core.db import SessionLocal
    from app.models.raw_record import RawRecord
    db = SessionLocal()
    hashes = db.scalars(
        select(RawRecord.row_hash).where(RawRecord.source_file_id == body["id"])
    ).all()
    db.close()
    assert len(hashes) == 2 and hashes[0] == hashes[1]


@pytest.mark.skipif(not LOAN_TAPE.exists(), reason="synthetic dataset not generated")
def test_large_fixture_1000_rows(client, login):
    content = LOAN_TAPE.read_bytes()
    body = _upload(client, login, content, filename="loan_tape.csv").json()
    assert body["row_count"] == 1000
    assert body["imported_count"] == 1000  # dirty values import fine; validation flags them later
    assert body["failed_count"] == 0
    # A known intentional issue is visible: L00001 appears 6x (5 injected dup + original).
    token = login(client, "operator@loantrust.demo", "operator123")
    res = client.get("/loans?q=L00001", headers=auth(token)).json()
    assert res["total"] >= 6
