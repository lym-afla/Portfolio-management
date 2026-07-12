"""Unit tests for ``services.transactions``.

Covers the classification helpers, ``get_price``, ``total_cash_flow`` (with
and without FX conversion), FX per-currency cash flow, the lifecycle history
helpers (``create_notional_history`` / ``create_split_history``), and the
transaction-save orchestration entry points
(:func:`save_single_transaction` / :func:`save_transactions`) for all three
branches (regular, FX, asset-transfer).

Money is always asserted as ``Decimal``.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from common.models import (
    BondMetadata,
    FXTransaction,
    NotionalHistory,
    Prices,
    SplitHistory,
    Transactions,
)
from services import transactions as txns_service
from services.transactions import (
    _build_phantom_cash_transaction,
    _normalize_decimal_field,
    create_notional_history,
    create_split_history,
    get_cash_flow_by_currency,
    get_price,
    is_disposal_transaction,
    is_neutral_transfer_transaction,
    is_paid_entry_transaction,
    is_position_increase,
    is_reward_transaction,
    reward_value,
    save_single_transaction,
    save_transactions,
    total_cash_flow,
)


# =============================================================================
# Classification helpers
# =============================================================================


class _StubTxn:
    """Minimal attribute bag mimicking a Transactions row for pure helpers."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.mark.unit
class TestClassificationHelpers:
    """Pure-function classification helpers (no DB)."""

    def test_is_position_increase_positive_quantity(self):
        assert is_position_increase(_StubTxn(quantity=Decimal("10"))) is True

    def test_is_position_increase_zero_quantity(self):
        assert is_position_increase(_StubTxn(quantity=Decimal("0"))) is False

    def test_is_position_increase_negative_quantity(self):
        assert is_position_increase(_StubTxn(quantity=Decimal("-5"))) is False

    def test_is_position_increase_none_quantity(self):
        assert is_position_increase(_StubTxn(quantity=None)) is False

    def test_is_paid_entry_transaction_buy(self):
        assert is_paid_entry_transaction(_StubTxn(type="Buy")) is True

    def test_is_paid_entry_transaction_crypto_trade_in(self):
        assert is_paid_entry_transaction(_StubTxn(type="Crypto trade in")) is True

    def test_is_paid_entry_transaction_sell(self):
        assert is_paid_entry_transaction(_StubTxn(type="Sell")) is False

    def test_is_reward_transaction_reward(self):
        assert is_reward_transaction(_StubTxn(type="Crypto reward")) is True

    def test_is_reward_transaction_other(self):
        assert is_reward_transaction(_StubTxn(type="Buy")) is False

    def test_is_disposal_transaction_sell(self):
        assert is_disposal_transaction(_StubTxn(type="Sell")) is True

    def test_is_disposal_transaction_crypto_trade_out(self):
        assert is_disposal_transaction(_StubTxn(type="Crypto trade out")) is True

    def test_is_disposal_transaction_buy(self):
        assert is_disposal_transaction(_StubTxn(type="Buy")) is False

    def test_is_neutral_transfer_in(self):
        assert is_neutral_transfer_transaction(_StubTxn(type="Crypto transfer in")) is True

    def test_is_neutral_transfer_out(self):
        assert is_neutral_transfer_transaction(_StubTxn(type="Crypto transfer out")) is True

    def test_is_neutral_transfer_other(self):
        assert is_neutral_transfer_transaction(_StubTxn(type="Buy")) is False

    def test_reward_value_for_reward(self):
        # abs(-5) * 2.5 == 12.5
        assert reward_value(
            _StubTxn(type="Crypto reward", quantity=Decimal("-5"), price=Decimal("2.5"))
        ) == Decimal("12.5")

    def test_reward_value_positive_quantity(self):
        assert reward_value(
            _StubTxn(type="Crypto reward", quantity=Decimal("4"), price=Decimal("1.25"))
        ) == Decimal("5")

    def test_reward_value_not_reward(self):
        assert reward_value(_StubTxn(type="Buy", quantity=Decimal("4"), price=Decimal("2"))) == Decimal(
            "0"
        )

    def test_reward_value_missing_fields(self):
        assert reward_value(_StubTxn(type="Crypto reward", quantity=None, price=None)) == Decimal("0")


# =============================================================================
# get_price
# =============================================================================


