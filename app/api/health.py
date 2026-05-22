"""Health check endpoint.

GET /healthz probes Postgres and Redis connectivity. Returns 200 if both are
reachable, 503 if either is down. Load balancers and Fly.io health checks use
this endpoint.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Probe database and broker connectivity.

    Returns ``{"status": "ok"}`` with 200 if both pass,
    or ``{"status": "degraded", "detail": "..."}`` with 503 if either fails.
    """
    checks: dict[str, str] = {}

    # Postgres probe
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # Redis probe
    try:
        import redis

        from app.config import settings

        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    body = {"status": "ok" if all_ok else "degraded", "checks": checks}
    return JSONResponse(content=body, status_code=status_code)
