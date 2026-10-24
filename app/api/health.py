from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
def health_check():
    """Health and liveness check endpoint for deployment monitoring."""
    return JSONResponse(content={"status": "ok", "app": "a2a-invoice-agent"})
