"""AI provider abstraction (ADR-004).

Ships a deterministic, exception-aware Mock (default) so the AI feature is fully
demonstrable offline and in tests, plus a FailingProvider to exercise the degraded path
(ADR-017). A real Anthropic provider can be added as another impl without touching callers.

Invariant: providers return advisory structured output only. Nothing here writes canonical
loan data — a human applies suggestions via the review module.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

AI_KINDS = ("explain", "suggest_correction", "resolve_conflict", "reviewer_note",
            "classify_severity", "nl_rule_generation")

_RULE_HELP = {
    "missing_loan_id": "The loan identifier is blank; without it the record cannot be tracked or joined.",
    "duplicate_loan_id": "This loan_id is shared by multiple records; only one can be canonical.",
    "duplicate_combo": "Borrower, principal and origination date match another loan — likely a duplicate.",
    "invalid_date_format": "A date field could not be parsed; the original value is malformed.",
    "maturity_before_origination": "Maturity precedes origination, which is chronologically impossible.",
    "negative_principal": "Original principal is negative, which is not a valid loan amount.",
    "balance_gt_principal": "Current balance exceeds the original principal, which should not happen.",
    "rate_out_of_range": "Interest rate is outside the plausible configured range.",
    "status_dpd_mismatch": "Payment status and days-past-due disagree.",
    "missing_document_status": "Document status is blank; document availability is unknown.",
    "source_conflict": "The servicer feed disagrees with the loan tape on this field.",
    "stale_record": "The record has not been updated within the freshness window.",
    "invalid_state_code": "Borrower state is not a valid USPS code.",
    "repeated_borrower": "This borrower appears on an unusually high number of loans.",
    "closed_positive_balance": "The loan is Closed yet still shows a positive balance.",
}


@dataclass
class AIResult:
    kind: str
    output: dict[str, Any]
    model: str
    provider: str
    prompt: str
    created_at: str
    latency_ms: int
    degraded: bool = False
    suggested_field: str | None = None
    suggested_value: str | None = None


class AIProvider(ABC):
    name: str = "base"
    model: str = "base"

    @abstractmethod
    def generate(self, kind: str, context: dict[str, Any]) -> AIResult: ...


def _dec(v) -> Decimal | None:
    try:
        return Decimal(str(v))
    except Exception:
        return None


class MockAIProvider(AIProvider):
    name = "mock"
    model = "mock-deterministic-v1"

    def generate(self, kind: str, context: dict[str, Any]) -> AIResult:
        rule = context.get("rule_id")
        field = context.get("field")
        observed = context.get("observed_value")
        loan = context.get("loan", {})
        prompt = f"[mock:{kind}] rule={rule} field={field} observed={observed}"

        if kind == "explain":
            output = {
                "kind": "explain",
                "explanation": (
                    f"This record was flagged by rule '{rule}' on field '{field}'. "
                    f"Observed value: {observed}. {_RULE_HELP.get(rule, 'See rule definition.')}"
                ),
                "severity_opinion": context.get("severity", "medium"),
                "evidence": [f"{field} = {observed}", context.get("message", "")],
            }
            return self._result(kind, output, prompt)

        if kind == "suggest_correction":
            sug_field, sug_value, rationale = self._suggest(rule, field, loan)
            output = {
                "kind": "suggest_correction",
                "field": sug_field,
                "current_value": str(loan.get(sug_field)) if sug_field else observed,
                "suggested_value": sug_value,
                "rationale": rationale,
                "confidence": "high" if sug_value is not None else "low",
            }
            return self._result(kind, output, prompt, sug_field, sug_value)

        if kind == "resolve_conflict":
            values = context.get("values", [])
            # Deterministic policy: prefer the value from the most recently updated source.
            recommended = None
            if values:
                recommended = max(values, key=lambda v: v.get("last_updated_at", "")).get("value")
            output = {
                "kind": "resolve_conflict",
                "field": field,
                "values": values,
                "recommended_value": recommended,
                "rationale": "Recommending the most recently updated source's value; confirm manually.",
            }
            return self._result(kind, output, prompt, field, recommended)

        if kind == "reviewer_note":
            output = {
                "kind": "reviewer_note",
                "note": (
                    f"Reviewed {rule} on {field} (observed {observed}). "
                    f"{_RULE_HELP.get(rule, '')} Action taken: pending reviewer decision."
                ),
            }
            return self._result(kind, output, prompt)

        if kind == "classify_severity":
            rule = context.get("rule_id", "")
            current_sev = context.get("severity", "medium")
            # Deterministic severity mapping for demo. Authoritative severity is ALWAYS
            # the deterministic engine result — this is advisory only.
            high_rules = {"balance_gt_principal", "negative_principal", "maturity_before_origination",
                          "missing_loan_id", "source_conflict"}
            medium_rules = {"duplicate_loan_id", "invalid_date_format", "rate_out_of_range",
                            "status_dpd_mismatch", "closed_positive_balance"}
            suggested = "high" if rule in high_rules else "medium" if rule in medium_rules else "low"
            agree = suggested == current_sev
            rule_help = _RULE_HELP.get(rule, "see rule definition")
            agree_txt = "AI agrees with the deterministic classification."
            disagree_txt = (
                f"AI note: consider re-evaluating if '{suggested}' better reflects "
                "business risk. Deterministic classification is authoritative."
            )
            output = {
                "kind": "classify_severity",
                "deterministic_severity": current_sev,
                "suggested_severity": suggested,
                "agrees_with_engine": agree,
                "rationale": (
                    f"Deterministic engine classified this as '{current_sev}'. "
                    f"AI suggests '{suggested}' based on rule semantics: {rule_help}. "
                    + (agree_txt if agree else disagree_txt)
                ),
                "advisory": True,
                "note": "Deterministic severity is authoritative — AI opinion is informational only.",
            }
            return self._result(kind, output, prompt)

        if kind == "batch_summary":
            stats = context.get("stats", {})
            total = stats.get("total", 0)
            by_sev = stats.get("by_severity", {})
            top_rule = (stats.get("top_rules") or [["", 0]])[0][0]
            conflicts = stats.get("source_conflicts", 0)
            priority = "high" if by_sev.get("high", 0) else ("medium" if by_sev.get("medium", 0) else "low")
            narrative = (
                f"{total} open exceptions: {by_sev.get('high', 0)} high, "
                f"{by_sev.get('medium', 0)} medium, {by_sev.get('low', 0)} low. "
                f"Most common issue: {top_rule or 'n/a'}. {conflicts} source conflicts. "
                f"Suggested review priority: {priority} — start with high-severity items."
            )
            return self._result("batch_summary",
                                {"kind": "batch_summary", "narrative": narrative, "priority": priority},
                                f"[mock:batch_summary] total={total}")

        if kind == "nl_rule_generation":
            nl = context.get("natural_language", "")
            nl_low = nl.lower()
            # Deterministic keyword matching → example rule skeleton. Advisory only — humans
            # must review and import to validation_rules.json; never auto-applied.
            if "interest rate" in nl_low or "rate" in nl_low:
                rules = [{"rule_id": "rate_out_of_range_custom", "field": "interest_rate",
                          "operator": "outside_range", "threshold_low": 0.5, "threshold_high": 35.0,
                          "severity": "medium", "message": "Interest rate outside expected range"}]
                explanation = (
                    "Parsed 'interest rate' intent. Generated a range-check rule for "
                    "interest_rate. Review thresholds and add to validation_rules.json if correct."
                )
            elif "balance" in nl_low or "principal" in nl_low:
                rules = [{"rule_id": "balance_exceeds_principal_custom", "field": "current_balance",
                          "operator": "gt_field", "compare_field": "original_principal",
                          "severity": "high",
                          "message": "Current balance must not exceed original principal"}]
                explanation = (
                    "Parsed 'balance / principal' intent. Generated a cross-field "
                    "comparison rule. Review and add to validation_rules.json if correct."
                )
            elif "date" in nl_low or "maturity" in nl_low or "origination" in nl_low:
                rules = [{"rule_id": "maturity_before_origination_custom",
                          "field": "maturity_date", "operator": "before_field",
                          "compare_field": "origination_date", "severity": "high",
                          "message": "Maturity date must be after origination date"}]
                explanation = (
                    "Parsed date-ordering intent. Generated a temporal-comparison rule. "
                    "Review and add to validation_rules.json if correct."
                )
            else:
                rules = [{"rule_id": "custom_flag", "field": "loan_id",
                          "operator": "required", "severity": "medium",
                          "message": f"Custom rule from: '{nl[:60]}'. Refine manually."}]
                explanation = (
                    "Could not identify a specific field pattern. Generated a placeholder "
                    "rule. Provide a more specific description (mention field names, operators, "
                    "thresholds) to get a more precise rule skeleton."
                )
            output = {
                "kind": "nl_rule_generation",
                "natural_language_input": nl,
                "generated_rules": rules,
                "explanation": explanation,
                "advisory": True,
                "note": (
                    "Generated rules are advisory. Review carefully before importing to "
                    "validation_rules.json. Deterministic engine rules are always authoritative."
                ),
            }
            return self._result(kind, output, f"[mock:nl_rule_generation] input={nl[:40]}")

        raise ValueError(f"unknown AI kind '{kind}'")

    def _suggest(self, rule, field, loan) -> tuple[str | None, str | None, str]:
        if rule == "balance_gt_principal":
            p = loan.get("original_principal")
            return "current_balance", (str(p) if p is not None else None), \
                "Cap current_balance at the original principal."
        if rule == "closed_positive_balance":
            return "current_balance", "0.00", "A Closed loan should have a zero balance."
        if rule == "status_dpd_mismatch":
            status = loan.get("payment_status")
            if status == "Current":
                return "days_past_due", "0", "Current loans should have 0 days past due."
            return "days_past_due", "30", "A late status implies days_past_due > 0."
        if rule == "invalid_state_code":
            return "borrower_state", None, "State code is invalid; verify against borrower records."
        if rule == "maturity_before_origination":
            return "maturity_date", None, "Maturity should be after origination; confirm the correct date."
        if rule == "missing_document_status":
            return "document_status", None, "Confirm document availability before setting a status."
        return field, None, "No deterministic correction; requires human judgement."

    def _result(self, kind, output, prompt, sug_field=None, sug_value=None) -> AIResult:
        return AIResult(
            kind=kind, output=output, model=self.model, provider=self.name, prompt=prompt,
            created_at=datetime.now(UTC).isoformat(), latency_ms=1,
            suggested_field=sug_field, suggested_value=sug_value,
        )


class FailingProvider(AIProvider):
    """Simulates an unavailable/broken provider (timeout/garbage). Used to test degradation."""

    name = "failing"
    model = "failing"

    def generate(self, kind: str, context: dict[str, Any]) -> AIResult:
        time.sleep(0)
        raise TimeoutError("AI provider unavailable (simulated)")


def get_ai_provider(settings) -> AIProvider:
    provider = (getattr(settings, "ai_provider", "mock") or "mock").lower()
    if provider == "failing":
        return FailingProvider()
    # 'anthropic' would be added here; default and fallback is the deterministic Mock.
    return MockAIProvider()
