"""Tests for services/accounts.py balance() — option premium exclusion."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from services.accounts import balance


@pytest.mark.django_db
class TestBalanceExcludesOptionPremium:
    def test_option_sell_premium_not_in_cash_balance(self, user):
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        opt = Assets.objects.create(type="Option", ISIN="CRYPTO:OPT:X", name="BTC-X-C",
                                    currency="BTC", exposure="Derivatives")
        opt.investors.add(user)
        OptionMetadata.objects.create(asset=opt, strike_price=Decimal("80000"), option_type="CALL",
                                      expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"))
        # Option SELL: cash_flow +0.000154 BTC (the premium). This is an option
        # economic event offset by the option liability, NOT a BTC cash balance.
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        result = balance(account, date(2026, 6, 1))
        # The premium must NOT appear as a BTC cash balance.
        assert "BTC" not in result or result.get("BTC") == Decimal("0")
