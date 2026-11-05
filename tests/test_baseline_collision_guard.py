"""`./do book-accept` must refuse a baseline that records a dropped condition.

Accepting a baseline is not a neutral act: booktest records whatever the
system did, defect included, and a wrong number in a committed baseline
then reads as the expected answer. Two such baselines sat in this repo
until 8324912, and both carried the same tell -- two different entities
with an identical measurement:

  K.H.N.-Marketing Oy    -> GL 4400  7383/16000  lift=2.3
  Bronex Software Oy     -> GL 4400  7383/16000  lift=2.3

Different vendors cannot have the same support out of the same
denominator. 7383/16000 is the tenant-wide count of GL 4400, so the
vendor clause was not in the condition at all. The same tell in
test_08_performance.py was one lift, 21.94, for two different tenants.

The guard below is the fail-first for that: these two baselines, as they
were actually committed, must be refused.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "baseline_collisions", REPO / "scripts" / "baseline_collisions.py")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[__module__], which is None for an unregistered module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = load_guard()


# books/book/test_03_relate.py/test_relate_vendor_to_gl.md at 8324912~1
VENDOR_BASELINE_WITH_A_DROPPED_CONDITION = """\
# Rule mining: vendor -> GL code (CUST-0000)


  EEE Energy Ecology Engineering Oy   -> GL 4400  3357/3426  lift=5.0
  K.H.N.-Marketing Oy                 -> GL 4400  7383/16000  lift=2.3
  Bronex Software Oy                  -> GL 4400  7383/16000  lift=2.3
  Kardex Finland Oy                   -> GL 4400  7383/16000  lift=2.3
  Cafetering Oy                       -> GL 4400  7383/16000  lift=2.3

Support ratios are exact counts from this customer's data.
"""

# books/book/test_08_performance.py/test_relate_latency.md at 8324912~1
LATENCY_BASELINE_WITH_A_DROPPED_CONDITION = """\
# _relate latency: vendor → gl_code

This is the slow operator -- it returns the discovered
association rules between fields.


## CUST-0000 — enterprise

0.622 ms (was 276.301 ms)
  rules returned: 10
  top related gl_code lift=21.94
  rules > 0: True


## CUST-0015 — midmarket

0.283 ms (was 125.365 ms)
  rules returned: 10
  top related gl_code lift=21.94
  rules > 0: True
"""


def test_the_same_support_for_two_vendors_is_refused():
    found = guard.collisions(VENDOR_BASELINE_WITH_A_DROPPED_CONDITION)
    assert found, "a support pair shared by four vendors was accepted"
    shared = {c.measurement for c in found}
    assert "7383/16000" in shared
    entities = next(c.entities for c in found if c.measurement == "7383/16000")
    assert "Bronex Software Oy" in entities and "Kardex Finland Oy" in entities


def test_the_same_lift_for_two_tenants_is_refused():
    found = guard.collisions(LATENCY_BASELINE_WITH_A_DROPPED_CONDITION)
    assert found, "one lift shared by two tenants was accepted"
    shared = {c.measurement for c in found}
    assert "lift=21.94" in shared
    entities = next(c.entities for c in found if c.measurement == "lift=21.94")
    assert len(entities) == 2
    assert all("CUST-00" in e for e in entities)


def test_a_repeated_measurement_within_one_entity_is_not_a_collision():
    # Two conjunctions under one heading may share a lift: they describe
    # the same predicted value, so there is no second entity to compare.
    text = """\
# Conjunction rule discovery: $patterns (CUST-0000)

  approver = CUST-0000-EMP-0006:
    amount_band="large" AND vendor="EEE Energy Ecology Engineering Oy"  lift=2.2
    amount_band="large" AND vendor="Dottoressa Oy"  lift=2.2
"""
    assert guard.collisions(text) == []


@pytest.mark.parametrize("baseline", sorted((REPO / "books" / "book").glob("*/*.md")),
                         ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_accepted_baseline_in_the_repo_is_clean(baseline):
    # The guard is only usable if today's accepted baselines pass it.
    found = guard.collisions(baseline.read_text())
    assert found == [], "\n".join(c.describe() for c in found)


def test_one_lift_written_two_ways_is_still_one_measurement():
    # 2.3 and 2.30 are the same number. Comparing the text would let a
    # dropped condition through whenever the formatter's precision differed
    # between rows.
    baseline = (
        "  Alpha Oy -> GL 4400  lift=2.3\n"
        "  Beta Oy  -> GL 4400  lift=2.30\n"
    )

    found = guard.collisions(baseline)

    assert [c.measurement for c in found] == ["lift=2.3"]


def test_a_lift_written_as_a_multiple_is_a_measurement_too():
    # test_mine_rules_for_customer prints "lift 5.0x", not "lift=5.0".
    baseline = """
  Bronex Software Oy      -> GL 4400   support 3256/3322 (98%)  lift 5.0x
  Kardex Finland Oy       -> GL 4600   support 1807/1843 (98%)  lift 5.0x
"""
    assert [c for c in guard.collisions(baseline) if c.measurement == "lift=5"], (
        "one lift shared by two vendors, written 'lift 5.0x', was accepted")
