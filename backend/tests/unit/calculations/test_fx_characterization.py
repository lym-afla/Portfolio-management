"""Characterization tests for ``services.fx.get_rate`` on the long-format schema.

These tests PIN the outputs that the long-format ``get_rate`` MUST produce. They
are the behavioral contract for the wide->long refactor (Task 3): every value
here was computed by hand from the documented storage convention and must not
change as the implementation is rewritten.

Storage convention (quote-per-base): a long-format row
``from_currency=X, to_currency=Y, rate=r`` stores "r units of X per 1 unit of Y"
(r X/Y). ``get_rate(source, target, date)`` returns the multiplier that converts
an amount in ``source`` into ``target``.

Per-hop rule (the critical invariant):
- If ``row.from_currency == hop_source``:  ``fx_rate /= row.rate``
- Else:                                   ``fx_rate *= row.rate``

Direction trace (these tests cover both branches):

1. RUB->USD with stored row from="RUB", to="USD", rate=90.5
   - "90.5 RUB per 1 USD". Need USD per RUB = 1/90.5.
   - row.from_currency (RUB) == hop_source (RUB) -> DIVIDE -> 0.011050.

2. USD->EUR with stored row from="USD", to="EUR", rate=1.1
   - "1.1 USD per 1 EUR". Need EUR per USD = 1/1.1.
   - row.from_currency (USD) == hop_source (USD) -> DIVIDE -> 0.909091.

3. EUR->USD with stored row from="USD", to="EUR", rate=1.1
   - "1.1 USD per 1 EUR". Need USD per EUR = 1.1.
   - row.from_currency (USD) != hop_source (EUR) -> MULTIPLY -> 1.100000.

4. GBP->RUB via USD (multi-hop):
   - from="USD", to="GBP", rate=1.22  ("1.22 USD per 1 GBP")
   - from="RUB", to="USD", rate=75    ("75 RUB per 1 USD")
   - Path GBP -> USD -> RUB.
     Hop1 GBP->USD: row.from (USD) != hop_source (GBP) -> MULTIPLY 1.22 -> 1.22
     Hop2 USD->RUB: row.from (RUB) != hop_source (USD) -> MULTIPLY 75   -> 91.5
   - conversions == 2.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import FX
from services.fx import get_rate


# The single reference date every test uses. Picked once so the date-range
# sanity check (5y before / 1y after) is always satisfied when there is data on
# this exact date.
REF_DATE = date(2024, 6, 3)


def _add_fx(from_cur, to_cur, rate, on_date=REF_DATE, investor=None):
    """Create a long-format FX row and optionally link an investor."""
    fx = FX.objects.create(
        date=on_date,
        from_currency=from_cur,
        to_currency=to_cur,
        rate=Decimal(rate),
    )
    if investor is not None:
        fx.investors.add(investor)
    return fx


@pytest.mark.fx
@pytest.mark.unit
class TestGetRateCharacterization:
    """Golden outputs that MUST NOT CHANGE across the long-format refactor."""

    def test_same_currency_short_circuits_to_one(self, user):
        """get_rate(X, X, ...) returns FX=1 with zero conversions."""
        # No FX rows at all -- same-currency must short-circuit before any DB hit.
        result = get_rate("USD", "USD", REF_DATE, investor=user)

        assert result["FX"] == Decimal("1")
        assert result["conversions"] == 0
        assert result["dates_async"] is False
        assert result["dates"] == []

    def test_rub_to_usd_golden(self, user):
        """RUB->USD on a from=RUB/to=USD/90.5 row -> 1/90.5 = 0.011050 (DIVIDE)."""
        _add_fx("RUB", "USD", "90.5", investor=user)

        result = get_rate("RUB", "USD", REF_DATE, investor=user)

        assert result["FX"] == Decimal("0.011050")
        assert result["conversions"] == 1
        assert result["dates"] == [REF_DATE]

    def test_usd_to_eur_quote_per_base(self, user):
        """USD->USD on a from=USD/to=EUR/1.1 row -> 1/1.1 = 0.909091 (DIVIDE)."""
        _add_fx("USD", "EUR", "1.1", investor=user)

        result = get_rate("USD", "EUR", REF_DATE, investor=user)

        assert result["FX"] == Decimal("0.909091")
        assert result["conversions"] == 1

    def test_eur_to_usd_reverse(self, user):
        """EUR->USD on the same from=USD/to=EUR/1.1 row -> 1.1 (MULTIPLY)."""
        _add_fx("USD", "EUR", "1.1", investor=user)

        result = get_rate("EUR", "USD", REF_DATE, investor=user)

        assert result["FX"] == Decimal("1.100000")
        assert result["conversions"] == 1

    def test_multi_hop_gbp_to_rub_via_usd(self, user):
        """GBP->RUB via USD: path GBP->USD->RUB, both MULTIPLY -> 1.22*75 = 91.5."""
        _add_fx("USD", "GBP", "1.22", investor=user)
        _add_fx("RUB", "USD", "75", investor=user)

        result = get_rate("GBP", "RUB", REF_DATE, investor=user)

        assert result["FX"] == Decimal("91.500000")
        assert result["conversions"] == 2

    def test_closest_date_uses_latest_before(self, user):
        """A request with no exact-date row uses the most recent earlier date."""
        earlier = REF_DATE - timedelta(days=3)
        _add_fx("USD", "EUR", "1.1", on_date=earlier, investor=user)

        result = get_rate("USD", "EUR", REF_DATE, investor=user)

        assert result["FX"] == Decimal("0.909091")
        assert result["dates"] == [earlier]

    def test_no_path_raises_value_error(self, user):
        """A currency with no connecting edge to the target raises ValueError."""
        _add_fx("USD", "EUR", "1.1", investor=user)
        # JPY is an island; there is no path JPY -> EUR.
        with pytest.raises(ValueError, match="No FX rate found"):
            get_rate("JPY", "EUR", REF_DATE, investor=user)
