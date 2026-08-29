# Scaling Strategy

> Principle: KEEP SIMPLE now; MODULARIZE for likely change; DISTRIBUTE only when a concrete trigger fires. Current scale (1k–5k rows) needs none of the heavy machinery.

## Current posture (chosen)
- Modular monolith, single Postgres, synchronous processing, in-process rule engine.
- Vertical scale + correct indexes handle the competition dataset with large headroom.

## Indexing plan (cheap, do early)
- `raw_records(source_file_id, row_number)`; `raw_records(row_hash)`
- `loans(loan_id)` unique-ish (dupes are data, handle in app), `loans(borrower_id)`, `loans(status)`
- `exceptions(status, severity, type)`, `exceptions(loan_id)`
- `verified_loans(loan_id, version)` UNIQUE, `verified_loans(verified_at)`
- `audit_events(loan_id, occurred_at)`, `audit_events(event_type)`
- Duplicate detection composite key: `(borrower_id, original_principal, origination_date)`

## Scaling ladder & explicit triggers

| Stage | Trigger (measured) | Action | Cost |
|---|---|---|---|
| 0. Now | ≤5k rows, 1 concurrent import | Sync, single process | none |
| 1. Bigger files | Import >2s p95 **or** file >100k rows | Stream parse + `COPY` bulk insert; batch validation | low |
| 2. Slow AI batch | AI batch-summary >5s **or** blocks UI | Move AI calls to `arq` + Redis worker; poll job status | low-med |
| 3. Many concurrent users | API p95 >300ms under load | Horizontal API replicas behind LB; move sessions to stateless JWT (already) | med |
| 4. DB hot | DB CPU >70% sustained | Read replicas for consumer/export reads; connection pooler (pgbouncer) | med |
| 5. Domain team split | Independent deploy needed for ingestion/validation | Extract that module into its own service using the existing service interface | high |

**Do NOT** introduce Kafka, Kubernetes, microservices, or a distributed cache before Stage 3–5 triggers are observed. Each is called out as premature for this project.

## What makes future extraction cheap
- Modules already talk through service functions, not internals (ADR-001).
- AI already behind an interface (ADR-004) — can become a remote service unchanged.
- Stateless JWT auth — API replicas need no shared session store.
- Canonical hashing + append-only tables — safe to shard/replicate reads.

## Load expectations (back-of-envelope)
5k rows × ~21 fields × ~10 rules = ~1M rule evaluations per import — sub-second in Python for pure functions. AI is the only slow/external dependency, hence on-demand + async-ready.

---

## Scaling roadmap (Loop 3)

| Current scale | Architecture | Trigger (measured) | Next step |
|---|---|---|---|
| Hackathon (1k–5k rows) | Modular monolith + PostgreSQL, sync ingestion | current | Keep simple |
| Larger files (>100k rows) | Add background `worker` service | import p95 >2s **or** file >100k rows | Move ingestion/validation async (arq + Redis) |
| High concurrency | Multiple worker replicas | queue backlog grows / jobs wait | Dedicated queue + N workers |
| Large audit volume | Audit partitioning/archival | `audit_events` query p95 degrades | Partition by month / archive cold rows |
| Multiple teams | Service extraction | deployment coupling blocks a team | Extract one bounded module via its existing service interface |

None of the right-hand columns are built now — they are triggers to watch, not work to do.

## Scenario decisions (see ADR-012…017 for full rationale)
- **Large file (S1):** stay synchronous; stream-parse + batched bulk inserts (batch 1,000). Trigger to go async documented above. → ADR-012.
- **Duplicate upload (S2):** new logical `source_files` row marked `duplicate_of`, reuse raw evidence, warn in summary. → ADR-013.
- **Validation retry (S3):** versioned runs; exceptions upserted on `(loan_id, rule_id)`; concurrent-run guard. → ADR-016/014.
- **AI failure (S4):** timeout + schema validation + degraded result logged; state untouched. → ADR-017.
- **Two reviewers (S5):** optimistic locking via `version` column → 409 on stale write. → ADR-015.
- **DB failure (S6):** decision+audit and snapshot+audit each in one transaction. → ADR-016.

## The 10× question — "what breaks first at 50k rows?"
- **Current bottleneck:** the **synchronous import request** (parse → normalize → validate → insert) done inside a single HTTP call. At ~50k rows the risk is (a) an HTTP/proxy timeout and (b) a long-held DB transaction.
- **Why it breaks:** one request holds a connection and a transaction for the full duration; batched inserts help but validation is still O(rows × rules) in the request thread; the browser gets no progress.
- **Measurement needed:** import wall-time p95 and peak RSS at 5k / 10k / 50k rows; DB transaction duration.
- **Scaling trigger:** import p95 > 2s or file > 100k rows.
- **Recommended future change:** accept the upload, persist raw rows, enqueue a normalize+validate job on an `arq`+Redis `worker`; the UI polls upload status. This is the single documented async step — deliberately deferred until the trigger fires.

## Index plan status
Indexes below are created **with the slice that introduces the table** (not pre-created on empty tables). Present today: `users(email)` unique, `users(role)`. Planned per table listed in the "Indexing plan" section above; each will carry a one-line comment stating the query it serves (avoids blind indexing).
