"""The Overrides KPI is a count of the tenant's overrides, not of a page.

It used to fetch `limit=100` rows and report `len(hits)`, so the KPI read
"OVERRIDES 100" on a tenant with 947, and the by-field / by-corrector
breakdowns were computed from whichever 100 rows came back first.
"""

from src.quality_service import compute_override_stats


class FakeClient:
    """947 overrides; returns only a page of rows, like the real engine."""

    TOTAL = 947
    BY_FIELD = {"gl_code": 567, "approver": 232, "cost_centre": 148}
    BY_CORRECTOR = {"Anna": 600, "Matti": 347}

    def search(self, table, where, limit=10):
        return {"total": self.TOTAL, "hits": [{"field": "gl_code", "corrected_by": "Anna"}] * min(limit, 100)}

    # Real `get` also lists values from OTHER tenants with $f 0.
    OTHER_TENANTS = {"Tuomas": 0, "Leena": 0}

    def query(self, body):
        counts = self.BY_FIELD if body.get("get") == "field" else {**self.BY_CORRECTOR, **self.OTHER_TENANTS}
        return {"total": len(counts),
                "hits": [{"$value": k, "$f": v} for k, v in counts.items()]}


def test_total_is_the_tenant_count_not_the_page_size():
    stats = compute_override_stats(FakeClient(), "CUST-0000")

    assert stats["total"] == 947


def test_breakdowns_cover_every_override():
    stats = compute_override_stats(FakeClient(), "CUST-0000")

    assert stats["by_field"] == {"gl_code": 567, "approver": 232, "cost_centre": 148}
    assert sum(stats["by_field"].values()) == 947
    assert sum(stats["by_corrector"].values()) == 947


def test_other_tenants_zero_frequency_values_are_not_listed():
    """`get` pads a filtered population with every value in the table at
    $f 0; a corrector who never corrected this tenant is not one of its
    correctors."""
    stats = compute_override_stats(FakeClient(), "CUST-0000")

    assert stats["by_corrector"] == {"Anna": 600, "Matti": 347}
