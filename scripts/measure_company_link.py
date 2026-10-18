#!/usr/bin/env python3
"""Does sending the vendor's company link change GL and approver accuracy? (ADR 0031 step A)

Pre-registered in docs/notes/company-link-preregistration.md. Read-only:
`_evaluate` only. Both arms score the same held-out invoices, so the
comparison is paired (exact McNemar on the discordant pairs).

    AITO_V2_ENV=master uv run python scripts/measure_company_link.py --out docs/notes/company-link-measured.md
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_v2_client import AitoV2Client, resolve_env  # noqa: E402
from src.config import load_config  # noqa: E402

TENANTS = [f"CUST-{i:04d}" for i in range(20)]
HOLD_OUT = [40, 7]        # invoice_id $hash $mod [40, 7]: residue 7, never an earlier test set
INPUTS = ("customer_id", "vendor", "amount", "category", "description")   # main's GL inputs
LINK = "vendor_business_id"


def body(customer_id: str, predict: str, with_link: bool) -> dict:
    """The demo's own query on main (pooled population), with or without the company link."""
    inputs = INPUTS + ((LINK,) if with_link else ())
    where = {f: {"$get": f} for f in inputs}
    query = {"from": "invoices", "where": where, "predict": predict}
    if predict == "approver":
        where["approver.customer_id"] = {"$get": "customer_id"}
        query["basedOn"] = ["role", "department"]
    return {"testSource": {"from": "invoices",
                           "where": {"customer_id": customer_id, "invoice_id": {"$hash": {"$mod": HOLD_OUT}}}},
            "evaluate": query, "select": ["testSamples", "cases"]}


def mcnemar_exact_p(only_a: int, only_b: int) -> float:
    n = only_a + only_b
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Europe/Helsinki"))
    if 8 <= now.hour < 10:
        raise SystemExit(f"Refusing at {now:%H:%M} Helsinki: 08:00-10:00 is quiet hours on shared Aito.")
    use_v2, env = resolve_env(os.environ.get("AITO_V2_ENV"))
    if not use_v2:
        raise SystemExit("Set AITO_V2_ENV (e.g. master).")
    cfg = load_config()
    client = AitoV2Client(cfg.aito_api_url, cfg.aito_api_key, env=env)
    engine = client._request("GET", "/_version")["version"]

    lines = ["# Company link in the invoice queries: held-out accuracy (ADR 0031 step A)", "",
             f"> Synthetic fixtures. Pre-registered in `docs/notes/company-link-preregistration.md`; "
             f"`scripts/measure_company_link.py` against Aito {engine}, {now:%Y-%m-%d %H:%M} Helsinki.", "",
             "| target | test invoices | without link | with link | only without right | only with right | exact McNemar p |",
             "|---|---|---|---|---|---|---|"]
    for predict in ("gl_code", "approver"):
        pairs = []
        for customer_id in TENANTS:
            arms = []
            for with_link in (False, True):
                result = client.evaluate(body(customer_id, predict, with_link))
                cases = sorted(result["cases"], key=lambda c: c["offset"])
                if len(cases) != result["testSamples"]:
                    raise RuntimeError(f"{customer_id} {predict}: {len(cases)} cases for {result['testSamples']} samples")
                arms.append(cases)
            without, with_ = arms
            if len(without) != len(with_):
                raise RuntimeError(f"{customer_id} {predict}: the arms scored different test sets")
            pairs += [(bool(a["accurate"]), bool(b["accurate"])) for a, b in zip(without, with_)]
            print(predict, customer_id, len(without), flush=True)
        n = len(pairs)
        only_without = sum(a and not b for a, b in pairs)
        only_with = sum(b and not a for a, b in pairs)
        lines.append(f"| {predict} | {n} | {sum(a for a, _ in pairs) / n:.1%} | {sum(b for _, b in pairs) / n:.1%} "
                     f"| {only_without} | {only_with} | {mcnemar_exact_p(only_without, only_with):.3g} |")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
