"""Deterministic demo seed: ingest the loan tape + servicer feed and run validation.

Idempotent (skips if the tape is already ingested). Use to land judges on a populated,
validated state, or run the live upload flow instead. Path:
    python -m app.demo_seed            (inside the api container, or locally)
Reads data files from DEMO_DATA_DIR (default: ../data/raw relative to backend, or /data/raw).
"""
import json
import os
from pathlib import Path

from sqlalchemy import select

from .core.db import SessionLocal
from .ingestion.service import ingest_csv, ingest_servicer_csv
from .models.source_file import SourceFile
from .validation.service import run_validation


def _find_data_dir() -> Path | None:
    candidates = [
        os.environ.get("DEMO_DATA_DIR"),
        "seed", "data/raw", "../data/raw", "/data/raw",  # 'seed' is shipped in the image
    ]
    for c in candidates:
        if c and (Path(c) / "loan_tape.csv").exists():
            return Path(c)
    return None


def seed_demo() -> dict:
    data_dir = _find_data_dir()
    if data_dir is None:
        print(json.dumps({"skipped": "loan_tape.csv not found; set DEMO_DATA_DIR"}))
        return {"skipped": True}

    db = SessionLocal()
    try:
        tape = (data_dir / "loan_tape.csv").read_bytes()
        # Idempotency: skip if this exact tape is already ingested.
        from .core.hashing import sha256_hex
        existing = db.scalar(
            select(SourceFile).where(SourceFile.file_hash == sha256_hex(tape),
                                     SourceFile.duplicate_of.is_(None))
        )
        if existing is not None:
            print(json.dumps({"skipped": "already seeded", "source_file_id": existing.id}))
            return {"skipped": True}

        sf = ingest_csv(db, filename="loan_tape.csv", content=tape,
                        uploaded_by_id="u-operator", uploaded_by_role="data_operator")
        srv_path = data_dir / "servicer_update.csv"
        if srv_path.exists():
            ingest_servicer_csv(db, filename="servicer_update.csv", content=srv_path.read_bytes(),
                                uploaded_by_id="u-operator", uploaded_by_role="data_operator")
        result = run_validation(db, source_file_id=sf["id"], actor_id="u-operator",
                                actor_role="data_operator")
        verified = _verify_a_few_clean_loans(db)
        out = {"seeded": True, "imported": sf["imported_count"], "totals": result["totals"],
               "verified_examples": verified}
        print(json.dumps(out))
        return out
    finally:
        db.close()


def _verify_a_few_clean_loans(db, count: int = 3) -> int:
    """Approve + verify a few CLEAN loans so the Consumer view has content for the demo
    ('successful verification' example). Deterministic (ordered by loan_id) and idempotent."""
    from .models.loan import Loan
    from .review.service import loan_decision
    from .verification.service import verify_loan

    clean = db.scalars(
        select(Loan).where(Loan.status == "clean").order_by(Loan.loan_id).limit(count)
    ).all()
    done = 0
    for loan in clean:
        try:
            loan_decision(db, loan_pk=loan.id, reviewer_id="u-reviewer", action="approve")
            verify_loan(db, loan_pk=loan.id, reviewer_id="u-reviewer")
            done += 1
        except Exception:  # noqa: BLE001 (best-effort demo setup)
            continue
    return done


if __name__ == "__main__":
    seed_demo()