@pytest.mark.unit
class TestGetPrice:
    """``get_price`` for regular vs bond transactions."""

    def test_get_price_returns_none_when_no_price(self, asset):
        txn = _StubTxn(price=None, security=asset, notional=None, account_id=None)
        assert get_price(txn) is None

    def test_get_price_regular_stock(self, asset):
        # Non-bond: price returned as-is.
        txn = _StubTxn(
            price=Decimal("50.25"),
            security=asset,
            notional=None,
            account_id=None,
        )
        assert get_price(txn) == Decimal("50.25")

    def test_get_price_bond_with_explicit_notional(self, bond_asset):
        # price stored as % of par; explicit notional wins.
        # 98.5% * 1000 / 100 == 985
        txn = _StubTxn(
            price=Decimal("98.5"),
            security=bond_asset,
            notional=Decimal("1000"),
            account_id=None,
        )
        assert get_price(txn) == Decimal("985")

    def test_get_price_bond_resolves_notional_when_missing(self, user, bond_asset):
        # No notional on the txn -> falls back to security.get_effective_notional.
        txn = _StubTxn(
            price=Decimal("100"),
            security=bond_asset,
            notional=None,
            account_id=None,
            date=date(2023, 6, 15),
            investor=user,
            currency="USD",
        )
        with patch.object(
            type(bond_asset),
            "get_effective_notional",
            return_value=Decimal("500"),
        ) as mock_eff:
            result = get_price(txn)
        mock_eff.assert_called_once()
        # 100% * 500 / 100 == 500
        assert result == Decimal("500")


# =============================================================================
# total_cash_flow
# =============================================================================


