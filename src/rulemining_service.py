"""Rule mining service — discover patterns with Aito _relate.

Uses _relate to find features (vendor, category, vendor_country) that
strongly predict GL codes. Extracts support ratios from Aito's
frequency statistics to produce human-readable rule candidates.

An accountant can look at "category=telecom → GL 6200, 17/17" and
immediately verify: yes, every telecom invoice goes to GL 6200.
"""

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS

# Feature fields to mine patterns from
CONDITION_FIELDS = ["category", "vendor", "vendor_country"]

# Minimum support count to surface a pattern
MIN_SUPPORT = 3


@dataclass
class RuleCandidate:
    condition_field: str
    condition_value: str
    target_field: str
    target_value: str
    target_label: str
    support_match: int   # fOnCondition — how many match both condition and target
    support_total: int   # fCondition — how many match the condition
    coverage: float      # fCondition / n — what fraction of all invoices this covers
    lift: float
    strength: str        # "strong", "review", or "weak"

    @property
    def support_ratio(self) -> float:
        if self.support_total == 0:
            return 0.0
        return self.support_match / self.support_total

    @property
    def pattern_display(self) -> str:
        return f'{self.condition_field}="{self.condition_value}"'

    @property
    def target_display(self) -> str:
        return f"GL {self.target_value} ({self.target_label})"

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern_display,
            "condition_field": self.condition_field,
            "condition_value": self.condition_value,
            "target": self.target_display,
            "target_value": self.target_value,
            "target_label": self.target_label,
            "support": f"{self.support_match}/{self.support_total}",
            "support_match": self.support_match,
            "support_total": self.support_total,
            "support_ratio": round(self.support_ratio, 3),
            "coverage": round(self.coverage * 100, 1),
            "lift": round(self.lift, 1),
            "strength": self.strength,
        }


def classify_strength(ratio: float) -> str:
    """Classify a support ratio into strength categories.

    - Strong (≥95%): promote immediately as rule
    - Review (≥75%): strong candidate, investigate exceptions
    - Weak (<75%): not a rule, may indicate sub-pattern
    """
    if ratio >= 0.95:
        return "strong"
    if ratio >= 0.75:
        return "review"
    return "weak"


def extract_candidates_from_relate(
    condition_field: str,
    condition_value: str,
    relate_result: dict,
    target_field: str = "gl_code",
) -> list[RuleCandidate]:
    """Extract rule candidates from a single _relate response.

    Takes the top hit (highest lift) and builds a RuleCandidate if
    it meets the minimum support threshold.
    """
    candidates = []

    for hit in relate_result.get("hits", []):
        related = hit.get("related", {})
        target_value = related.get(target_field, {}).get("$has")
        if target_value is None:
            continue

        fs = hit.get("fs", {})
        f_on_condition = int(fs.get("fOnCondition", 0))
        f_condition = int(fs.get("fCondition", 0))
        n = int(fs.get("n", 1))
        lift = hit.get("lift", 0.0)

        if f_on_condition < MIN_SUPPORT:
            continue

        ratio = f_on_condition / f_condition if f_condition > 0 else 0.0
        coverage = f_condition / n if n > 0 else 0.0

        candidate = RuleCandidate(
            condition_field=condition_field,
            condition_value=condition_value,
            target_field=target_field,
            target_value=target_value,
            target_label=GL_LABELS.get(target_value, target_value),
            support_match=f_on_condition,
            support_total=f_condition,
            coverage=coverage,
            lift=lift,
            strength=classify_strength(ratio),
        )
        candidates.append(candidate)

        # Only take the top hit (highest lift) per condition
        break

    return candidates


def mine_rules(client: AitoClient, customer_id: str | None = None) -> dict:
    """Mine rule candidates from the invoices table.

    Runs _relate for each unique value of each condition field,
    extracts the strongest GL code pattern, and returns sorted
    candidates.
    """
    all_candidates: list[RuleCandidate] = []

    for field in CONDITION_FIELDS:
        # Get unique values for this field by searching
        try:
            search_result = client.search("invoices", {}, limit=0)
            total_records = search_result.get("total", 0)
        except AitoError:
            continue

        # Get relate results for known values
        # We use _relate with specific field values to get clean patterns
        values = _get_field_values(client, field, customer_id=customer_id)

        for value in values:
            try:
                where = {field: value}
                if customer_id:
                    where["customer_id"] = customer_id
                result = client.relate("invoices", where, "gl_code")
                candidates = extract_candidates_from_relate(field, value, result)
                all_candidates.extend(candidates)
            except AitoError:
                continue

    # Sort by support ratio (strongest first), then by support count
    all_candidates.sort(key=lambda c: (c.support_ratio, c.support_match), reverse=True)

    # Compute metrics
    strong = sum(1 for c in all_candidates if c.strength == "strong")
    review = sum(1 for c in all_candidates if c.strength == "review")
    weak = sum(1 for c in all_candidates if c.strength == "weak")
    # Coverage gain from strong candidates only — capped because
    # overlapping patterns (vendor + category) cover the same invoices.
    # The real gain depends on which rules are actually promoted.
    strong_coverage = sum(c.coverage for c in all_candidates if c.strength == "strong")
    # Cap at 100% since patterns overlap
    coverage_display = min(strong_coverage * 100, 100.0)

    return {
        "candidates": [c.to_dict() for c in all_candidates],
        "metrics": {
            "total": len(all_candidates),
            "strong": strong,
            "review": review,
            "weak": weak,
            "coverage_gain": round(coverage_display, 1),
        },
    }


def _get_field_values(client: AitoClient, field: str, customer_id: str | None = None) -> list[str]:
    """Get distinct values for a field by sampling records."""
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        result = client.search("invoices", where, limit=100)
        values = set()
        for hit in result.get("hits", []):
            v = hit.get(field)
            if v is not None:
                values.add(v)
        return sorted(values)
    except AitoError:
        return []
