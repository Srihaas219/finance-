"""Verified records: hash reproducibility, immutability, versioning (V2), atomic verify,
traceability chain, consumer read-only + export."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.hashing import hash_record
from app.ingestion.service import ingest_csv
from app.models.verified import VerifiedLoan
from app.validation.service import run_validation
from tests.conftest import auth
from tests.test_ingestion import HEADER, _row


def _clean_loan(loan_id):
    """Ingest a clean loan (no exceptions) and validate. Returns loan_pk."""
    content = ("\n".join([HEADER, _row(loan_id=loan_id)]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename=f"{loan_id}.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    from app.models.loan import Loan
    pk = db.scalar(select(Loan.id).where(Loan.loan_id == loan_id))
    db.close()
    return pk


def _reviewer(client, login):
    return login(client, "reviewer@loantrust.demo", "reviewer123")


def test_verify_clean_loan_creates_v1_with_hash(client, login):
    pk = _clean_loan("VER1")
    token = _reviewer(client, login)
    client.post(f"/loans/{pk}/decision", headers=auth(token), json={"action": "approve"})
    r = client.post(f"/loans/{pk}/verify", headers=auth(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert len(body["record_hash"]) == 64


def test_record_hash_reproducible(client, login):
    pk = _clean_loan("VERHASH")
    token = _reviewer(client, login)
    client.post(f"/loans/{pk}/decision", headers=auth(token), json={"action": "approve"})
    vid = client.post(f"/loans/{pk}/verify", headers=auth(token)).json()["id"]
    db = SessionLocal()
    v = db.get(VerifiedLoan, vid)
    recomputed = hash_record({"loan_id": v.loan_id, "version": v.version, "snapshot": v.snapshot})
    stored = v.record_hash
    db.close()
    assert recomputed == stored


def test_cannot_verify_with_open_exceptions(client, login):
    # invalid state -> open exception -> verify blocked
    content = ("\n".join([HEADER, _row(loan_id="VERBLOCK", state="ZZ")]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename="verblock.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    from app.models.loan import Loan
    pk = db.scalar(select(Loan.id).where(Loan.loan_id == "VERBLOCK"))
    db.close()
    token = _reviewer(client, login)
    r = client.post(f"/loans/{pk}/verify", headers=auth(token))
    assert r.status_code == 400


def test_correction_creates_v2_and_v1_preserved(client, login):
    pk = _clean_loan("VERV2")
    token = _reviewer(client, login)
    client.post(f"/loans/{pk}/decision", headers=auth(token), json={"action": "approve"})
    v1 = client.post(f"/loans/{pk}/verify", headers=auth(token)).json()
    # A later correction + re-verify -> V2 supersedes V1; V1 remains.
    client.patch(f"/loans/{pk}/fields", headers=auth(token),
                 json={"field": "borrower_state", "value": "NY"})
    client.post(f"/loans/{pk}/decision", headers=auth(token), json={"action": "approve"})
    v2 = client.post(f"/loans/{pk}/verify", headers=auth(token)).json()
    assert v2["version"] == 2
    assert v2["supersedes_version"] == 1
    db = SessionLocal()
    versions = db.scalars(select(VerifiedLoan.version).where(VerifiedLoan.loan_pk == pk)).all()
    db.close()
    assert set(versions) == {1, 2}  # V1 still queryable
    assert v1["record_hash"] != v2["record_hash"]  # different snapshot -> different hash


def test_traceability_chain(client, login):
    pk = _clean_loan("VERTRACE")
    token = _reviewer(client, login)
    client.post(f"/loans/{pk}/decision", headers=auth(token), json={"action": "approve"})
    client.post(f"/loans/{pk}/verify", headers=auth(token))
    trace = client.get(f"/trace/{pk}", headers=auth(token)).json()
    assert trace["source_file"]["file_hash"]
    assert trace["raw_record"]["raw_payload"]["loan_id"] == "VERTRACE"
    assert trace["field_provenance"]
    assert trace["verified_versions"][0]["version"] == 1


def test_consumer_can_read_verified_and_export(client, login):
    pk = _clean_loan("VERCONS")
    rtoken = _reviewer(client, login)
    client.post(f"/loans/{pk}/decision", headers=auth(rtoken), json={"action": "approve"})
    client.post(f"/loans/{pk}/verify", headers=auth(rtoken))

    ctoken = login(client, "consumer@loantrust.demo", "consumer123")
    lst = client.get("/verified-loans", headers=auth(ctoken)).json()
    assert lst["total"] >= 1
    vid = next(i["id"] for i in lst["items"] if i["loan_id"] == "VERCONS")
    detail = client.get(f"/verified-loans/{vid}", headers=auth(ctoken)).json()
    assert detail["snapshot"]["loan_id"] == "VERCONS"
    # export
    exp = client.get("/export?format=csv", headers=auth(ctoken))
    assert exp.status_code == 200
    assert "record_hash" in exp.text


def test_consumer_cannot_verify_or_review(client, login):
    pk = _clean_loan("VERRBAC")
    ctoken = login(client, "consumer@loantrust.demo", "consumer123")
    assert client.post(f"/loans/{pk}/verify", headers=auth(ctoken)).status_code == 403
    assert client.post(f"/loans/{pk}/decision", headers=auth(ctoken),
                       json={"action": "approve"}).status_code == 403
    # operator cannot export (consumer-only)
    otoken = login(client, "operator@loantrust.demo", "operator123")
    assert client.get("/export", headers=auth(otoken)).status_code == 403
