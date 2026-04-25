#!/usr/bin/env python3
"""Warm up the API cache for top customers.

Hits the running API server's endpoints for top-N customers,
populating the in-memory cache. Run after starting the dev server
to ensure the demo is responsive without waiting for startup
warmup to complete.

Usage:
    ./do warm-cache              # warm top 5 customers
    ./do warm-cache --top 10     # warm top 10 customers
    ./do warm-cache --all        # warm all 255 customers (slow!)
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

API_BASE = "http://localhost:8200"


def list_customers(top: int | None = None) -> list[dict]:
    """Get customers from the API, sorted by invoice count desc."""
    r = httpx.get(f"{API_BASE}/api/customers", timeout=30)
    r.raise_for_status()
    customers = r.json().get("customers", [])
    customers.sort(key=lambda c: -c.get("invoice_count", 0))
    return customers[:top] if top else customers


def warm_customer(customer: dict, endpoints: list[str]) -> tuple[str, float, list[str]]:
    """Hit each endpoint for one customer, return total time."""
    cid = customer["customer_id"]
    start = time.monotonic()
    failed = []
    for ep in endpoints:
        try:
            r = httpx.get(f"{API_BASE}{ep}?customer_id={cid}", timeout=180)
            if r.status_code != 200:
                failed.append(f"{ep}({r.status_code})")
        except Exception as e:
            failed.append(f"{ep}({type(e).__name__})")
    elapsed = time.monotonic() - start
    return cid, elapsed, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=5, help="Warm top N customers (default 5)")
    parser.add_argument("--all", action="store_true", help="Warm all customers")
    parser.add_argument("--workers", type=int, default=3, help="Parallel customers")
    parser.add_argument("--fast", action="store_true", help="Only invoices+quality (skip matching/rules/anomalies)")
    args = parser.parse_args()

    # Check API is up
    try:
        r = httpx.get(f"{API_BASE}/api/health", timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Error: API not reachable at {API_BASE} ({e})")
        print("Start the server first: ./do dev")
        sys.exit(1)

    top = None if args.all else args.top
    customers = list_customers(top=top)
    print(f"Warming {len(customers)} customers (parallel: {args.workers})...")

    # Default: warm everything. --fast skips slow endpoints.
    endpoints = ["/api/invoices/pending", "/api/quality/overview"]
    if not args.fast:
        endpoints += ["/api/matching/pairs", "/api/anomalies/scan", "/api/rules/candidates"]

    print(f"Endpoints per customer: {endpoints}")
    print()

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: warm_customer(c, endpoints), customers))

    total = time.monotonic() - start
    print()
    for cid, elapsed, failed in results:
        status = "ok" if not failed else f"FAIL: {','.join(failed)}"
        print(f"  {cid}: {elapsed:>6.1f}s  {status}")

    print(f"\nTotal: {total:.1f}s for {len(customers)} customers ({len(endpoints)} endpoints each)")


if __name__ == "__main__":
    main()