@pytest.mark.unit
class TestTotalCashFlow:
    """Net cash flow for each transaction type."""

    def test_stock_split_always_zero(self, asset):
        txn = _StubTxn(type="Stock split", currency="USD")
        assert total_cash_flow(txn) == Decimal("0")

    def test_buy_base_cash_flow(self, asset):
        # -qty * price == -100 * 50 == -5000, no aci/commission.
        txn = _StubTxn(
            type="Buy",
            quantity=Decimal("100"),
            price=Decimal("50"),
            aci=None,
            commission=None,
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        assert total_cash_flow(txn) == Decimal("-5000.00")

    def test_buy_with_aci_and_commission(self, asset):
        # -100*50 + (-25 aci) + (-5 commission) == -5030
        txn = _StubTxn(
            type="Buy",
            quantity=Decimal("100"),
            price=Decimal("50"),
            aci=Decimal("-25"),
            commission=Decimal("-5"),
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        assert total_cash_flow(txn) == Decimal("-5030.00")

    def test_sell_base_cash_flow(self, asset):
        # -(-30) * 60 == 1800
        txn = _StubTxn(
            type="Sell",
            quantity=Decimal("-30"),
            price=Decimal("60"),
            aci=None,
            commission=None,
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        assert total_cash_flow(txn) == Decimal("1800.00")

    def test_sell_with_commission(self, asset):
        # 1800 + (-3 commission) == 1797
        txn = _StubTxn(
            type="Sell",
            quantity=Decimal("-30"),
            price=Decimal("60"),
            aci=None,
            commission=Decimal("-3"),
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        assert total_cash_flow(txn) == Decimal("1797.00")

    def test_dividend_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Dividend", cash_flow=Decimal("75"), currency="USD")
        assert total_cash_flow(txn) == Decimal("75.00")

    def test_coupon_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Coupon", cash_flow=Decimal("21.25"), currency="USD")
        assert total_cash_flow(txn) == Decimal("21.25")

    def test_bond_redemption_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Bond redemption", cash_flow=Decimal("500"), currency="USD")
        assert total_cash_flow(txn) == Decimal("500.00")

    def test_bond_maturity_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Bond maturity", cash_flow=Decimal("1000"), currency="USD")
        assert total_cash_flow(txn) == Decimal("1000.00")

    def test_cash_in_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Cash in", cash_flow=Decimal("1000"), currency="USD")
        assert total_cash_flow(txn) == Decimal("1000.00")

    def test_cash_out_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Cash out", cash_flow=Decimal("-250"), currency="USD")
        assert total_cash_flow(txn) == Decimal("-250.00")

    def test_tax_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Tax", cash_flow=Decimal("-15"), currency="USD")
        assert total_cash_flow(txn) == Decimal("-15.00")

    def test_interest_income_uses_cash_flow_field(self, asset):
        txn = _StubTxn(type="Interest income", cash_flow=Decimal("33.5"), currency="USD")
        assert total_cash_flow(txn) == Decimal("33.50")

    def test_broker_commission_uses_cash_flow_field(self, asset):
        txn = _StubTxn(
            type="Broker commission", cash_flow=Decimal("-7.5"), currency="USD"
        )
        assert total_cash_flow(txn) == Decimal("-7.50")

    def test_broker_commission_falls_back_to_commission_field(self, asset):
        # No cash_flow -> uses commission field directly.
        txn = _StubTxn(
            type="Broker commission",
            cash_flow=None,
            commission=Decimal("-9.25"),
            currency="USD",
        )
        assert total_cash_flow(txn) == Decimal("-9.25")

    def test_broker_commission_no_fields(self, asset):
        txn = _StubTxn(
            type="Broker commission", cash_flow=None, commission=None, currency="USD"
        )
        assert total_cash_flow(txn) == Decimal("0.00")

    def test_buy_without_quantity_returns_zero(self, asset):
        # quantity None -> branch skipped -> Decimal(0).
        txn = _StubTxn(
            type="Buy",
            quantity=None,
            price=Decimal("50"),
            aci=None,
            commission=None,
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        assert total_cash_flow(txn) == Decimal("0.00")

    def test_unknown_type_returns_zero(self, asset):
        txn = _StubTxn(type="Repo", currency="USD")
        assert total_cash_flow(txn) == Decimal("0.00")

    def test_total_cash_flow_fx_conversion(self, asset, user, fx_rates_usd_eur):
        # Buy 100 @ 50 USD -> -5000 USD; convert to EUR via FX rate.
        txn = _StubTxn(
            type="Buy",
            quantity=Decimal("100"),
            price=Decimal("50"),
            aci=None,
            commission=None,
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
            date=date(2023, 6, 15),
            investor=user,
        )
        # Determine the rate that get_rate returns for USD->EUR on 2023-06-15
        # so we can assert the exact converted value.
        from services.fx import get_rate

        fx_rate = get_rate("USD", "EUR", date(2023, 6, 15))[ "FX" ]
        expected = round(Decimal("-5000") * fx_rate, 2)
        assert total_cash_flow(txn, target_currency="EUR") == expected

    def test_total_cash_flow_same_currency_no_conversion(self, asset):
        txn = _StubTxn(
            type="Buy",
            quantity=Decimal("10"),
            price=Decimal("20"),
            aci=None,
            commission=None,
            currency="USD",
            security=asset,
            notional=None,
            account_id=None,
        )
        # target == source -> no conversion applied.
        assert total_cash_flow(txn, target_currency="USD") == Decimal("-200.00")


# =============================================================================
# get_cash_flow_by_currency (FXTransaction)
# =============================================================================


@pytest.mark.unit
class TestGetCashFlowByCurrency:
    """Per-currency cash flow for an FXTransaction."""

    def test_from_currency_outflow(self, fx_transaction):
        # from_amount 1000 USD -> -1000
        assert get_cash_flow_by_currency(fx_transaction, "USD") == Decimal("-1000.00")

    def test_to_currency_inflow(self, fx_transaction):
        assert get_cash_flow_by_currency(fx_transaction, "EUR") == Decimal("920.00")

    def test_unrelated_currency_returns_zero(self, fx_transaction):
        assert get_cash_flow_by_currency(fx_transaction, "GBP") == Decimal("0")

    def test_from_currency_with_commission_in_from(self, user, account):
        fx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2023, 2, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000"),
            to_amount=Decimal("920"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("-5"),
            commission_currency="USD",
        )
        # -1000 + (-5) == -1005
        assert get_cash_flow_by_currency(fx, "USD") == Decimal("-1005")

    def test_to_currency_with_commission_in_to(self, user, account):
        fx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2023, 2, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000"),
            to_amount=Decimal("920"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("-3"),
            commission_currency="EUR",
        )
        # 920 + (-3) == 917
        assert get_cash_flow_by_currency(fx, "EUR") == Decimal("917")

    def test_commission_in_third_currency(self, user, account):
        fx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2023, 2, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000"),
            to_amount=Decimal("920"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("-2"),
            commission_currency="GBP",
        )
        # USD and EUR unaffected; GBP gets the commission.
        assert get_cash_flow_by_currency(fx, "USD") == Decimal("-1000")
        assert get_cash_flow_by_currency(fx, "EUR") == Decimal("920")
        assert get_cash_flow_by_currency(fx, "GBP") == Decimal("-2")


# =============================================================================
# save_single_transaction
# =============================================================================


@pytest.mark.unit
class TestSaveSingleTransaction:
    """The 3-way branch: regular / FX / asset-transfer."""

    def test_regular_buy_persists_and_normalizes(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "quantity": "100.123456789",  # string -> normalized to 9 dp
            "price": "50.50",
            "commission": "-5",
        }
        result = save_single_transaction(data)

        assert result["success"] is True
        assert result["type"] == "regular"
        txn_id = result["transaction_id"]
        assert txn_id is not None

        txn = Transactions.objects.get(id=txn_id)
        assert txn.investor == user
        assert txn.account == account
        assert txn.security == asset
        assert txn.type == "Buy"
        assert txn.quantity == Decimal("100.123456789")
        assert txn.price == Decimal("50.500000000")  # quantized to 9 dp
        assert txn.commission == Decimal("-5.000000000")

    def test_regular_dividend(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Dividend",
            "date": date(2023, 3, 31),
            "quantity": None,
            "price": None,
            "cash_flow": "75.00",
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        assert result["type"] == "regular"
        txn = Transactions.objects.get(id=result["transaction_id"])
        assert txn.type == "Dividend"
        assert txn.cash_flow == Decimal("75.00")

    def test_fx_transaction_persists(self, user, account):
        data = {
            "investor": user,
            "account": account,
            "date": date(2023, 2, 15),
            "from_currency": "USD",
            "to_currency": "EUR",
            "from_amount": "1000",
            "to_amount": "920",
            "exchange_rate": "0.92",
            "commission": "2.00",
            "is_fx": True,
        }
        result = save_single_transaction(data)

        assert result["success"] is True
        assert result["type"] == "fx"
        fx = FXTransaction.objects.get(id=result["transaction_id"])
        assert fx.from_currency == "USD"
        assert fx.to_currency == "EUR"
        assert fx.from_amount == Decimal("1000.000000000")
        assert fx.to_amount == Decimal("920.000000000")
        assert fx.exchange_rate == Decimal("0.920000000")
        # is_fx popped from dict
        assert "is_fx" not in data

    def test_asset_transfer_buy_creates_phantom_cash_in(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "quantity": Decimal("10"),
            "price": Decimal("100"),
            "is_asset_transfer": True,
        }
        result = save_single_transaction(data)

        assert result["success"] is True
        assert result["type"] == "asset_transfer"
        main = Transactions.objects.get(id=result["transaction_id"])
        # Asset transfer forces cash_flow/commission to None.
        assert main.cash_flow is None
        assert main.commission is None

        # Exactly one phantom "Cash in" balancing row should exist.
        phantom = Transactions.objects.filter(
            investor=user, account=account, type="Cash in", security__isnull=True
        ).get()
        # +|price*qty| == 1000
        assert phantom.cash_flow == Decimal("1000.00")

    def test_asset_transfer_sell_creates_phantom_cash_out(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Sell",
            "date": date(2023, 1, 15),
            "quantity": Decimal("-10"),
            "price": Decimal("100"),
            "is_asset_transfer": True,
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        assert result["type"] == "asset_transfer"

        phantom = Transactions.objects.get(
            investor=user, account=account, type="Cash out", security__isnull=True
        )
        # -|price*qty| == -1000
        assert phantom.cash_flow == Decimal("-1000.00")

    def test_asset_transfer_with_price_calculation_uses_market_price(
        self, user, account, asset, monkeypatch
    ):
        # needs_price_calculation -> _resolve_asset_transfer_price runs.
        # Patch calculate_buy_in_price (imported lazily from services.realized)
        # to return None so the helper falls through to the market-price lookup.
        Prices.objects.create(
            security=asset, date=date(2023, 1, 10), price=Decimal("42.00")
        )
        monkeypatch.setattr(
            "services.realized.calculate_buy_in_price", lambda *a, **k: None
        )
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "quantity": Decimal("5"),
            "price": None,
            "is_asset_transfer": True,
            "needs_price_calculation": True,
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        main = Transactions.objects.get(id=result["transaction_id"])
        # buy_in_price None -> most recent market price on/before date == 42.
        assert main.price == Decimal("42.000000")

    def test_asset_transfer_price_calc_falls_back_to_zero(
        self, user, account, asset, monkeypatch
    ):
        # No buy-in price AND no market price rows -> falls back to Decimal(0)
        # via the broad except in _resolve_asset_transfer_price.
        monkeypatch.setattr(
            "services.realized.calculate_buy_in_price", lambda *a, **k: None
        )
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "quantity": Decimal("5"),
            "price": None,
            "is_asset_transfer": True,
            "needs_price_calculation": True,
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        main = Transactions.objects.get(id=result["transaction_id"])
        assert main.price == Decimal("0")

    def test_asset_transfer_no_phantom_when_no_price(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "quantity": Decimal("10"),
            "price": None,
            "is_asset_transfer": True,
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        # No phantom created when price is missing.
        assert not Transactions.objects.filter(
            investor=user, account=account, security__isnull=True
        ).exists()

    def test_save_single_transaction_coerces_pandas_timestamp_date(self, user, account, asset):
        class FakeTimestamp:
            """Minimal stand-in for a pandas Timestamp."""

            def __init__(self, dt):
                self._dt = dt

            def to_pydatetime(self):
                return self._dt

        ts = FakeTimestamp(datetime(2023, 5, 1, 9, 30, 0))
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": ts,
            "quantity": Decimal("1"),
            "price": Decimal("10"),
        }
        result = save_single_transaction(data)
        assert result["success"] is True
        txn = Transactions.objects.get(id=result["transaction_id"])
        assert txn.date == datetime(2023, 5, 1, 9, 30, 0)

    def test_save_single_transaction_error_returns_failure(self, user, monkeypatch):
        # Force an exception inside the regular branch by patching
        # _normalize_decimal_fields to raise.
        def boom(data, model, fields):
            raise RuntimeError("boom")

        monkeypatch.setattr(txns_service, "_normalize_decimal_fields", boom)
        data = {
            "investor": user,
            "account": "not-an-account",  # would also fail, but boom fires first
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 1),
        }
        result = save_single_transaction(data)
        assert result["success"] is False
        assert "boom" in result["error"]


# =============================================================================
# save_transactions (bulk)
# =============================================================================


@pytest.mark.unit
class TestSaveTransactions:
    """Bulk save across the three branches."""

    def test_bulk_creates_regular_transactions(self, user, account, asset):
        rows = [
            {
                "investor": user,
                "account": account,
                "security": asset,
                "currency": "USD",
                "type": "Buy",
                "date": date(2023, 1, 15),
                "quantity": Decimal("100"),
                "price": Decimal("50"),
            },
            {
                "investor": user,
                "account": account,
                "security": asset,
                "currency": "USD",
                "type": "Sell",
                "date": date(2023, 6, 15),
                "quantity": Decimal("-30"),
                "price": Decimal("60"),
            },
        ]
        save_transactions(rows)

        assert Transactions.objects.filter(investor=user).count() == 2
        types = set(Transactions.objects.filter(investor=user).values_list("type", flat=True))
        assert types == {"Buy", "Sell"}

    def test_bulk_creates_fx_transactions(self, user, account):
        rows = [
            {
                "investor": user,
                "account": account,
                "date": date(2023, 2, 15),
                "from_currency": "USD",
                "to_currency": "EUR",
                "from_amount": Decimal("1000"),
                "to_amount": Decimal("920"),
                "exchange_rate": Decimal("0.92"),
                "is_fx": True,
            },
            {
                "investor": user,
                "account": account,
                "date": date(2023, 3, 15),
                "from_currency": "EUR",
                "to_currency": "USD",
                "from_amount": Decimal("500"),
                "to_amount": Decimal("540"),
                "exchange_rate": Decimal("1.08"),
                "is_fx": True,
            },
        ]
        save_transactions(rows)
        assert FXTransaction.objects.filter(investor=user).count() == 2

    def test_bulk_asset_transfer_creates_phantom(self, user, account, asset):
        rows = [
            {
                "investor": user,
                "account": account,
                "security": asset,
                "currency": "USD",
                "type": "Buy",
                "date": date(2023, 1, 15),
                "quantity": Decimal("10"),
                "price": Decimal("100"),
                "is_asset_transfer": True,
            }
        ]
        save_transactions(rows)
        # 1 main + 1 phantom
        assert Transactions.objects.filter(investor=user).count() == 2
        assert Transactions.objects.filter(
            investor=user, type="Cash in", security__isnull=True
        ).count() == 1

    def test_bulk_mixed_batch(self, user, account, asset):
        rows = [
            {
                "investor": user,
                "account": account,
                "security": asset,
                "currency": "USD",
                "type": "Buy",
                "date": date(2023, 1, 15),
                "quantity": Decimal("10"),
                "price": Decimal("50"),
            },
            {
                "investor": user,
                "account": account,
                "date": date(2023, 2, 15),
                "from_currency": "USD",
                "to_currency": "EUR",
                "from_amount": Decimal("100"),
                "to_amount": Decimal("92"),
                "exchange_rate": Decimal("0.92"),
                "is_fx": True,
            },
            {
                "investor": user,
                "account": account,
                "security": asset,
                "currency": "USD",
                "type": "Buy",
                "date": date(2023, 3, 15),
                "quantity": Decimal("5"),
                "price": Decimal("20"),
                "is_asset_transfer": True,
            },
        ]
        save_transactions(rows)
        # 2 regular + 1 phantom cash + 1 FX.
        assert Transactions.objects.filter(investor=user).count() == 3
        assert FXTransaction.objects.filter(investor=user).count() == 1

    def test_bulk_empty_list_is_noop(self, user):
        # No rows -> no error, nothing created.
        save_transactions([])
        assert Transactions.objects.filter(investor=user).count() == 0

    def test_bulk_re_raises_on_error(self, user, monkeypatch):
        # bulk_create blowing up should re-raise (caller's atomic rolls back).
        def boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(Transactions.objects, "bulk_create", boom)
        rows = [
            {
                "investor": user,
                "account": None,  # invalid FK
                "currency": "USD",
                "type": "Buy",
                "date": date(2023, 1, 1),
                "quantity": Decimal("1"),
                "price": Decimal("1"),
            }
        ]
        with pytest.raises(RuntimeError, match="db down"):
            save_transactions(rows)

    def test_bulk_bond_redemption_creates_notional_history(
        self, user, account, bond_asset_with_meta
    ):
        rows = [
            {
                "investor": user,
                "account": account,
                "security": bond_asset_with_meta,
                "currency": "USD",
                "type": "Bond redemption",
                "date": date(2023, 6, 15),
                "quantity": Decimal("-5"),
                "price": Decimal("100"),
                "notional_change": Decimal("100"),
            }
        ]
        save_transactions(rows)
        # bulk path seeds NotionalHistory manually (bypasses save()).
        assert NotionalHistory.objects.filter(asset=bond_asset_with_meta).count() == 1
        nh = NotionalHistory.objects.get(asset=bond_asset_with_meta)
        assert nh.change_reason == "REDEMPTION"
        assert nh.change_amount == Decimal("-100.000000")


# =============================================================================
# create_notional_history
# =============================================================================


@pytest.mark.unit
class TestCreateNotionalHistory:
    """Bond redemption -> NotionalHistory upsert."""

    def test_redemption_creates_new_history_entry(
        self, user, account, bond_asset_with_meta
    ):
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 6, 15),
            quantity=Decimal("-5"),
            price=Decimal("100"),
            notional_change=Decimal("100"),
        )

        create_notional_history(txn)

        nh = NotionalHistory.objects.get(asset=bond_asset_with_meta)
        assert nh.date == date(2023, 6, 15)
        assert nh.change_reason == "REDEMPTION"
        assert nh.change_amount == Decimal("-100.000000")
        # previous_notional = initial_notional (1000) - 100 == 900
        assert nh.notional_per_unit == Decimal("900.000000")

    def test_maturity_uses_maturity_reason(self, user, account, bond_asset_with_meta):
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond maturity",
            date=date(2023, 6, 15),
            quantity=Decimal("-10"),
            price=Decimal("100"),
            notional_change=Decimal("500"),
        )
        create_notional_history(txn)
        nh = NotionalHistory.objects.get(asset=bond_asset_with_meta)
        assert nh.change_reason == "MATURITY"

    def test_existing_matching_entry_is_updated(self, user, account, bond_asset_with_meta):
        # Pre-create a nearby entry within the ±7 day window with matching amount.
        NotionalHistory.objects.create(
            asset=bond_asset_with_meta,
            date=date(2023, 6, 20),  # within 7 days of txn date 2023-06-15
            change_amount=Decimal("-100"),
            change_reason="REDEMPTION",
            notional_per_unit=Decimal("950"),
            comment="original API entry",
        )
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 6, 15),
            quantity=Decimal("-5"),
            price=Decimal("100"),
            notional_change=Decimal("100"),
        )
        create_notional_history(txn)

        # Should still be exactly one entry, now updated to the txn date.
        assert NotionalHistory.objects.filter(asset=bond_asset_with_meta).count() == 1
        nh = NotionalHistory.objects.get(asset=bond_asset_with_meta)
        assert nh.date == date(2023, 6, 15)
        assert nh.change_amount == Decimal("-100.000000")
        assert "Updated from transaction" in nh.comment

    def test_no_bond_metadata_is_logged_and_skipped(self, user, account, bond_asset):
        # bond_asset has no BondMetadata -> early return, no row created.
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 6, 15),
            quantity=Decimal("-5"),
            price=Decimal("100"),
            notional_change=Decimal("100"),
        )
        create_notional_history(txn)
        assert NotionalHistory.objects.filter(asset=bond_asset).count() == 0

    def test_uses_previous_history_notional(self, user, account, bond_asset_with_meta):
        # Earlier history entry present -> new notional derived from it, not
        # from initial_notional.
        NotionalHistory.objects.create(
            asset=bond_asset_with_meta,
            date=date(2023, 1, 1),
            change_amount=None,
            change_reason="INITIAL",
            notional_per_unit=Decimal("800"),  # already amortized down
        )
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 6, 15),
            quantity=Decimal("-5"),
            price=Decimal("100"),
            notional_change=Decimal("50"),
        )
        create_notional_history(txn)
        nh = NotionalHistory.objects.get(
            asset=bond_asset_with_meta, change_reason="REDEMPTION"
        )
        # 800 - 50 == 750
        assert nh.notional_per_unit == Decimal("750.000000")


