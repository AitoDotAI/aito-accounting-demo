"""In-memory rate limiter for the public demo API.

Caps per-IP request rate so a hosted instance can't burn through
the Aito quota under hostile traffic. Uses a sliding window — no
Redis, no external state.

Behind a single-replica Container App the remote IP is the
ingress proxy, so MAX_REQUESTS is effectively a global cap.
DEMO_MAX_REQUESTS env var lets the hosted deploy lower this
without a code change.
"""

import os
import time
from collections import defaultdict

_requests: dict[str, list[float]] = defaultdict(list)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Default: 60/min for dev. Hosted deploys override via DEMO_MAX_REQUESTS=30.
MAX_REQUESTS = _env_int("DEMO_MAX_REQUESTS", 60)
WINDOW_SECONDS = 60

DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")


def check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS

    _requests[client_ip] = [t for t in _requests[client_ip] if t > window_start]

    if len(_requests[client_ip]) >= MAX_REQUESTS:
        return False

    _requests[client_ip].append(now)
    return True
