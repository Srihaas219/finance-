# Demo Readiness (≤5 minutes)

> Mirrors PS §15 exactly. The whole system is optimized so this script runs deterministically with Mock AI and seeded data.
> See [`docs/demo-script.md`](demo-script.md) for the timed 5-minute script.

## Demo reliability engineering (2026-08-28 final)
Status of the seven reliability guarantees:
1. ✅ Fresh setup works — `docker compose up --build` verified (db+api+web on Postgres, migrations 0001→0008).
2. ✅ Seed users exist — 3 roles seeded idempotently on startup.
3. ✅ Predictable exceptions — deterministic synthetic tape: 1000 loans, all 15 PS issue classes, fixed seed.
4. ✅ One-command reset — `make demo-reset` / `docker compose down -v`.
5. ✅ AI mock mode — deterministic exception-aware Mock; **6 AI kinds** (explain/suggest/resolve_conflict/classify_severity/reviewer_note/nl_rule_generation); degraded path tested; no network needed.
6. ✅ No external dependency for core demo — all local; AI is Mock.
7. ✅ Critical-path coverage — **132 backend tests** + **1 Playwright browser E2E** (full Operator→Reviewer→Consumer journey on real backend, no mocked API responses).

**2026-08-28 state (final):** Playwright E2E passes (1.6s). 132 backend tests pass. Ruff clean. TypeScript clean. Frontend builds clean. All **6 AI kinds** work deterministically (`explain`/`suggest_correction`/`resolve_conflict`/`classify_severity`/`reviewer_note`/`nl_rule_generation`). NL rule generation added end-to-end: Mock keyword→skeleton, `POST /ai/nl-rule`, Reviewer panel UI. Architecture note deliverable created (`docs/architecture-note.md`). Sample output files created (`data/processed/sample_verified_loans.csv`, `data/processed/sample_audit_trail.json`). `classify_severity` advisory, never overwrites deterministic severity. Reviewer UX clear hierarchy (Exception → Why → Evidence → AI Copilot → Human Decision → History). Consumer 8-step traceability chain, VERIFIED header, SHA-256 hash visible.

**Live smoke evidence (2026-08-27, Postgres):** 1000 imported → validate {high 45, medium 24, low 184}, 14 classes → quality 76.5% → AI explain+suggest → human apply → verify v1 (hash `561a7047…`) → consumer export (CSV header OK) → trace (source→raw row 61→2 AI recs→4 decisions→verified v1) → audit shows loan.imported/ai.recommendation.generated/field.edited/exception.ignore/loan.approve/verified.created.

**Final Hardening smoke (2026-08-27, Postgres):** `make demo-seed` → 1000 loans + servicer feed + validation → **all 15 classes**, 759 open exceptions incl. 506 source_conflict, quality 50.7% → AI `resolve_conflict` on L00001 compares loan_tape vs servicer_feed and recommends → demo_seed idempotent (skips on re-run) → re-validation idempotent (759→759, no duplicates). One-command populate: `make demo-seed`; full reset+populate: `make demo-reset`.

## Pre-flight checklist
- [ ] `docker compose up --build` boots clean; `/readyz` (or `/ready`) green.
- [ ] `make demo-reset` run → deterministic seed loaded (fixed IDs/timestamps).
- [ ] `AI_PROVIDER=mock` (or real key present and tested).
- [ ] Test credentials for all 3 roles work (from `users.json`, listed in README).
- [ ] A known conflict/exception loan id noted for the AI step.
- [ ] Verified-record hash recompute snippet ready (to show reproducibility).

## The 14-step flow (with what to show)
1. **Log in as Data Operator.**
2. **Upload messy loan tape** (`loan_tape.csv`) — show upload accepted, file hash.
3. **Import + validation summary** — counts imported/failed; exceptions by type/severity; corrections-needed.
4. **Open records with validation failures** — loan detail showing the deterministic exception(s).
5. **Log in as Reviewer.** Show exception queue; filter by severity; search by loan/borrower id.
6. **Use AI to explain an exception** — AI panel returns explanation + (for the conflict loan) source comparison; show prompt/model/timestamp badge.
7. **Accept / edit / reject AI recommendation** — edit a suggested value, then apply → note it creates a *human* review decision, AI stays advisory.
8. **Approve or reject loan records** — approve the corrected loan.
9. **Create verified loan records** — snapshot created; show `record_hash`.
10. **Log in as Data Consumer.**
11. **Verified records dashboard** — data-quality score, verification history.
12. **Open one loan + inspect audit trail** — walk raw→normalized→validated→AI→decision→verified.
13. **Show API response for verified records** — `GET /verified-loans/:id` (and `/export`).
14. **Show AI Development Log** — prompts, rejected outputs, % estimate.

## Talking points to hit the rubric
- **Traceability (10):** in step 12, click a verified field back to the original raw cell; recompute the hash live.
- **AI quality (15):** in step 7, stress "AI never wrote the data — a human did; both are logged separately."
- **Agentic (15):** step 14 + this docs/ folder as evidence of AI-assisted engineering.
- **Completeness (20):** the whole thing runs from one command; nothing mocked except the AI provider (by design, for reliability).
- **Honest limitations:** production security, real OCR, real data connectors are out of scope (PS §16) — say so.

## Fallbacks if something fails live
- AI provider hiccup → already on Mock; if real, switch env to mock and `demo-reset`.
- State polluted → `make demo-reset` (≤5s) restores a clean run.
- FE issue → show the same step via API (`curl`/Swagger) as backup.

## Timing budget (≤5:00)
Operator 0:00–1:20 · Reviewer+AI 1:20–3:10 · Consumer+audit+API 3:10–4:30 · AI Dev Log 4:30–5:00.
