from fastapi import FastAPI
from app.core.redis import redis_client

app = FastAPI()

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