#!/usr/bin/env python3
"""Automated reconciliation: actual data + validation engine + ground-truth ledger.

Builds a throwaway DB, ingests the real loan_tape + servicer feed, runs the deterministic
validation engine, then compares the produced exceptions against
data/raw/expected_exception_sample.csv (the injected ground truth).

The ledger is keyed by `row_index` = 0-based position in the loan-tape data rows, which maps
to raw_record.row_number = row_index + 1. For each injected (row_index, issue_code) we check
the engine raised that rule on that loan (TRUE POSITIVE) or not (FALSE NEGATIVE). Engine
exceptions not in the ledger are EXTRA and classified (natural duplicates / multi-field
conflicts are expected, not validator bugs).

Usage: python scripts/reconcile_ground_truth.py   (exit 0 if no false negatives)
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

# Use a throwaway SQLite DB so this is reproducible and side-effect free.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ.setdefault("RULESET_PATH", str(REPO / "backend" / "seed" / "validation_rules.json"))

from app.core.db import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401  (register all models)
from app.ingestion.service import ingest_csv, ingest_servicer_csv  # noqa: E402
from app.models.loan import Loan  # noqa: E402
from app.models.raw_record import RawRecord  # noqa: E402
from app.models.validation import LoanException  # noqa: E402
from app.validation.service import run_validation  # noqa: E402
from sqlalchemy import select  # noqa: E402

DATA = REPO / "data" / "raw"


def _ingest_and_validate(db):
    sf = ingest_csv(db, filename="loan_tape.csv", content=(DATA / "loan_tape.csv").read_bytes(),
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    srv = DATA / "servicer_update.csv"
    if srv.exists():
        ingest_servicer_csv(db, filename="servicer_update.csv", content=srv.read_bytes(),
                            uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    return sf["id"]


def reconcile() -> dict:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    sfid = _ingest_and_validate(db)

    # row_number (1-based) -> loan_pk for the loan-tape file
    rr_rows = db.execute(
        select(RawRecord.row_number, Loan.id)
        .join(Loan, Loan.raw_record_id == RawRecord.id)
        .where(RawRecord.source_file_id == sfid)
    ).all()
    rownum_to_pk = {rn: pk for rn, pk in rr_rows}

    # engine exceptions: {(loan_pk, rule_id)} present, plus per-rule counts
    ex_rows = db.scalars(select(LoanException)).all()
    engine_by_loan_rule = defaultdict(set)  # loan_pk -> {rule_id}
    engine_exceptions = []  # (loan_pk, rule_id, field)
    for e in ex_rows:
        engine_by_loan_rule[e.loan_pk].add(e.rule_id)
        engine_exceptions.append((e.loan_pk, e.rule_id, e.field))
    db.close()

    # ledger rows
    ledger = list(csv.DictReader((DATA / "expected_exception_sample.csv").open()))

    per_class = defaultdict(lambda: {"expected": 0, "true_positive": 0, "false_negative": 0})
    false_negatives = []
    for row in ledger:
        code = row["issue_code"]
        ridx = int(row["row_index"])
        rownum = ridx + 1  # ledger is 0-based; raw_record.row_number is 1-based
        per_class[code]["expected"] += 1
        pk = rownum_to_pk.get(rownum)
        if pk is not None and code in engine_by_loan_rule.get(pk, set()):
            per_class[code]["true_positive"] += 1
        else:
            per_class[code]["false_negative"] += 1
            false_negatives.append({"row_index": ridx, "issue_code": code, "loan_id": row["loan_id"]})

    # extras: engine exceptions whose (loan row, rule) is NOT in the ledger
    ledger_keys = {(int(r["row_index"]) + 1, r["issue_code"]) for r in ledger}
    pk_to_rownum = {pk: rn for rn, pk in rr_rows}
    extra_by_rule = Counter()
    for pk, rule, _field in engine_exceptions:
        rn = pk_to_rownum.get(pk)
        if rn is None or (rn, rule) not in ledger_keys:
            extra_by_rule[rule] += 1

    total_expected = sum(c["expected"] for c in per_class.values())
    total_tp = sum(c["true_positive"] for c in per_class.values())
    total_fn = sum(c["false_negative"] for c in per_class.values())

    return {
        "total_engine_exceptions": len(engine_exceptions),
        "ledger_expected": total_expected,
        "true_positives": total_tp,
        "false_negatives": total_fn,
        "per_class": dict(per_class),
        "false_negative_detail": false_negatives,
        "extra_by_rule": dict(extra_by_rule),
    }


def main() -> int:
    r = reconcile()
    print("=" * 68)
    print("GROUND-TRUTH RECONCILIATION")
    print("=" * 68)
    print(f"{'issue_class':<30} {'expected':>8} {'found(TP)':>10} {'missing(FN)':>12}")
    for code in sorted(r["per_class"]):
        c = r["per_class"][code]
        print(f"{code:<30} {c['expected']:>8} {c['true_positive']:>10} {c['false_negative']:>12}")
    print("-" * 68)
    print(f"{'TOTAL':<30} {r['ledger_expected']:>8} {r['true_positives']:>10} {r['false_negatives']:>12}")
    print()
    print(f"Engine produced {r['total_engine_exceptions']} exceptions total.")
    print(f"Extra (beyond ledger, by rule): {r['extra_by_rule']}")
    if r["false_negatives"]:
        print("\nFALSE NEGATIVES (injected but NOT detected):")
        for fn in r["false_negative_detail"]:
            print(f"  {fn}")
    verdict = "PASS — every injected issue detected" if r["false_negatives"] == 0 else "FAIL"
    print(f"\nVERDICT: {verdict}")
    try:
        os.unlink(_tmp.name)
    except OSError:
        pass
    return 0 if r["false_negatives"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
