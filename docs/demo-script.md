# LoanTrust Copilot — 5-Minute Demo Script

> **Setup**: `make demo-reset` then open the app. All data is deterministic.
> **AI**: Mock mode (zero credentials, fully offline, deterministic output).

---

## 0:00–0:20 · Problem Statement (spoken)

> "Financial institutions receive loan data from multiple sources — origination systems, servicer feeds — and it arrives messy. Fields are wrong, sources disagree, dates are malformed. Manually reviewing thousands of records is slow and error-prone.
>
> LoanTrust Copilot is a loan data verification console. It ingests raw CSVs, preserves them immutably, normalizes to a canonical 21-field model, runs 15 deterministic validation rules, flags exceptions, and routes them to human reviewers — with AI assistance — producing verified, hashed, auditable records."

---

## 0:20–1:00 · Data Operator — Upload & Ingest

**[Log in as Data Operator]**

- Click **"Data Operator"** demo button on the login page.
- Note the dashboard: _Uploads_, _Records imported_, _Needs attention_ stats.

**[Upload loan tape]**

- Select `data/raw/loan_tape.csv` (1,000 rows).
- Click **"Upload & ingest"**.
- Show the result: "Imported **1000** / 1000 rows · failed 0".
- Point to the `file sha-256` hash: **"Raw evidence is cryptographically preserved."**

**[Upload servicer feed]**

- Select `data/raw/servicer_update.csv`.
- Click **"Upload servicer feed"**.
- Explain: **"Second source — servicer data is compared field-by-field."**

**[Run validation]**

- Click **"Run validation"**.
- Show result: N high · N medium · N low exceptions.
- Open "Records needing attention" — show normalization failures (e.g., malformed dates).

---

## 1:00–1:30 · Operator → Dashboard summary

- Stat cards update: exceptions counted by severity.
- Explain: **"The system found 15 classes of data quality issues deterministically — no AI needed for detection."**

---

## 1:30–2:40 · Reviewer — Exception Triage & AI Assistance

**[Log out → Log in as Reviewer]**

- Exception Queue shows open items filtered by severity.
- Filter to **High** severity — show the queue shrinking.

**[Open a source_conflict exception]**

- Select a `source_conflict` exception (loan tape vs servicer feed disagree).
- Show the detail panel hierarchy:
  1. **Severity / Status / Rule** — labeled clearly.
  2. **"Why did this fail?"** — deterministic rule message.
  3. **Canonical value** and **Observed value** (the conflict).
  4. **Source Evidence** — raw → canonical provenance panel.

**[Request AI assistance]**

- Click **"compare sources"** — AI returns a side-by-side comparison of loan_tape vs servicer_feed values.
- Show the **"advisory only"** badge. **"AI cannot decide — it informs."**
- Click **"classify severity"** — AI confirms or questions the deterministic severity (advisory only).

**[AI panel is separate from decision]**

- Point out: AI Copilot section is visually separate from Human Decision section.
- "AI assistance is logged — every interaction has a model/provider/timestamp audit trail."

---

## 2:40–3:20 · Reviewer — Human Decision

**[Make the decision]**

- Click **"Start review"** to mark in-progress.
- Add a reviewer comment: "Confirmed — servicer feed is more recent."
- Click **"Approve loan"** → loan status updates.
- Click **"Verify loan"** → system creates an immutable verified record.
- Show success: "Verified v1 · hash abc123…"

**[Key point]**

> "The human made the decision. AI assisted. The verified record captures the complete audit chain — who, what, when, why."

---

## 3:20–3:50 · Data Consumer — Verified Records

**[Log out → Log in as Data Consumer]**

- Verified Records list: 3+ loans with **VERIFIED** badge, version, and hash prefix.
- Click the first verified loan.

**[Show integrity proof]**

- VERIFIED header (green) with version number.
- `record hash:` — full SHA-256 hash. **"Reproducible — hash the canonical snapshot any time."**
- Verified by / Verified at — complete audit.

---

## 3:50–4:30 · Consumer — Traceability Chain

**[Click "Inspect traceability"]**

Walk the 8-step lineage:

```
1. Source file      — loan_tape.csv · sha256 95b7a854…
2. Raw record       — row 3 · immutable row hash
3. Normalization    — 21 fields canonical with provenance
4. Validation       — rules evaluated, 0 findings (clean)
5. Exceptions       — none — clean record
6. AI               — 0 AI interactions
7. Review decisions — 1 human decision
8. Verified version — v1 · hash 12259e2d…
```

> "Every step is traceable. You can reconstruct the path from raw source file to verified output."

**[Export]**

- Click **"Export CSV"** or **"Export JSON"** — download begins immediately.

---

## 4:30–4:50 · Backend API & AI Evidence

**[Open browser DevTools or Postman]**

- `GET /verified-loans` — paginated list with hashes.
- `GET /verified-loans/:id` — snapshot + validation_summary.
- `GET /trace/:loan_pk` — full lineage object.
- `GET /export?format=csv` — streaming export.

**[Show AI audit]**

- `GET /ai/logs/:id` — every AI call logged with provider, model, prompt, latency, degraded flag.
- "AI provider is behind an abstraction — swap Mock for real Anthropic with one env var."

---

## 4:50–5:00 · Close

> "LoanTrust Copilot gives you:
>
> — **Deterministic validation** across 15 data quality classes
> — **Advisory AI** that assists but never decides
> — **Human-in-the-loop** review with full audit trail
> — **Cryptographically hashed** verified records
> — **Complete traceability** from raw source to verified output
>
> Messy data in. Verified, auditable, trustworthy data out."

---

## Quick Reference

| Role | Email | Password |
|------|-------|----------|
| Data Operator | operator@loantrust.demo | operator123 |
| Reviewer | reviewer@loantrust.demo | reviewer123 |
| Data Consumer | consumer@loantrust.demo | consumer123 |

**One-command reset**: `make demo-reset`
**Demo URL**: `http://localhost:5173`
**API docs**: `http://localhost:8000/docs`
