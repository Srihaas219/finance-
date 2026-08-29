#!/usr/bin/env python3
"""Deterministic synthetic loan dataset generator for LoanTrust Copilot.

WHY THIS EXISTS: the organizer's real dataset is not shipped with the repo, and the
public Fannie/Freddie sources are registration- and terms-gated (see
scripts/download_datasets.py). The problem statement recommends using a synthetic
dataset for judging. This script produces organizer-SHAPED files that conform exactly
to the PS §6 schema and deliberately embed all 15 PS §7 intentional issue classes, with
a ground-truth ledger (expected_exception_sample.csv) so validation can be tested.

It is DETERMINISTIC (fixed seed + fixed reference date) so hashes, counts, and the demo
are reproducible. Output files are treated as immutable evidence once written.

Usage:
    python scripts/generate_synthetic_dataset.py [--rows 1000] [--out data/raw] [--force]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20260827
AS_OF = date(2026, 8, 1)  # fixed "today" so staleness is deterministic

LOAN_TYPES = ["Auto", "Personal", "Mortgage", "Student", "SMB"]
PURPOSES = ["Purchase", "Refinance", "Debt Consolidation", "Home Improvement", "Working Capital"]
CREDIT_GRADES = ["A", "B", "C", "D"]
INCOME_BANDS = ["<30k", "30-60k", "60-100k", "100-150k", ">150k"]
SERVICERS = ["Acme Servicing", "BlueRiver Loan Co", "Cornerstone Servicing", "DeltaPay"]
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
]
# payment_status enum used by the (clean) baseline
STATUS_CURRENT = "Current"
STATUS_30 = "30 Days Late"
STATUS_60 = "60 Days Late"
STATUS_90 = "90+ Days Late"
STATUS_CLOSED = "Closed"

CANONICAL_COLUMNS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]


def _fmt_money(x: float) -> str:
    return f"{x:.2f}"


def _iso(d: date) -> str:
    return d.isoformat()


def build_baseline(n: int, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for i in range(1, n + 1):
        loan_id = f"L{i:05d}"
        borrower_id = f"B{rng.randint(1, n // 2):05d}"
        orig = AS_OF - timedelta(days=rng.randint(200, 3000))
        term = rng.choice([24, 36, 48, 60, 120, 180, 360])
        maturity = orig + timedelta(days=term * 30)
        principal = round(rng.uniform(5_000, 500_000), 2)
        # current balance <= principal for a healthy loan
        balance = round(principal * rng.uniform(0.2, 0.98), 2)
        rate = round(rng.uniform(3.0, 18.0), 3)
        dpd = 0
        status = STATUS_CURRENT
        last_pay = AS_OF - timedelta(days=rng.randint(1, 40))
        last_updated = AS_OF - timedelta(days=rng.randint(0, 60))
        rows.append(
            {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "loan_type": rng.choice(LOAN_TYPES),
                "origination_date": _iso(orig),
                "maturity_date": _iso(maturity),
                "original_principal": _fmt_money(principal),
                "current_balance": _fmt_money(balance),
                "interest_rate": f"{rate:.3f}",
                "term_months": str(term),
                "borrower_state": rng.choice(STATES),
                "loan_purpose": rng.choice(PURPOSES),
                "credit_grade": rng.choice(CREDIT_GRADES),
                "employment_length": str(rng.randint(0, 40)),
                "income_band": rng.choice(INCOME_BANDS),
                "payment_status": status,
                "days_past_due": str(dpd),
                "servicer_name": rng.choice(SERVICERS),
                "last_payment_date": _iso(last_pay),
                "last_updated_at": _iso(last_updated),
                "document_status": rng.choice(["complete", "partial"]),
                "source_system": "origination_core",
            }
        )
    return rows


def inject_issues(rows: list[dict], rng: random.Random) -> list[dict]:
    """Mutate specific rows to embed each PS §7 issue class. Returns the ground-truth ledger."""
    ledger: list[dict] = []
    n = len(rows)

    def rec(idx: int, code: str, field: str, severity: str, note: str):
        ledger.append(
            {
                "row_index": idx,
                "loan_id": rows[idx]["loan_id"],
                "issue_code": code,
                "field": field,
                "severity": severity,
                "note": note,
            }
        )

    # Disjoint index bands so issues don't collide.
    def band(start, count):
        return list(range(start, start + count))

    # 1 missing_loan_id
    for idx in band(10, 5):
        rows[idx]["loan_id"] = ""
        rec(idx, "missing_loan_id", "loan_id", "high", "loan_id blank")
    # 2 duplicate_loan_id (reuse a known good id)
    for idx in band(20, 5):
        rows[idx]["loan_id"] = "L00001"
        rec(idx, "duplicate_loan_id", "loan_id", "high", "loan_id duplicates L00001")
    # 3 duplicate_combo (borrower + principal + orig date)
    anchor = rows[100]
    for idx in band(30, 4):
        rows[idx]["borrower_id"] = anchor["borrower_id"]
        rows[idx]["original_principal"] = anchor["original_principal"]
        rows[idx]["origination_date"] = anchor["origination_date"]
        rec(idx, "duplicate_combo", "borrower_id+original_principal+origination_date", "medium",
            "matches anchor L00101 combo")
    # 4 invalid_date_format
    bad_dates = ["13/45/2021", "not-a-date", "2021-13-01", "31/02/2020", "2020/00/10", "Jan-2021", "", "20211301"]
    for k, idx in enumerate(band(40, 8)):
        field = "origination_date" if k % 2 == 0 else "maturity_date"
        rows[idx][field] = bad_dates[k]
        rec(idx, "invalid_date_format", field, "high", f"unparseable date '{bad_dates[k]}'")
    # 5 maturity_before_origination
    for idx in band(50, 6):
        o = date.fromisoformat(rows[idx]["origination_date"])
        rows[idx]["maturity_date"] = _iso(o - timedelta(days=400))
        rec(idx, "maturity_before_origination", "maturity_date", "high", "maturity < origination")
    # 6 negative_principal
    for idx in band(60, 5):
        rows[idx]["original_principal"] = _fmt_money(-abs(float(rows[idx]["original_principal"])))
        rec(idx, "negative_principal", "original_principal", "high", "negative principal")
    # 7 balance_gt_principal
    for idx in band(70, 6):
        p = float(rows[idx]["original_principal"])
        rows[idx]["current_balance"] = _fmt_money(round(p * 1.25, 2))
        rec(idx, "balance_gt_principal", "current_balance", "high", "current_balance > original_principal")
    # 8 rate_out_of_range
    bad_rates = ["45.000", "-2.000", "0.000", "99.900", "38.000", "0.100"]
    for k, idx in enumerate(band(80, 6)):
        rows[idx]["interest_rate"] = bad_rates[k]
        rec(idx, "rate_out_of_range", "interest_rate", "medium", f"rate {bad_rates[k]} outside [0.5,25]")
    # 9 status_dpd_mismatch
    for k, idx in enumerate(band(90, 7)):
        if k % 2 == 0:
            rows[idx]["payment_status"] = STATUS_CURRENT
            rows[idx]["days_past_due"] = str(rng.choice([45, 90, 120]))
            rec(idx, "status_dpd_mismatch", "payment_status/days_past_due", "medium",
                "Current but dpd>0")
        else:
            rows[idx]["payment_status"] = STATUS_90
            rows[idx]["days_past_due"] = "0"
            rec(idx, "status_dpd_mismatch", "payment_status/days_past_due", "medium",
                "90+ Days Late but dpd=0")
    # 10 missing_document_status
    for idx in band(110, 8):
        rows[idx]["document_status"] = ""
        rec(idx, "missing_document_status", "document_status", "low", "document_status blank")
    # 12 stale_record (11 is cross-file, done in servicer_update)
    for idx in band(130, 10):
        rows[idx]["last_updated_at"] = _iso(AS_OF - timedelta(days=rng.randint(400, 1200)))
        rec(idx, "stale_record", "last_updated_at", "low", "not updated within staleness window")
    # 13 invalid_state_code
    bad_states = ["ZZ", "XX", "Cal", "N/A", "99", "us"]
    for k, idx in enumerate(band(150, 6)):
        rows[idx]["borrower_state"] = bad_states[k]
        rec(idx, "invalid_state_code", "borrower_state", "medium", f"invalid state '{bad_states[k]}'")
    # 14 repeated_borrower (one borrower across several loans)
    for idx in band(160, 5):
        rows[idx]["borrower_id"] = "B00007"
        rec(idx, "repeated_borrower", "borrower_id", "low", "suspicious repeated borrower B00007")
    # 15 closed_positive_balance
    for idx in band(170, 5):
        rows[idx]["payment_status"] = STATUS_CLOSED
        rows[idx]["current_balance"] = _fmt_money(round(rng.uniform(500, 20000), 2))
        rec(idx, "closed_positive_balance", "payment_status/current_balance", "high",
            "Closed but current_balance > 0")

    return ledger


def build_servicer_update(rows: list[dict], rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Second source with partial + CONFLICTING info (PS issue 11). Returns (rows, conflict ledger)."""
    cols = ["loan_id", "current_balance", "payment_status", "days_past_due",
            "last_updated_at", "servicer_name", "source_system"]
    out: list[dict] = []
    conflicts: list[dict] = []
    # take every ~3rd loan that has a real id
    for idx in range(0, len(rows), 3):
        r = rows[idx]
        if not r["loan_id"]:
            continue
        conflict = idx % 6 == 0  # ~half of the updates conflict
        bal = float(r["current_balance"] or 0)
        new_bal = round(bal * (0.6 if conflict else 0.97), 2)
        new_status = (STATUS_30 if conflict else r["payment_status"])
        out.append(
            {
                "loan_id": r["loan_id"],
                "current_balance": _fmt_money(new_bal),
                "payment_status": new_status,
                "days_past_due": str(rng.choice([0, 15, 30]) if conflict else 0),
                "last_updated_at": _iso(AS_OF - timedelta(days=rng.randint(0, 20))),
                "servicer_name": r["servicer_name"],
                "source_system": "servicer_feed",
            }
        )
        if conflict:
            conflicts.append(
                {
                    "row_index": idx,
                    "loan_id": r["loan_id"],
                    "issue_code": "source_conflict",
                    "field": "current_balance/payment_status",
                    "severity": "medium",
                    "note": f"servicer_feed disagrees with loan_tape (bal {r['current_balance']} vs {new_bal})",
                }
            )
    return out, conflicts, cols  # type: ignore[return-value]


