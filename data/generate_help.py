#!/usr/bin/env python3
"""Generate help articles + simulated impression/click data.

Three article categories:
  - app:      product documentation (how Aito features work in this app)
  - legal:    Finnish AP / VAT compliance pointers (illustrative)
  - internal: per-customer company-specific guidance

Impressions are synthesized so the click-through-rate ranking signal
exists from day one — otherwise it's a chicken-and-egg problem.
Real usage replaces these with live impression/click data.

Usage: python data/generate_help.py
"""

import argparse
import json
import random
from pathlib import Path

random.seed(7)

DATA_DIR = Path(__file__).parent

# ── App documentation ────────────────────────────────────────────

APP_ARTICLES = [
    {
        "title": "How GL code prediction works",
        "body": "When a new invoice arrives, Aito predicts its GL code by looking at the customer's history of similar invoices. The where clause is { customer_id, vendor, amount, category } and the predicted field is gl_code. Each prediction comes with a confidence score $p between 0 and 1, plus a $why explanation showing which input features drove the result.",
        "tags": "gl_code prediction confidence why",
        "page_context": "/invoices",
    },
    {
        "title": "Reading the touchless rate",
        "body": "Touchless rate is the share of pending invoices Aito predicts at confidence ≥ 0.85. These are auto-routed without human review. Click the metric card to filter the table to only touchless invoices and confirm what's happening.",
        "tags": "touchless rate threshold filter",
        "page_context": "/invoices",
    },
    {
        "title": "Why a rule says 'Drifting'",
        "body": "A rule's status is Drifting when its precision over the last 12 weeks fell by more than 5 percentage points. Open the 12-week sparkline to see exactly when the drop happened. Common causes: vendor changed business model, new approver onboarded, override pattern emerging.",
        "tags": "drift drifting precision rule status",
        "page_context": "/quality/rules",
    },
    {
        "title": "Form Fill: confirming vs overriding predictions",
        "body": "A predicted field is shown in italic gold = State 2. Tab or click outside to confirm; the field switches to confirmed green State 3. Press Esc to clear. Type to replace. The visual distinction matters — predicted-but-wrong values silently shipping is the most dangerous form-fill failure.",
        "tags": "form fill smart predicted confirmed tab esc",
        "page_context": "/formfill",
    },
    {
        "title": "Payment matching via _predict invoice_id",
        "body": "When a bank transaction arrives, Aito traverses the schema link from bank_transactions.invoice_id to invoices and ranks candidates by association with the description tokens and amount. No separate matching service or Levenshtein heuristic — just _predict.",
        "tags": "matching bank transactions predict invoice_id link",
        "page_context": "/matching",
    },
    {
        "title": "Anomaly clusters: gl_mismatch, fraud_signal, unfamiliar, approver",
        "body": "Anomalies are grouped by reason. Fraud signals (red header) show round-number amounts to weak-history vendors and call for compliance escalation. GL mismatches are likely data-entry errors. Unfamiliar patterns mean Aito has no strong precedent. Approver issues mean the routing pattern shifted.",
        "tags": "anomaly fraud cluster category reasons recommendation",
        "page_context": "/anomalies",
    },
    {
        "title": "What does 'lift 38×' mean?",
        "body": "Lift is how many times more often a combination occurs vs random expectation. Lift > 20× is very strong, 5–20× is strong, 1–5× is weak, < 1× is anti-correlated. Hover the lift number anywhere in the app for the same explanation.",
        "tags": "lift relate explanation tooltip",
        "page_context": "/rulemining",
    },
    {
        "title": "How rules are mined",
        "body": "Rules aren't hand-coded. The mine_rules_for_customer function calls _relate(vendor → gl_code) per customer and keeps patterns where support_ratio ≥ 0.95 with at least 5 matches. A new vendor automatically becomes a rule once it meets the threshold; a vendor that drops below loses its rule.",
        "tags": "rule mining relate support threshold",
        "page_context": "/rulemining",
    },
    {
        "title": "Switching customers",
        "body": "The customer dropdown in the topbar searches by id, tier, or name. The green dot means the customer's data is warmed in cache (instant load). Amber means cold — the first request takes 10–20 seconds while Aito computes predictions. Subsequent visits are cached for an hour.",
        "tags": "customer dropdown switch warm cold cache",
        "page_context": "/",
    },
    {
        "title": "What is the Data flow toggle?",
        "body": "Click 'Data flow' in the topbar to overlay numbered gold badges on UI elements showing which Aito call produced each piece of data. The Aito side panel adds a 'Data flow on this page' section listing the calls. Every claim on screen traces to a specific query.",
        "tags": "data flow tour debug audit trace",
        "page_context": "/",
    },
]

