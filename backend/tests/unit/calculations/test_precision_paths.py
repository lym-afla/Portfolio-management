"""Tests for currency-aware rounding via broker.cash_precision (sub-project 4 follow-up).

Crypto brokers (OKX/Bybit) have cash_precision=8; fiat brokers=2. Realized G/L
and basis for crypto-scale values (e.g. BTC option profit +0.00014322) must
display at full precision, not round to 0.00.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from services.realized import realized_gain_loss


def _make_crypto_broker_account(user, name="Crypto Test Broker"):
    """Broker with cash_precision=8 (matches OKX/Bybit migration 0098)."""
    broker = Brokers.objects.create(investor=user, name=name, country="Crypto", cash_precision=8)
    return Accounts.objects.create(broker=broker, name="Crypto Acct")


def _make_option(user, strike=Decimal("80000"), opt_type="CALL", expiry=date(2026, 6, 5)):
    name = f"BTC-{expiry.strftime('%d%b%y').upper()}-{strike}-{opt_type[0]}"
    asset = Assets.objects.create(
        type="Option", ISIN=f"CRYPTO:OPT:{name}", name=name,
        currency="BTC", exposure="Derivatives",
    )
    asset.investors.add(user)
    OptionMetadata.objects.create(
        asset=asset, strike_price=strike, option_type=opt_type,
        expiration_date=expiry, contract_size=Decimal("0.01"),
    )
    return asset


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestCryptoPrecisionRealized:
    def test_crypto_option_realized_not_rounded_to_zero(self, user):
        """With cash_precision=8, the +0.00014322 BTC option profit must NOT
        round to 0.00 at the realized_gain_loss outer boundary."""
        account = _make_crypto_broker_account(user)
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
            commission=Decimal("-0.00001078"), commission_currency="BTC",
        )
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        result = realized_gain_loss(opt, date(2026, 6, 6), investor=user, account_ids=[account.id])
        # Pre-fix: rounds to 0.00 (2dp). Post-fix: 0.00014322 (8dp).
        assert result["all_time"]["total"] == Decimal("0.00014322")

    def test_fiat_realized_still_2dp(self, user, account):
        """Fiat broker (cash_precision=2) keeps 2dp rounding — no behavior change."""
        from common.models import Assets as A, Transactions as T
        from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL
        stock = A.objects.create(type="Stock", ISIN="PRECTEST1", name="Prec Test", currency="USD")
        stock.investors.add(user)
        T.objects.create(investor=user, account=account, security=stock, currency="USD",
            type=TRANSACTION_TYPE_BUY, date=datetime(2023, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("10"), price=Decimal("100"))
        T.objects.create(investor=user, account=account, security=stock, currency="USD",
            type=TRANSACTION_TYPE_SELL, date=datetime(2023, 6, 1, tzinfo=timezone.utc),
            quantity=Decimal("-10"), price=Decimal("150.005"))  # would be 500.05 at 2dp
        result = realized_gain_loss(stock, date(2023, 7, 1), investor=user, account_ids=[account.id])
        # Fiat: 2dp → 500.05 (the 0.005 rounds HALF_UP to 0.01 at 2dp of the per-unit, * 10)
        assert result["all_time"]["total"] == result["all_time"]["total"].quantize(Decimal("0.01"))
