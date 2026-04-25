#!/usr/bin/env python3
"""Generate realistic Finnish accounting data at scale.

Produces 100K+ invoices with temporal patterns, Zipf vendor
distribution, log-normal amounts, and proportional bank
transactions and overrides.

Usage:
    python data/generate_fixtures.py              # 100K invoices
    python data/generate_fixtures.py --small      # 1K invoices (fast dev)
    python data/generate_fixtures.py --count 50000
"""

import argparse
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent

# ── Vendor definitions ──────────────────────────────────────────────
# Tier 1: High-frequency recurring vendors (60% of invoices)
# Tier 2: Medium-frequency quarterly/monthly (30%)
# Tier 3: Long-tail rare vendors (10%)

VENDORS_TIER1 = [
    {"vendor": "Telia Finland", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 1200, "amount_std": 400, "frequency": "monthly"},
    {"vendor": "Elisa Oyj", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 800, "amount_std": 300, "frequency": "monthly"},
    {"vendor": "Kesko Oyj", "country": "FI", "category": "supplies", "gl_code": "4400", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 4500, "amount_std": 2000, "frequency": "weekly"},
    {"vendor": "SOK Corporation", "country": "FI", "category": "supplies", "gl_code": "4400", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 6000, "amount_std": 3000, "frequency": "weekly"},
    {"vendor": "Fazer Bakeries", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 2000, "amount_std": 800, "frequency": "weekly"},
    {"vendor": "Valio Oy", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 1500, "amount_std": 600, "frequency": "weekly"},
    {"vendor": "ISS Palvelut", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 5000, "amount_std": 1500, "frequency": "monthly"},
    {"vendor": "Securitas Oy", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 3500, "amount_std": 1000, "frequency": "monthly"},
    {"vendor": "AWS EMEA", "country": "IE", "category": "cloud", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_mean": 2500, "amount_std": 1500, "frequency": "monthly"},
    {"vendor": "Microsoft Ireland", "country": "IE", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 3000, "amount_std": 2000, "frequency": "monthly"},
]

VENDORS_TIER2 = [
    {"vendor": "Hartwall Oy", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 3000, "amount_std": 2000, "frequency": "biweekly"},
    {"vendor": "Kone Oyj", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 12000, "amount_std": 5000, "frequency": "quarterly"},
    {"vendor": "Wärtsilä Oyj", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 45, "amount_mean": 20000, "amount_std": 10000, "frequency": "quarterly"},
    {"vendor": "Staples Finland", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 150, "amount_std": 100, "frequency": "weekly"},
    {"vendor": "Lyreco Oy", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 120, "amount_std": 80, "frequency": "biweekly"},
    {"vendor": "Verkkokauppa.com", "country": "FI", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 1200, "amount_std": 800, "frequency": "monthly"},
    {"vendor": "Dustin Finland", "country": "FI", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 2000, "amount_std": 1500, "frequency": "monthly"},
    {"vendor": "SAP SE", "country": "DE", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 15000, "amount_std": 10000, "frequency": "quarterly"},
    {"vendor": "Coor Service Management", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 4000, "amount_std": 1500, "frequency": "monthly"},
    {"vendor": "Lindström Oy", "country": "FI", "category": "facilities", "gl_code": "5100", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 2500, "amount_std": 800, "frequency": "monthly"},
    {"vendor": "Fonecta Oy", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 500, "amount_std": 200, "frequency": "monthly"},
    {"vendor": "DNA Oyj", "country": "FI", "category": "telecom", "gl_code": "6200", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 600, "amount_std": 250, "frequency": "monthly"},
    {"vendor": "Paulig Oy", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 800, "amount_std": 400, "frequency": "biweekly"},
    {"vendor": "Atria Oyj", "country": "FI", "category": "food_bev", "gl_code": "4100", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 14, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 2500, "amount_std": 1200, "frequency": "weekly"},
    {"vendor": "Caverion Oyj", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 8000, "amount_std": 4000, "frequency": "quarterly"},
    {"vendor": "Bravida Finland", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 6000, "amount_std": 3000, "frequency": "quarterly"},
    {"vendor": "Visma Solutions", "country": "FI", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 2000, "amount_std": 800, "frequency": "monthly"},
    {"vendor": "Google Ireland", "country": "IE", "category": "cloud", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_mean": 1500, "amount_std": 1000, "frequency": "monthly"},
    {"vendor": "Gigantti Oy", "country": "FI", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 800, "amount_std": 500, "frequency": "monthly"},
    {"vendor": "PostNord Oy", "country": "FI", "category": "logistics", "gl_code": "4600", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 400, "amount_std": 200, "frequency": "weekly"},
    {"vendor": "Posti Group", "country": "FI", "category": "logistics", "gl_code": "4600", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 350, "amount_std": 150, "frequency": "weekly"},
    {"vendor": "If Vakuutus", "country": "FI", "category": "insurance", "gl_code": "5300", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 0, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 8000, "amount_std": 3000, "frequency": "quarterly"},
    {"vendor": "Fennia Oy", "country": "FI", "category": "insurance", "gl_code": "5300", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 0, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 5000, "amount_std": 2000, "frequency": "quarterly"},
    {"vendor": "KPMG Finland", "country": "FI", "category": "consulting", "gl_code": "5400", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 15000, "amount_std": 8000, "frequency": "quarterly"},
    {"vendor": "PwC Finland", "country": "FI", "category": "consulting", "gl_code": "5400", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 12000, "amount_std": 6000, "frequency": "quarterly"},
]

VENDORS_TIER3 = [
    {"vendor": "Rautakirja Oy", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 80, "amount_std": 40, "frequency": "rare"},
    {"vendor": "Murata Electronics", "country": "JP", "category": "it_equipment", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "Wire Transfer", "due_days": 60, "amount_mean": 25000, "amount_std": 15000, "frequency": "rare"},
    {"vendor": "Siemens AG", "country": "DE", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 45, "amount_mean": 30000, "amount_std": 15000, "frequency": "rare"},
    {"vendor": "ABB Oy", "country": "FI", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 18000, "amount_std": 8000, "frequency": "rare"},
    {"vendor": "Schneider Electric", "country": "FR", "category": "maintenance", "gl_code": "5200", "cost_centre": "CC-300", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 45, "amount_mean": 22000, "amount_std": 10000, "frequency": "rare"},
    {"vendor": "Oracle Finland", "country": "FI", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 20000, "amount_std": 12000, "frequency": "rare"},
    {"vendor": "Salesforce UK", "country": "GB", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_mean": 5000, "amount_std": 3000, "frequency": "rare"},
    {"vendor": "Slack Technologies", "country": "IE", "category": "software", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_mean": 800, "amount_std": 300, "frequency": "rare"},
    {"vendor": "Hetzner GmbH", "country": "DE", "category": "cloud", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 500, "amount_std": 300, "frequency": "rare"},
    {"vendor": "DigitalOcean", "country": "US", "category": "cloud", "gl_code": "6100", "cost_centre": "CC-400", "approver": "Mikael H.", "vat_pct": 24, "payment_method": "Credit Card", "due_days": 0, "amount_mean": 300, "amount_std": 200, "frequency": "rare"},
    {"vendor": "Manpower Finland", "country": "FI", "category": "consulting", "gl_code": "5400", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 8000, "amount_std": 4000, "frequency": "rare"},
    {"vendor": "Adecco Finland", "country": "FI", "category": "consulting", "gl_code": "5400", "cost_centre": "CC-100", "approver": "Tiina M.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 6000, "amount_std": 3000, "frequency": "rare"},
    {"vendor": "Otava Oy", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 10, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 200, "amount_std": 100, "frequency": "rare"},
    {"vendor": "Sanoma Oyj", "country": "FI", "category": "office", "gl_code": "4500", "cost_centre": "CC-100", "approver": "Mikael H.", "vat_pct": 10, "payment_method": "SEPA Credit Transfer", "due_days": 14, "amount_mean": 300, "amount_std": 150, "frequency": "rare"},
    {"vendor": "Tikkurila Oyj", "country": "FI", "category": "supplies", "gl_code": "4400", "cost_centre": "CC-210", "approver": "Sanna L.", "vat_pct": 24, "payment_method": "SEPA Credit Transfer", "due_days": 30, "amount_mean": 1500, "amount_std": 800, "frequency": "rare"},
]

ALL_VENDORS = VENDORS_TIER1 + VENDORS_TIER2 + VENDORS_TIER3

# GL code labels
GL_LABELS = {
    "4100": "COGS", "4400": "Supplies", "4500": "Office", "4600": "Logistics",
    "5100": "Facilities", "5200": "Maintenance", "5300": "Insurance",
    "5400": "Consulting", "6100": "IT & Software", "6200": "Telecom",
}

DESCRIPTIONS = {
    "telecom": ["Monthly subscription", "Mobile plan", "Broadband service", "Data plan", "Phone service"],
    "supplies": ["Grocery supplies", "Retail products", "Store inventory", "Wholesale order", "Materials"],
    "food_bev": ["Bakery products", "Dairy delivery", "Beverages", "Catering order", "Food supplies"],
    "maintenance": ["Equipment service", "Annual maintenance", "Spare parts", "Technical inspection", "Repair work"],
    "office": ["Office supplies", "Printer paper", "Stationery", "Desk accessories", "Books"],
    "it_equipment": ["Laptop purchase", "Monitor order", "Peripherals", "Network equipment", "Accessories"],
    "facilities": ["Cleaning services", "Security monthly", "Building maintenance", "Waste management"],
    "software": ["License renewal", "SaaS subscription", "Enterprise license", "Support contract"],
    "cloud": ["Cloud hosting", "Compute resources", "Storage fees", "CDN services"],
    "logistics": ["Shipping", "Courier service", "Freight", "Parcel delivery"],
    "insurance": ["Property insurance", "Liability coverage", "Fleet insurance", "Risk premium"],
    "consulting": ["Advisory services", "Audit fees", "Project consulting", "Strategy review"],
}

APPROVERS = ["Mikael H.", "Sanna L.", "Tiina M."]

# Date range: 24 months
START_DATE = date(2024, 5, 1)
END_DATE = date(2026, 4, 30)
TOTAL_DAYS = (END_DATE - START_DATE).days


def lognormal_amount(mean: float, std: float) -> float:
    """Generate a log-normal amount with Finnish rounding bias."""
    # Convert mean/std to log-normal parameters
    variance = std ** 2
    mu = math.log(mean ** 2 / math.sqrt(variance + mean ** 2))
    sigma = math.sqrt(math.log(1 + variance / mean ** 2))
    amount = random.lognormvariate(mu, sigma)
    # Finnish rounding: bias toward .00 and .50
    if random.random() < 0.3:
        amount = round(amount, 0)
    elif random.random() < 0.5:
        amount = round(amount * 2, 0) / 2  # round to .50
    else:
        amount = round(amount, 2)
    return max(1.0, amount)


def random_date() -> str:
    """Generate a random date in the 24-month range."""
    days = random.randint(0, TOTAL_DAYS)
    d = START_DATE + timedelta(days=days)
    return d.isoformat()


def pick_vendor(tier_weights=(0.60, 0.30, 0.10)):
    """Pick a vendor using Zipf-like tier distribution."""
    r = random.random()
    if r < tier_weights[0]:
        return random.choice(VENDORS_TIER1)
    elif r < tier_weights[0] + tier_weights[1]:
        return random.choice(VENDORS_TIER2)
    else:
        return random.choice(VENDORS_TIER3)


def generate_invoices(n: int = 100000) -> list[dict]:
    """Generate n invoices with realistic patterns."""
    invoices = []
    unrouted_ratio = 0.12  # 12% unrouted

    for i in range(n):
        vdef = pick_vendor()
        amount = lognormal_amount(vdef["amount_mean"], vdef["amount_std"])
        desc = random.choice(DESCRIPTIONS.get(vdef["category"], ["Invoice"]))
        inv_date = random_date()

        # Routing: 20% rules, 68% Aito, 12% unrouted
        routed = random.random() >= unrouted_ratio
        if routed:
            routed_by = "rule" if random.random() < 0.23 else ("aito" if random.random() < 0.90 else "human")
        else:
            routed_by = "none"

        # Occasional GL anomaly (2%)
        gl_code = vdef["gl_code"]
        if random.random() < 0.02:
            gl_code = random.choice(list(GL_LABELS.keys()))

        invoice = {
            "invoice_id": f"INV-{10000 + i}",
            "vendor": vdef["vendor"],
            "vendor_country": vdef["country"],
            "category": vdef["category"],
            "amount": amount,
            "gl_code": gl_code,
            "cost_centre": vdef["cost_centre"],
            "approver": vdef["approver"],
            "vat_pct": vdef["vat_pct"],
            "payment_method": vdef["payment_method"],
            "due_days": vdef["due_days"],
            "description": desc,
            "invoice_date": inv_date,
            "routed": routed,
            "routed_by": routed_by,
        }
        invoices.append(invoice)

    return invoices


def generate_bank_transactions(invoices: list[dict]) -> list[dict]:
    """Generate bank transactions, ~60% matching invoices."""
    transactions = []
    routed = [inv for inv in invoices if inv["routed"]]
    n_matched = int(len(routed) * 0.60)
    matched = random.sample(routed, min(n_matched, len(routed)))

    bank_descs = {}  # vendor -> bank description style

    for inv in matched:
        vendor = inv["vendor"]
        if vendor not in bank_descs:
            # Generate a bank description style for this vendor
            parts = vendor.upper().split()
            if random.random() < 0.2:
                bank_descs[vendor] = parts[0]  # abbreviated
            elif random.random() < 0.3:
                bank_descs[vendor] = vendor.upper() + " OY"
            else:
                bank_descs[vendor] = vendor.upper()

        bank_desc = bank_descs[vendor]
        # Amount may differ slightly
        amount_diff = random.choice([0, 0, 0, 0, 0.50, -0.50, 1.00, 2.00])
        bank_amount = round(inv["amount"] + amount_diff, 2)
        bank = random.choice(["OP Bank", "Nordea", "Danske Bank", "Handelsbanken"])

        txn = {
            "transaction_id": f"TXN-{100000 + len(transactions)}",
            "description": bank_desc,
            "vendor_name": inv["vendor"],
            "amount": bank_amount,
            "bank": bank,
            "invoice_id": inv["invoice_id"],
        }
        transactions.append(txn)

    # Unmatched bank transactions (~5% of total)
    n_unmatched = max(20, len(transactions) // 20)
    unmatched_descs = [
        "UNKNOWN PAYMENT", "MISC TRANSFER", "SALARY REFUND",
        "INSURANCE PREMIUM", "TAX REFUND", "BANK FEE",
        "INTEREST PAYMENT", "DIVIDEND", "CORRECTION",
    ]
    for i in range(n_unmatched):
        txn = {
            "transaction_id": f"TXN-{100000 + len(transactions)}",
            "description": random.choice(unmatched_descs),
            "vendor_name": None,
            "amount": round(random.uniform(10, 5000), 2),
            "bank": random.choice(["OP Bank", "Nordea"]),
            "invoice_id": None,
        }
        transactions.append(txn)

    return transactions


def generate_overrides(invoices: list[dict]) -> list[dict]:
    """Generate human override records (~6% of invoices)."""
    overrides = []
    correctors = APPROVERS
    n_overrides = max(20, len(invoices) // 16)

    # GL code overrides (65% of overrides)
    for _ in range(int(n_overrides * 0.65)):
        inv = random.choice(invoices)
        predicted = inv["gl_code"]
        corrected = random.choice([c for c in GL_LABELS.keys() if c != predicted])
        overrides.append({
            "override_id": f"OVR-{1000 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "gl_code",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.45, 0.88), 2),
            "corrected_by": random.choice(correctors),
        })

    # Approver overrides (20%)
    for _ in range(int(n_overrides * 0.20)):
        inv = random.choice(invoices)
        predicted = inv["approver"]
        corrected = random.choice([a for a in correctors if a != predicted])
        overrides.append({
            "override_id": f"OVR-{1000 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "approver",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.50, 0.92), 2),
            "corrected_by": random.choice(correctors),
        })

    # Cost centre overrides (15%)
    centres = ["CC-100", "CC-210", "CC-300", "CC-400"]
    for _ in range(int(n_overrides * 0.15)):
        inv = random.choice(invoices)
        predicted = inv["cost_centre"]
        corrected = random.choice([c for c in centres if c != predicted])
        overrides.append({
            "override_id": f"OVR-{1000 + len(overrides)}",
            "invoice_id": inv["invoice_id"],
            "field": "cost_centre",
            "predicted_value": predicted,
            "corrected_value": corrected,
            "confidence_was": round(random.uniform(0.55, 0.85), 2),
            "corrected_by": random.choice(correctors),
        })

    return overrides


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100000)
    parser.add_argument("--small", action="store_true", help="Generate 1K invoices for fast dev")
    args = parser.parse_args()

    n = 1000 if args.small else args.count

    print(f"Generating {n} invoices with {len(ALL_VENDORS)} vendors...")
    invoices = generate_invoices(n)
    bank_txns = generate_bank_transactions(invoices)
    overrides = generate_overrides(invoices)

    for name, records in [("invoices", invoices), ("bank_transactions", bank_txns), ("overrides", overrides)]:
        path = DATA_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(records, f, indent=None, ensure_ascii=False)
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"  {name}: {len(records)} records ({size_mb:.1f} MB)")

    # Print vendor distribution
    vendor_counts = {}
    for inv in invoices:
        vendor_counts[inv["vendor"]] = vendor_counts.get(inv["vendor"], 0) + 1
    top10 = sorted(vendor_counts.items(), key=lambda x: -x[1])[:10]
    print(f"\nTop 10 vendors:")
    for v, c in top10:
        print(f"  {v:25} {c:>6} ({c/len(invoices)*100:.1f}%)")

    cat_counts = {}
    for inv in invoices:
        cat_counts[inv["category"]] = cat_counts.get(inv["category"], 0) + 1
    print(f"\nCategories:")
    for cat, c in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:20} {c:>6} ({c/len(invoices)*100:.1f}%)")


if __name__ == "__main__":
    main()
