import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.redis import redis_client
from app.routes.room import router
from app.websockets.routes import router as websocket_router

logger = logging.getLogger(__name__)

app = FastAPI()
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(router)
app.include_router(websocket_router)


@app.get("/")
def welcome():
    return "hello"


@app.get("/health")
def health_check():
    try:
        redis_client.ping()
    except Exception as exc:
        logger.exception("Redis health check failed")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "redis": "disconnected"},
        ) from exc

    return {"status": "healthy", "redis": "connected"}