# ── Legal / compliance (illustrative for Finland) ───────────────

LEGAL_ARTICLES = [
    {
        "title": "VAT (ALV) deduction requirements in Finland",
        "body": "For an invoice's input VAT to be deductible the supplier must be VAT-registered (Y-tunnus on file), the invoice must contain the supplier's VAT number, the breakdown of VAT per rate, and the seller's name. Aito flags missing fields as anomalies. Standard rate is 24%, reduced rates 14% (food, restaurants) and 10% (books, accommodation).",
        "tags": "vat alv deduction finland tax compliance",
        "page_context": None,
    },
    {
        "title": "Invoice retention period",
        "body": "Finnish accounting law requires invoices to be retained for at least 6 years from the end of the calendar year. Underlying documents (such as bank statements proving payment) follow the same rule. The prediction_log table is treated as audit support and falls under the same period.",
        "tags": "retention archive 6 years finland legal",
        "page_context": None,
    },
    {
        "title": "Reverse-charge VAT for EU service purchases",
        "body": "When a Finnish company buys services from another EU member state, the buyer accounts for both input and output VAT (käännetty verovelvollisuus). The invoice should NOT include foreign VAT. Aito's GL prediction handles this through the vendor_country field — non-FI EU vendors route to a different GL.",
        "tags": "reverse charge eu vat käännetty",
        "page_context": None,
    },
    {
        "title": "SOX-equivalent controls (segregation of duties)",
        "body": "Finland doesn't have SOX directly but listed companies fall under similar control frameworks (sisäinen valvonta). The key principle: the person who creates the invoice cannot also be the approver. Aito's approver prediction enforces this when paired with the customer's employee table — predicted approver is never the same person as processor.",
        "tags": "sox internal control segregation duties approver",
        "page_context": "/quality/rules",
    },
    {
        "title": "GDPR and prediction logs",
        "body": "The prediction_log table contains user names (the approvers). Under GDPR this is personal data with legitimate-interest basis (audit trail of work activity). Right to erasure does NOT override the 6-year retention. Right of access does — user can request all log entries naming them.",
        "tags": "gdpr privacy retention erasure",
        "page_context": "/quality/predictions",
    },
    {
        "title": "Late payment interest in Finnish B2B",
        "body": "B2B invoices accrue late payment interest at the reference rate + 8 percentage points (Finnish Interest Act, Korkolaki). Aito's anomaly detection flags suspicious due dates. The default in this demo is 30 days net, with vendors in maintenance/consulting categories on 45 days.",
        "tags": "late payment interest korkolaki due net days",
        "page_context": "/invoices",
    },
    {
        "title": "Required invoice fields under Finnish VAT law",
        "body": "A valid Finnish invoice must contain: invoice date, sequential invoice number, supplier name + Y-tunnus + VAT number, buyer name + Y-tunnus, description of goods/services, taxable amount per VAT rate, VAT rate, total VAT, total amount due. Missing any of these makes the input VAT non-deductible.",
        "tags": "invoice fields y-tunnus vat finland required",
        "page_context": None,
    },
    {
        "title": "Bookkeeping rules — Liikekirjuri vs custom chart",
        "body": "Most Finnish companies use the standard Liikekirjuri chart of accounts (numbering 1000–9999). This demo uses illustrative codes (4400 Materials, 5300 Insurance, 6200 Telecom) for readability. In production deployments the customer's actual chart is loaded into the gl_codes table.",
        "tags": "liikekirjuri chart accounts finland",
        "page_context": None,
    },
    {
        "title": "Money laundering (AML): suspicious transaction reporting",
        "body": "Round-number amounts to vendors with weak history are an AML red flag. The fraud_signal anomaly cluster surfaces exactly this pattern. Reporting is filed via the Financial Intelligence Unit (rahanpesun selvittelykeskus). Internal controls should require dual approval above €10K to a new vendor.",
        "tags": "aml money laundering fraud red flag reporting",
        "page_context": "/anomalies",
    },
    {
        "title": "Auditor's right to query the prediction system",
        "body": "External auditors have a right to inspect controls including AI-assisted ones. The Quality > Rules view exports the rules valid at any historical date via /api/quality/rules/history. The prediction_log table provides per-decision audit trail. Both satisfy audit walkthroughs.",
        "tags": "audit auditor inspect history walkthrough",
        "page_context": "/quality/rules",
    },
]

