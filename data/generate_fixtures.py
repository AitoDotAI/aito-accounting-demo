#!/usr/bin/env python3
"""Generate sample accounting data fixtures for the Aito demo.

Run once to create the JSON files. The generated data is checked into
the repo — this script documents how it was created and can regenerate
if the schema changes.

Usage: python data/generate_fixtures.py
"""

import json
import random
from pathlib import Path

random.seed(42)  # Reproducible output

DATA_DIR = Path(__file__).parent

# ── Vendor definitions ──────────────────────────────────────────────
# Each vendor has consistent patterns that Aito should learn.
VENDORS = [
    {"vendor": "Telia Finland", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (500, 2000)},
    {"vendor": "Elisa Oyj", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (300, 1500)},
    {"vendor": "Kesko Oyj", "country": "FI", "category": "supplies", "gl_code": "4400", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (1000, 8000)},
    {"vendor": "SOK Corporation", "country": "FI", "category": "supplies", "gl_code": "4400", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (2000, 12000)},
    {"vendor": "Fazer Bakeries", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (800, 4000)},
    {"vendor": "Valio Oy", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (500, 3000)},
    {"vendor": "Hartwall Oy", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (1000, 15000)},
    {"vendor": "Kone Oyj", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (5000, 25000)},
    {"vendor": "Wärtsilä Oyj", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 45, "amount_range": (8000, 40000)},
    {"vendor": "Staples Finland", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (20, 500)},
    {"vendor": "Lyreco Oy", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (30, 400)},
    {"vendor": "Verkkokauppa.com", "country": "FI", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_range": (100, 3000)},
    {"vendor": "Dustin Finland", "country": "FI", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (200, 5000)},
    {"vendor": "ISS Palvelut", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (3000, 8000)},
    {"vendor": "Securitas Oy", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (2000, 6000)},
    # Foreign vendors — less predictable
    {"vendor": "SAP SE", "country": "DE", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (5000, 50000)},
    {"vendor": "Microsoft Ireland", "country": "IE", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_range": (500, 8000)},
    {"vendor": "AWS EMEA", "country": "IE", "category": "cloud", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_range": (200, 5000)},
]

DESCRIPTIONS = {
    "telecom": ["Monthly subscription", "Mobile plan Q{q}", "Broadband service", "Data plan"],
    "supplies": ["Grocery supplies", "Retail products Q{q}", "Store inventory", "Wholesale order"],
    "food_bev": ["Bakery products", "Dairy delivery", "Beverages Q{q}", "Catering order"],
    "maintenance": ["Equipment service", "Annual maintenance", "Spare parts", "Technical inspection"],
    "office": ["Office supplies", "Printer paper", "Stationery order", "Desk accessories"],
    "it_equipment": ["Laptop purchase", "Monitor order", "Peripherals", "Network equipment"],
    "facilities": ["Cleaning services", "Security monthly", "Building maintenance", "Waste management"],
    "software": ["License renewal", "SaaS subscription Q{q}", "Enterprise license", "Support contract"],
    "cloud": ["Cloud hosting", "AWS monthly", "Compute resources", "Storage fees"],
}


def round_amount(amount: float) -> float:
    """Round to realistic invoice amounts (cents)."""
    return round(amount, 2)


def generate_invoices(n: int = 200) -> list[dict]:
    """Generate n invoices with learnable patterns."""
    invoices = []
    for i in range(n):
        vendor_def = random.choice(VENDORS)
        q = (i % 4) + 1
        lo, hi = vendor_def["amount_range"]
        amount = round_amount(random.uniform(lo, hi))

        desc_templates = DESCRIPTIONS[vendor_def["category"]]
        description = random.choice(desc_templates).format(q=q)

        # Most invoices are routed (simulates historical data)
        # ~70% by rules for known vendors, ~20% by Aito, ~10% human
        route_roll = random.random()
        if route_roll < 0.23:
            routed_by = "rule"
        elif route_roll < 0.91:
            routed_by = "aito"
        else:
            routed_by = "human"

        # Introduce occasional variation (makes anomaly detection interesting)
        gl_code = vendor_def["gl_code"]
        approver = vendor_def["approver"]
        cost_centre = vendor_def["cost_centre"]

        if random.random() < 0.03:  # 3% anomalous GL code
            gl_code = random.choice(["4100", "4400", "4500", "5100", "5200", "6100", "6200"])

        invoice = {
            "invoice_id": f"INV-{2600 + i}",
            "vendor": vendor_def["vendor"],
            "vendor_country": vendor_def["country"],
            "category": vendor_def["category"],
            "amount": amount,
            "gl_code": gl_code,
            "cost_centre": cost_centre,
            "approver": approver,
            "vat_pct": vendor_def["vat_pct"],
            "payment_method": vendor_def["payment_method"],
            "due_days": vendor_def["due_days"],
            "description": description,
            "routed": True,
            "routed_by": routed_by,
        }
        invoices.append(invoice)

    # Add some unrouted invoices (for rule mining)
    for i in range(30):
        vendor_def = random.choice(VENDORS)
        lo, hi = vendor_def["amount_range"]
        amount = round_amount(random.uniform(lo, hi))
        desc_templates = DESCRIPTIONS[vendor_def["category"]]
        description = random.choice(desc_templates).format(q=random.randint(1, 4))

        invoice = {
            "invoice_id": f"INV-{2800 + i}",
            "vendor": vendor_def["vendor"],
            "vendor_country": vendor_def["country"],
            "category": vendor_def["category"],
            "amount": amount,
            "gl_code": vendor_def["gl_code"],
            "cost_centre": vendor_def["cost_centre"],
            "approver": vendor_def["approver"],
            "vat_pct": vendor_def["vat_pct"],
            "payment_method": vendor_def["payment_method"],
            "due_days": vendor_def["due_days"],
            "description": description,
            "routed": False,
            "routed_by": "none",
        }
        invoices.append(invoice)

    return invoices


def generate_bank_transactions(invoices: list[dict]) -> list[dict]:
    """Generate bank transactions, some matching invoices."""
    transactions = []
    # Match ~60% of routed invoices to bank transactions
    routed = [inv for inv in invoices if inv["routed"]]
    matched = random.sample(routed, min(100, int(len(routed) * 0.6)))

    for inv in matched:
        # Bank descriptions are uppercased vendor names, sometimes abbreviated
        bank_desc = inv["vendor"].upper()
        if random.random() < 0.2:
            bank_desc = bank_desc.split()[0]  # Just first word

        # Amount may differ slightly (rounding, fees)
        amount_diff = random.choice([0, 0, 0, 0, 0.50, -0.50, 1.00, 2.00])
        bank_amount = round_amount(inv["amount"] + amount_diff)

        bank = random.choice(["OP Bank", "Nordea", "Danske Bank", "Handelsbanken"])

        txn = {
            "transaction_id": f"TXN-{10000 + len(transactions)}",
            "description": bank_desc,
            "amount": bank_amount,
            "bank": bank,
            "invoice_id": inv["invoice_id"],
        }
        transactions.append(txn)

    # Add some unmatched bank transactions
    for i in range(20):
        txn = {
            "transaction_id": f"TXN-{10000 + len(transactions)}",
            "description": random.choice(["UNKNOWN PAYMENT", "MISC TRANSFER", "SALARY REFUND", "INSURANCE PREMIUM"]),
            "amount": round_amount(random.uniform(100, 5000)),
            "bank": random.choice(["OP Bank", "Nordea"]),
            "invoice_id": None,
        }
        transactions.append(txn)

    return transactions


def generate_overrides(invoices: list[dict]) -> list[dict]:
    """Generate human override records for the feedback loop."""
    overrides = []
    correctors = ["Sanna L.", "Mikael H.", "Tiina M."]

    # GL code overrides — most common type
    for i in range(29):
        inv = random.choice(invoices)
        predicted = inv["gl_code"]
        corrected = random.choice([c for c in ["4100", "4400", "4500", "5100", "5200", "6100", "6200"] if c != predicted])
        overrides.append({
            "override_id": f"OVR-{100 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "gl_code",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.55, 0.88), 2),
            "corrected_by": random.choice(correctors),
        })

    # Approver overrides
    for i in range(9):
        inv = random.choice(invoices)
        predicted = inv["approver"]
        corrected = random.choice([a for a in correctors if a != predicted])
        overrides.append({
            "override_id": f"OVR-{100 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "approver",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.60, 0.92), 2),
            "corrected_by": random.choice(correctors),
        })

    # Cost centre overrides
    for i in range(6):
        inv = random.choice(invoices)
        centres = ["CC-100", "CC-210", "CC-300", "CC-400"]
        predicted = inv["cost_centre"]
        corrected = random.choice([c for c in centres if c != predicted])
        overrides.append({
            "override_id": f"OVR-{100 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "cost_centre",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.65, 0.85), 2),
            "corrected_by": random.choice(correctors),
        })

    return overrides


def main():
    invoices = generate_invoices(200)
    bank_txns = generate_bank_transactions(invoices)
    overrides = generate_overrides(invoices)

    for name, records in [("invoices", invoices), ("bank_transactions", bank_txns), ("overrides", overrides)]:
        path = DATA_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(records)} records to {path.name}")


if __name__ == "__main__":
    main()
