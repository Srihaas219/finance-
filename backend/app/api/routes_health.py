from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.db import get_db

router = APIRouter(tags=["health"])


def _liveness() -> dict:
    """Liveness: process is up. No dependency checks."""
    return {"status": "ok"}


def _readiness(db: Session) -> JSONResponse:
    """Readiness: dependencies usable. 503 if not ready (for LB / compose ordering)."""
    checks = {"db": False}
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "checks": checks})


# Primary paths plus conventional aliases (/health, /ready) required by the spec.
@router.get("/healthz")
@router.get("/health")
def healthz():
    return _liveness()


@router.get("/readyz")
@router.get("/ready")
def readyz(db: Session = Depends(get_db)):
    return _readiness(db)
