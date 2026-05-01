"""Multi-tenancy support data for the landing page.

The home screen claim — "same vendor, different tenants, different
predictions" — needs two things at render time:

1. A ranked list of vendors that appear across many tenants with
   *different* dominant GLs (high cross-tenant contrast).
2. The predicted template (gl, approver, cost-centre, …) that each
   of those tenants would assign to that vendor.

Step 1 is a deterministic scan of the invoices fixture (no Aito).
Step 2 needs Aito and is the slow part — 4 templates × 8 vendors =
32 _search round-trips that we don't want on the user's first
paint. So we compute (1) and (2) at deploy time and serve a static
JSON.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
INVOICES_FIXTURE = _PROJECT_ROOT / "data" / "invoices.json"

# Tunables — kept module-level so the precompute and the live
# fallback agree on shape.
MIN_TENANTS_PER_VENDOR = 3        # vendors with fewer ledgers are noise
MIN_INVOICES_PER_TENANT_VENDOR = 5  # below this, dominant GL is unstable
MIN_DISTINCT_GLS = 2              # the whole point is contrast


def compute_shared_vendors(invoices_path: Path = INVOICES_FIXTURE) -> list[dict]:
    """Rank cross-tenant vendors by GL contrast.

    Returns the unbounded list, sorted by (distinct_gls, tenant_count)
    descending. Callers slice to the limit they want.
    """
    if not invoices_path.exists():
        return []

    vendor_tenant_gl: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in json.loads(invoices_path.read_text()):
        v, c, gl = row.get("vendor"), row.get("customer_id"), row.get("gl_code")
        if v and c and gl:
            vendor_tenant_gl[v][c][gl] += 1

    out: list[dict] = []
    for vendor, tenants in vendor_tenant_gl.items():
        if len(tenants) < MIN_TENANTS_PER_VENDOR:
            continue
        per_tenant = {c: gl.most_common(1)[0] for c, gl in tenants.items()}
        well_supported = {
            c: (gl, n) for c, (gl, n) in per_tenant.items()
            if n >= MIN_INVOICES_PER_TENANT_VENDOR
        }
        if len(well_supported) < MIN_TENANTS_PER_VENDOR:
            continue
        distinct_gls = len({gl for _, (gl, _) in well_supported.items()})
        if distinct_gls < MIN_DISTINCT_GLS:
            continue
        out.append({
            "vendor": vendor,
            "tenant_count": len(well_supported),
            "distinct_gls": distinct_gls,
            "tenants": [
                {"customer_id": c, "gl_code": gl, "n": n}
                for c, (gl, n) in sorted(well_supported.items(), key=lambda x: -x[1][1])
            ],
        })

    out.sort(key=lambda x: (-x["distinct_gls"], -x["tenant_count"]))
    return out
