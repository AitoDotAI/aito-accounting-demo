"""Rule mining service — discover conjunction rules with Aito `$patterns`.

Mines AND-conjunction rules (`vendor="X" AND amount_band="large" → …`)
for the fields an AP clerk has to code on each invoice. Two design rules
keep the output honest:

  1. **Inputs only.** Candidate clauses are built solely from fields known
     when an invoice *arrives* — vendor, category, vendor_country,
     amount_band. Never from `gl_code`, `approver`, `cost_centre`, etc.,
     which are *assigned during* coding/approval. A rule that conditions
     on the approver can't fire at routing time (the approver isn't known
     yet) — that's leakage, and we don't do it.

  2. **Multiple targets, exact counts.** We mine rules separately for each
     *output* field — `gl_code` and `approver` — each predicted from the
     same input set. `$patterns` only *discovers* the conjunctions; their
     support is then computed with exact `_search` counts (see
     `discover_conjunctions` / `build_candidate`), so the displayed
     "X of Y" matches the drill-down's invoice list.

The two targets show complementary structure: `gl_code` is mostly
single-input (category/vendor → GL), except the capitalization rule
(`category=it_equipment AND amount_band=large → 1600`); `approver` is
genuinely multi-input (a category's normal approver, but large invoices
escalate to a senior signer). See ADR 0014.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS

# Fields known at invoice intake — the only legitimate rule inputs.
# `$related` narrows these to the k most predictive of each target before
# mining. (Raw `amount` is excluded: $patterns can't mine a Decimal into
# threshold clauses, so the data carries a categorical `amount_band`.)
CANDIDATE_FIELDS = ["vendor", "category", "vendor_country", "amount_band"]

# Output fields we discover rules *for*. Each is predicted from the inputs
# above — never used as an input to another, so no rule leaks a value that
# isn't known at routing time.
TARGET_FIELDS = ["gl_code", "approver"]

# `$related` focus cap: top-k candidate fields kept per target value.
RELATED_K = 8

# Max distinct values to mine per target field (most frequent first). Each
# is one heavy pattern-mining call, so we bound the fan-out.
MAX_TARGET_VALUES = 8

# Max rule rows returned per target value.
RULES_PER_TARGET = 6

# Minimum exact rows where the rule fires AND lands on the target value.
MIN_SUPPORT = 3

# Only surface *positive* rules — conjunctions that make the target value
# MORE likely than its base rate (lift > 1). $related's infoGain mode also
# surfaces anti-correlations (a strong rule reappears as a lift≈0
# anti-pattern for every other target value); those are noise, dropped on
# the exact lift.
MIN_LIFT = 1.0


def target_value_label(target_field: str, value: str) -> str:
    """Human label for a target value (GL name, or the approver itself)."""
    if target_field == "gl_code":
        return GL_LABELS.get(value, value)
    return value


@dataclass
class RuleClause:
    """One `field = value` term of a conjunction rule."""

    field: str
    value: str

    @property
    def display(self) -> str:
        return f'{self.field}="{self.value}"'

    def to_dict(self) -> dict:
        return {"field": self.field, "value": self.value}


@dataclass
class RuleCandidate:
    """A discovered conjunction rule: `clauses → target_field=target_value`.

    Stat fields are exact `_search` counts (ADR 0014):
        rule_match   — rows matching the LHS AND the target value
        rule_total   — rows matching the LHS (precision base)
        target_total — rows at the target value (coverage base)
        n            — rows in scope (lift base rate)
    """

    clauses: list[RuleClause]
    target_field: str
    target_value: str
    target_label: str
    rule_match: int
    rule_total: int
    target_total: int
    n: int
    lift: float
    strength: str  # "strong", "review", or "weak"

    @property
    def support_ratio(self) -> float:
        """Rule precision: of rows matching the LHS, share at the target value."""
        if self.rule_total == 0:
            return 0.0
        return self.rule_match / self.rule_total

    @property
    def coverage(self) -> float:
        """Recall: of the target value's rows, the share this rule explains."""
        if self.target_total == 0:
            return 0.0
        return self.rule_match / self.target_total

    @property
    def pattern_display(self) -> str:
        return " AND ".join(c.display for c in self.clauses)

    @property
    def target_display(self) -> str:
        if self.target_field == "gl_code":
            return f"GL {self.target_value} ({self.target_label})"
        return self.target_label  # approver name

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern_display,
            "clauses": [c.to_dict() for c in self.clauses],
            "target_field": self.target_field,
            "target": self.target_display,
            "target_value": self.target_value,
            "target_label": self.target_label,
            "support": f"{self.rule_match}/{self.rule_total}",
            "support_match": self.rule_match,
            "support_total": self.rule_total,
            "support_ratio": round(self.support_ratio, 3),
            "coverage": round(self.coverage * 100, 1),
            "lift": round(self.lift, 1),
            "strength": self.strength,
        }


