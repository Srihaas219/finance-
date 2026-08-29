#!/usr/bin/env python3
"""Verify raw datasets against data/manifest.json (SHA-256 + presence).

Fails loudly if a file is missing or its hash changed — evidence must not be silently
replaced. Run after download/generation and in CI/demo pre-flight.

Usage: python scripts/verify_datasets.py [--raw data/raw]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    args = ap.parse_args()
    raw = Path(args.raw)
    manifest_path = Path("data/manifest.json")
    if not manifest_path.exists():
        print("ERROR: data/manifest.json missing. Run profile_datasets.py first.")
        return 2

    manifest = json.loads(manifest_path.read_text())
    ok = True
    for entry in manifest["files"]:
        p = raw / entry["filename"]
        if not p.exists():
            print(f"MISSING: {entry['filename']}")
            ok = False
            continue
        actual = sha256_file(p)
        if actual != entry["sha256"]:
            print(f"HASH MISMATCH: {entry['filename']}\n  expected {entry['sha256']}\n  actual   {actual}")
            ok = False
        else:
            print(f"OK: {entry['filename']} ({entry['bytes']} bytes)")
    print("VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
