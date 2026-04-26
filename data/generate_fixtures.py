#!/usr/bin/env python3
"""Generate multi-tenant Finnish accounting data at scale.

Produces ~1M invoices across 256 customers with geometric size
distribution. Each customer has its own employees, GL code mappings,
and approver assignments. Vendors come from real PRH company data.

Usage:
    python data/generate_fixtures.py              # full 1M
    python data/generate_fixtures.py --small      # ~8K invoices (fast dev)
    python data/generate_fixtures.py --medium     # ~100K invoices
"""

import argparse
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent

# ── Constants ─────────────────────────────────────────────────────

DEPARTMENTS = ["Finance", "Operations", "Sales", "IT", "HR", "Procurement"]
ROLES = ["CEO", "Director", "Manager", "Supervisor", "Employee"]
BANKS = ["OP Bank", "Nordea", "Danske Bank", "Handelsbanken", "S-Pankki"]

CATEGORIES = [
    "telecom", "supplies", "food_bev", "office", "it_equipment",
    "facilities", "maintenance", "software", "cloud", "logistics",
    "insurance", "consulting",
]

GL_CODES = {
    "telecom": ("6200", "Telecom"),
    "supplies": ("4400", "Supplies & Materials"),
    "food_bev": ("4100", "COGS"),
    "office": ("4500", "Office Expenses"),
    "it_equipment": ("6100", "IT & Software"),
    "facilities": ("5100", "Facilities"),
    "maintenance": ("5200", "Maintenance"),
    "software": ("6100", "IT & Software"),
    "cloud": ("6100", "IT & Software"),
    "logistics": ("4600", "Logistics"),
    "insurance": ("5300", "Insurance"),
    "consulting": ("5400", "Professional Services"),
}

COST_CENTRES = {
    "Finance": "CC-100", "Operations": "CC-200", "Sales": "CC-300",
    "IT": "CC-400", "HR": "CC-500", "Procurement": "CC-600",
}

PAYMENT_METHODS = ["SEPA Credit Transfer", "SEPA Credit Transfer", "SEPA Credit Transfer", "Credit Card", "Wire Transfer"]

# Date range: 24 months
START_DATE = date(2024, 5, 1)
END_DATE = date(2026, 4, 30)
TOTAL_DAYS = (END_DATE - START_DATE).days

# ── Invoice description templates ─────────────────────────────────
# Category-specific English templates with {vendor} and {ref} slots.
# Each category has many templates for variety.

