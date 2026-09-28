"""Hourly restore of the demo's seeded rules. See ADR 0025.

Promote and Demote are public on the demo. Without this, a visitor who
demotes the routed rules strips them for every later visitor until a
person runs `./do seed-rules`. This puts each touched tenant back to its
seeded state on a timer, and records doing so.

Same shape as `cache_watch`: a daemon thread, off the request path, that
survives a failed pass. `RULES_RESTORE_SECONDS` sets the interval (default
3600); `0` disables it.
"""

import logging
import os
import threading

from src import rule_governance

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600

_thread: threading.Thread | None = None
_stop = threading.Event()


def interval_seconds() -> int:
    raw = os.environ.get("RULES_RESTORE_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        log.warning("RULES_RESTORE_SECONDS=%r is not an integer; restore disabled", raw)
        return 0


def restore_once(client) -> dict[str, int]:
    """One pass: every tenant a visitor touched, back to its seed. Returns
    {customer_id: events_written} for tenants that changed."""
    changed = {}
    for cid in sorted(rule_governance.tenants_changed_by_visitors(client)):
        n = rule_governance.restore_seed(client, cid, changed_by="auto-restore")
        if n:
            rule_governance.refresh_governed_views(cid)
            changed[cid] = n
    return changed


def _loop(client, interval: int) -> None:
    while not _stop.wait(interval):
        try:
            changed = restore_once(client)
            if changed:
                log.info("restored seeded rules: %s", changed)
        except Exception:
            # A timer that dies on one bad pass looks healthy and silently
            # stops restoring -- worse than no timer.
            log.exception("rule restore pass failed; continuing")


def start(client) -> bool:
    global _thread
    interval = interval_seconds()
    if interval == 0 or _thread is not None:
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(client, interval),
                               name="rule-restore", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    global _thread
    _stop.set()
    _thread = None
