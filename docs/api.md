# API Documentation

> Implemented endpoints. Auth: `Authorization: Bearer <jwt>` from `POST /auth/login`.
> Errors are JSON `{"detail": "..."}` with proper status codes — no stack traces leak.
> Every response carries an `X-Request-ID` header (also in logs).

## Auth
| Method | Path | Role | Body / Notes |
|---|---|---|---|
| POST | `/auth/login` | public | `{email, password}` → `{access_token, role, name}` |
| GET | `/auth/me` | any authed | current user |

## Health
| Method | Path | Notes |
|---|---|---|
| GET | `/healthz`, `/health` | liveness `{status:"ok"}` |
| GET | `/readyz`, `/ready` | readiness; 503 if DB down |

## Ingestion (Slice 1 / Phase 2)
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/uploads` | **data_operator** | multipart `file`; `?kind=loan_tape` (default) or `?kind=servicer_update` (second source for source_conflict). 201 → `UploadSummary`. 400 on empty/bad-header. Duplicate content → `duplicate:true` + `original_upload_id`. |
| GET | `/uploads` | data_operator | paginated (`limit`,`offset`) import history |
| GET | `/uploads/{id}` | data_operator | `UploadSummary` incl. up to 10 `failed_samples` |
| GET | `/loans` | operator, reviewer | paginated; `?source_file_id=`, `?q=`, `?attention=true` (normalization issues). Items include `normalization_status` + `issue_fields`. |
| GET | `/loans/{loan_pk}` | operator, reviewer | canonical fields + `normalization_status` + `field_provenance` (per-field raw→transform→canonical→status) + `provenance` (source file, raw cell, row#, row_hash) |
| GET | `/audit/{loan_id}` | operator, reviewer | audit events for a business loan_id |

### UploadSummary (response)
```json
{
  "id": "…", "filename": "loan_tape.csv", "kind": "loan_tape",
  "byte_size": 175943, "file_hash": "95b7a854…(64 hex)",
  "duplicate": false, "original_upload_id": null,
  "row_count": 1000, "imported_count": 1000, "failed_count": 0,
  "failed_samples": [{"row_number": 12, "reason": "row has more columns than header"}],
  "note": null
}
```

### Role-gated dashboards
| Method | Path | Role |
|---|---|---|
| GET | `/operator/summary` | data_operator (real upload/record counts) |
| GET | `/reviewer/summary` | reviewer (stub until Slice 2–3) |
| GET | `/consumer/summary` | data_consumer (stub until Slice 5) |

## Error conventions
- `400` bad input (empty file, header missing `loan_id`).
- `401` missing/invalid token. `403` wrong role. `404` unknown id.
- `500` returns generic "Internal Server Error" (no traceback); details are in structured logs keyed by `X-Request-ID`.

## Validation & Exceptions (Slice 2)
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/validate?source_file_id=` | operator | run the 15-rule engine; creates a versioned run, upserts exceptions |
| GET | `/exceptions` | operator, reviewer | filter `severity`,`type`,`status`; search `q`; paginated |
| GET | `/exceptions/{id}` | operator, reviewer | exception detail |
| GET | `/summary` | all | uploads, loans, open exceptions by severity/type, quality score, verified count |

## Reviewer workbench (Slice 3)
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/exceptions/{id}/review` | reviewer | `{action: start_review\|ignore\|reopen, expected_version, comment}`; **409** on stale version |
| POST | `/loans/{pk}/comments` | reviewer | add a comment |
| PATCH | `/loans/{pk}/fields` | reviewer | `{field, value}`; allow-list only (400 on forbidden); re-validates |
| POST | `/loans/{pk}/decision` | reviewer | `{action: approve\|reject\|request_correction}`; approve gated on 0 open exceptions |
| POST | `/loans/{pk}/verify` | reviewer | create immutable verified snapshot (see Slice 5) |
| GET | `/loans/{pk}/history` | reviewer | review decision log |

## AI copilot (Slice 4) — advisory only
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/ai/request` | reviewer | `{exception_id, kind}` kind ∈ explain\|suggest_correction\|resolve_conflict\|reviewer_note; degrades gracefully |
| GET | `/ai/recommendations/{loan_pk}` | reviewer | recommendations for a loan |
| POST | `/ai/recommendations/{id}/apply` | reviewer | `{disposition: accepted\|edited\|rejected, override_value}`; accept/edit applies via the human review path |
| GET | `/ai/logs/{id}` | reviewer, operator | prompt/model/provider/latency/degraded metadata |

## Verified records, consumer & traceability (Slice 5)
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/verified-loans` | all readers | latest version per loan; search `q`; paginated |
| GET | `/verified-loans/{id}` | all readers | snapshot + record_hash + validation summary |
| GET | `/verified-loans/{id}/versions` | all readers | version history (V1..Vn) |
| GET | `/trace/{loan_pk}` | all readers | full raw→verified lineage (money shot) |
| GET | `/export?format=csv\|json` | consumer | export latest verified records; emits `verified.exported` audit |

## Invariants enforced server-side
- Deterministic engine owns exceptions; AI writes only `ai_recommendations` (never `loans`).
- Verified snapshots are append-only; corrections create V+1.
- Every state change writes an audit event in the same transaction.
- Optimistic concurrency (409) on exception writes.
