import redis

from app.core.config import Settings


settings = Settings()

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True
)
print(redis_client.ping())