# =============================================================================
# create_split_history
# =============================================================================


@pytest.mark.unit
class TestCreateSplitHistory:
    """Stock split -> SplitHistory upsert + asset comment update."""

    def test_split_creates_history_and_updates_comment(
        self, user, account, asset
    ):
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("0"),
            price=None,
            split_from=1,
            split_to=2,
            comment="2:1 split",
        )
        create_split_history(txn)

        sh = SplitHistory.objects.get(asset=asset)
        assert sh.split_from == 1
        assert sh.split_to == 2
        assert sh.source == "TRANSACTION"
        assert sh.comment == "2:1 split"

        asset.refresh_from_db()
        assert "Stock split 2:1 on 2023-06-15" in asset.comment

    def test_split_updates_existing_entry(self, user, account, asset):
        # Disable the Transactions.save() lifecycle hook so we control the
        # pre-existing SplitHistory ourselves and can assert the update path.
        with patch("services.transactions.create_split_history") as hook:
            hook.return_value = None
            txn = Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency="USD",
                type="Stock split",
                date=date(2023, 6, 15),
                quantity=Decimal("0"),
                price=None,
                split_from=1,
                split_to=3,
                comment="3:1 split",
            )
        SplitHistory.objects.create(
            asset=asset,
            transaction=txn,
            date=date(2023, 6, 10),
            split_from=1,
            split_to=2,
            adjustment_factor=Decimal("0.5"),
            source="TRANSACTION",
            comment="old",
        )
        create_split_history(txn)

        assert SplitHistory.objects.filter(asset=asset).count() == 1
        sh = SplitHistory.objects.get(asset=asset)
        assert sh.split_to == 3
        assert sh.date == date(2023, 6, 15)
        assert sh.comment == "3:1 split"

    def test_split_appends_comment_when_one_exists(self, user, account, asset):
        asset.comment = "Existing note"
        asset.save()
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("0"),
            price=None,
            split_from=1,
            split_to=2,
            comment="2:1 split",
        )
        create_split_history(txn)
        asset.refresh_from_db()
        assert asset.comment.startswith("Existing note")
        assert "Stock split 2:1 on 2023-06-15" in asset.comment