TEMPLATES = {
    "telecom": [
        "Monthly mobile subscription - {ref}",
        "Broadband service - office line {ref}",
        "Data plan renewal - corporate account",
        "Phone service contract Q{q} - {ref}",
        "VoIP service monthly fee",
        "Mobile fleet management - {count} devices",
        "Internet connectivity - main office",
        "Telecommunications service agreement",
        "SIM card order - new employees",
        "Conference call service - monthly",
    ],
    "supplies": [
        "Wholesale order - retail products {ref}",
        "Store inventory replenishment Q{q}",
        "Grocery supplies - weekly delivery",
        "Materials order - {ref}",
        "Packaging materials - bulk order",
        "Raw materials procurement - production",
        "Supply chain order #{ref}",
        "Warehouse restocking - standard items",
        "Consumables order - operations",
        "Production materials - batch {ref}",
    ],
    "food_bev": [
        "Bakery products - weekly delivery",
        "Dairy supply - regular order {ref}",
        "Catering order - staff meeting",
        "Beverage supply Q{q}",
        "Food service contract - cafeteria",
        "Fresh produce delivery - week {week}",
        "Coffee and beverages - office supply",
        "Lunch service - corporate dining",
        "Snack vending restocking",
        "Catering - client event {ref}",
    ],
    "office": [
        "Office supplies - standard order",
        "Printer paper and toner - Q{q}",
        "Stationery order - {ref}",
        "Desk accessories and ergonomics",
        "Filing and storage supplies",
        "Presentation materials",
        "Business cards - new employees",
        "Whiteboard markers and supplies",
        "Envelopes and mailing supplies",
        "Calendar and planner order",
    ],
    "it_equipment": [
        "Laptop purchase - new hire",
        "Monitor order - {count} units",
        "Keyboard and mouse - bulk order",
        "Network switch replacement",
        "Server hardware upgrade",
        "USB-C docking stations - {count} pcs",
        "Headset order - remote workers",
        "Webcam and AV equipment",
        "Printer - department {dept}",
        "External storage drives",
    ],
    "facilities": [
        "Cleaning services - monthly contract",
        "Security service - {ref}",
        "Building maintenance - scheduled",
        "Waste management - monthly",
        "HVAC maintenance - quarterly",
        "Pest control - annual service",
        "Elevator maintenance - Q{q}",
        "Fire safety inspection",
        "Window cleaning - exterior",
        "Landscaping - seasonal",
    ],
    "maintenance": [
        "Equipment service - annual maintenance",
        "Spare parts order - {ref}",
        "Technical inspection - production line",
        "Preventive maintenance - Q{q}",
        "Repair work - order {ref}",
        "Calibration service - instruments",
        "Machine overhaul - scheduled",
        "Safety equipment replacement",
        "Generator maintenance",
        "Plumbing repair - facilities",
    ],
    "software": [
        "License renewal - Enterprise Plan",
        "SaaS subscription - {count} seats",
        "Annual support contract - {ref}",
        "Software upgrade - version {ver}",
        "Development tools license",
        "Security software - annual",
        "CRM subscription - Q{q}",
        "ERP module license",
        "Cloud platform subscription",
        "Collaboration tools - monthly",
    ],
    "cloud": [
        "Cloud hosting - monthly usage",
        "Compute resources - on-demand",
        "Storage fees - {count} TB",
        "CDN service - bandwidth charges",
        "Database hosting - managed service",
        "Container orchestration - monthly",
        "Serverless compute charges",
        "Data transfer - egress fees",
        "Load balancer service",
        "Cloud monitoring - monthly",
    ],
    "logistics": [
        "Shipping - domestic parcel {ref}",
        "Freight transport - order {ref}",
        "Courier service - express delivery",
        "Pallet delivery - warehouse",
        "Return logistics - processing",
        "International shipping - EU",
        "Last mile delivery contract",
        "Warehouse storage - monthly",
        "Fleet fuel charges - {ref}",
        "Customs clearance - import",
    ],
    "insurance": [
        "Property insurance - annual premium",
        "Liability coverage - renewal",
        "Fleet insurance - {count} vehicles",
        "Workers compensation - Q{q}",
        "Business interruption coverage",
        "Cyber liability insurance",
        "Directors and officers liability",
        "Professional indemnity renewal",
        "Equipment breakdown coverage",
        "Travel insurance - corporate",
    ],
    "consulting": [
        "Advisory services - strategy review",
        "Audit fees - annual Q{q}",
        "Project consulting - phase {ref}",
        "Legal services - contract review",
        "Tax advisory - annual filing",
        "HR consulting - recruitment",
        "IT consulting - infrastructure",
        "Management consulting - Q{q}",
        "Financial advisory - M&A",
        "Compliance review - regulatory",
    ],
}


# ── Helper functions ──────────────────────────────────────────────

def lognormal_amount(mean: float, std: float) -> float:
    """Generate a log-normal amount with Finnish rounding bias."""
    variance = std ** 2
    mu = math.log(mean ** 2 / math.sqrt(variance + mean ** 2))
    sigma = math.sqrt(math.log(1 + variance / mean ** 2))
    amount = random.lognormvariate(mu, sigma)
    if random.random() < 0.3:
        amount = round(amount, 0)
    elif random.random() < 0.5:
        amount = round(amount * 2, 0) / 2
    else:
        amount = round(amount, 2)
    return max(1.0, amount)


def random_date() -> str:
    days = random.randint(0, TOTAL_DAYS)
    return (START_DATE + timedelta(days=days)).isoformat()


def finnish_reference(rng: random.Random) -> str:
    """Generate a Finnish reference number (Viite) with ISO 7064 mod 10 check digit."""
    base = str(rng.randint(1000, 99999999))
    weights = [7, 3, 1]
    s = sum(int(c) * weights[i % 3] for i, c in enumerate(reversed(base)))
    check = (10 - s % 10) % 10
    return base + str(check)