# ── Internal (per-customer guidance — illustrative) ─────────────

INTERNAL_TEMPLATES = [
    {
        "title_tpl": "Approval policy: invoices over €10,000",
        "body_tpl": "{customer} requires dual approval for any invoice above €10,000. The approver's signature is recorded in the overrides table even when the prediction is correct, to preserve the SOX trail. For amounts above €50,000, the CFO must also sign.",
        "tags": "approval policy threshold dual cfo over",
        "page_context": "/invoices",
    },
    {
        "title_tpl": "Cost centre rules at {customer}",
        "body_tpl": "At {customer}, cost centres are mapped strictly by department: Operations → CC-200, Sales → CC-300, IT → CC-400. Aito learns this from history but if the cost centre prediction looks wrong, override it — the next mining cycle will incorporate the correction.",
        "tags": "cost centre department mapping override",
        "page_context": "/formfill",
    },
    {
        "title_tpl": "Vendor onboarding at {customer}",
        "body_tpl": "Before a new vendor's first invoice can be processed at {customer}, procurement must complete the vendor checklist (Y-tunnus check, AML screening, IBAN verification). Aito's 'unfamiliar pattern' anomaly flags first-time vendors so they don't sneak through automation.",
        "tags": "vendor onboarding checklist procurement first-time",
        "page_context": "/anomalies",
    },
    {
        "title_tpl": "Quarter-end close at {customer}",
        "body_tpl": "{customer} closes the books on the 5th business day of the following month. Run Quality > Rules > Snapshot before close to lock the rule set in effect during the quarter. The snapshot becomes part of the audit support pack.",
        "tags": "close month quarter end snapshot audit",
        "page_context": "/quality/rules",
    },
    {
        "title_tpl": "Override policy at {customer}",
        "body_tpl": "{customer}'s policy requires the corrector to enter a reason for any GL or approver override — these surface in the Quality > Override Patterns view. Patterns repeating > 5 times with lift > 20× become rule candidates and are reviewed by the Controller monthly.",
        "tags": "override policy reason corrector pattern review",
        "page_context": "/quality/overrides",
    },
]


