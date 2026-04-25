#!/usr/bin/env python3
"""Fetch real Finnish company data from PRH YTJ API.

Downloads ~10K companies across industry categories to build a
realistic corporate entity table for the Predictive Ledger demo.

Source: https://avoindata.prh.fi/opendata-ytj-api/v3/companies
License: Open data (Creative Commons Attribution 4.0)

Usage: python data/fetch_companies.py
"""

import json
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent
OUTPUT_FILE = DATA_DIR / "corporate_entities_raw.json"

API_BASE = "https://avoindata.prh.fi/opendata-ytj-api/v3/companies"

# Fetch companies by industry keywords to get diverse set
SEARCH_QUERIES = [
    ("IT", 1500),
    ("consulting", 1000),
    ("logistics", 800),
    ("energy", 800),
    ("construction", 600),
    ("restaurant", 600),
    ("retail", 600),
    ("cleaning", 170),
    ("telecom", 120),
    ("manufacturing", 500),
    ("design", 500),
    ("marketing", 500),
    ("finance", 500),
    ("medical", 500),
    ("food", 500),
    ("transport", 500),
    ("security", 300),
    ("software", 500),
]


def fetch_batch(query: str, max_results: int, offset: int = 0) -> list[dict]:
    """Fetch a batch of companies from PRH API."""
    params = {
        "name": query,
        "companyForm": "OY",
        "maxResults": min(max_results, 100),  # API max per request
        "resultsFrom": offset,
    }
    try:
        r = httpx.get(API_BASE, params=params, headers={"Accept": "application/json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("companies", [])
    except Exception as e:
        print(f"    Error fetching {query} offset={offset}: {e}")
        return []


def parse_company(raw: dict) -> dict | None:
    """Extract clean company record from PRH API response."""
    bid = raw.get("businessId", {}).get("value")
    if not bid:
        return None

    # Get current name
    names = raw.get("names", [])
    name = None
    for n in names:
        if n.get("endDate") is None:  # current name
            name = n.get("name")
            break
    if not name and names:
        name = names[0].get("name")
    if not name:
        return None

    # Get industry (English description)
    industry_code = ""
    industry_desc = ""
    bline = raw.get("mainBusinessLine")
    if bline:
        industry_code = str(bline.get("type", ""))
        for desc in bline.get("descriptions", []):
            if desc.get("languageCode") == "3":  # English
                industry_desc = desc.get("description", "")
                break
            if desc.get("languageCode") == "1" and not industry_desc:  # Finnish fallback
                industry_desc = desc.get("description", "")

    # Get city
    city = ""
    for office in raw.get("registeredOffices", []):
        if office.get("endDate") is None:
            for desc in office.get("descriptions", []):
                city = desc.get("description", "")
                break
            break

    # Get registration date
    reg_date = raw.get("businessId", {}).get("registrationDate", "")

    return {
        "business_id": bid,
        "name": name,
        "industry_code": industry_code,
        "industry": industry_desc,
        "city": city,
        "registration_date": reg_date,
    }


def main():
    all_companies = {}  # keyed by business_id to dedup

    for query, target in SEARCH_QUERIES:
        print(f"Fetching '{query}' (target {target})...")
        fetched = 0
        offset = 0

        while fetched < target:
            batch_size = min(100, target - fetched)
            batch = fetch_batch(query, batch_size, offset)
            if not batch:
                break

            for raw in batch:
                company = parse_company(raw)
                if company and company["business_id"] not in all_companies:
                    all_companies[company["business_id"]] = company
                    fetched += 1

            offset += len(batch)
            if len(batch) < batch_size:
                break  # no more results

            time.sleep(0.3)  # rate limit courtesy

        print(f"  got {fetched} new companies (total: {len(all_companies)})")

    # Save
    companies = list(all_companies.values())
    with open(OUTPUT_FILE, "w") as f:
        json.dump(companies, f, indent=None, ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"\nSaved {len(companies)} companies to {OUTPUT_FILE.name} ({size_mb:.1f} MB)")

    # Print distribution
    industries = {}
    for c in companies:
        ind = c["industry"][:30] if c["industry"] else "unknown"
        industries[ind] = industries.get(ind, 0) + 1
    print("\nTop industries:")
    for ind, count in sorted(industries.items(), key=lambda x: -x[1])[:15]:
        print(f"  {ind:35} {count}")


if __name__ == "__main__":
    main()
