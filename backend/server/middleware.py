"""What stands between the internet and the routes: a health check, a rate
limit, and the app key. Listed in this order in settings.MIDDLEWARE.

* Health check first, so Cloud Run's probe is answered without a key, without
  counting against any limit, and even though its Host header would be refused.
* Rate limit before the key check, so someone guessing keys is throttled
  instead of getting unlimited tries.
* Settings are read on every request, so tests can change them, and a limit or
  key of 0 / "" switches that check off (the development default).

None of this touches the feedback or hum code: it only decides whether a request
gets through to it.
"""

import hmac
import math
import threading
import time
from collections import deque

from django.conf import settings
from django.http import HttpResponse, JsonResponse

HEALTH_PATH = "/healthz"
HUM_PREFIX = "/api/hum/"
# The spoken-reply URL is fetched by an audio player, which can't send our header.
# Its id is 96 random bits and expires, so the URL itself is the credential.
KEY_EXEMPT_GET_PREFIX = "/api/hum/talk/speech/"


class RateLimiter:
    """At most `limit` hits per `window` seconds for each key (a sliding window).

    A rejected request is not recorded, so hammering a locked-out route doesn't
    extend the lock-out. The number of tracked keys is capped so a flood of
    distinct clients can't use up memory.
    """

    def __init__(self, clock=time.monotonic, window: float = 60.0, max_keys: int = 10_000):
        self._clock = clock
        self._window = window
        self._max_keys = max_keys
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._hits)

    def check(self, key: str, limit: int) -> float:
        """0.0 if the request is allowed (and counted), else seconds until it would be."""
        if limit <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            hits = self._hits.get(key)
            if hits is None:
                self._make_room(now)
                hits = self._hits[key] = deque()
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= limit:
                return self._window - (now - hits[0])
            hits.append(now)
            return 0.0

    def _make_room(self, now: float) -> None:
        if len(self._hits) < self._max_keys:
            return
        cutoff = now - self._window
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]
        while len(self._hits) >= self._max_keys:  # still full of live clients: drop the longest-known
            del self._hits[next(iter(self._hits))]


def client_id(request) -> str:
    """Who is calling. Behind Cloud Run the LAST X-Forwarded-For entry is the one
    its proxy appended; earlier entries are whatever the caller wrote, so they can
    be rotated freely and must not be trusted. (To confirm on the first deploy.)"""
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    return forwarded[-1] if forwarded else request.META.get("REMOTE_ADDR", "unknown")


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == HEALTH_PATH:
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.limiter = RateLimiter()

    def __call__(self, request):
        if request.path.startswith(HUM_PREFIX):
            bucket, limit = "hum", getattr(settings, "RATE_LIMIT_HUM_PER_MINUTE", 0)
        else:
            bucket, limit = "default", getattr(settings, "RATE_LIMIT_DEFAULT_PER_MINUTE", 0)
        wait = self.limiter.check(f"{bucket}:{client_id(request)}", limit)
        if wait > 0:
            seconds = max(1, math.ceil(wait))
            response = JsonResponse(
                {"error": f"Too many requests. Try again in {seconds} seconds.", "code": "rate_limited"},
                status=429,
            )
            response["Retry-After"] = str(seconds)
            return response
        return self.get_response(request)


class AppKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = getattr(settings, "APP_API_KEY", "")
        if key and not self._allowed(request, key):
            return JsonResponse(
                {"error": "This app isn't allowed to use the server.", "code": "unauthorized"},
                status=401,
            )
        return self.get_response(request)

    @staticmethod
    def _allowed(request, key: str) -> bool:
        if request.method in ("GET", "HEAD") and request.path.startswith(KEY_EXEMPT_GET_PREFIX):
            return True
        provided = request.META.get("HTTP_X_APP_KEY", "")
        # Compare as bytes: compare_digest raises on non-ASCII text, which would turn a bad key into a 500.
        return hmac.compare_digest(provided.encode("utf-8"), key.encode("utf-8"))
