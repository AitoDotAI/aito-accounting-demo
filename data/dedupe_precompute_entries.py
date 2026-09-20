#!/usr/bin/env python3
"""Drop duplicate rows from the Aito-backed precompute_entries table.

Background: precompute_store.put() does delete-then-insert as Aito
has no native upsert. When two precompute processes ran against the
same Aito instance close together (e.g. one manual test push, then
a full ./do precompute) the inserts can race the deletes and leave
duplicate rows.

Reads in src.precompute_store.get() use limit=1 so behaviour stays
correct, but duplicates are noise and inflate the table. This
script removes them: keep the most-recent row per `name`, delete
the rest.

Idempotent. Run any time the count drifts from the expected
(2 cross-tenant + 7 × N customers).

Usage:
    uv run python data/dedupe_precompute_entries.py
    uv run python data/dedupe_precompute_entries.py --dry-run
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_client import AitoClient  # noqa: E402
from src.config import load_config  # noqa: E402
from src.precompute_store import PRECOMPUTE_TABLE  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would be deleted; don't delete.")
    args = parser.parse_args()

    client = AitoClient(load_config())

    # Fetch every row's name + computed_at (payloads can be 100s of KB
    # apiece — we only need the metadata to decide what to keep).
    rows: list[dict] = []
    offset = 0
    page = 100
    while True:
        r = client._request("POST", "/_search", json={
            "from": PRECOMPUTE_TABLE,
            "limit": page,
            "offset": offset,
            "select": ["name", "computed_at", "$id"] if False else ["name", "computed_at"],
        })
        hits = r.get("hits", [])
        rows.extend(hits)
        if len(hits) < page:
            break
        offset += page

    by_name: dict[str, list[dict]] = defaultdict(list)
    for h in rows:
        by_name[h["name"]].append(h)

    duplicates: list[tuple[str, int]] = []
    for name, group in by_name.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda h: h.get("computed_at", 0), reverse=True)
        # Keep the freshest, drop the rest.
        for stale in group[1:]:
            duplicates.append((name, stale["computed_at"]))

    if not duplicates:
        print(f"No duplicates. {len(rows)} rows across {len(by_name)} unique names.")
        return

    print(f"Found {len(duplicates)} duplicate rows across {sum(1 for n, g in by_name.items() if len(g) > 1)} names:")
    for name, ts in duplicates:
        print(f"  - {name} (computed_at={ts})")

    if args.dry_run:
        print("\n--dry-run: no changes made.")
        return

    # Aito's data delete API filters by where, not by row id.
    # For each duplicate we delete the specific stale row by
    # (name, computed_at) — the freshest row for the same name has
    # a different computed_at so it won't match.
    deleted = 0
    for name, ts in duplicates:
        try:
            client._request(
                "POST",
                f"/data/{PRECOMPUTE_TABLE}/delete",
                json={
                    "from": PRECOMPUTE_TABLE,
                    "where": {"name": name, "computed_at": ts},
                },
            )
            deleted += 1
        except Exception as e:
            print(f"  failed to delete {name}@{ts}: {e}")

    print(f"\nDeleted {deleted}/{len(duplicates)} stale rows.")


if __name__ == "__main__":
    main()
