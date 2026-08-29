"""Tests for Groq dual-key failover provider.

All tests are deterministic — no real Groq credentials required.

Patching contract
-----------------
_http_post(self, *, key, model, messages, **kw) → parsed dict or raises GroqError subclass.
Callers: _with_retry → call.  call returns (raw_dict, slot_num).
GroqProvider.generate() calls km.call() — patch km.call to test generate() in isolation.

Scenarios covered:
  1.  key1 success → key2 not used
  2.  key1 auth failure → key2 used (fallback)
  3.  key1 timeout → retries → key2 used when retries exhausted
  4.  key1 5xx → bounded retry → fallback to key2
  5.  429 with Retry-After → no rapid key cycling; raises immediately
  6.  all keys unavailable → clean degraded response from GroqProvider
  7.  malformed model output → no key rotation
  8.  key recovery after cooldown
  9.  concurrent requests → consistent key state
 10.  no secret leakage in logs
 11.  Mock provider completely unchanged
 12.  AI no-mutation invariant still passes
"""
from __future__ import annotations

import logging
import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ai.groq_provider import (
    GroqAuthError,
    GroqKeyManager,
    GroqMalformedError,
    GroqProvider,
    GroqProviderError,
    GroqRateLimitError,
    _KeyState,
    build_groq_provider,
)
from app.ai.provider import AIResult, MockAIProvider, get_ai_provider


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_GOOD_RESPONSE_BODY = {
    "choices": [{"message": {"content": '{"kind":"explain","explanation":"Test.","evidence":[]}'}}]
}

_SUGGEST_RESPONSE_BODY = {
    "choices": [{
        "message": {
            "content": (
                '{"kind":"suggest_correction","field":"current_balance",'
                '"current_value":"350000","suggested_value":"300000",'
                '"rationale":"Cap at principal.","confidence":"high"}'
            )
        }
    }]
}


def _km(key1="k1", key2="k2", *, max_retries=1, backoff_base=0.0, cooldown=999.0):
    """Key manager with near-zero backoff so tests run fast."""
    return GroqKeyManager(
        key1, key2,
        max_retries=max_retries,
        backoff_base=backoff_base,
        cooldown_seconds=cooldown,
    )


# ---------------------------------------------------------------------------
# 1. key1 success → key2 not used
# ---------------------------------------------------------------------------

def test_key1_success_key2_not_called():
    """When key1 succeeds, key2 must never be tried."""
    km = _km()
    keys_used = []

    def fake_http_post(**kwargs):
        keys_used.append(kwargs["key"])
        return _GOOD_RESPONSE_BODY

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        raw, slot = km.call("model", [{"role": "user", "content": "hi"}])

    assert slot == 1
    assert len(keys_used) == 1
    assert "k2" not in keys_used, "key2 must not be used when key1 succeeds"
    assert raw == _GOOD_RESPONSE_BODY


# ---------------------------------------------------------------------------
# 2. key1 auth failure → key2 used
# ---------------------------------------------------------------------------

def test_key1_auth_failure_fallback_to_key2():
    """401 on key1 → key1 marked unhealthy → key2 tried and succeeds."""
    km = _km()

    def fake_http_post(**kwargs):
        if kwargs["key"] == "k1":
            raise GroqAuthError("auth failed", status=401)
        return _GOOD_RESPONSE_BODY

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        raw, slot = km.call("model", [])

    assert slot == 2
    assert raw == _GOOD_RESPONSE_BODY
    assert not km._keys[0][1].healthy  # key1 marked unhealthy
    assert km._preferred_idx == 1      # key2 now preferred


# ---------------------------------------------------------------------------
# 3. key1 timeout → retries exhausted → falls back to key2
# ---------------------------------------------------------------------------

def test_key1_timeout_retry_then_fallback():
    """Timeout on key1 retried max_retries times, then falls back to key2."""
    km = _km(max_retries=2)
    calls = []

    def fake_http_post(**kwargs):
        calls.append(kwargs["key"])
        if kwargs["key"] == "k1":
            raise GroqProviderError("Groq request timed out")
        return _GOOD_RESPONSE_BODY

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        raw, slot = km.call("model", [])

    assert slot == 2
    assert calls.count("k1") == 2  # max_retries=2 attempts on key1
    assert calls.count("k2") == 1


# ---------------------------------------------------------------------------
# 4. key1 5xx → bounded retry → fallback to key2
# ---------------------------------------------------------------------------

def test_key1_5xx_bounded_retry_then_fallback():
    """503 from key1 → retried max_retries times → falls over to key2."""
    km = _km(max_retries=2)
    k1_calls = [0]

    def fake_http_post(**kwargs):
        if kwargs["key"] == "k1":
            k1_calls[0] += 1
            raise GroqProviderError("Groq server error 503", status=503)
        return _GOOD_RESPONSE_BODY

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        raw, slot = km.call("model", [])

    assert slot == 2
    assert k1_calls[0] == 2  # exactly max_retries attempts on key1


# ---------------------------------------------------------------------------
# 5a. 429 with Retry-After → raises immediately, no key cycling
# ---------------------------------------------------------------------------

