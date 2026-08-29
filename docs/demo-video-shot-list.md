# LoanTrust Copilot — Demo Video Shot List

**Target length:** ≤5 minutes  
**Setup:** `make demo-reset` before recording. Use `http://localhost:8080`.  
**AI:** Mock mode (offline, deterministic — no key needed).

---

## Pre-recording checklist

- [ ] `make demo-reset` completed (fresh seed, 1000 loans, 15 issue classes)
- [ ] Browser at `http://localhost:8080` (full-screen, 1080p or higher)
- [ ] Postman / browser DevTools open in a second tab (for API shot)
- [ ] `docs/ai-development-log.md` open in a third tab (for agentic evidence shot)
- [ ] Screen recorder capturing browser + audio
- [ ] Timer visible to stay under 5:00

---

## Shot 1 — Product Intro  `0:00–0:20`

**Screen:** Login page at `http://localhost:8080`

**Narrate:**
> "Financial institutions receive messy loan data from multiple sources — origination systems, servicer feeds. Fields are wrong, sources conflict, dates malformed. LoanTrust Copilot ingests raw CSVs, validates 15 data quality classes deterministically, routes exceptions to human reviewers with AI assistance, and produces immutable, auditable verified records."

**Show:** Login page with three role buttons visible.

---

## Shot 2 — Operator Login  `0:20–0:35`

**Screen:** Login → Data Operator dashboard

**Action:**
1. Click "Data Operator" preset or enter `operator@loantrust.demo` / `operator123`
2. Login → Operator dashboard

**Show:** Dashboard stat cards — uploads, records imported, needs attention, corrections needed.

---

## Shot 3 — Upload Loan Tape  `0:35–1:00`

**Screen:** Operator upload panel

**Action:**
1. Select `data/raw/loan_tape.csv` (1,000 rows)
2. Click "Upload & ingest"
3. Show result: "Imported **1000** / 1000 rows · failed 0"

**Narrate:**
> "1,000 rows imported. The file SHA-256 hash is recorded — raw evidence is cryptographically preserved and never modified."

**Show:** File hash value in the upload summary.

---

## Shot 4 — Servicer Feed Upload  `1:00–1:15`

**Screen:** Operator servicer upload

**Action:**
1. Select `data/raw/servicer_update.csv`
2. Click "Upload servicer feed"

**Narrate:**
> "A second source — servicer data. The engine compares fields from both sources to detect conflicts."

---

## Shot 5 — Validation Summary  `1:15–1:40`

**Screen:** Operator → Run validation → results

**Action:**
1. Click "Run validation"
2. Show exception counts by severity and type

**Narrate:**
> "760 exceptions across 15 issue classes: source conflicts, missing fields, invalid dates, balance violations, duplicate IDs. Deterministic — no AI needed for detection."

**Show:** Exception breakdown table (all 15 types visible or mention them).

---

## Shot 6 — Reviewer Login + Exception Queue  `1:40–2:10`

**Screen:** Reviewer dashboard

**Action:**
1. Log out → log in as `reviewer@loantrust.demo` / `reviewer123`
2. Show exception queue with severity filters
3. Filter to **High** severity — queue narrows

**Narrate:**
> "The Reviewer sees the exception queue. Filter by severity, type, or search by loan ID."

---

## Shot 7 — Exception Detail + Evidence  `2:10–2:30`

**Screen:** Exception detail panel for a `source_conflict` exception

**Action:**
1. Click a `source_conflict` exception
2. Show the 5-section hierarchy:
   - Severity / Status pill
   - "Why did this fail?" — rule message
   - Canonical vs Observed values
   - Source Evidence (raw → canonical provenance)

**Narrate:**
> "The system shows exactly why the rule fired — raw source column, the transformation applied, and the canonical value. Full field-level provenance."

---

## Shot 8 — AI Assistance  `2:30–3:00`

**Screen:** AI Copilot section in exception detail

**Action:**
1. Click "compare sources" → AI returns side-by-side loan_tape vs servicer_feed comparison
2. Show the **"advisory only"** badge
3. Click "classify severity" → AI opinion on severity (advisory)

**Narrate:**
> "AI assists — it does not decide. Every AI call is logged with provider, model, prompt hash, and latency. The AI Copilot section is visually and architecturally separated from the Human Decision section."

**Show:** Advisory badge, model/timestamp info.

---

## Shot 9 — Human Decision + Verification  `3:00–3:30`

**Screen:** Human Decision section

**Action:**
1. Click "Start review" → status → in_review
2. Add comment: "Servicer feed is more recent — accepted"
3. Click "Approve loan"
4. Click "Verify loan"
5. Show: "Verified v1 · hash abc123…"

**Narrate:**
> "The human makes the decision. AI assisted, but the human approved. The verified record captures the complete audit chain — who, what, when, why — in a cryptographic snapshot."

