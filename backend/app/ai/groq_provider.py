"""Groq AI provider with dual-key credential failover.

Architecture:
    GroqProvider (implements AIProvider ABC)
        └── GroqKeyManager
                ├── KEY_1  (_KeyState: healthy/unhealthy, failure_count, cooldown_until)
                └── KEY_2  (_KeyState: ...)

Failover policy (see FAILOVER_POLICY in the prompt):
    A. Auth failure (401/403)  → mark key unhealthy; try other key once.
    B. Transient failure (5xx, timeout, network) → bounded exponential retry; then try other key.
    C. Rate limit (429)        → respect Retry-After; do NOT cycle keys aggressively.
    D. Malformed model output  → degrade gracefully; NO key switch (model issue, not key issue).

SECURITY:
    - Keys are held in memory only; NEVER logged; NEVER stored in DB; NEVER sent to frontend.
    - Authorization headers are excluded from log fields.
    - TLS verification is always enabled (verify=True).

AI Safety Invariants (unchanged from MockAIProvider):
    - All output is advisory only.
    - AI cannot edit canonical loan data directly.
    - AI cannot verify or approve loans.
    - A human reviewer applies suggestions via the review module.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from .provider import AIProvider, AIResult

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_TIMEOUT = 20.0
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_BACKOFF_BASE = 1.0
_DEFAULT_COOLDOWN = 60.0
_TEMP_FAILURE_COOLDOWN_DIVISOR = 4  # shorter cooldown for transient failures


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class GroqError(Exception):
    def __init__(self, msg: str, *, status: int | None = None, retry_after: float | None = None):
        super().__init__(msg)
        self.status = status
        self.retry_after = retry_after


class GroqAuthError(GroqError):
    """401 / 403 — key is invalid, revoked, or not authorised."""


class GroqRateLimitError(GroqError):
    """429 — rate limit reached (org-level; not a per-key bypass signal)."""


class GroqProviderError(GroqError):
    """5xx / timeout / network — transient provider failure."""


class GroqMalformedError(GroqError):
    """Model returned syntactically bad JSON or wrong schema.
    This is a MODEL issue, not a KEY issue — do NOT switch keys."""


# ---------------------------------------------------------------------------
# Per-key health tracking
# ---------------------------------------------------------------------------

@dataclass
class _KeyState:
    slot: int            # 1 or 2 — used only for safe log metadata (never the key itself)
    healthy: bool = True
    failure_count: int = 0
    _cooldown_until: float = field(default=0.0, repr=False)

    def mark_unhealthy(self, cooldown_seconds: float) -> None:
        self.healthy = False
        self.failure_count += 1
        self._cooldown_until = time.monotonic() + cooldown_seconds

    def try_recover(self) -> None:
        """Restore healthy status if cooldown has elapsed."""
        if not self.healthy and time.monotonic() >= self._cooldown_until:
            self.healthy = True
            logger.info("groq key_slot=%d recovered after cooldown", self.slot)


# ---------------------------------------------------------------------------
# Key manager
# ---------------------------------------------------------------------------

class GroqKeyManager:
    """
    Manages up to two Groq API keys with deterministic, thread-safe failover.

    Selection strategy:
        preferred_key → request → success                     → keep preferred
                                → auth failure                → mark unhealthy; try other key
                                → 5xx/timeout (after retry)  → mark unhealthy (short); try other key
                                → 429 + Retry-After           → honour header; do NOT cycle
                                → 429 no Retry-After          → try other key at most once
                                → malformed output            → propagate immediately; no key change

    Keys are NEVER logged. All log statements use only the slot number (1 or 2).
    """

    def __init__(
        self,
        key1: str,
        key2: str | None = None,
        *,
        cooldown_seconds: float = _DEFAULT_COOLDOWN,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
    ) -> None:
        if not key1:
            raise ValueError("GROQ_API_KEY_1 is required when AI_PROVIDER=groq")
        self._keys: list[tuple[str, _KeyState]] = [(key1, _KeyState(slot=1))]
        if key2:
            self._keys.append((key2, _KeyState(slot=2)))
        self._preferred_idx: int = 0
        self._lock = threading.Lock()
        self._cooldown = cooldown_seconds
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def _healthy_order(self) -> list[int]:
        """Indices of available keys in preferred-first order. Called under self._lock."""
        for _, state in self._keys:
            state.try_recover()
        n = len(self._keys)
        return [
            (self._preferred_idx + i) % n
            for i in range(n)
            if self._keys[(self._preferred_idx + i) % n][1].healthy
        ]

    def call(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> tuple[dict, int]:
        """
        Execute one Groq API request with failover.
        Returns (response_body, key_slot_number).
        Raises a GroqError subclass when all options are exhausted.
        """
        with self._lock:
            slots = self._healthy_order()

        if not slots:
            raise GroqProviderError("all Groq keys are unhealthy or on cooldown")

        last_exc: GroqError | None = None
        fallback_attempted = False

        for slot_idx in slots:
            key, state = self._keys[slot_idx]
            slot_num = state.slot

            try:
                result = self._with_retry(
                    key=key, slot=slot_num, model=model, messages=messages, **kwargs
                )
                # Promote this slot to preferred if it differs (e.g. after fallback success)
                with self._lock:
                    if self._preferred_idx != slot_idx:
                        logger.info(
                            "groq key_slot=%d succeeded (fallback=%s); now preferred",
                            slot_num, fallback_attempted,
                        )
                        self._preferred_idx = slot_idx
                return result, slot_num

            except GroqMalformedError:
                # Model issue — propagate immediately, no key change
                raise

            except GroqAuthError as exc:
                logger.warning(
                    "groq key_slot=%d auth failure (status=%s); marking unhealthy",
                    slot_num, exc.status,
                )
                with self._lock:
                    state.mark_unhealthy(self._cooldown)
                    if self._preferred_idx == slot_idx and len(self._keys) > 1:
                        self._preferred_idx = (slot_idx + 1) % len(self._keys)
                last_exc = exc
                fallback_attempted = True
                continue

            except GroqRateLimitError as exc:
                logger.warning(
                    "groq key_slot=%d rate limited; retry_after=%.1fs",
                    slot_num, exc.retry_after or 0.0,
                )
                if exc.retry_after and exc.retry_after > 0:
                    # Honour Retry-After — do not spin through keys to evade limits
                    raise
                # No Retry-After → try other key once, then give up
                last_exc = exc
                if fallback_attempted:
                    break
                fallback_attempted = True
                continue

            except GroqProviderError as exc:
                logger.warning(
                    "groq key_slot=%d provider error after retries; trying next if available",
                    slot_num,
                )
                with self._lock:
                    state.mark_unhealthy(self._cooldown / _TEMP_FAILURE_COOLDOWN_DIVISOR)
                last_exc = exc
                fallback_attempted = True
                continue

        raise last_exc or GroqProviderError("all Groq keys exhausted")

    def _with_retry(
        self, *, key: str, slot: int, model: str, messages: list[dict], **kwargs: Any
    ) -> dict:
        """Bounded exponential backoff for transient failures on a single key."""
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._http_post(key=key, model=model, messages=messages, **kwargs)
            except (GroqAuthError, GroqRateLimitError, GroqMalformedError):
                raise  # These are not transient — don't retry
            except GroqProviderError as exc:
                logger.info(
                    "groq key_slot=%d attempt=%d/%d transient failure",
                    slot, attempt, self._max_retries,
                )
                last_exc = exc
                if attempt < self._max_retries:
                    delay = min(self._backoff_base * (2 ** (attempt - 1)), 10.0)
                    time.sleep(delay)
        raise last_exc or GroqProviderError("max retries exceeded")

    def _http_post(self, *, key: str, model: str, messages: list[dict], **kwargs: Any) -> dict:
        """Single HTTPS POST to Groq. Authorization header is NEVER included in logs."""
        try:
            with httpx.Client(timeout=self._timeout, verify=True) as client:
                resp = client.post(
                    _GROQ_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {key}",  # key never reaches logger
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, **kwargs},
                )
        except httpx.TimeoutException as exc:
            raise GroqProviderError("Groq request timed out") from exc
        except httpx.RequestError as exc:
            raise GroqProviderError("Groq connection error") from exc

        status = resp.status_code

        if status == 200:
            try:
                return resp.json()
            except Exception as exc:
                raise GroqMalformedError("Groq response is not valid JSON") from exc

        if status in (401, 403):
            raise GroqAuthError("Groq authentication failed", status=status)

        if status == 429:
            retry_after: float | None = None
            for hdr in ("Retry-After", "x-ratelimit-reset-requests"):
                raw = resp.headers.get(hdr)
                if raw:
                    try:
                        retry_after = float(raw)
                    except (ValueError, TypeError):
                        pass
                    break
            raise GroqRateLimitError("Groq rate limit exceeded", status=429, retry_after=retry_after)

        if status >= 500:
            raise GroqProviderError(f"Groq server error {status}", status=status)

        raise GroqProviderError(f"Groq unexpected HTTP {status}", status=status)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an AI assistant for a loan data verification console. "
    "Your role is to provide ADVISORY analysis to human reviewers. "
    "You NEVER make final decisions. All output is advisory only and subject to mandatory "
    "human review and approval before any action is taken. "
    "AI cannot verify loans, approve loans, or modify canonical loan data. "
    "Respond with valid JSON only — no prose outside the JSON object."
)

_KIND_SCHEMA: dict[str, str] = {
    "explain": (
        'Return JSON: {"kind":"explain","explanation":"<string>",'
        '"severity_opinion":"<low|medium|high>","evidence":["<string>",...]}'
    ),
    "suggest_correction": (
        'Return JSON: {"kind":"suggest_correction","field":"<field_name or null>",'
        '"current_value":"<string or null>","suggested_value":"<string or null>",'
        '"rationale":"<string>","confidence":"<low|medium|high>"}'
    ),
    "resolve_conflict": (
        'Return JSON: {"kind":"resolve_conflict","field":"<field>",'
        '"values":[{"source":"<name>","value":"<v>","last_updated_at":"<iso>"}],'
        '"recommended_value":"<value or null>","rationale":"<string>"}'
    ),
    "reviewer_note": (
        'Return JSON: {"kind":"reviewer_note","note":"<string>"}'
    ),
    "classify_severity": (
        'Return JSON: {"kind":"classify_severity","deterministic_severity":"<current>",'
        '"suggested_severity":"<low|medium|high>","agrees_with_engine":true|false,'
        '"rationale":"<string>","advisory":true,"note":"<string or null>"}'
    ),
    "nl_rule_generation": (
        'Return JSON: {"kind":"nl_rule_generation","natural_language_input":"<input>",'
        '"generated_rules":[{"rule_id":"<id>","field":"<field>","operator":"<op>",'
        '"severity":"<low|medium|high>","message":"<string>"}],'
        '"explanation":"<string>","advisory":true,"note":"<string or null>"}'
    ),
}


def _build_prompt(kind: str, context: dict) -> str:
    schema_instr = _KIND_SCHEMA.get(kind, "Return valid JSON for the requested task.")
    ctx_json = json.dumps(context, default=str)
    return f"{schema_instr}\n\nContext:\n{ctx_json}"


def _parse_content(kind: str, content: str) -> dict:
    """Extract and parse JSON from model response. Raises GroqMalformedError on failure."""
    text = content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
        text = "\n".join(inner).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GroqMalformedError(f"model returned invalid JSON for kind={kind}") from exc
    if not isinstance(data, dict):
        raise GroqMalformedError(f"model returned non-object JSON for kind={kind}")
    data.setdefault("kind", kind)
    return data


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------

class GroqProvider(AIProvider):
    """
    Real Groq provider implementing the AIProvider ABC.

    Uses GroqKeyManager for dual-key failover. All AI safety invariants are
    preserved — output is advisory only; canonical data is never mutated here.
    """

    name = "groq"

    def __init__(self, key_manager: GroqKeyManager, model: str = _DEFAULT_MODEL) -> None:
        self._km = key_manager
        self.model = model

    def generate(self, kind: str, context: dict[str, Any]) -> AIResult:
        prompt_text = _build_prompt(kind, context)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ]
        t0 = time.monotonic()

        try:
            raw, key_slot = self._km.call(
                self.model, messages, temperature=0.1, max_tokens=512
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            content = raw["choices"][0]["message"]["content"]
            output = _parse_content(kind, content)  # may raise GroqMalformedError
            return AIResult(
                kind=kind,
                output=output,
                model=self.model,
                provider=self.name,
                prompt=f"[groq:{kind}] key_slot={key_slot}",
                created_at=datetime.now(UTC).isoformat(),
                latency_ms=latency_ms,
                degraded=False,
                suggested_field=output.get("field"),
                suggested_value=output.get("suggested_value"),
            )

        except GroqMalformedError:
            # Model output issue — log and degrade; no key was rotated by key manager
            logger.warning("groq malformed model output for kind=%s; degrading", kind)
            return self._degraded(kind, int((time.monotonic() - t0) * 1000))

        except (GroqError, Exception):  # noqa: BLE001
            # All keys exhausted or unexpected error — degrade gracefully
            return self._degraded(kind, int((time.monotonic() - t0) * 1000))

    def _degraded(self, kind: str, latency_ms: int) -> AIResult:
        return AIResult(
            kind=kind,
            output={
                "kind": kind,
                "degraded": True,
                "message": "Groq AI assistance temporarily unavailable. Review manually.",
            },
            model=self.model,
            provider=self.name,
            prompt=f"[groq:{kind}] degraded",
            created_at=datetime.now(UTC).isoformat(),
            latency_ms=latency_ms,
            degraded=True,
        )


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_groq_provider(settings) -> GroqProvider:
    """Construct a GroqProvider from application settings. Raises ValueError if misconfigured."""
    key1: str = getattr(settings, "groq_api_key_1", "") or ""
    key2: str | None = getattr(settings, "groq_api_key_2", "") or None
    model: str = getattr(settings, "groq_model", _DEFAULT_MODEL) or _DEFAULT_MODEL
    timeout: float = float(getattr(settings, "groq_timeout_seconds", _DEFAULT_TIMEOUT))
    max_retries: int = int(getattr(settings, "groq_max_retries", _DEFAULT_MAX_RETRIES))
    backoff: float = float(getattr(settings, "groq_backoff_base_seconds", _DEFAULT_BACKOFF_BASE))

    if not key1:
        raise ValueError(
            "AI_PROVIDER=groq requires GROQ_API_KEY_1. "
            "Set it in .env or fall back to AI_PROVIDER=mock."
        )

    km = GroqKeyManager(
        key1, key2,
        timeout_seconds=timeout,
        max_retries=max_retries,
        backoff_base=backoff,
    )
    return GroqProvider(km, model=model)
