import os
import time, random
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

def load_retry_config():
    """Pull retry knobs from environment (.env)."""
    return {
        "max_attempts": int(os.getenv("MAX_RETRIES", 5)),
        "base_delay": float(os.getenv("BASE_DELAY", 0.2)),
        "backoff": float(os.getenv("BACKOFF", 2.0)),
        "jitter_ratio": float(os.getenv("JITTER_RATIO", 0.5)),
    }

def retry_with_jitter(
    *,
    max_attempts=5,
    base_delay=0.2,
    backoff=2.0,
    jitter_ratio=0.5,
    exceptions=(Exception,),
    on_retry=None,
):
    """Decorator that retries with exponential backoff + jitter."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    attempt += 1
                    return fn(*args, **kwargs)
                except exceptions as err:
                    if attempt >= max_attempts:
                        raise
                    base = base_delay * (backoff ** (attempt - 1))
                    low = base * (1 - jitter_ratio)
                    high = base * (1 + jitter_ratio)
                    sleep_s = random.uniform(low, high)
                    if on_retry:
                        on_retry(attempt, err, sleep_s)
                    time.sleep(sleep_s)
        return wrapper
    return decorator