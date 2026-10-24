import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.agent_card import router as agent_card_router
from app.api.a2a import router as a2a_router
from app.api.health import router as health_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("a2a-invoice-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    logger.info("Initializing database schema...")
    init_db()
    logger.info("Database initialized successfully.")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_payload_limit(request: Request, call_next):
    """Enforce maximum payload size limit (512 KiB per specification)."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_PAYLOAD_SIZE:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Payload exceeds maximum allowed size of 512 KiB"},
            media_type="application/a2a+json",
        )
    return await call_next(request)


# Include Agent Card at root level: GET /.well-known/agent-card.json
app.include_router(agent_card_router)

# Include Health Check: GET /healthz
app.include_router(health_router)

# Include A2A routes at /a2a (standard) and at / (root fallback)
app.include_router(a2a_router, prefix="/a2a", tags=["A2A"])
app.include_router(a2a_router, tags=["A2A-Root"])
