"""Tests for the crypto transfer-neutrality fix in realized_gain_loss.

Matched transfers (both legs in portfolio, shared import_group_id) are neutral.
Unmatched transfers realize: OUT -> disposition; IN -> basis event.

These tests document the realized.py:747-755 fix: previously EVERY crypto
transfer was treated as neutral (position += qty, no G/L), which dropped basis
silently for one-sided transfers (cold-wallet withdrawals, moves to the
un-modeled OKX funding account) and corrupted realized P&L / IRR.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Transactions
from services.realized import realized_gain_loss


def _make_btc(user):
    asset = Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:BTC",
        name="BTC",
        currency="USD",
        exposure="Commodity",
    )
    asset.investors.add(user)
    return asset


def _make_account(broker, name="Counter Account"):
    return Accounts.objects.create(broker=broker, name=name)


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestMatchedTransferIsNeutral:
    """A matched transfer (both legs in portfolio, shared import_group_id)
    stays neutral: no realized G/L is recognized on either leg."""

    def test_matched_transfer_out_in_no_gain(self, user, account, broker):
        btc = _make_btc(user)
        counter = _make_account(broker, name="Counter Account")
        # Buy 1 @ 60000
        Transactions.objects.create(
            investor=user,
            account=account,
            security=btc,
            currency="USD",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"),
            price=Decimal("60000"),
        )
        # Transfer out 0.5 from `account` ...
        Transactions.objects.create(
            investor=user,
            account=account,
            security=btc,
            currency="USD",
            type="Crypto transfer out",
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            quantity=Decimal("-0.5"),
            import_provider="test",
            import_group_id="grp-1",
            import_account_id="acct-A",
        )
        # ... matched transfer in to the counter in-portfolio account.
        Transactions.objects.create(
            investor=user,
            account=counter,
            security=btc,
            currency="USD",
            type="Crypto transfer in",
            date=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            quantity=Decimal("0.5"),
            import_provider="test",
            import_group_id="grp-1",
            import_account_id="acct-A",
        )
        result = realized_gain_loss(btc, date(2026, 3, 1), investor=user)
        # No realized G/L from the matched transfer.
        assert result["all_time"]["total"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestUnmatchedTransferOutIsDisposition:
    """An unmatched Crypto transfer out (no in-portfolio partner with the same
    import_group_id) is a priced disposition: it flows into the disposal branch
    and realizes G/L at average cost (cold-wallet withdrawal behavior)."""

    def test_unmatched_out_realizes_loss_at_zero_proceeds(self, user, account):
        btc = _make_btc(user)
        # Buy 1 @ 60000 -> average cost basis 60000 per coin.
        Transactions.objects.create(
            investor=user,
            account=account,
            security=btc,
            currency="USD",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"),
            price=Decimal("60000"),
        )
        # Cold-wallet withdrawal: no import_group_id, no matching in.
        # A withdrawal receives no cash, so the disposition proceeds are 0.
        Transactions.objects.create(
            investor=user,
            account=account,
            security=btc,
            currency="USD",
            type="Crypto transfer out",
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            quantity=Decimal("-0.5"),
        )
        result = realized_gain_loss(btc, date(2026, 3, 1), investor=user)
        # Disposition of 0.5 BTC at avg cost basis 60000 with proceeds 0
        # -> loss = (0 - 60000) * 0.5 = -30000 USD.
        # (price_appreciation = -(tx_price - buy_in_price) * closing_quantity
        #                       = -(0 - 60000) * (-0.5) = -30000)
        assert result["all_time"]["total"] == Decimal("-30000")
