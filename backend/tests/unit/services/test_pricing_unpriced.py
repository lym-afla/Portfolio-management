"""Quantity-only movements must not replace the last usable fallback price."""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Transactions
from services.pricing import price_at_date


@pytest.mark.django_db
@pytest.mark.parametrize("prior_price", [Decimal("5"), Decimal("0")])
def test_unpriced_movement_preserves_last_known_price(user, account, asset, prior_price):
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Buy",
        date=datetime(2026, 7, 1),
        quantity=Decimal("1"),
        price=prior_price,
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Crypto transfer in",
        date=datetime(2026, 7, 2),
        quantity=Decimal("1"),
        price=None,
    )

    quote = price_at_date(asset, datetime(2026, 7, 3), currency="USD")

    assert quote.price == prior_price
    assert quote.date == datetime(2026, 7, 1)
