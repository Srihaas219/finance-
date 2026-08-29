"""Load the versioned validation ruleset (config-driven, ADR-011)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from ..core.config import get_settings


@dataclass(frozen=True)
class Ruleset:
    version: str
    as_of_date: date
    staleness_days: int
    rate_min: float
    rate_max: float
    allowed_payment_status: frozenset[str]
    allowed_states: frozenset[str]
    required_fields: tuple[str, ...]
    allowed_edit_fields: frozenset[str]
    forbidden_edit_fields: frozenset[str]
    repeated_borrower_threshold: int
    severities: dict[str, str] = field(default_factory=dict)

    def severity_of(self, rule_code: str) -> str:
        return self.severities.get(rule_code, "medium")


def load_ruleset(path: str | None = None) -> Ruleset:
    p = Path(path or get_settings().ruleset_path)
    data = json.loads(p.read_text())
    rate = data.get("interest_rate_range", {"min": 0.5, "max": 25.0})
    severities = {r["code"]: r.get("severity", "medium") for r in data.get("rules", [])}
    return Ruleset(
        version=data.get("ruleset_version", "unknown"),
        as_of_date=date.fromisoformat(data.get("as_of_date", "2026-08-01")),
        staleness_days=int(data.get("staleness_days", 365)),
        rate_min=float(rate["min"]),
        rate_max=float(rate["max"]),
        allowed_payment_status=frozenset(data.get("allowed_payment_status", [])),
        allowed_states=frozenset(data.get("allowed_states", [])),
        required_fields=tuple(data.get("required_fields", [])),
        allowed_edit_fields=frozenset(data.get("allowed_edit_fields", [])),
        forbidden_edit_fields=frozenset(data.get("forbidden_edit_fields", [])),
        repeated_borrower_threshold=int(data.get("repeated_borrower_threshold", 5)),
        severities=severities,
    )


@lru_cache
def default_ruleset() -> Ruleset:
    return load_ruleset()