def test_429_with_retry_after_raises_immediately():
    """429 + Retry-After header must raise without switching to key2."""
    km = _km()

    def fake_http_post(**kwargs):
        raise GroqRateLimitError("rate limited", status=429, retry_after=30.0)

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        with pytest.raises(GroqRateLimitError) as exc_info:
            km.call("model", [])

    assert exc_info.value.retry_after == 30.0
    # key1 must still be healthy — 429 is not a permanent auth failure
    assert km._keys[0][1].healthy


# ---------------------------------------------------------------------------
# 5b. 429 without Retry-After → may try key2, then gives up
# ---------------------------------------------------------------------------

def test_429_no_retry_after_tries_key2_at_most_once():
    """429 with no Retry-After may cycle once but must not loop indefinitely."""
    km = _km()
    calls = []

    def fake_http_post(**kwargs):
        calls.append(kwargs["key"])
        raise GroqRateLimitError("rate limited", status=429, retry_after=None)

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        with pytest.raises(GroqRateLimitError):
            km.call("model", [])

    assert calls.count("k2") <= 1  # key2 tried at most once


# ---------------------------------------------------------------------------
# 6. all keys unavailable → clean degraded from GroqProvider
# ---------------------------------------------------------------------------

def test_both_keys_unhealthy_call_raises():
    """When both keys are unhealthy, call() raises GroqProviderError."""
    km = _km(cooldown=999.0)
    km._keys[0][1].mark_unhealthy(999.0)
    km._keys[1][1].mark_unhealthy(999.0)

    with pytest.raises(GroqProviderError, match="unhealthy"):
        km.call("model", [])


def test_groq_provider_degrades_when_all_keys_fail():
    """GroqProvider.generate() returns a degraded AIResult when all keys fail."""
    km = _km(cooldown=999.0)
    km._keys[0][1].mark_unhealthy(999.0)
    km._keys[1][1].mark_unhealthy(999.0)

    result = GroqProvider(km).generate("explain", {"rule_id": "x", "field": "f"})

    assert isinstance(result, AIResult)
    assert result.degraded is True
    assert "message" in result.output


# ---------------------------------------------------------------------------
# 7. malformed model output → no key rotation
# ---------------------------------------------------------------------------

def test_malformed_json_from_model_raises_without_key_switch():
    """GroqMalformedError propagates from _http_post and does NOT rotate keys."""
    km = _km()

    def fake_http_post(**kwargs):
        raise GroqMalformedError("Groq response is not valid JSON")

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        with pytest.raises(GroqMalformedError):
            km.call("model", [])

    # key1 must still be healthy — malformed output is a model problem
    assert km._keys[0][1].healthy
    assert km._preferred_idx == 0


def test_groq_provider_degrades_gracefully_on_malformed_output():
    """GroqProvider.generate() degrades (no exception) when model output is unparseable."""
    km = _km()

    bad_body = {
        "choices": [{"message": {"content": "<<<not json>>>"}}]
    }

    with patch.object(km, "call", return_value=(bad_body, 1)):
        result = GroqProvider(km).generate("explain", {})

    assert result.degraded is True
    assert km._keys[0][1].healthy  # key state untouched


# ---------------------------------------------------------------------------
# 8. key recovery after cooldown
# ---------------------------------------------------------------------------

def test_key_state_recovers_after_cooldown():
    """A key marked unhealthy becomes healthy again after cooldown expires."""
    state = _KeyState(slot=1)
    state.mark_unhealthy(0.01)
    assert not state.healthy
    time.sleep(0.05)
    state.try_recover()
    assert state.healthy


def test_key_manager_uses_recovered_key():
    """After cooldown, the recovered key is picked again as preferred."""
    km = _km(cooldown=0.01)
    km._keys[0][1].mark_unhealthy(0.01)
    time.sleep(0.05)

    def fake_http_post(**kwargs):
        return _GOOD_RESPONSE_BODY

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        _, slot = km.call("model", [])

    assert slot == 1


# ---------------------------------------------------------------------------
# 9. concurrent requests → consistent key state
# ---------------------------------------------------------------------------

def test_concurrent_requests_no_race_condition():
    """20 concurrent threads must not corrupt key state or lose results."""
    km = _km(max_retries=1)
    results = []
    errors = []

    def fake_http_post(**kwargs):
        return _GOOD_RESPONSE_BODY

    def worker():
        try:
            _, slot = km.call("model", [])
            results.append(slot)
        except Exception as exc:
            errors.append(exc)

    with patch.object(km, "_http_post", side_effect=fake_http_post):
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

    assert not errors, f"Unexpected thread errors: {errors}"
    assert len(results) == 20
    assert all(s in (1, 2) for s in results)


# ---------------------------------------------------------------------------
# 10. no secret leakage in logs
# ---------------------------------------------------------------------------

