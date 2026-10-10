from fastapi import FastAPI
from app.core.redis import redis_client
from app.routes.room import router
from app.websockets.routes import router as websocket_router

app = FastAPI()

app.include_router(router)

app.include_router(websocket_router)

@app.get("/")
def welcome():
    return "hello"

@app.get("/health")
def health_check():
   try:
    status = redis_client.ping()

    return {
        "status": "healthy",
        "redis": "connected"
    }

   except Exception as e:
    print(e)

    return {
        "status": "unhealthy",
        "redis": "disconnected"
    }