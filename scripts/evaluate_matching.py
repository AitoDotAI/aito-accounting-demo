#!/usr/bin/env python3
"""Measure payment-to-invoice matching accuracy against ground truth.

    ./do eval-matching                     # 25 payments, CUST-0000
    ./do eval-matching --n 50 --pool 60    # bigger sample, harder pool
    ./do eval-matching --no-reference      # strip the Viite/RF number first
    ./do eval-matching --compare-reference # both, side by side

Every other predictive view in this demo can state its accuracy —
`_evaluate` measures GL coding and approver routing directly. Payment
matching could not, so nobody knew whether it worked: the UI showed a
"match rate", which only counts how many pairs were produced, not how
many were RIGHT. A matcher that pairs every payment with the wrong
invoice scores 100% on that metric.

Ground truth is `bank_transactions.invoice_id` — the fixture generator
records which invoice each payment settles, so the correct answer is
known for every row.

The task is posed the way an accounts-payable system meets it: a payment
arrives, and it has to be assigned to one invoice out of the open
ledger. The candidate pool therefore holds the payments' true targets
PLUS decoy invoices from the same customer, so a match is a real
discrimination and not a lookup in a pool of one.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_client import AitoClient  # noqa: E402
from src.config import load_config  # noqa: E402
from src.matching_service import match_bank_txn_to_invoice  # noqa: E402

# Finnish bank reference formats the generator emits. These digits are
# noise: an invoice carries no reference field, so nothing in the ledger
# can ever match them. Stripping them measures how much they cost.
REFERENCE = re.compile(
    r"(VIITE[:\s]+[\d\s]+|Viite:?\s*[\d\s]+|RF\d{2}[\s\d]+|LASKU\s+[\d\-]+)",
    re.IGNORECASE,
)


def strip_reference(description: str) -> str:
    """Remove the reference number, leaving vendor and date."""
    without = REFERENCE.sub(" ", description)
    without = re.sub(r"\s*/\s*(?=/|$)", "", without)   # empty ' / /' segments
    return re.sub(r"\s{2,}", " ", without).strip(" /-")


def load_sample(client: AitoClient, customer_id: str, n: int, pool_size: int, seed: int):
    """Draw `n` payments and build the open-invoice pool they compete over.

    Returns (payments, pool). Every payment's true invoice is in the
    pool — people do not pay invoices that aren't in the ledger — and
    the remainder are decoys that make the choice non-trivial.
    """
    txns = client.search(
        "bank_transactions", {"customer_id": customer_id}, limit=max(n * 4, 40)
    ).get("hits", [])
    txns = [t for t in txns if t.get("invoice_id")]
    if not txns:
        raise SystemExit(f"no linked bank transactions for {customer_id}")

    rng = random.Random(seed)
    payments = rng.sample(txns, min(n, len(txns)))

    truth_ids = {t["invoice_id"] for t in payments}
    targets = client.search(
        "invoices", {"customer_id": customer_id, "invoice_id": {"$or": sorted(truth_ids)}},
        limit=len(truth_ids),
    ).get("hits", [])

    decoys = client.search(
        "invoices", {"customer_id": customer_id}, limit=pool_size + len(truth_ids)
    ).get("hits", [])

    pool: dict[str, dict] = {}
    for row in targets + decoys:
        pool.setdefault(row["invoice_id"], {
            "invoice_id": row["invoice_id"], "vendor": row["vendor"], "amount": row["amount"],
        })
        if len(pool) >= pool_size + len(truth_ids):
            break
    # Guarantee every truth survived the cap.
    for row in targets:
        pool.setdefault(row["invoice_id"], {
            "invoice_id": row["invoice_id"], "vendor": row["vendor"], "amount": row["amount"],
        })
    return payments, list(pool.values())


def evaluate(client, payments, pool, *, strip: bool, workers: int) -> list[dict]:
    """Run the matcher over every payment and score it against truth."""
    def one(txn: dict) -> dict:
        description = txn["description"]
        pair = match_bank_txn_to_invoice(
            client,
            {
                "txn_id": txn.get("transaction_id"),
                "description": strip_reference(description) if strip else description,
                "amount": txn["amount"],
                "bank": txn.get("bank", ""),
                "customer_id": txn.get("customer_id"),
            },
            pool,
        )
        return {
            "txn_id": txn.get("transaction_id"),
            "description": description,
            "truth": txn["invoice_id"],
            "predicted": pair.invoice_id if pair else None,
            "status": pair.status if pair else "no-match",
            "confidence": pair.confidence if pair else 0.0,
            "correct": bool(pair and pair.invoice_id == txn["invoice_id"]),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool_exec:
        return list(pool_exec.map(one, payments))


def report(label: str, rows: list[dict], pool_size: int, detail: int) -> dict:
    n = len(rows)
    answered = [r for r in rows if r["predicted"]]
    correct = [r for r in rows if r["correct"]]
    asserted = [r for r in rows if r["status"] == "matched"]
    asserted_ok = [r for r in asserted if r["correct"]]

    accuracy = len(correct) / n if n else 0.0
    coverage = len(answered) / n if n else 0.0
    precision = len(asserted_ok) / len(asserted) if asserted else 0.0
    # What a matcher that always guesses the single most plausible
    # invoice would get: 1 / pool size. The bar to beat.
    baseline = 1.0 / pool_size if pool_size else 0.0

    print(f"\n=== {label} ===")
    print(f"  payments evaluated        {n}")
    print(f"  candidate invoices        {pool_size}")
    print(f"  ACCURACY (right invoice)  {len(correct)}/{n} = {accuracy:.1%}")
    print(f"  random baseline           {baseline:.1%}")
    print(f"  coverage (any answer)     {coverage:.1%}")
    print(f"  precision on 'matched'    {len(asserted_ok)}/{len(asserted)} = {precision:.1%}"
          if asserted else "  precision on 'matched'    n/a (none asserted)")
    mean_conf = sum(r["confidence"] for r in answered) / len(answered) if answered else 0.0
    print(f"  mean confidence           {mean_conf:.2f}")

    statuses: dict[str, int] = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    print(f"  status breakdown          {statuses}")

    wrong = [r for r in answered if not r["correct"]]
    if wrong:
        print(f"\n  {len(wrong)} wrong assignment(s) — these are the demo's failure mode:")
        for r in wrong[:detail]:
            print(f"    {r['description'][:62]}")
            print(f"      predicted {r['predicted']}  truth {r['truth']}  "
                  f"conf={r['confidence']:.2f}  status={r['status']}")
    missed = [r for r in rows if not r["predicted"]]
    if missed:
        print(f"\n  {len(missed)} payment(s) left unmatched:")
        for r in missed[:detail]:
            print(f"    {r['description'][:62]}  (truth {r['truth']})")
    return {"accuracy": accuracy, "coverage": coverage, "precision": precision}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--customer", default="CUST-0000")
    parser.add_argument("--n", type=int, default=25, help="payments to evaluate")
    parser.add_argument("--pool", type=int, default=30, help="decoy invoices in the ledger")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--detail", type=int, default=8, help="failing cases to print")
    parser.add_argument("--no-reference", action="store_true",
                        help="strip the Viite/RF number from the payment description")
    parser.add_argument("--compare-reference", action="store_true",
                        help="measure with AND without the reference number")
    args = parser.parse_args()

    client = AitoClient(load_config())
    payments, pool = load_sample(client, args.customer, args.n, args.pool, args.seed)
    print(f"Payment -> invoice matching, {args.customer}: "
          f"{len(payments)} payments against {len(pool)} open invoices")

    if args.compare_reference:
        with_ref = evaluate(client, payments, pool, strip=False, workers=args.workers)
        report("WITH reference number (as generated today)", with_ref, len(pool), args.detail)
        without = evaluate(client, payments, pool, strip=True, workers=args.workers)
        report("WITHOUT reference number", without, len(pool), args.detail)
        return 0

    rows = evaluate(client, payments, pool, strip=args.no_reference, workers=args.workers)
    label = "reference stripped" if args.no_reference else "as generated"
    report(label, rows, len(pool), args.detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
