"""CSV ingestion: preserve raw evidence, normalize to canonical loans, emit audit events.

Design (ADR-012/013): stream-parse, batched inserts, single transaction (atomic import),
duplicate content -> new logical upload referencing the original (raw not re-stored).
"""
from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import build_event
from ..core.hashing import hash_record, sha256_hex
from ..core.ids import new_id
from ..models.loan import Loan
from ..models.raw_record import RawRecord
from ..models.servicer import ServicerRecord
from ..models.source_file import SourceFile
from .normalize import (
    CANONICAL_FIELDS,
    normalization_status,
    normalize_date,
    normalize_int,
    normalize_money,
    normalize_payment_status,
    normalize_row_full,
)

_EXTRA_KEY = "__extra__"
BATCH_SIZE = 1000

# Canonical fields that go onto the Loan model (all of them for Slice 1).
_LOAN_FIELDS = list(CANONICAL_FIELDS)


def _decode(content: bytes) -> str:
    return content.decode("utf-8-sig", errors="replace")


def ingest_csv(
    db: Session,
    *,
    filename: str,
    content: bytes,
    uploaded_by_id: str,
    uploaded_by_role: str,
    kind: str = "loan_tape",
) -> dict:
    file_hash = sha256_hex(content)

    # Duplicate detection: an existing canonical (non-duplicate) upload with the same bytes.
    original = db.scalar(
        select(SourceFile).where(SourceFile.file_hash == file_hash, SourceFile.duplicate_of.is_(None))
    )

    sf = SourceFile(
        id=new_id(),
        filename=filename,
        kind=kind,
        byte_size=len(content),
        file_hash=file_hash,
        content=content,
        uploaded_by=uploaded_by_id,
    )

    if original is not None:
        # ADR-013: preserve the fact of re-upload; reuse original evidence; don't re-parse.
        sf.duplicate_of = original.id
        sf.row_count = original.row_count
        sf.imported_count = original.imported_count
        sf.failed_count = original.failed_count
        db.add(sf)
        db.flush()  # ensure source_file row exists before its audit event (FK order)
        db.add(
            build_event(
                "file.uploaded",
                entity_type="source_file",
                entity_id=sf.id,
                actor_id=uploaded_by_id,
                actor_role=uploaded_by_role,
                payload={"filename": filename, "file_hash": file_hash, "duplicate_of": original.id},
                source_file_id=sf.id,
            )
        )
        db.commit()
        return {
            "id": sf.id,
            "filename": filename,
            "kind": kind,
            "byte_size": sf.byte_size,
            "file_hash": file_hash,
            "duplicate": True,
            "original_upload_id": original.id,
            "row_count": sf.row_count,
            "imported_count": sf.imported_count,
            "failed_count": sf.failed_count,
            "failed_samples": [],
            "note": "Duplicate content of an existing upload; raw evidence reused.",
        }

    db.add(sf)
    db.flush()  # ensure sf.id is usable as FK

    reader = csv.DictReader(io.StringIO(_decode(content)), restkey=_EXTRA_KEY, restval="")
    header = reader.fieldnames
    if not header or "loan_id" not in header:
        raise ValueError("CSV header missing required 'loan_id' column")

    db.add(
        build_event(
            "file.uploaded",
            entity_type="source_file",
            entity_id=sf.id,
            actor_id=uploaded_by_id,
            actor_role=uploaded_by_role,
            payload={"filename": filename, "file_hash": file_hash, "columns": header},
            source_file_id=sf.id,
        )
    )

    # Separate batches flushed in FK-dependency order (raw_records -> loans -> audit).
    # Postgres enforces FKs immediately, so a mixed add_all can violate ordering; SQLite
    # (FKs off by default) hides this. Explicit ordering keeps both correct.
    rr_batch: list = []
    loan_batch: list = []
    audit_batch: list = []
    total = imported = failed = 0
    failed_samples: list = []

    def flush_batches(force: bool = False):
        if not force and len(rr_batch) < BATCH_SIZE:
            return
        if rr_batch:
            db.add_all(rr_batch)
            db.flush()
            rr_batch.clear()
        if loan_batch:
            db.add_all(loan_batch)
            db.flush()
            loan_batch.clear()
        if audit_batch:
            db.add_all(audit_batch)
            db.flush()
            audit_batch.clear()

    for i, row in enumerate(reader, start=1):
        total += 1
        raw_payload = {k: (row.get(k) or "") for k in header}
        extra = row.get(_EXTRA_KEY)
        row_hash = hash_record(raw_payload)
        rr = RawRecord(
            id=new_id(),
            source_file_id=sf.id,
            row_number=i,
            raw_payload=raw_payload,
            row_hash=row_hash,
        )
        rr_batch.append(rr)

        if extra:  # structural failure: unexpected extra columns
            rr.import_status = "failed"
            rr.failure_reason = "row has more columns than header"
            failed += 1
            if len(failed_samples) < 10:
                failed_samples.append({"row_number": i, "reason": rr.failure_reason})
            flush_batches()
            continue

        canonical, notes, provenance = normalize_row_full(raw_payload)
        loan = Loan(
            id=new_id(),
            source_file_id=sf.id,
            raw_record_id=rr.id,
            status="imported",
            normalization_status=normalization_status(provenance),
            normalization_notes=notes or None,
            field_provenance=provenance,
            **{f: canonical.get(f) for f in _LOAN_FIELDS},
        )
        imported += 1
        loan_batch.append(loan)
        audit_batch.append(
            build_event(
                "loan.imported",
                entity_type="loan",
                entity_id=loan.id,
                actor_id=uploaded_by_id,
                actor_role=uploaded_by_role,
                loan_id=loan.loan_id,
                payload={"row_number": i, "row_hash": row_hash, "normalization_notes": len(notes)},
                source_file_id=sf.id,
            )
        )
        flush_batches()

    flush_batches(force=True)

    sf.row_count = total
    sf.imported_count = imported
    sf.failed_count = failed
    db.commit()

    return {
        "id": sf.id,
        "filename": filename,
        "kind": kind,
        "byte_size": sf.byte_size,
        "file_hash": file_hash,
        "duplicate": False,
        "original_upload_id": None,
        "row_count": total,
        "imported_count": imported,
        "failed_count": failed,
        "failed_samples": failed_samples,
        "note": None,
    }


