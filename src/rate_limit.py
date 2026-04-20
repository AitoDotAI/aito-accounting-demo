"""Simple in-memory rate limiter for the public demo API.

Limits requests per IP to prevent abuse of the Aito API key.
Uses a sliding window counter — no external dependencies.
"""

import time
from collections import defaultdict

_requests: dict[str, list[float]] = defaultdict(list)

# Max requests per window per IP
MAX_REQUESTS = 60
WINDOW_SECONDS = 60


def check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS

    # Clean old entries
    _requests[client_ip] = [t for t in _requests[client_ip] if t > window_start]

    if len(_requests[client_ip]) >= MAX_REQUESTS:
        return False

    _requests[client_ip].append(now)
    return True