---

## Shot 10 — Consumer Login + Verified Records  `3:30–3:50`

**Screen:** Consumer dashboard

**Action:**
1. Log out → log in as `consumer@loantrust.demo` / `consumer123`
2. Show verified records list with VERIFIED badges, versions, hash prefixes

**Narrate:**
> "The Data Consumer sees only verified records — never raw data. Quality score reflects the validated portfolio."

---

## Shot 11 — Record Hash + Integrity  `3:50–4:05`

**Screen:** Verified loan detail

**Action:**
1. Click a verified loan
2. Show VERIFIED header (green) + version number
3. Highlight `record hash:` — full SHA-256

**Narrate:**
> "The record hash is reproducible — hash the canonical snapshot any time and you get the same value. Tamper-evident."

---

## Shot 12 — Traceability Chain  `4:05–4:30`

**Screen:** 8-step traceability chain

**Action:**
1. Click "Inspect traceability"
2. Walk through the 8 steps:
   - Source file → Raw record → Normalization → Validation → Exceptions → AI → Review decisions → Verified version

**Narrate:**
> "Every step from raw CSV to verified output is traceable. A judge or auditor can follow the lineage field by field."

---

## Shot 13 — API Response  `4:30–4:45`

**Screen:** Browser DevTools Network tab or Postman

**Show:**
- `GET /verified-loans` → paginated list with hashes
- `GET /trace/:loan_pk` → full lineage object

**Narrate:**
> "The same traceability is exposed via REST API. Consumer systems can pull verified data programmatically."

---

## Shot 14 — AI Development Log  `4:45–5:00`

**Screen:** `docs/ai-development-log.md` (or shown in browser via GitHub/VS Code)

**Show:**
- Tools used section
- Representative prompts (8 listed)
- Rejected AI outputs section (7 examples with root causes)
- AI-generated % estimates per loop (90–95%)

**Narrate:**
> "The AI Development Log documents how Claude Code was used to build this system — representative prompts, AI-generated percentage, and — critically — 7 cases where AI output was rejected or corrected with documented reasons."

**Final line:**
> "LoanTrust Copilot: deterministic validation, advisory AI, human-in-the-loop review, cryptographic integrity. Messy data in — verified, auditable, trustworthy data out."

---

## Timing summary

| Shot | Topic | Start | End | Duration |
|------|-------|-------|-----|---------|
| 1 | Product intro | 0:00 | 0:20 | 0:20 |
| 2 | Operator login | 0:20 | 0:35 | 0:15 |
| 3 | Upload loan tape | 0:35 | 1:00 | 0:25 |
| 4 | Servicer upload | 1:00 | 1:15 | 0:15 |
| 5 | Validation summary | 1:15 | 1:40 | 0:25 |
| 6 | Reviewer + queue | 1:40 | 2:10 | 0:30 |
| 7 | Exception detail | 2:10 | 2:30 | 0:20 |
| 8 | AI assistance | 2:30 | 3:00 | 0:30 |
| 9 | Human decision + verify | 3:00 | 3:30 | 0:30 |
| 10 | Consumer dashboard | 3:30 | 3:50 | 0:20 |
| 11 | Record hash | 3:50 | 4:05 | 0:15 |
| 12 | Traceability chain | 4:05 | 4:30 | 0:25 |
| 13 | API response | 4:30 | 4:45 | 0:15 |
| 14 | AI development log | 4:45 | 5:00 | 0:15 |
| **TOTAL** | | | | **5:00** |

---

## Rubric talking points (hit these explicitly)

| Rubric category | Shot # | What to say |
|-----------------|--------|-------------|
| Completeness /20 | 1,5 | "All 8 modules implemented, 15 issue classes, 6 AI kinds, 3 role dashboards" |
| Backend /15 | 3,5 | "Stream-parse ingestion, SHA-256 hash, optimistic concurrency, 132 tests" |
| Frontend /15 | 6,7,10 | "Exception queue filters, 5-section reviewer workbench, 8-step traceability" |
| AI Quality /15 | 8 | "Advisory only, separate from human decision, every call logged, 6 kinds" |
| Agentic /15 | 14 | "AI Development Log: 8 prompts, 7 rejected outputs, 90-95% AI-generated" |
| Traceability /10 | 12 | "8-step chain, field-level provenance, reproducible hash" |
| Demo /10 | all | "One command setup, deterministic seed, Mock AI = no credentials needed" |

---

## Fallback plan

| Issue | Recovery |
|-------|---------|
| Frontend unresponsive | Show same step via Swagger at `http://localhost:8000/docs` |
| State polluted | `make demo-reset` (≤30s) — restores everything |
| AI returns wrong output | Expected — it's advisory; human overrides; good talking point |
| Hash looks different | Recompute: canonical JSON → SHA-256 — should match |
