import os
from django.conf import settings
import redis

_redis_client = None


def get_redis_client():
    """
    Returns a Redis client instance based on settings.REDIS_URL.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = getattr(settings, "REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    if redis_url.startswith("fakeredis://"):
        # Local dev without a Redis server: in-process only, so pair it with
        # CELERY_TASK_ALWAYS_EAGER=True and CHANNEL_LAYERS_BACKEND=inmemory.
        import fakeredis
        _redis_client = fakeredis.FakeRedis(decode_responses=True)
    else:
        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def set_redis_client(client):
    """
    Allows overriding the Redis client (useful for unit testing with FakeRedis).
    """
    global _redis_client
    _redis_client = client
