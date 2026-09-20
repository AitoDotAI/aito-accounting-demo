"""Background poll that drops caches when a rebuild lands. See ADR 0023.

The alternative is remembering to call `POST /api/cache/invalidate` after
every precompute, which was forgotten four times in three sessions. This
never runs on the request path: one small query a minute on a daemon
thread, so a slow or unreachable Aito costs a page view nothing.
"""

import logging
import os
import threading

from src import admin_ops, cache_versions

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60

_thread: threading.Thread | None = None
_stop = threading.Event()


def interval_seconds() -> int:
    """Poll interval; `0` disables the watcher entirely."""
    raw = os.environ.get("CACHE_WATCH_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        log.warning("CACHE_WATCH_SECONDS=%r is not an integer; watcher disabled", raw)
        return 0


def poll_once(snapshot: dict[str, int]) -> tuple[dict[str, int], set[str]]:
    """One comparison. Returns the new snapshot and what changed.

    Pure enough to test without a thread or a clock: hand it the previous
    snapshot, it reads the versions table and tells you what moved.

    An unreachable Aito yields `{}`, which `changed_since` reports as no
    change — the snapshot is then left ALONE rather than replaced with the
    empty read, so a transient outage cannot make every scope look new on
    the following poll.
    """
    latest = cache_versions.current()
    if not latest:
        return snapshot, set()
    changed = cache_versions.changed_since(snapshot, latest)
    if changed:
        dropped = admin_ops.apply_version_changes(changed)
        log.info("cache versions moved for %s; dropped %s precompute and %s cache entries",
                 sorted(changed), dropped["precompute_entries_dropped"],
                 dropped["cache_entries_dropped"])
    return {**snapshot, **latest}, changed


def _loop(interval: int) -> None:
    # Seed from the current state WITHOUT invalidating: at startup L1 is
    # empty anyway, and treating every scope as changed would drop the
    # caches of every container that restarts.
    snapshot = cache_versions.current()
    while not _stop.wait(interval):
        try:
            snapshot, _ = poll_once(snapshot)
        except Exception:
            # A watcher that dies on one bad poll is worse than no watcher:
            # it looks healthy and silently stops noticing rebuilds.
            log.exception("cache version poll failed; continuing")


def start() -> bool:
    """Start the watcher unless it is disabled or already running."""
    global _thread
    interval = interval_seconds()
    if interval == 0 or _thread is not None:
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(interval,),
                               name="cache-watch", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    """Stop the watcher. Used by tests; a daemon thread needs no shutdown."""
    global _thread
    _stop.set()
    _thread = None