# =============================================================================
# Private helpers (light coverage of the normalized-decimal + phantom builder)
# =============================================================================


@pytest.mark.unit
class TestPrivateHelpers:
    """Direct tests for the shared private helpers."""

    def test_normalize_decimal_field_quantizes(self):
        # 1.2345 -> quantize to 2 dp == 1.23 (ROUND_HALF_UP)
        result = _normalize_decimal_field(Decimal("1.2345"), 10, 2)
        assert result == Decimal("1.23")

    def test_normalize_decimal_field_half_up(self):
        result = _normalize_decimal_field(Decimal("2.5"), 10, 0)
        assert result == Decimal("3")

    def test_normalize_decimal_field_overflow_returns_zero(self):
        # 12 integer digits but max_digits=5 -> overflow -> 0.
        assert _normalize_decimal_field(Decimal("123456789012"), 5, 2) == Decimal("0")

    def test_normalize_decimal_field_zero_value(self):
        # abs_value == 0 -> int_digits = 1 branch (line 545).
        assert _normalize_decimal_field(Decimal("0"), 10, 2) == Decimal("0.00")

    def test_normalize_decimal_field_invalid_returns_zero(self):
        assert _normalize_decimal_field("not-a-number", 10, 2) == Decimal("0")

    def test_build_phantom_cash_transaction_buy(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "price": Decimal("100"),
            "quantity": Decimal("10"),
        }
        phantom = _build_phantom_cash_transaction(data)
        assert phantom is not None
        assert phantom.type == "Cash in"
        assert phantom.cash_flow == Decimal("1000")
        assert phantom.security is None

    def test_build_phantom_cash_transaction_sell(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Sell",
            "date": date(2023, 1, 15),
            "price": Decimal("100"),
            "quantity": Decimal("-10"),
        }
        phantom = _build_phantom_cash_transaction(data)
        assert phantom is not None
        assert phantom.type == "Cash out"
        assert phantom.cash_flow == Decimal("-1000")

    def test_build_phantom_returns_none_when_no_price(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "price": None,
            "quantity": Decimal("10"),
        }
        assert _build_phantom_cash_transaction(data) is None

    def test_build_phantom_returns_none_when_no_quantity(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "currency": "USD",
            "type": "Buy",
            "date": date(2023, 1, 15),
            "price": Decimal("100"),
            "quantity": None,
        }
        assert _build_phantom_cash_transaction(data) is None

    def test_resolve_asset_transfer_price_uses_buy_in_price(
        self, user, account, asset, monkeypatch
    ):
        # When calculate_buy_in_price returns a value, _resolve_asset_transfer_price
        # short-circuits with data["price"] = buy_in_price (lines 622-623).
        from services.transactions import _resolve_asset_transfer_price

        monkeypatch.setattr(
            "services.realized.calculate_buy_in_price",
            lambda *a, **k: Decimal("123.45"),
        )
        data = {
            "investor": user,
            "account": account,
            "security": asset,
            "date": date(2023, 1, 15),
            "price": None,
        }
        _resolve_asset_transfer_price(data)
        assert data["price"] == Decimal("123.45")


