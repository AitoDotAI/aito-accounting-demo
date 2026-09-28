#!/usr/bin/env python3
"""Promote each tenant's currently-routing rules, once. See ADR 0025.

Before governance, Invoice Processing routed on the top mined rules
(`mine_rules_for_customer`, default top_n) with nobody approving them.
This records exactly that set as promoted, by "seed", so the demo routes
the same invoices on day one -- and from then on only promoted rules
route. Idempotent: an already-active rule is not promoted again.

    AITO_V2_ENV=master ./do seed-rules            # every tenant with rules
    AITO_V2_ENV=master ./do seed-rules --limit 20
    AITO_V2_ENV=master ./do seed-rules --customer CUST-0007
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_v2_client import AitoV2Client, resolve_env  # noqa: E402
from src.config import load_config  # noqa: E402
from src.quality_service import mine_rules_for_customer  # noqa: E402
from src.rule_governance import routing_rules, seed_promoted  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--customer", help="seed one tenant")
    parser.add_argument("--limit", type=int, help="seed the first N tenants")
    args = parser.parse_args()

    use_v2, env = resolve_env(os.environ.get("AITO_V2_ENV"))
    if not use_v2:
        raise SystemExit("Set AITO_V2_ENV (e.g. master): rule_revisions is a v2 collection.")
    cfg = load_config()
    client = AitoV2Client(cfg.aito_api_url, cfg.aito_api_key, env=env)

    if args.customer:
        customers = [args.customer]
    else:
        rows = client.search("customers", {}, limit=1000).get("hits", [])
        customers = sorted(r["customer_id"] for r in rows)
        if args.limit:
            customers = customers[: args.limit]

    total = 0
    for cid in customers:
        mined = mine_rules_for_customer(client, cid)
        written = seed_promoted(client, cid, mined)
        active = len(routing_rules(client, cid))
        if written or active != len(mined):
            print(f"  {cid}: mined {len(mined)}, promoted {written}, now routing {active}")
        if active != len(mined):
            print(f"    !! {cid} routes {active} rules but mined {len(mined)} -- "
                  "day one would NOT match the pre-governance behaviour")
        total += written
    print(f"Seeded {total} promotions across {len(customers)} tenant(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
