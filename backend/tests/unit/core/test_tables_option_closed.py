"""Tests for the closed-positions table builder with option assets (sub-project 4 follow-up).

The BTC option's settlement row has price 0 (OTM terminal) — get_price returns
None for it, which previously caused None * Decimal TypeError at
tables_utils.py:198 and silently dropped the option from Closed positions.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Prices, Transactions
from core.tables_utils import _calculate_closed_table_output_for_api


def _make_btc_underlying(user, usd_price=Decimal("60000")):
    """Create the BTC Crypto asset + a pinned USD price for FX conversion.

    The option settles in BTC; tables_utils computes the entry/exit value via
    ``get_fx_rate("BTC", "USD", ...)`` which chains through ``crypto_fx_rate``
    to the BTC asset's ``Prices`` row. Pinning 60000 USD/BTC makes the FX
    deterministic: 1 BTC = 60000 USD. Mirrors the fixture in
    ``test_nav_option_paths.py``.
    """
    btc = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 1, 1), price=usd_price)
    return btc


@pytest.mark.django_db
class TestOptionInClosedPositions:
    def test_otm_option_appears_in_closed_table(self, user):
        # Pin BTC->USD at 60000 so the entry-value FX is deterministic.
        _make_btc_underlying(user, usd_price=Decimal("60000"))
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        opt = Assets.objects.create(
            type="Option", ISIN="CRYPTO:OPT:BTC-05JUN26-80000-C",
            name="BTC-05JUN26-80000-C", currency="BTC", exposure="Derivatives",
        )
        opt.investors.add(user)
        OptionMetadata.objects.create(
            asset=opt, strike_price=Decimal("80000"), option_type="CALL",
            expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"),
        )
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        # use_default_currency=False so currency_used="USD" and FX(BTC->USD)=60000
        # is applied to the BTC-denominated option premium. With
        # use_default_currency=True the value would stay in BTC coin units and
        # never reach the 9.24 USD figure asserted below.
        rows, _ = _calculate_closed_table_output_for_api(
            user.id, [opt], date(2026, 8, 8),
            ["investment_date", "realized_gl", "exit_date"],
            False, "USD", [account.id], None,
        )
        assert len(rows) == 1, "option must appear in closed positions"
        assert rows[0]["exit_date"] == datetime(2026, 6, 5, 8, 0, 34, tzinfo=timezone.utc) or \
               rows[0]["exit_date"].date() == date(2026, 6, 5)

        # Entry value must apply contract_size (0.01): qty 7 × price 0.0022 BTC
        # × contract_size 0.01 × FX(BTC->USD=60000) = 9.24. Without
        # contract_size it would be 100x too large (924.0 — the $85M-class bug
        # at the original CSV price). The SELL row's stored price is the
        # per-contract BTC premium (0.0022); contract_size converts the
        # per-contract coin notional to actual coin.
        assert rows[0]["entry_value"] == Decimal("9.24"), (
            f"entry_value should apply contract_size (7 × 0.0022 × 0.01 × 60000 "
            f"= 9.24); got {rows[0]['entry_value']}"
        )