def build_document_manifest(rows: list[dict], rng: random.Random) -> tuple[list[dict], list[str]]:
    cols = ["loan_id", "document_status", "documents_available", "note"]
    out = []
    for r in rows:
        if not r["loan_id"]:
            continue
        # A minority are missing documents entirely (used by doc-availability validation).
        roll = rng.random()
        if roll < 0.08:
            status, count = "missing", 0
        elif roll < 0.25:
            status, count = "partial", rng.randint(1, 2)
        else:
            status, count = "complete", rng.randint(3, 5)
        out.append({"loan_id": r["loan_id"], "document_status": status,
                    "documents_available": str(count), "note": ""})
    return out, cols


def validation_rules() -> dict:
    return {
        "ruleset_version": "1.0.0",
        "as_of_date": AS_OF.isoformat(),
        "staleness_days": 365,
        "interest_rate_range": {"min": 0.5, "max": 25.0},
        "repeated_borrower_threshold": 5,
        "allowed_payment_status": [STATUS_CURRENT, STATUS_30, STATUS_60, STATUS_90, STATUS_CLOSED],
        "allowed_states": STATES,
        "required_fields": ["loan_id", "borrower_id", "original_principal", "origination_date",
                            "maturity_date", "payment_status"],
        "allowed_edit_fields": [
            "borrower_state", "payment_status", "days_past_due", "document_status",
            "interest_rate", "maturity_date", "last_payment_date", "current_balance",
        ],
        "forbidden_edit_fields": ["loan_id", "borrower_id", "original_principal", "origination_date"],
        "rules": [
            {"code": "missing_loan_id", "severity": "high"},
            {"code": "missing_required_field", "severity": "high"},
            {"code": "duplicate_loan_id", "severity": "high"},
            {"code": "duplicate_combo", "severity": "medium"},
            {"code": "invalid_date_format", "severity": "high"},
            {"code": "maturity_before_origination", "severity": "high"},
            {"code": "negative_principal", "severity": "high"},
            {"code": "balance_gt_principal", "severity": "high"},
            {"code": "rate_out_of_range", "severity": "medium"},
            {"code": "status_dpd_mismatch", "severity": "medium"},
            {"code": "missing_document_status", "severity": "low"},
            {"code": "source_conflict", "severity": "medium"},
            {"code": "stale_record", "severity": "low"},
            {"code": "invalid_state_code", "severity": "medium"},
            {"code": "repeated_borrower", "severity": "low"},
            {"code": "closed_positive_balance", "severity": "high"},
        ],
    }


