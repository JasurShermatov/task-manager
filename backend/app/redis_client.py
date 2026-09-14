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

        def scan_iter(self, match=None):
            pref = (match or "").rstrip("*")
            return [k for k in list(self.d) if k.startswith(pref)]

    rds = _Mem()


# ---------------------------------------------------------------- kirish urinishlari
# Bu hisob — himoya vositasi, kirishning sharti emas. Redis yiqilsa ham odam tizimga
# kira olishi kerak, shuning uchun quyidagilar hech qachon xato tashlamaydi.

def attempts(key: str) -> int:
    try:
        return int(rds.get(key) or 0)
    except Exception:  # noqa: BLE001
        return 0


def attempts_bump(key: str, n: int, ttl: int = 900) -> None:
    try:
        rds.set(key, n, ex=ttl)
    except Exception:  # noqa: BLE001
        pass


def attempts_clear(prefix: str) -> None:
    """Shu login bo'yicha hamma qulfni olib tashlaydi (IP lar bo'yicha tarqalgan).

    Boshliq parolni almashtirgan zahoti odam kira olishi kerak — aks holda u yangi
    parol bilan ham 15 daqiqa kutib o'tiradi va sababini tushunmaydi.
    """
    try:
        for k in list(rds.scan_iter(match=f"{prefix}*")):
            rds.delete(k)
    except Exception:  # noqa: BLE001
        pass