@pytest.mark.unit
class TestNotionalHistoryGuard:
    """``_create_notional_history_if_bond_redemption`` early-return guards."""

    def test_non_redemption_type_is_noop(self, user, account, asset):
        from services.transactions import _create_notional_history_if_bond_redemption

        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("10"),
            price=Decimal("50"),
            notional_change=Decimal("100"),
        )
        # Should be a no-op (no NotionalHistory for a Buy).
        before = NotionalHistory.objects.count()
        _create_notional_history_if_bond_redemption(txn)
        assert NotionalHistory.objects.count() == before

    def test_redemption_without_security_is_noop(self, user, account):
        from services.transactions import _create_notional_history_if_bond_redemption

        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=None,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 1, 15),
            quantity=None,
            price=None,
            notional_change=Decimal("100"),
        )
        before = NotionalHistory.objects.count()
        _create_notional_history_if_bond_redemption(txn)
        assert NotionalHistory.objects.count() == before

    def test_redemption_with_zero_notional_change_is_noop(
        self, user, account, bond_asset_with_meta
    ):
        from services.transactions import _create_notional_history_if_bond_redemption

        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 1, 15),
            quantity=None,
            price=None,
            notional_change=Decimal("0"),
        )
        before = NotionalHistory.objects.count()
        _create_notional_history_if_bond_redemption(txn)
        assert NotionalHistory.objects.count() == before

    def test_redemption_creates_history(self, user, account, bond_asset_with_meta):
        from services.transactions import _create_notional_history_if_bond_redemption

        before = NotionalHistory.objects.count()
        txn = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_with_meta,
            currency="USD",
            type="Bond redemption",
            date=date(2023, 1, 15),
            quantity=Decimal("-5"),
            price=Decimal("100"),
            notional_change=Decimal("100"),
        )
        _create_notional_history_if_bond_redemption(txn)
        assert NotionalHistory.objects.count() == before + 1


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bond_asset_with_meta(bond_asset):
    """A bond asset with BondMetadata (initial_notional 1000)."""
    BondMetadata.objects.create(
        asset=bond_asset,
        initial_notional=Decimal("1000"),
        nominal_currency="USD",
        coupon_rate=Decimal("5"),
        coupon_frequency=2,
        issue_date=date(2023, 1, 1),
        maturity_date=date(2030, 1, 1),
        bond_type="FIXED",
    )
    return bond_asset
