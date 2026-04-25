"""Quality dashboard service — aggregate metrics per customer."""

from src.aito_client import AitoClient, AitoError


def compute_automation_breakdown(client: AitoClient, customer_id: str | None = None) -> dict:
    """Compute automation rate split between rules, Aito, and human."""
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        all_invoices = client.search("invoices", where, limit=300)
    except AitoError:
        return {"total": 0, "rule": 0, "aito": 0, "human": 0, "none": 0}

    hits = all_invoices.get("hits", [])
    total = len(hits)
    rule = sum(1 for h in hits if h.get("routed_by") == "rule")
    aito = sum(1 for h in hits if h.get("routed_by") == "aito")
    human = sum(1 for h in hits if h.get("routed_by") == "human")
    none_ = sum(1 for h in hits if h.get("routed_by") == "none")

    return {
        "total": total,
        "rule": rule, "aito": aito, "human": human, "none": none_,
        "rule_pct": round(rule / total * 100) if total else 0,
        "aito_pct": round(aito / total * 100) if total else 0,
        "human_pct": round(human / total * 100) if total else 0,
        "automation_rate": round((rule + aito) / total * 100) if total else 0,
    }


def compute_override_stats(client: AitoClient, customer_id: str | None = None) -> dict:
    """Compute override statistics from the overrides table."""
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        all_overrides = client.search("overrides", where, limit=100)
    except AitoError:
        return {"total": 0, "by_field": {}, "by_corrector": {}}

    hits = all_overrides.get("hits", [])
    total = len(hits)
    by_field: dict[str, int] = {}
    by_corrector: dict[str, int] = {}

    for h in hits:
        field = h.get("field", "unknown")
        by_field[field] = by_field.get(field, 0) + 1
        corrector = h.get("corrected_by", "unknown")
        by_corrector[corrector] = by_corrector.get(corrector, 0) + 1

    return {"total": total, "by_field": by_field, "by_corrector": by_corrector}


def compute_override_patterns(client: AitoClient, customer_id: str | None = None) -> list[dict]:
    """Find emerging patterns from overrides using _relate."""
    patterns = []
    try:
        where = {"field": "gl_code"}
        if customer_id:
            where["customer_id"] = customer_id
        result = client.relate("overrides", where, "corrected_value")
    except AitoError:
        return patterns

    for hit in result.get("hits", []):
        related = hit.get("related", {})
        corrected = related.get("corrected_value", {}).get("$has")
        if corrected is None:
            continue
        fs = hit.get("fs", {})
        f_on = int(fs.get("fOnCondition", 0))
        lift = hit.get("lift", 0)
        if f_on < 2:
            continue
        patterns.append({"corrected_to": corrected, "field": "gl_code", "count": f_on, "lift": round(lift, 1)})

    return patterns


def get_quality_overview(client: AitoClient, customer_id: str | None = None) -> dict:
    """Compute all quality metrics for a customer."""
    return {
        "automation": compute_automation_breakdown(client, customer_id),
        "overrides": compute_override_stats(client, customer_id),
        "override_patterns": compute_override_patterns(client, customer_id),
    }
