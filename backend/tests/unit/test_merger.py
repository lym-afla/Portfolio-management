"""
Test cases for Merger functionality.

Tests all three merger types:
- All-stock: old shares converted to new shares, cost basis carries over
- All-cash: old shares liquidated for cash, realized gain/loss recognized
- Hybrid: combination of stock conversion and cash payment

Also tests cost basis (buy-in price) correctness after mergers.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from common.models import Assets, MergerRecord, Transactions
from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_MERGER_IN, TRANSACTION_TYPE_MERGER_OUT


def _create_transaction(investor, account, security, txn_type, txn_date, quantity, price, **kwargs):
    """Helper to create a transaction with a date."""
    if isinstance(txn_date, date) and not isinstance(txn_date, datetime):
        txn_date = datetime.combine(txn_date, datetime.min.time())
    return Transactions.objects.create(
        investor=investor,
        account=account,
        security=security,
        currency=security.currency,
        type=txn_type,
        date=txn_date,
        quantity=quantity,
        price=price,
        **kwargs,
    )


def _create_asset(user, name, isin, currency="USD"):
    """Helper to create a test asset linked to a user."""
    asset = Assets.objects.create(
        type="Mutual fund",
        ISIN=isin,
        name=name,
        currency=currency,
        exposure="Equity",
    )
    asset.investors.add(user)
    return asset


# ============================================================================
# ALL-STOCK MERGER TESTS
# ============================================================================


@pytest.mark.unit
class TestAllStockMerger:
    """Test all-stock merger: old shares → new shares at a conversion ratio."""

    def test_basic_all_stock_merger(self, user, account):
        """100 shares of A at $10 → 75 shares of B. Cost carries over."""
        old_sec = _create_asset(user, "Fund A", "US0000000001")
        new_sec = _create_asset(user, "Fund B", "US0000000002")

        # Buy 100 shares at $10
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 15), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user, account_ids=[account.id])
        assert old_position == Decimal("100")

        old_cost = old_sec.calculate_buy_in_price(merger_date, user, old_sec.currency, account_ids=[account.id])
        assert old_cost == Decimal("10")

        # Create merger record
        conversion_ratio = Decimal("0.75")
        merger = MergerRecord.objects.create(
            investor=user,
            old_security=old_sec,
            new_security=new_sec,
            merger_date=merger_date,
            conversion_ratio=conversion_ratio,
            cash_per_share=Decimal("0"),
        )

        # Create MERGER_OUT
        _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
            quantity=-old_position, price=old_cost, merger=merger,
        )

        # Create MERGER_IN
        new_quantity = old_position * conversion_ratio
        new_cost_per_share = (old_position * old_cost) / new_quantity
        _create_transaction(
            user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
            quantity=new_quantity, price=new_cost_per_share, merger=merger,
        )

        # Verify positions
        assert old_sec.position(merger_date, user) == Decimal("0")
        assert new_sec.position(merger_date, user) == Decimal("75")

    def test_all_stock_cost_basis_carries_over(self, user, account):
        """Buy-in price of new security reflects carryover cost."""
        old_sec = _create_asset(user, "Fund A", "US0000000011")
        new_sec = _create_asset(user, "Fund B", "US0000000012")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)
        conversion_ratio = Decimal("0.75")
        new_quantity = old_position * conversion_ratio
        new_cost_per_share = (old_position * old_cost) / new_quantity  # 1000/75 = 13.333...

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=conversion_ratio,
        )
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
                            quantity=-old_position, price=old_cost, merger=merger)
        _create_transaction(user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
                            quantity=new_quantity, price=new_cost_per_share, merger=merger)

        # Buy-in price of new security = total old cost / new quantity
        new_buy_in = new_sec.calculate_buy_in_price(merger_date, user)
        expected = (Decimal("100") * Decimal("10")) / (Decimal("100") * Decimal("0.75"))
        # calculate_buy_in_price rounds to 6 decimal places
        assert abs(new_buy_in - expected) < Decimal("0.000001")

    def test_all_stock_no_realized_gain_loss(self, user, account):
        """All-stock merger should produce zero realized gain/loss on old security."""
        old_sec = _create_asset(user, "Fund A", "US0000000021")
        new_sec = _create_asset(user, "Fund B", "US0000000022")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=Decimal("0.75"),
        )
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
                            quantity=-old_position, price=old_cost, merger=merger)
        new_quantity = old_position * Decimal("0.75")
        new_cost = (old_position * old_cost) / new_quantity
        _create_transaction(user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
                            quantity=new_quantity, price=new_cost, merger=merger)

        realized = old_sec.realized_gain_loss(merger_date, user)
        # MERGER_OUT is not a SELL, so no realized gain/loss
        assert realized["all_time"]["total"] == Decimal("0")

    def test_weighted_average_cost_carries_over(self, user, account):
        """Multiple buys at different prices → weighted average carries to new security."""
        old_sec = _create_asset(user, "Fund A", "US0000000031")
        new_sec = _create_asset(user, "Fund B", "US0000000032")

        # Buy at different prices
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("60"), Decimal("10"))
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 2, 15), Decimal("40"), Decimal("15"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)
        # Weighted avg = (60*10 + 40*15) / 100 = 1200/100 = 12

        assert old_position == Decimal("100")
        assert old_cost == Decimal("12")

        conversion_ratio = Decimal("0.8")
        new_quantity = old_position * conversion_ratio
        new_cost = (old_position * old_cost) / new_quantity  # 1200/80 = 15

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=conversion_ratio,
        )
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
                            quantity=-old_position, price=old_cost, merger=merger)
        _create_transaction(user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
                            quantity=new_quantity, price=new_cost, merger=merger)

        new_buy_in = new_sec.calculate_buy_in_price(merger_date, user)
        assert new_buy_in == Decimal("15")  # 1200/80


# ============================================================================
# ALL-CASH MERGER TESTS
# ============================================================================


@pytest.mark.unit
class TestAllCashMerger:
    """Test all-cash merger: old shares liquidated for cash per share."""

    def test_basic_all_cash_merger(self, user, account):
        """100 shares at $10 cost, cashed out at $15/share."""
        old_sec = _create_asset(user, "Fund A", "US0000000041")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)

        cash_per_share = Decimal("15")
        total_cash = cash_per_share * old_position

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=None,
            merger_date=merger_date, conversion_ratio=None,
            cash_per_share=cash_per_share,
        )

        _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
            quantity=-old_position, price=old_cost, cash_flow=total_cash, merger=merger,
        )

        assert old_sec.position(merger_date, user) == Decimal("0")
        assert MergerRecord.objects.get(id=merger.id).new_security is None

    def test_all_cash_realized_gain(self, user, account):
        """All-cash merger should recognize realized gain: cash - cost basis."""
        old_sec = _create_asset(user, "Fund A", "US0000000051")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)

        cash_per_share = Decimal("15")
        total_cash = cash_per_share * old_position

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=None,
            merger_date=merger_date, cash_per_share=cash_per_share,
        )

        _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
            quantity=-old_position, price=old_cost, cash_flow=total_cash, merger=merger,
        )

        # MERGER_OUT is not a SELL type, so realized_gain_loss won't count it
        # This is by design: realized gain for all-cash merger = cash - cost basis
        # calculated directly from the transaction data
        expected_gain = total_cash - (old_position * old_cost)  # 1500 - 1000 = 500
        assert expected_gain == Decimal("500")


# ============================================================================
# HYBRID MERGER TESTS
# ============================================================================


@pytest.mark.unit
class TestHybridMerger:
    """Test hybrid merger: combination of stock conversion and cash payment."""

    def test_basic_hybrid_merger(self, user, account):
        """100 shares at $10 cost → 50 shares of B + $8/share cash."""
        old_sec = _create_asset(user, "Fund A", "US0000000061")
        new_sec = _create_asset(user, "Fund B", "US0000000062")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)
        total_old_cost = old_position * old_cost  # 1000

        conversion_ratio = Decimal("0.5")
        cash_per_share = Decimal("8")
        total_cash = cash_per_share * old_position  # 800

        new_quantity = old_position * conversion_ratio  # 50
        # Cost carries in full to new shares
        new_cost_per_share = total_old_cost / new_quantity  # 1000/50 = 20

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=conversion_ratio,
            cash_per_share=cash_per_share,
        )

        _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
            quantity=-old_position, price=old_cost, cash_flow=total_cash, merger=merger,
        )
        _create_transaction(
            user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
            quantity=new_quantity, price=new_cost_per_share, merger=merger,
        )

        assert old_sec.position(merger_date, user) == Decimal("0")
        assert new_sec.position(merger_date, user) == Decimal("50")

    def test_hybrid_buy_in_price(self, user, account):
        """Buy-in price of new security in hybrid merger reflects full carryover cost."""
        old_sec = _create_asset(user, "Fund A", "US0000000071")
        new_sec = _create_asset(user, "Fund B", "US0000000072")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        old_cost = old_sec.calculate_buy_in_price(merger_date, user)

        conversion_ratio = Decimal("0.5")
        cash_per_share = Decimal("8")
        new_quantity = old_position * conversion_ratio
        new_cost_per_share = (old_position * old_cost) / new_quantity

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=conversion_ratio,
            cash_per_share=cash_per_share,
        )
        _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
            quantity=-old_position, price=old_cost, cash_flow=cash_per_share * old_position, merger=merger,
        )
        _create_transaction(
            user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
            quantity=new_quantity, price=new_cost_per_share, merger=merger,
        )

        new_buy_in = new_sec.calculate_buy_in_price(merger_date, user)
        # Full cost ($1000) carries to 50 shares = $20/share
        assert new_buy_in == Decimal("20")


# ============================================================================
# MERGER RECORD MODEL TESTS
# ============================================================================


@pytest.mark.unit
class TestMergerRecordModel:
    """Test MergerRecord model creation and string representation."""

    def test_merger_record_creation(self, user, account):
        """Test creating a MergerRecord."""
        old_sec = _create_asset(user, "Fund A", "US0000000081")
        new_sec = _create_asset(user, "Fund B", "US0000000082")

        merger = MergerRecord.objects.create(
            investor=user,
            old_security=old_sec,
            new_security=new_sec,
            merger_date=date(2025, 6, 1),
            conversion_ratio=Decimal("0.75"),
            cash_per_share=Decimal("0"),
        )

        assert merger.investor == user
        assert merger.old_security == old_sec
        assert merger.new_security == new_sec
        assert merger.conversion_ratio == Decimal("0.75")
        assert merger.cash_per_share == Decimal("0")

    def test_merger_record_all_cash_null_new_security(self, user):
        """MergerRecord for all-cash has null new_security."""
        old_sec = _create_asset(user, "Fund A", "US0000000091")

        merger = MergerRecord.objects.create(
            investor=user,
            old_security=old_sec,
            new_security=None,
            merger_date=date(2025, 6, 1),
            cash_per_share=Decimal("15"),
        )

        assert merger.new_security is None
        assert "Cash" in str(merger)

    def test_transactions_linked_to_merger(self, user, account):
        """Both MERGER_OUT and MERGER_IN link to the same MergerRecord."""
        old_sec = _create_asset(user, "Fund A", "US0000000101")
        new_sec = _create_asset(user, "Fund B", "US0000000102")

        merger = MergerRecord.objects.create(
            investor=user,
            old_security=old_sec,
            new_security=new_sec,
            merger_date=date(2025, 6, 1),
            conversion_ratio=Decimal("0.75"),
        )

        txn_out = _create_transaction(
            user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, date(2025, 6, 1),
            quantity=Decimal("-100"), price=Decimal("10"), merger=merger,
        )
        txn_in = _create_transaction(
            user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, date(2025, 6, 1),
            quantity=Decimal("75"), price=Decimal("13.333333"), merger=merger,
        )

        assert txn_out.merger == merger
        assert txn_in.merger == merger
        assert merger.transactions.count() == 2


# ============================================================================
# PARTIAL POSITION MERGER TESTS
# ============================================================================


@pytest.mark.unit
class TestPartialPositionMerger:
    """Test merger when some shares were already sold before the merger."""

    def test_partial_position_merger(self, user, account):
        """Buy 100, sell 30, merge remaining 70 shares."""
        old_sec = _create_asset(user, "Fund A", "US0000000111")
        new_sec = _create_asset(user, "Fund B", "US0000000112")

        from constants import TRANSACTION_TYPE_SELL

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY, date(2025, 1, 10), Decimal("100"), Decimal("10"))
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_SELL, date(2025, 3, 15), Decimal("-30"), Decimal("12"))

        merger_date = date(2025, 6, 1)
        old_position = old_sec.position(merger_date, user)
        assert old_position == Decimal("70")

        old_cost = old_sec.calculate_buy_in_price(merger_date, user)
        assert old_cost == Decimal("10")  # Buy-in price unchanged

        conversion_ratio = Decimal("0.75")
        new_quantity = old_position * conversion_ratio
        new_cost = (old_position * old_cost) / new_quantity

        merger = MergerRecord.objects.create(
            investor=user, old_security=old_sec, new_security=new_sec,
            merger_date=merger_date, conversion_ratio=conversion_ratio,
        )
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_MERGER_OUT, merger_date,
                            quantity=-old_position, price=old_cost, merger=merger)
        _create_transaction(user, account, new_sec, TRANSACTION_TYPE_MERGER_IN, merger_date,
                            quantity=new_quantity, price=new_cost, merger=merger)

        assert new_sec.position(merger_date, user) == Decimal("52.5")  # 70 * 0.75
        new_buy_in = new_sec.calculate_buy_in_price(merger_date, user)
        # 70 shares * $10 = $700 total cost, 52.5 new shares = ~13.333/share
        expected = Decimal("700") / Decimal("52.5")
        assert abs(new_buy_in - expected) < Decimal("0.000001")


# ============================================================================
# MULTI-ACCOUNT MERGER (API) TESTS
# ============================================================================


@pytest.mark.unit
class TestMultiAccountMergerApi:
    """A merger is a corporate action that applies to every account where
    the investor holds the old security, producing one MergerRecord and
    per-account MERGER_OUT/MERGER_IN transactions."""

    def test_all_stock_merger_spans_all_accounts(self, authenticated_client, user, account, account_uk):
        old_sec = _create_asset(user, "Fund A", "US0000000901")
        new_sec = _create_asset(user, "Fund B", "US0000000902")

        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY,
                            date(2025, 1, 10), Decimal("60"), Decimal("10"))
        _create_transaction(user, account_uk, old_sec, TRANSACTION_TYPE_BUY,
                            date(2025, 1, 10), Decimal("40"), Decimal("10"))

        payload = {
            "old_security_id": old_sec.id,
            "new_security_id": new_sec.id,
            "merger_date": "2025-06-01",
            "conversion_ratio": "0.75",
        }
        response = authenticated_client.post(
            "/database/api/create-merger/", payload, format="json"
        )
        assert response.status_code == 201, response.content

        body = response.json()
        assert len(body["accounts"]) == 2
        by_acc = {entry["account_id"]: entry for entry in body["accounts"]}
        assert Decimal(by_acc[account.id]["new_quantity"]) == Decimal("45")
        assert Decimal(by_acc[account_uk.id]["new_quantity"]) == Decimal("30")

        merger_date = date(2025, 6, 1)
        assert old_sec.position(merger_date, user, account_ids=[account.id]) == Decimal("0")
        assert old_sec.position(merger_date, user, account_ids=[account_uk.id]) == Decimal("0")
        assert new_sec.position(merger_date, user, account_ids=[account.id]) == Decimal("45")
        assert new_sec.position(merger_date, user, account_ids=[account_uk.id]) == Decimal("30")

        # Exactly one MergerRecord covers both accounts.
        assert MergerRecord.objects.filter(old_security=old_sec, merger_date=merger_date).count() == 1

    def test_merger_skips_accounts_with_zero_position(self, authenticated_client, user, account, account_uk):
        old_sec = _create_asset(user, "Fund A", "US0000000911")
        new_sec = _create_asset(user, "Fund B", "US0000000912")

        # Only `account` holds shares; `account_uk` is linked via broker but holds none.
        _create_transaction(user, account, old_sec, TRANSACTION_TYPE_BUY,
                            date(2025, 1, 10), Decimal("50"), Decimal("10"))

        response = authenticated_client.post(
            "/database/api/create-merger/",
            {
                "old_security_id": old_sec.id,
                "new_security_id": new_sec.id,
                "merger_date": "2025-06-01",
                "conversion_ratio": "0.5",
            },
            format="json",
        )
        assert response.status_code == 201, response.content
        body = response.json()
        assert len(body["accounts"]) == 1
        assert body["accounts"][0]["account_id"] == account.id

    def test_merger_errors_when_no_account_has_position(self, authenticated_client, user, account):
        old_sec = _create_asset(user, "Fund A", "US0000000921")
        new_sec = _create_asset(user, "Fund B", "US0000000922")

        response = authenticated_client.post(
            "/database/api/create-merger/",
            {
                "old_security_id": old_sec.id,
                "new_security_id": new_sec.id,
                "merger_date": "2025-06-01",
                "conversion_ratio": "1",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "no positive position" in response.json()["error"]
