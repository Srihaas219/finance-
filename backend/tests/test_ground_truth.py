"""Regression guard: the reconciliation script must show ZERO false negatives, i.e. the
deterministic engine detects every injected issue in the ground-truth ledger (252 rows)."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reconcile_ground_truth.py"
LEDGER = REPO / "data" / "raw" / "expected_exception_sample.csv"


@pytest.mark.skipif(not LEDGER.exists(), reason="ground-truth ledger not present")
def test_reconciliation_no_false_negatives():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=str(REPO)
    )
    out = result.stdout
    assert "VERDICT: PASS" in out, f"reconciliation failed:\n{out}\n{result.stderr}"
    # every class fully matched
    assert "TOTAL" in out
    assert result.returncode == 0
