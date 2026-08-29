# LoanTrust Copilot — Documentation Index

Foundation docs for the Intain Full Stack Track "Loan Data Verification Copilot".
**Loop 1 status: architecture & planning complete. No business logic implemented yet.**

## Read in this order
1. [architecture.md](architecture.md) — system context, modular-monolith components, sync/async, AI trust boundaries, audit & hashing, failure handling.
2. [data-lifecycle.md](data-lifecycle.md) — 3 immutability layers, raw→verified lineage, normalization contract, 15 issue classes.
3. [system-state-machine.md](system-state-machine.md) — loan states, allowed/forbidden transitions, roles, audit events.
4. [architecture-decisions.md](architecture-decisions.md) — ADR-001..011 with trade-offs and reconsideration triggers.
5. [requirements-traceability.md](requirements-traceability.md) — every PS requirement → component/API/DB/UI/test/demo/status.
6. [scaling-strategy.md](scaling-strategy.md) — keep-simple posture, indexes, scaling ladder with explicit triggers.
7. [devops-plan.md](devops-plan.md) — environments, compose, env vars, migrations, seed, demo-reset, health, CI.
8. [test-strategy.md](test-strategy.md) — pyramid, 15 golden fixtures, invariant tests, AI mock testing.
9. [risk-register.md](risk-register.md) — Phase D self-review across 6 lenses, P0 mitigations.
10. [task-ledger.md](task-ledger.md) — P0/P1/P2 scope + numbered vertical slices (roadmap).
11. [ai-development-log.md](ai-development-log.md) — required agentic-coding evidence (living).
12. [demo-readiness.md](demo-readiness.md) — the 14-step ≤5-min demo script.

Reference: [reference/problem-statement-extracted.txt](reference/problem-statement-extracted.txt) — authoritative requirements extracted from the Intain PDF.

## Core invariants (non-negotiable)
- Deterministic validation is the source of truth; **AI is advisory and never mutates canonical data**.
- Raw source data is preserved immutably; verified records are immutable, versioned, hashed snapshots.
- Every important state change emits an audit event in the same transaction.
- The app remains fully usable if the AI provider fails (Mock provider is the default).

## Next loop
Implement **Slice 0 — Foundation & Skeleton** (see task-ledger.md), then stop for review.
