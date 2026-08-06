"""Tests for the stablecoin FX peg (USD↔USDT, USD↔USDC at 1.0).

The peg is a universal constant: stablecoins are pegged to USD at 1.0,
seeded as global FX rows (no investor link). The get_rate resolution
treats them as universal graph edges and exempts them from the per-investor
filter in the per-hop rate lookup.

Test isolation: the peg rows are normally seeded by migration 0093, but
other tests in the suite use ``@pytest.mark.django_db(transaction=True)``
(e.g. test_bond_aci.py), which truncates all tables between tests — wiping
the migration-seeded rows. To stay independent of run order, this class
re-seeds the peg rows in an autouse setup if they are missing.
"""
from datetime import date
from decimal import Decimal

import pytest

from common.models import FX
from services.fx import get_rate

# The peg date is set well before the earliest transaction so the closest
# date-on-or-before lookup always finds it (mirrors migration 0093).
_PEG_DATE = date(2000, 1, 1)
_PEG_RATE = Decimal("1.0000000000")
_PEG_PAIRS = [("USD", "USDT"), ("USD", "USDC")]


@pytest.mark.django_db
@pytest.mark.fx
class TestStablecoinPeg:
    """Pin the stablecoin peg behavior."""

    @pytest.fixture(autouse=True)
    def _ensure_peg_rows(self):
        """Re-seed the global peg rows if a prior TransactionTestCase wiped them.

        ``get_or_create`` is idempotent: if migration 0093's rows survive, this
        is a no-op; if they were truncated, they are restored. Without this,
        the multi-hop and global-row tests fail depending on suite ordering.
        """
        for from_curr, to_curr in _PEG_PAIRS:
            FX.objects.get_or_create(
                date=_PEG_DATE,
                from_currency=from_curr,
                to_currency=to_curr,
                defaults={"rate": _PEG_RATE},
            )
        yield

    def test_usd_to_usdt_is_one(self):
        """USD → USDT returns 1.0 (direct peg)."""
        result = get_rate("USD", "USDT", date(2026, 1, 1))
        assert result["FX"] == Decimal("1.000000")
        assert result["conversions"] == 1

    def test_usdt_to_usd_is_one(self):
        """USDT → USD returns 1.0 (reverse peg)."""
        result = get_rate("USDT", "USD", date(2026, 1, 1))
        assert result["FX"] == Decimal("1.000000")
        assert result["conversions"] == 1

    def test_usd_to_usdc_is_one(self):
        """USD → USDC returns 1.0 (direct peg)."""
        result = get_rate("USD", "USDC", date(2026, 1, 1))
        assert result["FX"] == Decimal("1.000000")

    def test_usdt_to_eur_matches_usd_to_eur(self, user):
        """USDT → EUR multi-hops through the 1.0 peg to USD, then USD → EUR.

        The result must equal USD → EUR because the USDT→USD hop contributes
        a factor of 1.0."""
        # Seed a USDEUR row for the test investor
        FX.objects.create(
            date=date(2024, 1, 1),
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("1.100000"),
        ).investors.add(user)

        usdt_to_eur = get_rate("USDT", "EUR", date(2024, 6, 1), investor=user)
        usd_to_eur = get_rate("USD", "EUR", date(2024, 6, 1), investor=user)

        assert usdt_to_eur["FX"] == usd_to_eur["FX"]
        assert usdt_to_eur["conversions"] == 2  # USDT→USD→EUR

    def test_peg_works_without_investor(self):
        """The peg resolves even when no investor is specified."""
        result = get_rate("USDT", "USD", date(2026, 1, 1))
        assert result["FX"] == Decimal("1.000000")

    def test_peg_rows_are_global(self):
        """Peg rows exist in the DB (seeded by migration 0093, re-seeded by the
        autouse fixture if a prior TransactionTestCase wiped them)."""
        usdt = FX.objects.filter(from_currency="USD", to_currency="USDT").first()
        assert usdt is not None
        assert usdt.rate == Decimal("1.0000000000")
        usdc = FX.objects.filter(from_currency="USD", to_currency="USDC").first()
        assert usdc is not None
        assert usdc.rate == Decimal("1.0000000000")