def ingest_servicer_csv(
    db: Session, *, filename: str, content: bytes, uploaded_by_id: str, uploaded_by_role: str,
) -> dict:
    """Ingest the second-source servicer feed into ServicerRecords (no canonical loans).

    Same evidence/dedup guarantees as loan-tape ingestion (ADR-013): file hash, raw_records,
    single transaction. Values are normalized to match the canonical loan so the
    `source_conflict` rule compares like-for-like.
    """
    file_hash = sha256_hex(content)
    original = db.scalar(
        select(SourceFile).where(SourceFile.file_hash == file_hash, SourceFile.duplicate_of.is_(None))
    )
    sf = SourceFile(
        id=new_id(), filename=filename, kind="servicer_update", byte_size=len(content),
        file_hash=file_hash, content=content, uploaded_by=uploaded_by_id,
    )
    if original is not None:
        sf.duplicate_of = original.id
        sf.row_count = original.row_count
        sf.imported_count = original.imported_count
        db.add(sf)
        db.flush()
        db.add(build_event(
            "file.uploaded", entity_type="source_file", entity_id=sf.id,
            actor_id=uploaded_by_id, actor_role=uploaded_by_role, source_file_id=sf.id,
            payload={"filename": filename, "file_hash": file_hash, "duplicate_of": original.id},
        ))
        db.commit()
        return {"id": sf.id, "kind": "servicer_update", "duplicate": True,
                "original_upload_id": original.id, "row_count": sf.row_count,
                "imported_count": sf.imported_count}

    db.add(sf)
    db.flush()
    reader = csv.DictReader(io.StringIO(_decode(content)), restkey=_EXTRA_KEY, restval="")
    header = reader.fieldnames
    if not header or "loan_id" not in header:
        raise ValueError("servicer CSV header missing required 'loan_id' column")
    db.add(build_event("file.uploaded", entity_type="source_file", entity_id=sf.id,
                       actor_id=uploaded_by_id, actor_role=uploaded_by_role, source_file_id=sf.id,
                       payload={"filename": filename, "file_hash": file_hash, "columns": header}))

    rr_batch: list = []
    sr_batch: list = []
    total = imported = 0

    def flush(force=False):
        if force or len(rr_batch) >= BATCH_SIZE:
            if rr_batch:
                db.add_all(rr_batch)
                db.flush()
                rr_batch.clear()
            if sr_batch:
                db.add_all(sr_batch)
                db.flush()
                sr_batch.clear()

    for i, row in enumerate(reader, start=1):
        total += 1
        raw_payload = {k: (row.get(k) or "") for k in header}
        rr = RawRecord(id=new_id(), source_file_id=sf.id, row_number=i,
                       raw_payload=raw_payload, row_hash=hash_record(raw_payload))
        rr_batch.append(rr)
        notes: list = []
        sr_batch.append(ServicerRecord(
            id=new_id(), source_file_id=sf.id, raw_record_id=rr.id,
            loan_id=(raw_payload.get("loan_id") or "").strip() or None,
            current_balance=normalize_money(raw_payload.get("current_balance"), "current_balance", notes),
            payment_status=normalize_payment_status(
                raw_payload.get("payment_status"), "payment_status", notes),
            days_past_due=normalize_int(raw_payload.get("days_past_due"), "days_past_due", notes),
            last_updated_at=normalize_date(
                raw_payload.get("last_updated_at"), "last_updated_at", notes),
            servicer_name=(raw_payload.get("servicer_name") or "").strip() or None,
            source_system=(raw_payload.get("source_system") or "").strip() or None,
        ))
        imported += 1
        flush()
    flush(force=True)

    sf.row_count = total
    sf.imported_count = imported
    db.commit()
    return {"id": sf.id, "kind": "servicer_update", "duplicate": False,
            "original_upload_id": None, "row_count": total, "imported_count": imported}