def test_no_secret_leakage_in_logs(caplog):
    """API keys must never appear in any log record."""
    secret1 = "gsk_SUPER_SECRET_KEY_ONE_12345678"
    secret2 = "gsk_SUPER_SECRET_KEY_TWO_87654321"

    km = GroqKeyManager(secret1, secret2, cooldown_seconds=0.01, max_retries=1, backoff_base=0.0)

    def fake_http_post(**kwargs):
        raise GroqAuthError("auth failed", status=401)

    with caplog.at_level(logging.DEBUG):
        with patch.object(km, "_http_post", side_effect=fake_http_post):
            try:
                km.call("model", [])
            except Exception:
                pass

    log_text = caplog.text
    assert secret1 not in log_text, "key1 leaked into logs"
    assert secret2 not in log_text, "key2 leaked into logs"
    # Slot number (not key value) is permitted in logs
    assert "key_slot=" in log_text


# ---------------------------------------------------------------------------
# 11. Mock provider completely unchanged
# ---------------------------------------------------------------------------

def test_mock_provider_explain_unchanged():
    """MockAIProvider explain kind still works correctly."""
    mock = MockAIProvider()
    result = mock.generate("explain", {
        "rule_id": "balance_gt_principal",
        "field": "current_balance",
        "observed_value": "350000",
        "severity": "high",
        "message": "Balance exceeds principal",
        "loan": {"original_principal": "300000"},
    })
    assert result.degraded is False
    assert result.provider == "mock"
    assert "explanation" in result.output
    assert result.output["kind"] == "explain"


def test_mock_provider_all_six_kinds_work():
    """All 6 AI kinds remain functional on MockAIProvider."""
    mock = MockAIProvider()
    context = {
        "rule_id": "source_conflict", "field": "current_balance",
        "observed_value": "100", "severity": "high",
        "message": "conflict", "loan": {},
        "values": [
            {"source": "loan_tape", "value": "100", "last_updated_at": "2024-01-01"},
            {"source": "servicer_feed", "value": "110", "last_updated_at": "2024-06-01"},
        ],
        "natural_language": "flag interest rate above 30%",
        "stats": {"total": 5, "by_severity": {"high": 2}},
    }
    for kind in ("explain", "suggest_correction", "resolve_conflict",
                 "reviewer_note", "classify_severity", "nl_rule_generation"):
        r = mock.generate(kind, context)
        assert not r.degraded, f"MockAIProvider degraded unexpectedly for kind={kind}"


def test_get_ai_provider_defaults_to_mock():
    """get_ai_provider returns MockAIProvider when ai_provider is 'mock'."""
    settings = MagicMock()
    settings.ai_provider = "mock"
    assert isinstance(get_ai_provider(settings), MockAIProvider)


def test_get_ai_provider_groq_missing_key_falls_back_to_mock():
    """AI_PROVIDER=groq with no key1 → graceful fallback to Mock, no crash."""
    settings = MagicMock()
    settings.ai_provider = "groq"
    settings.groq_api_key_1 = ""
    settings.groq_api_key_2 = ""
    settings.groq_model = "llama-3.3-70b-versatile"
    settings.groq_timeout_seconds = 20
    settings.groq_max_retries = 2
    settings.groq_backoff_base_seconds = 1.0
    assert isinstance(get_ai_provider(settings), MockAIProvider)


def test_get_ai_provider_groq_with_key_returns_groq_provider():
    """AI_PROVIDER=groq with a key → returns GroqProvider."""
    settings = MagicMock()
    settings.ai_provider = "groq"
    settings.groq_api_key_1 = "gsk_valid_key_placeholder"
    settings.groq_api_key_2 = ""
    settings.groq_model = "llama-3.3-70b-versatile"
    settings.groq_timeout_seconds = 20
    settings.groq_max_retries = 2
    settings.groq_backoff_base_seconds = 1.0
    assert isinstance(get_ai_provider(settings), GroqProvider)


# ---------------------------------------------------------------------------
# 12. AI no-mutation invariant — GroqProvider returns advisory AIResult only
# ---------------------------------------------------------------------------

def test_groq_provider_output_is_advisory_airesult():
    """GroqProvider.generate() returns an AIResult, not a DB write or model change."""
    km = _km()

    with patch.object(km, "call", return_value=(_SUGGEST_RESPONSE_BODY, 1)):
        result = GroqProvider(km).generate("suggest_correction", {
            "rule_id": "balance_gt_principal",
            "field": "current_balance",
            "observed_value": "350000",
            "loan": {"original_principal": "300000"},
        })

    assert isinstance(result, AIResult)
    assert result.provider == "groq"
    assert result.degraded is False
    # Advisory fields populated from model output
    assert result.suggested_field == "current_balance"
    assert result.suggested_value == "300000"
    # Output is a plain dict — no DB session, no canonical write
    assert isinstance(result.output, dict)
    assert result.output.get("kind") == "suggest_correction"


def test_groq_provider_cannot_bypass_advisory_boundary():
    """GroqProvider has no method that writes to a database or modifies canonical data.
    Structural check: the only public method is generate(), which returns AIResult."""
    provider = GroqProvider(_km())
    public_methods = [m for m in dir(provider) if not m.startswith("_")]
    writable_names = {"save", "write", "update", "commit", "delete", "approve", "reject"}
    overlap = writable_names & set(public_methods)
    assert not overlap, f"GroqProvider exposes mutation methods: {overlap}"
