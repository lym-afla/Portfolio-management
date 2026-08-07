"""Tests for option paths in services/realized.py (sub-project 4).

Mirrors test_realized_bond_paths.py structure: helper builders + class-scoped
tests using user/account fixtures from conftest.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Assets, OptionMetadata, Transactions
from services.realized import get_economic_basis, realized_gain_loss


def _make_option(user, underlying="BTC", strike=Decimal("80000"), opt_type="CALL",
                 expiry=date(2026, 6, 5), contract_size=Decimal("0.01")):
    name = f"{underlying}-{expiry.strftime('%d%b%y').upper()}-{strike}-{opt_type[0]}"
    asset = Assets.objects.create(
        type="Option", ISIN=f"CRYPTO:OPT:{name}", name=name,
        currency="BTC", exposure="Derivatives",
    )
    asset.investors.add(user)
    OptionMetadata.objects.create(
        asset=asset, strike_price=strike, option_type=opt_type,
        expiration_date=expiry, contract_size=contract_size,
    )
    return asset


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestGetEconomicBasisOption:
    def test_long_option_basis_uses_contract_size(self, user, account):
        """A BUY of 7 contracts @ 0.0022 with size 0.01 -> basis 0.000154 BTC."""
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade in",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0.0022"),
            cash_flow=Decimal("-0.000154"),
        )
        # rounded=False: the coin basis (0.000154 BTC) is below 2 dp, so the
        # default rounded=True path would quantize it to 0.00 and hide the
        # contract_size effect. Assert the unrounded value directly.
        basis = get_economic_basis(opt, date(2026, 6, 1), investor=user, rounded=False)
        assert basis == Decimal("0.000154")  # 7 * 0.0022 * 0.01
