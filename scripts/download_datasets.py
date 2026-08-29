#!/usr/bin/env python3
"""Dataset bootstrap entry point.

Reality (documented honestly): the organizer's synthetic package is NOT shipped in this
repo, and the public sources in the problem statement are registration- and
terms-gated, so they cannot be fetched non-interactively:

  - Fannie Mae Single-Family Loan Performance Data
      https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data
      (requires account + terms acceptance via Data Dynamics)
  - Freddie Mac Single-Family Loan-Level Dataset
      https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset
      (requires sign-in via Clarity Data Intelligence)

Therefore the reproducible default is a DETERMINISTIC SYNTHETIC dataset that conforms to
the PS §6 schema and embeds the PS §7 issue classes. This script:
  1. If an organizer package path is provided via --organizer-dir, copies those files in
     (never overwriting without --force) and records them.
  2. Otherwise generates the synthetic bootstrap dataset.
Then it profiles + verifies so data/manifest.json is populated.

Usage:
    python scripts/download_datasets.py                 # synthetic bootstrap
    python scripts/download_datasets.py --organizer-dir /path/to/package --force
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED = [
    "loan_tape.csv",
    "servicer_update.csv",
    "document_manifest.csv",
    "validation_rules.json",
    "expected_exception_sample.csv",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--organizer-dir", default=None,
                    help="Path to the real organizer package (copies files into data/raw).")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    raw = Path("data/raw")
    raw.mkdir(parents=True, exist_ok=True)

    if args.organizer_dir:
        src = Path(args.organizer_dir)
        for name in EXPECTED:
            s = src / name
            d = raw / name
            if not s.exists():
                print(f"WARN: {name} not found in organizer dir; skipping")
                continue
            if d.exists() and not args.force:
                print(f"SKIP (exists, immutable): {name} — use --force to replace")
                continue
            shutil.copy2(s, d)
            print(f"COPIED organizer file: {name}")
    else:
        print("No --organizer-dir given → generating deterministic synthetic bootstrap dataset.")
        cmd = [sys.executable, "scripts/generate_synthetic_dataset.py", "--rows", str(args.rows)]
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, check=True)

    # Fingerprint + verify.
    subprocess.run([sys.executable, "scripts/profile_datasets.py"], check=True)
    return subprocess.run([sys.executable, "scripts/verify_datasets.py"]).returncode


if __name__ == "__main__":
    sys.exit(main())