def classify_strength(ratio: float) -> str:
    """Classify a precision ratio: Strong ≥95%, Review ≥75%, Weak <75%."""
    if ratio >= 0.95:
        return "strong"
    if ratio >= 0.75:
        return "review"
    return "weak"


def parse_conjunction(related: dict) -> list[RuleClause]:
    """Parse a `$patterns` `related` proposition into rule clauses.

    Two shapes occur — single feature `{"vendor": {"$has": "X"}}` and
    conjunction `{"$and": [...]}` — both rendered as a clause list.
    """
    terms = related["$and"] if "$and" in related else [related]
    clauses: list[RuleClause] = []
    for term in terms:
        for fld, pred in term.items():
            if fld.startswith("$"):
                continue
            value = pred.get("$has") if isinstance(pred, dict) else pred
            if value is None:
                continue
            clauses.append(RuleClause(field=fld, value=str(value)))
    return clauses


def discover_conjunctions(
    target_field: str,
    target_value: str,
    relate_result: dict,
) -> list[list[RuleClause]]:
    """Pull candidate conjunctions out of one `$patterns` response.

    Discovery only — `$patterns`' `fs` are smoothed estimates (fractional,
    rounded to deterministic), so support is recomputed exactly later. We
    assert each hit's `condition` is the target field (else the
    conjunctions are mined against the wrong thing), keep positive ones
    (estimated `lift > 1`), and de-duplicate.
    """
    conjunctions: list[list[RuleClause]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for hit in relate_result.get("hits", []):
        condition = hit.get("condition", {})
        if target_field not in condition:
            raise ValueError(
                f"$patterns hit for {target_field}={target_value} has condition "
                f"{condition!r}; expected the target field as the condition. The "
                f"discovery would be against the wrong target — refusing to proceed."
            )

        clauses = parse_conjunction(hit.get("related", {}))
        if not clauses:
            continue
        if float(hit.get("lift", 0.0) or 0.0) <= MIN_LIFT:
            continue

        key = tuple(sorted((c.field, c.value) for c in clauses))
        if key in seen:
            continue
        seen.add(key)
        conjunctions.append(clauses)
    return conjunctions


def build_candidate(
    clauses: list[RuleClause],
    target_field: str,
    target_value: str,
    rule_total: int,
    rule_match: int,
    target_total: int,
    n: int,
) -> RuleCandidate:
    """Assemble a RuleCandidate from EXACT `_search` counts.

    Pure (no network). The counts are the same exact matches the drill-down
    uses, so the displayed "X of Y" agrees with the invoices listed there.
    Lift is precision over the target value's base rate.
    """
    precision = rule_match / rule_total if rule_total else 0.0
    base_rate = target_total / n if n else 0.0
    lift = precision / base_rate if base_rate else 0.0
    return RuleCandidate(
        clauses=clauses,
        target_field=target_field,
        target_value=target_value,
        target_label=target_value_label(target_field, target_value),
        rule_match=rule_match,
        rule_total=rule_total,
        target_total=target_total,
        n=n,
        lift=lift,
        strength=classify_strength(precision),
    )


def mine_rules(client: AitoClient, customer_id: str | None = None) -> dict:
    """Mine conjunction rule candidates for every target field.

    For each target field, for each of its most frequent values, run one
    `$patterns` `_relate` to *discover* the input conjunctions that predict
    it, then price each with exact `_search` counts. Flatten across
    targets, sort strongest-first, and summarise.
    """
    where_filter = {"customer_id": customer_id} if customer_id else {}
    try:
        n = _count(client, where_filter)  # exact rows in scope (lift base)
    except AitoError:
        return {"candidates": [], "metrics": _empty_metrics()}
    if n == 0:
        return {"candidates": [], "metrics": _empty_metrics()}

    # Build the work list: (target_field, target_value) pairs.
    work: list[tuple[str, str]] = []
    for field in TARGET_FIELDS:
        for value in _top_values(client, field, where_filter):
            work.append((field, value))
    if not work:
        return {"candidates": [], "metrics": _empty_metrics()}

    def mine_one(item: tuple[str, str]) -> list[RuleCandidate]:
        target_field, target_value = item
        try:
            result = client.relate_patterns(
                "invoices",
                target={target_field: target_value},
                candidate_fields=CANDIDATE_FIELDS,
                where_filter=where_filter or None,
                k=RELATED_K,
                limit=RULES_PER_TARGET,
            )
        except AitoError:
            return []
        conjunctions = discover_conjunctions(target_field, target_value, result)
        if not conjunctions:
            return []
        try:
            target_total = _count(client, {**where_filter, target_field: target_value})
        except AitoError:
            return []

        out: list[RuleCandidate] = []
        for clauses in conjunctions:
            clause_where = {**where_filter, **{c.field: c.value for c in clauses}}
            try:
                rule_total = _count(client, clause_where)
                rule_match = _count(client, {**clause_where, target_field: target_value})
            except AitoError:
                continue
            if rule_match < MIN_SUPPORT:
                continue
            candidate = build_candidate(
                clauses, target_field, target_value, rule_total, rule_match, target_total, n
            )
            if candidate.lift <= MIN_LIFT:  # positive only, on the exact lift
                continue
            out.append(candidate)
        return out

    all_candidates: list[RuleCandidate] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for batch in pool.map(mine_one, work):
            all_candidates.extend(batch)

    all_candidates.sort(key=lambda c: (c.support_ratio, c.rule_match), reverse=True)
    return {
        "candidates": [c.to_dict() for c in all_candidates],
        "metrics": _metrics(all_candidates),
    }


def _metrics(candidates: list[RuleCandidate]) -> dict:
    strong = sum(1 for c in candidates if c.strength == "strong")
    review = sum(1 for c in candidates if c.strength == "review")
    weak = sum(1 for c in candidates if c.strength == "weak")
    # Coverage gain ≈ share of invoices a human could auto-route with the
    # strong *GL* rules (the automation metric). Approver rules are scored
    # separately, so they don't inflate this. Σ rule_match over strong
    # gl_code rules / n, capped at 100% (rules overlap).
    n = max((c.n for c in candidates), default=0)
    explained = sum(
        c.rule_match for c in candidates if c.strength == "strong" and c.target_field == "gl_code"
    )
    coverage_gain = min(explained / n * 100, 100.0) if n else 0.0
    return {
        "total": len(candidates),
        "strong": strong,
        "review": review,
        "weak": weak,
        "coverage_gain": round(coverage_gain, 1),
    }


def _empty_metrics() -> dict:
    return {"total": 0, "strong": 0, "review": 0, "weak": 0, "coverage_gain": 0.0}


def _count(client: AitoClient, where: dict) -> int:
    """Exact row count for a where-clause via `_search` with `limit: 0`."""
    return int(client.search("invoices", where, limit=0).get("total", 0))


# ── Rule diagnostics (ADR 0015) ───────────────────────────────────────
#
# Relate the rule's *remaining* input features to its output, within the
# rule's matched population, to explain its exceptions. A feature value's
# lift toward the output sorts it: > 1 goes with agreement, < 1 marks the
# exceptions. Thresholds keep near-neutral (lift ≈ 1) features out.
DIAGNOSE_AGREE_LIFT = 1.05
DIAGNOSE_EXCEPTION_LIFT = 0.9
DIAGNOSE_MIN_F = 3  # min support for a feature value to be worth reporting


def diagnose_rule(
    client: AitoClient,
    customer_id: str | None,
    clauses: list[dict],
    target_field: str,
    target_value: str,
) -> dict:
    """Explain a rule's exceptions by relating its remaining inputs to the
    output within its matched population (ADR 0015).

    `clauses` is the rule's `$and` conjunction as `[{field, value}, ...]`.
    """
    clause_fields = {c["field"] for c in clauses}
    remaining = [f for f in CANDIDATE_FIELDS if f not in clause_fields]
    empty = {
        "remaining_inputs": remaining,
        "explains_exceptions": [],
        "explains_agreement": [],
        "suggestion": None,
    }
    if not remaining:
        return empty

    population_where: dict = {"customer_id": customer_id} if customer_id else {}
    for c in clauses:
        population_where[c["field"]] = c["value"]
    try:
        result = client.relate_features(
            "invoices", population_where, {target_field: target_value}, remaining
        )
    except AitoError:
        return empty
    return interpret_diagnosis(remaining, result)


def interpret_diagnosis(remaining_inputs: list[str], relate_result: dict) -> dict:
    """Split a diagnostic `_relate` response into agreement vs exception
    drivers, and propose a refinement. Pure — no network.
    """
    agreement: list[dict] = []
    exceptions: list[dict] = []
    entries: list[dict] = []
    for hit in relate_result.get("hits", []):
        related = hit.get("related", {})
        parsed = parse_conjunction(related)  # a single-feature proposition
        if len(parsed) != 1:
            continue
        clause = parsed[0]
        fs = hit.get("fs", {})
        total = int(fs.get("f", 0))
        agree = int(fs.get("fOnCondition", 0))
        if total < DIAGNOSE_MIN_F:
            continue
        lift = float(hit.get("lift", 0.0) or 0.0)
        entry = {
            "field": clause.field,
            "value": clause.value,
            "lift": round(lift, 2),
            "agree": agree,
            "total": total,
            "agree_ratio": round(agree / total, 3) if total else 0.0,
        }
        entries.append(entry)
        if lift >= DIAGNOSE_AGREE_LIFT:
            agreement.append(entry)
        elif lift <= DIAGNOSE_EXCEPTION_LIFT:
            exceptions.append(entry)

    exceptions.sort(key=lambda e: e["lift"])       # most disagreeing first
    agreement.sort(key=lambda e: -e["lift"])       # strongest agreement first
    return {
        "remaining_inputs": remaining_inputs,
        "explains_exceptions": exceptions,
        "explains_agreement": agreement,
        "suggestion": _suggest_refinement(entries, exceptions),
    }


def _suggest_refinement(entries: list[dict], exceptions: list[dict]) -> dict | None:
    """If the exceptions concentrate on one feature value, suggest adding
    the complementary (agreeing) value of that field as a clause.

    e.g. exceptions are all `amount_band=medium` (0/26) and the agreements
    are `amount_band=large` (322/327) → add `amount_band="large"`.
    """
    if not exceptions:
        return None
    worst = exceptions[0]
    # Best agreeing value of the SAME field: high agree ratio, real support.
    same_field = [
        e for e in entries
        if e["field"] == worst["field"] and e["value"] != worst["value"]
        and e["agree_ratio"] >= 0.9 and e["agree"] >= DIAGNOSE_MIN_F
    ]
    if not same_field:
        return None
    best = max(same_field, key=lambda e: e["agree"])
    return {
        "field": best["field"],
        "value": best["value"],
        "text": (
            f'Add {best["field"]}="{best["value"]}" — the rule holds in '
            f'{best["agree"]}/{best["total"]} of those, and it drops the '
            f'{worst["field"]}="{worst["value"]}" exceptions '
            f'({worst["agree"]}/{worst["total"]} matched).'
        ),
    }


def _top_values(client: AitoClient, field: str, where_filter: dict) -> list[str]:
    """Most frequent values of a target field in scope, most-common first.

    Bounds the fan-out to MAX_TARGET_VALUES — one heavy pattern call per
    value — and focuses on the values that carry real invoice volume.
    """
    try:
        result = client.search("invoices", where_filter, limit=400)
    except AitoError:
        return []
    counts: dict[str, int] = {}
    for hit in result.get("hits", []):
        v = hit.get(field)
        if v:
            counts[v] = counts.get(v, 0) + 1
    ranked = sorted(counts, key=lambda x: counts[x], reverse=True)
    return ranked[:MAX_TARGET_VALUES]
