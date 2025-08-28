import os
import redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_redis = redis.Redis.from_url(REDIS_URL)
queue = Queue("tasksvc", connection=_redis)