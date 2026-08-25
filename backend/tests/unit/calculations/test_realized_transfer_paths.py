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


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestEarnPlusInternalTransferChoreography:
    """The full OKX two-account choreography must preserve cost basis.

    Real-data regression (TRUMP): buy on trading -> internal transfer to
    funding (matched pair G1) -> earn subscription (funding) -> earn
    redemption (funding, qty includes in-kind yield) -> internal transfer
    back to trading (matched pair G2, where the funding-side OUT sorts by id
    AFTER the trading-side IN) -> sell on trading.

    The earn rows are principal book-moves (unconditionally neutral). Their
    basis round-trips through the paired internal transfers, so the sell's
    buy-in must stay ~73.18 (buy price) and the realized G/L must be the
    economic loss (~-38.49), NOT the diluted -13.63 the flat replay produced
    when the redemption inflated position with zero basis.
    """

    def _setup(self, user):
        from common.models import Brokers
        broker = Brokers.objects.create(
            investor=user, name="OKX-CHOREO", country="Crypto", cash_precision=8
        )
        trading = Accounts.objects.create(broker=broker, name="Trading")
        funding = Accounts.objects.create(broker=broker, name="Funding")
        coin = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:CHOREO", name="CHOREO",
            currency="USD", exposure="Commodity",
        )
        coin.investors.add(user)
        return trading, funding, coin

    def test_earn_cycle_preserves_buy_in(self, user):
        trading, funding, coin = self._setup(user)
        # Create in strict id order (ascending) so the replay interleaves
        # exactly like the real import: funding-side rows sort after the
        # trading-side rows they follow.
        rows = [
            (trading, "Crypto trade in", None, Decimal("0.680300000"), Decimal("73.209000000"),
             None, "okx_csv", datetime(2025, 1, 19, 12, 4, 51, tzinfo=timezone.utc)),
            (trading, "Crypto transfer out", "G1", Decimal("-0.679619700"), None,
             "transfer", "okx_csv", datetime(2025, 1, 19, 12, 7, 0, tzinfo=timezone.utc)),
            (funding, "Crypto transfer out", "earn-a", Decimal("-0.679619700"), None,
             "okx_earn_subscription", "okx_csv", datetime(2025, 1, 19, 12, 7, 1, tzinfo=timezone.utc)),
            (funding, "Crypto transfer in", "G1", Decimal("0.679619700"), None,
             "okx_internal_transfer", "okx_csv", datetime(2025, 1, 19, 12, 7, 1, tzinfo=timezone.utc)),
            (trading, "Crypto transfer in", "G2", Decimal("0.679860400"), None,
             "transfer", "okx_csv", datetime(2025, 2, 9, 17, 15, 18, tzinfo=timezone.utc)),
            (funding, "Crypto transfer in", "earn-b", Decimal("0.679860399"), None,
             "okx_earn_redemption", "okx_csv", datetime(2025, 2, 9, 17, 15, 18, tzinfo=timezone.utc)),
            (funding, "Crypto transfer out", "G2", Decimal("-0.679860399"), None,
             "okx_internal_transfer", "okx_csv", datetime(2025, 2, 9, 17, 15, 18, tzinfo=timezone.utc)),
            (trading, "Crypto trade out", None, Decimal("-0.679800000"), Decimal("16.557000000"),
             None, "okx_csv", datetime(2025, 2, 9, 17, 17, 3, tzinfo=timezone.utc)),
        ]
        for acct, ttype, group, qty, price, evt, prov, when in rows:
            Transactions.objects.create(
                investor=user, account=acct, security=coin, currency="CHOREO" if ttype.startswith("Crypto transfer") else "USDT",
                type=ttype, date=when, quantity=qty, price=price,
                import_group_id=group, import_event_type=evt, import_provider=prov,
            )
        result = realized_gain_loss(
            coin, date(2025, 2, 10), investor=user,
            account_ids=[trading.id, funding.id], currency="USD",
        )
        # Economic truth: bought 0.6803 @ 73.209, sold 0.6798 @ 16.557.
        # Buy-in must stay at the buy price (~73.18 after the tiny in-kind
        # yield dilution), NOT the diluted ~36.61.
        expected = (Decimal("16.557") - Decimal("73.18")) * Decimal("0.6798")
        total = result["all_time"]["total"]
        assert total == pytest.approx(expected, abs=Decimal("0.5")), (
            f"realized should be ~{expected} (economic loss), got {total}"
        )
        assert total < Decimal("-30"), (
            f"realized must be a large loss, not the diluted -13.6; got {total}"
        )
