"""Redis with an in-memory fallback so the API still works if Redis is down."""
import time

from .config import settings

try:
    import redis as _redis
    _client = _redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    _client.ping()
    rds = _client
except Exception:  # pragma: no cover
    class _Mem:
        def __init__(self):
            self.d = {}

        def get(self, k):
            v = self.d.get(k)
            if v and v[1] and v[1] < time.time():
                self.d.pop(k, None)
                return None
            return v[0] if v else None

        def set(self, k, v, ex=None):
            self.d[k] = (str(v), time.time() + ex if ex else None)

        def delete(self, k):
            self.d.pop(k, None)

    rds = _Mem()