def make_internal_articles(customer_id: str, customer_name: str, rng: random.Random) -> list[dict]:
    out = []
    for i, tpl in enumerate(INTERNAL_TEMPLATES):
        out.append({
            "article_id": f"{customer_id}-INT-{i:02d}",
            "title": tpl["title_tpl"].format(customer=customer_name),
            "body": tpl["body_tpl"].format(customer=customer_name),
            "category": "internal",
            "customer_id": customer_id,
            "tags": tpl["tags"],
            "page_context": tpl["page_context"],
        })
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-customers", type=int, default=20,
                        help="Generate internal articles for the top N customers")
    args = parser.parse_args()

    # Load customers (need names + ids)
    customers_path = DATA_DIR / "customers.json"
    if not customers_path.exists():
        print("Run ./do generate-data first to produce customers.json")
        return
    with open(customers_path) as f:
        customers = json.load(f)
    customers = sorted(customers, key=lambda c: -c["invoice_count"])[: args.internal_customers]

    # Build articles
    articles = []
    for i, a in enumerate(APP_ARTICLES):
        articles.append({
            "article_id": f"APP-{i:02d}",
            "title": a["title"],
            "body": a["body"],
            "category": "app",
            "customer_id": "*",
            "tags": a["tags"],
            "page_context": a["page_context"],
        })
    for i, a in enumerate(LEGAL_ARTICLES):
        articles.append({
            "article_id": f"LEGAL-{i:02d}",
            "title": a["title"],
            "body": a["body"],
            "category": "legal",
            "customer_id": "*",
            "tags": a["tags"],
            "page_context": a["page_context"],
        })
    rng = random.Random(7)
    for cust in customers:
        articles.extend(make_internal_articles(cust["customer_id"], cust["name"], rng))

    # Build impressions: synthesize 50 impressions per customer-page,
    # with a CTR pattern that favors articles whose page_context matches
    # the impression's page (10x more likely to be clicked).
    pages = ["/invoices", "/formfill", "/matching", "/rulemining", "/anomalies",
             "/quality/overview", "/quality/rules", "/quality/predictions",
             "/quality/overrides"]

    impressions = []
    impression_id = 0
    timestamp_base = 1714000000  # ~mid-2024

    # Sessions of 3 impressions each: imp1 has no prev, imp2 follows
    # imp1 (prev_article_id = imp1.article_id) with bias toward
    # tag-overlapping articles, imp3 follows imp2 similarly.
    #
    # This gives Aito's _recommend the signal to learn "users who
    # clicked A next clicked B" — the related-articles ranking.
    #
    # ~27 sessions × 9 pages × 20 customers = 4,860 sessions →
    # ~14,580 impressions, similar to the prior single-shot setup.

    def tag_overlap(a: dict, b: dict) -> int:
        ta = set((a.get("tags") or "").split())
        tb = set((b.get("tags") or "").split())
        return len(ta & tb)

    def click_prob(article: dict, page: str, cid: str) -> float:
        p = 0.15
        if article.get("page_context") == page:
            p += 0.35
        if article["category"] == "app":
            p += 0.10
        if article["category"] == "internal" and article["customer_id"] == cid:
            p += 0.20
        return min(0.85, p)

    def pick_next(prev: dict, available: list[dict], rng: random.Random) -> dict:
        # Weight each candidate by tag overlap + page_context match
        weights = []
        for art in available:
            if art["article_id"] == prev["article_id"]:
                weights.append(0)
                continue
            w = 1.0
            w += tag_overlap(prev, art) * 3.0
            if art.get("page_context") == prev.get("page_context") and prev.get("page_context"):
                w += 4.0
            if art["category"] == prev["category"]:
                w += 1.5
            weights.append(w)
        total = sum(weights)
        if total <= 0:
            return rng.choice(available)
        r = rng.random() * total
        for art, w in zip(available, weights):
            r -= w
            if r <= 0:
                return art
        return available[-1]

    SESSIONS_PER_PAGE = 27

    for cust in customers:
        cid = cust["customer_id"]
        available = [a for a in articles if a["customer_id"] in ("*", cid)]
        for page in pages:
            for _ in range(SESSIONS_PER_PAGE):
                # Session of 3 sequential impressions
                prev_article = None
                for step in range(3):
                    if prev_article is None:
                        art = rng.choice(available)
                    else:
                        art = pick_next(prev_article, available, rng)
                    p_click = click_prob(art, page, cid)
                    # Bonus: if prev_article was clicked and shares tags,
                    # this one is more likely to be clicked too (user is
                    # genuinely exploring a topic).
                    if prev_article and tag_overlap(prev_article, art) >= 2:
                        p_click = min(0.90, p_click + 0.15)
                    clicked = rng.random() < p_click

                    impressions.append({
                        "impression_id": f"IMP-{impression_id:08d}",
                        "article_id": art["article_id"],
                        "customer_id": cid,
                        "page": page,
                        "query": "",
                        "clicked": clicked,
                        "timestamp": timestamp_base + impression_id * 60,
                        "prev_article_id": prev_article["article_id"] if prev_article else None,
                    })
                    impression_id += 1
                    # Only "follow" from a clicked article — non-clicks
                    # break the session
                    prev_article = art if clicked else None

    # Save
    with open(DATA_DIR / "help_articles.json", "w") as f:
        json.dump(articles, f, indent=None, ensure_ascii=False)
    with open(DATA_DIR / "help_impressions.json", "w") as f:
        json.dump(impressions, f, indent=None, ensure_ascii=False)

    print(f"  help_articles:    {len(articles)} ({len(APP_ARTICLES)} app + {len(LEGAL_ARTICLES)} legal "
          f"+ {len(articles) - len(APP_ARTICLES) - len(LEGAL_ARTICLES)} internal)")
    print(f"  help_impressions: {len(impressions)}")
    clicked = sum(1 for i in impressions if i["clicked"])
    print(f"  CTR overall:      {clicked}/{len(impressions)} = {clicked/len(impressions)*100:.1f}%")


if __name__ == "__main__":
    main()
