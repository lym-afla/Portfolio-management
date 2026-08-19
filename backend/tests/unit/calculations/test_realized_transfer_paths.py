"""Tests for the crypto transfer-neutrality behavior in realized_gain_loss.

Matched transfers (both legs in portfolio, shared import_group_id) are neutral.
Until issue #29's two-account model lands, ALL crypto transfers are neutral
(including unmatched one-sided moves), because pre-#29 we cannot distinguish
OKX Funding↔Trading internal wallet moves from genuine external flows. The
matched-vs-unmatched disposition distinction (sub-project 4 Task 12) is
reverted; the `_transfer_is_matched` helper is retained, gated behind
``TRANSFER_DISPOSITION_ENABLED`` for #29 to reactivate.
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
class TestUnmatchedTransferIsNeutralUntilTwoAccountModel:
    """Until issue #29's two-account model lands, ALL crypto transfers are
    neutral — including unmatched one-sided moves (OKX Funding↔Trading internal
    transfers, which dominate the user's data and are NOT external withdrawals).
    The matched-vs-unmatched distinction (Task 12) is reverted because pre-#29
    we cannot distinguish internal moves from genuine external flows.
    """

    def test_unmatched_out_is_neutral_no_realized(self, user, account):
        btc = _make_btc(user)
        Transactions.objects.create(
            investor=user, account=account, security=btc, currency="USD",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("60000"),
        )
        # Unmatched transfer out (no import_group_id sibling) — now neutral.
        Transactions.objects.create(
            investor=user, account=account, security=btc, currency="BTC",
            type="Crypto transfer out",
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            quantity=Decimal("-0.5"),
        )
        result = realized_gain_loss(btc, date(2026, 3, 1), investor=user)
        # No realized G/L from the transfer — neutral.
        assert result["all_time"]["total"] == Decimal("0")
