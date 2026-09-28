"""Invoice amount bands: small / medium / large.

Aito conditions on a categorical band, not on a raw Decimal. An amount
sent as a number is effectively ignored -- so every place that predicts
from an amount must send the band too. One definition, used by the
fixtures that generate the data and by the services that query it, so the
two cannot drift apart.
"""

AMOUNT_BAND_SMALL_MAX = 1_000.0
AMOUNT_BAND_LARGE_MIN = 10_000.0


def amount_band(amount: float) -> str:
    """Bucket an invoice amount into small / medium / large."""
    if amount < AMOUNT_BAND_SMALL_MAX:
        return "small"
    if amount >= AMOUNT_BAND_LARGE_MIN:
        return "large"
    return "medium"