def rf_reference(rng: random.Random) -> str:
    """Generate an RF (creditor) reference like RF18 1234 5678 9012 3456."""
    digits = "".join(str(rng.randint(0, 9)) for _ in range(rng.randint(8, 16)))
    # ISO 11649 mod 97 check
    rearranged = digits + "271500"  # 'RF' + '00'
    check = 98 - (int(rearranged) % 97)
    return f"RF{check:02d} " + " ".join(digits[i:i+4] for i in range(0, len(digits), 4))


def vendor_to_bank_desc(vendor_name: str, rng: random.Random) -> str:
    """Convert a vendor name to a bank-statement-style description.

    Real bank exports are noisy: ALL CAPS, sometimes truncated, sometimes
    with city, sometimes with OY suffix added/dropped.
    """
    name = vendor_name.upper()
    # 30% truncate to first word(s)
    r = rng.random()
    if r < 0.10:
        # Just first word
        name = name.split()[0]
    elif r < 0.25:
        # Drop "OY"/"OYJ"/"AB"/"AB OY" suffixes
        for suffix in [" OYJ AB", " AB OY", " OYJ", " OY", " AB"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
    elif r < 0.40:
        # Add city
        cities = ["HELSINKI", "ESPOO", "VANTAA", "TAMPERE", "TURKU", "OULU"]
        name += f" {rng.choice(cities)}"

    # Truncate long names — bank exports often cap at 35 chars
    if len(name) > 35:
        name = name[:35].rstrip()
    return name


def generate_description(category: str) -> str:
    templates = TEMPLATES.get(category, ["Invoice - {ref}"])
    template = random.choice(templates)
    return template.format(
        ref=f"{random.randint(1000, 9999)}",
        q=random.randint(1, 4),
        count=random.randint(2, 50),
        week=random.randint(1, 52),
        dept=random.choice(DEPARTMENTS),
        ver=f"{random.randint(1, 5)}.{random.randint(0, 9)}",
    )


# ── Customer generation ──────────────────────────────────────────

def generate_customers(scale: str = "full") -> list[dict]:
    """Generate 256 customers with geometric size distribution."""
    tiers = {
        "full":   [(1, 128000), (2, 64000), (4, 32000), (8, 16000), (16, 8000), (32, 4000), (64, 2000), (128, 1000)],
        "medium": [(1, 16000), (2, 8000), (4, 4000), (8, 2000), (16, 1000), (32, 500), (64, 250), (128, 125)],
        "small":  [(1, 2000), (2, 1000), (4, 500), (8, 250), (16, 125), (32, 64), (64, 32), (128, 16)],
    }

    tier_list = tiers[scale]
    customers = []
    cid = 0

    tier_names = ["enterprise", "enterprise", "large", "large", "midmarket", "midmarket", "small", "small"]

    for tier_idx, (count, invoice_count) in enumerate(tier_list):
        tier_name = tier_names[tier_idx]
        for i in range(count):
            employee_count = max(1, invoice_count // 100)
            customers.append({
                "customer_id": f"CUST-{cid:04d}",
                "name": f"Customer {cid:04d}",  # will be enriched later
                "size_tier": tier_name,
                "invoice_count": invoice_count,
                "employee_count": employee_count,
            })
            cid += 1

    total_invoices = sum(c["invoice_count"] for c in customers)
    print(f"  {len(customers)} customers, {total_invoices:,} total invoices planned")
    return customers


# ── Employee generation ───────────────────────────────────────────

FIRST_NAMES = [
    "Matti", "Juha", "Mikko", "Timo", "Jari", "Antti", "Markku", "Pekka",
    "Anna", "Maria", "Sanna", "Tiina", "Päivi", "Laura", "Hanna", "Minna",
    "Tuomas", "Ville", "Janne", "Petri", "Eero", "Kari", "Heikki", "Tapani",
    "Elina", "Johanna", "Katja", "Riikka", "Outi", "Merja", "Kirsi", "Pirjo",
]

LAST_NAMES = [
    "Virtanen", "Korhonen", "Nieminen", "Mäkinen", "Hämäläinen", "Laine",
    "Heikkinen", "Koskinen", "Järvinen", "Lehtonen", "Lehtinen", "Saarinen",
    "Niemi", "Salminen", "Heinonen", "Heikkilä", "Kinnunen", "Salonen",
    "Turunen", "Laitinen", "Tuominen", "Rantanen", "Karjalainen", "Jokinen",
]


def generate_employees(customer: dict) -> list[dict]:
    """Generate employee hierarchy for a customer."""
    cid = customer["customer_id"]
    n = customer["employee_count"]
    employees = []

    for i in range(n):
        # Role distribution based on position
        if i == 0:
            role = "CEO" if n > 1 else "CEO"
        elif i < max(2, n * 0.05):
            role = "Director"
        elif i < max(3, n * 0.15):
            role = "Manager"
        elif i < max(4, n * 0.30):
            role = "Supervisor"
        else:
            role = "Employee"

        dept = DEPARTMENTS[i % len(DEPARTMENTS)] if n > 1 else "General"
        fname = FIRST_NAMES[i % len(FIRST_NAMES)]
        lname = LAST_NAMES[(i * 7 + hash(cid)) % len(LAST_NAMES)]

        # Supervisor: find someone with a higher role in same dept
        supervisor_id = None
        if role != "CEO" and employees:
            role_idx = ROLES.index(role)
            candidates = [e for e in employees if ROLES.index(e["role"]) < role_idx]
            if candidates:
                # Prefer same department
                dept_candidates = [e for e in candidates if e["department"] == dept]
                sup = random.choice(dept_candidates) if dept_candidates else random.choice(candidates)
                supervisor_id = sup["employee_id"]

        employees.append({
            "employee_id": f"{cid}-EMP-{i:04d}",
            "customer_id": cid,
            "name": f"{fname} {lname}",
            "role": role,
            "department": dept,
            "supervisor_id": supervisor_id,
            "active": True,
        })

    return employees


# ── Vendor assignment per customer ────────────────────────────────

def assign_vendors_to_customer(customer: dict, entities: list[dict], rng: random.Random) -> list[dict]:
    """Assign a subset of corporate entities as vendors for this customer.

    Each customer uses 20-80 vendors depending on size. Returns vendor
    definitions with customer-specific GL code and approver mappings.
    """
    n_vendors = min(len(entities), max(20, customer["invoice_count"] // 500))
    # Pick a random subset of entities
    selected = rng.sample(entities, min(n_vendors, len(entities)))

    vendors = []
    for entity in selected:
        # Assign a category based on industry
        industry = (entity.get("industry") or "").lower()
        if any(w in industry for w in ["software", "programming", "computer"]):
            cat = "software"
        elif any(w in industry for w in ["telecom", "communication"]):
            cat = "telecom"
        elif any(w in industry for w in ["clean", "facility", "security"]):
            cat = "facilities"
        elif any(w in industry for w in ["food", "restaurant", "cafe", "bakery", "dairy"]):
            cat = "food_bev"
        elif any(w in industry for w in ["transport", "freight", "logistics", "shipping"]):
            cat = "logistics"
        elif any(w in industry for w in ["insurance"]):
            cat = "insurance"
        elif any(w in industry for w in ["consult", "audit", "legal", "advisory"]):
            cat = "consulting"
        elif any(w in industry for w in ["construct", "building", "engineer", "maintenance"]):
            cat = "maintenance"
        elif any(w in industry for w in ["retail", "wholesale", "sale"]):
            cat = "supplies"
        elif any(w in industry for w in ["energy", "electric"]):
            cat = "maintenance"
        else:
            cat = rng.choice(CATEGORIES)

        gl_code, gl_label = GL_CODES[cat]

        vendors.append({
            "business_id": entity["business_id"],
            "name": entity["name"],
            "country": "FI",
            "category": cat,
            "gl_code": gl_code,
            "amount_mean": rng.uniform(200, 20000),
            "amount_std_ratio": rng.uniform(0.2, 0.6),
            "vat_pct": 24 if cat != "insurance" else 0,
            "due_days": rng.choice([14, 14, 30, 30, 30, 45]),
        })

    return vendors


# ── Invoice generation ────────────────────────────────────────────

def generate_invoices_for_customer(
    customer: dict,
    vendors: list[dict],
    employees: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Generate invoices, bank transactions, and overrides for one customer."""
    cid = customer["customer_id"]
    n = customer["invoice_count"]
    rng = random.Random(hash(cid))

    # Weighted vendor selection (some vendors invoice more often)
    vendor_weights = [rng.uniform(0.5, 3.0) for _ in vendors]
    total_weight = sum(vendor_weights)
    vendor_probs = [w / total_weight for w in vendor_weights]

    invoices = []
    bank_txns = []
    overrides = []

    # Find approvers (managers and above)
    approvers = [e for e in employees if e["role"] in ("CEO", "Director", "Manager")]
    if not approvers:
        approvers = employees[:1]

    for i in range(n):
        # Pick vendor (weighted)
        r = rng.random()
        cumulative = 0
        vendor_idx = 0
        for j, p in enumerate(vendor_probs):
            cumulative += p
            if r <= cumulative:
                vendor_idx = j
                break
        vdef = vendors[vendor_idx]

        amount = lognormal_amount(vdef["amount_mean"], vdef["amount_mean"] * vdef["amount_std_ratio"])
        desc = generate_description(vdef["category"])
        inv_date = random_date()

        # Processor and approver from employees
        dept_employees = [e for e in employees if e["department"] in ("Finance", "Procurement")]
        processor = rng.choice(dept_employees) if dept_employees else rng.choice(employees)
        approver = rng.choice(approvers)

        # Routing
        routed = rng.random() >= 0.12
        routed_by = "rule" if rng.random() < 0.20 else ("aito" if rng.random() < 0.90 else "human") if routed else "none"

        # Occasional GL anomaly (2%)
        gl_code = vdef["gl_code"]
        if rng.random() < 0.02:
            gl_code = rng.choice(list(set(v[0] for v in GL_CODES.values())))

        invoice = {
            "invoice_id": f"{cid}-INV-{i:06d}",
            "customer_id": cid,
            "vendor_business_id": vdef["business_id"],
            "vendor": vdef["name"],
            "vendor_country": vdef["country"],
            "category": vdef["category"],
            "amount": amount,
            "gl_code": gl_code,
            "cost_centre": COST_CENTRES.get(processor["department"], "CC-100"),
            "approver": approver["name"],
            "processor": processor["employee_id"],
            "vat_pct": vdef["vat_pct"],
            "payment_method": rng.choice(PAYMENT_METHODS),
            "due_days": vdef["due_days"],
            "description": desc,
            "invoice_date": inv_date,
            "routed": routed,
            "routed_by": routed_by,
        }
        invoices.append(invoice)

        # Bank transaction for ~60% of routed invoices
        if routed and rng.random() < 0.60:
            vendor_part = vendor_to_bank_desc(vdef["name"], rng)
            # Reference number style: Finnish viite (75%), RF reference (20%), free-text note (5%)
            ref_choice = rng.random()
            if ref_choice < 0.75:
                ref = f"VIITE {finnish_reference(rng)}"
            elif ref_choice < 0.95:
                ref = rf_reference(rng)
            else:
                ref = f"LASKU {rng.randint(2024, 2026)}-{rng.randint(1000, 9999)}"

            # Payment date typically near invoice date
            pay_date = inv_date  # already ISO; we'll reformat to dd.mm.yy
            try:
                d = date.fromisoformat(pay_date)
                pay_str = f"{d.day:02d}.{d.month:02d}.{str(d.year)[-2:]}"
            except Exception:
                pay_str = ""

            # Concatenate parts as a real bank export would
            parts = [vendor_part, ref]
            if pay_str:
                parts.append(f"PVM {pay_str}")
            bank_desc = " / ".join(parts)
            if len(bank_desc) > 70:
                bank_desc = bank_desc[:70].rstrip()

            amt_diff = rng.choice([0, 0, 0, 0.50, -0.50, 1.00])
            bank_txns.append({
                "transaction_id": f"{cid}-TXN-{len(bank_txns):06d}",
                "customer_id": cid,
                "description": bank_desc,
                "vendor_name": vdef["name"],
                "amount": round(amount + amt_diff, 2),
                "bank": rng.choice(BANKS),
                "invoice_id": invoice["invoice_id"],
            })

        # Override for ~6% of invoices
        if rng.random() < 0.06:
            field = rng.choice(["gl_code", "gl_code", "gl_code", "approver", "cost_centre"])
            if field == "gl_code":
                predicted = gl_code
                corrected = rng.choice([c for c in set(v[0] for v in GL_CODES.values()) if c != predicted])
            elif field == "approver":
                predicted = approver["name"]
                corrected = rng.choice([a["name"] for a in approvers if a["name"] != predicted]) if len(approvers) > 1 else predicted
            else:
                predicted = invoice["cost_centre"]
                corrected = rng.choice([v for v in COST_CENTRES.values() if v != predicted])

            overrides.append({
                "override_id": f"{cid}-OVR-{len(overrides):06d}",
                "customer_id": cid,
                "invoice_id": invoice["invoice_id"],
                "field": field,
                "predicted_value": predicted,
                "corrected_value": corrected,
                "confidence_was": round(rng.uniform(0.40, 0.88), 2),
                "corrected_by": rng.choice(approvers)["name"],
            })

    return invoices, bank_txns, overrides


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--small", action="store_true", help="~8K invoices")
    parser.add_argument("--medium", action="store_true", help="~100K invoices")
    args = parser.parse_args()

    scale = "small" if args.small else ("medium" if args.medium else "full")

    # Load corporate entities
    entities_file = DATA_DIR / "corporate_entities_raw.json"
    if not entities_file.exists():
        print(f"Error: {entities_file} not found. Run: python data/fetch_companies.py")
        return

    with open(entities_file) as f:
        all_entities = json.load(f)
    print(f"Loaded {len(all_entities)} corporate entities from PRH")

    # Generate customers
    print(f"\nGenerating customers ({scale} scale)...")
    customers = generate_customers(scale)

    # Generate employees
    print("Generating employees...")
    all_employees = []
    for cust in customers:
        emps = generate_employees(cust)
        all_employees.extend(emps)
    print(f"  {len(all_employees)} employees")

    # Generate invoices per customer
    print("Generating invoices...")
    all_invoices = []
    all_bank_txns = []
    all_overrides = []
    customer_rng = random.Random(42)

    for idx, cust in enumerate(customers):
        vendors = assign_vendors_to_customer(cust, all_entities, customer_rng)
        emps = [e for e in all_employees if e["customer_id"] == cust["customer_id"]]
        invoices, bank_txns, overrides = generate_invoices_for_customer(cust, vendors, emps)
        all_invoices.extend(invoices)
        all_bank_txns.extend(bank_txns)
        all_overrides.extend(overrides)

        if (idx + 1) % 50 == 0 or idx == len(customers) - 1:
            print(f"  {idx+1}/{len(customers)} customers, {len(all_invoices):,} invoices so far")

    # Prepare corporate entities for upload (subset that's actually used)
    used_bids = {inv["vendor_business_id"] for inv in all_invoices}
    corp_entities = [e for e in all_entities if e["business_id"] in used_bids]

    # Save all fixtures
    fixtures = {
        "customers": customers,
        "corporate_entities": corp_entities,
        "employees": all_employees,
        "invoices": all_invoices,
        "bank_transactions": all_bank_txns,
        "overrides": all_overrides,
    }

    print(f"\nSaving fixtures...")
    for name, records in fixtures.items():
        path = DATA_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(records, f, indent=None, ensure_ascii=False)
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"  {name}: {len(records):,} records ({size_mb:.1f} MB)")

    # Stats
    print(f"\nSummary:")
    print(f"  Customers: {len(customers)}")
    print(f"  Corporate entities: {len(corp_entities)}")
    print(f"  Employees: {len(all_employees)}")
    print(f"  Invoices: {len(all_invoices):,}")
    print(f"  Bank transactions: {len(all_bank_txns):,}")
    print(f"  Overrides: {len(all_overrides):,}")

    # Customer size distribution
    print(f"\n  Size distribution:")
    by_tier = {}
    for c in customers:
        tier = c["size_tier"]
        by_tier[tier] = by_tier.get(tier, 0) + 1
    for tier, count in sorted(by_tier.items()):
        tier_invoices = sum(c["invoice_count"] for c in customers if c["size_tier"] == tier)
        print(f"    {tier:12} {count:4} customers, {tier_invoices:>10,} invoices")


if __name__ == "__main__":
    main()