def write_csv(path: Path, cols: list[str], rows: list[dict]):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    loan_tape_path = out / "loan_tape.csv"
    if loan_tape_path.exists() and not args.force:
        raise SystemExit(f"{loan_tape_path} exists. Use --force to regenerate (evidence is immutable).")

    rng = random.Random(SEED)
    rows = build_baseline(args.rows, rng)
    ledger = inject_issues(rows, rng)
    servicer, conflicts, servicer_cols = build_servicer_update(rows, rng)
    manifest_rows, manifest_cols = build_document_manifest(rows, rng)
    ledger_all = ledger + conflicts

    write_csv(loan_tape_path, CANONICAL_COLUMNS, rows)
    write_csv(out / "servicer_update.csv", servicer_cols, servicer)
    write_csv(out / "document_manifest.csv", manifest_cols, manifest_rows)
    (out / "validation_rules.json").write_text(json.dumps(validation_rules(), indent=2))
    write_csv(out / "expected_exception_sample.csv",
              ["row_index", "loan_id", "issue_code", "field", "severity", "note"], ledger_all)

    # Per-issue golden fixtures for later validation tests (deterministic subsets).
    golden_dir = Path("tests/fixtures/golden")
    golden_dir.mkdir(parents=True, exist_ok=True)
    by_code: dict[str, list[int]] = {}
    for e in ledger:  # single-file issues only (conflicts need two files)
        by_code.setdefault(e["issue_code"], []).append(e["row_index"])
    for code, idxs in by_code.items():
        write_csv(golden_dir / f"{code}.csv", CANONICAL_COLUMNS, [rows[i] for i in idxs])

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "seed": SEED,
        "as_of": AS_OF.isoformat(),
        "loan_tape_rows": len(rows),
        "servicer_update_rows": len(servicer),
        "document_manifest_rows": len(manifest_rows),
        "expected_exceptions": len(ledger_all),
        "issue_classes": sorted(by_code.keys()) + ["source_conflict"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
