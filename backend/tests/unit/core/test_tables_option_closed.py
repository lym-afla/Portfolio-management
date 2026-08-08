"""Tests for the closed-positions table builder with option assets (sub-project 4 follow-up).

The BTC option's settlement row has price 0 (OTM terminal) — get_price returns
None for it, which previously caused None * Decimal TypeError at
tables_utils.py:198 and silently dropped the option from Closed positions.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from core.tables_utils import _calculate_closed_table_output_for_api


@pytest.mark.django_db
class TestOptionInClosedPositions:
    def test_otm_option_appears_in_closed_table(self, user):
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
        rows, _ = _calculate_closed_table_output_for_api(
            user.id, [opt], date(2026, 8, 8),
            ["investment_date", "realized_gl", "exit_date"],
            True, "USD", [account.id], None,
        )
        assert len(rows) == 1, "option must appear in closed positions"
        assert rows[0]["exit_date"] == datetime(2026, 6, 5, 8, 0, 34, tzinfo=timezone.utc) or \
               rows[0]["exit_date"].date() == date(2026, 6, 5)
